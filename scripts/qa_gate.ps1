#Requires -Version 5.1
<#
.SYNOPSIS
  Independent, dev-environment-free QA gate for the invite-gated alpha.

.DESCRIPTION
  Spins up a RUN-SCOPED, one-shot PostgreSQL 16 container (its own name, its own
  volume, its own random host port), migrates it, and runs the full release
  battery against it:

    - backend suite (tests + simulations + evidence + analyses), -W error
    - web: lint, typecheck, unit tests, production build
    - contract neutrality: rebuild openapi.json + types.gen.ts and diff the
      committed artefacts

  The container is ALWAYS reclaimed on exit (success, failure, or Ctrl-C), and it
  never touches the developer's Postgres or the canonical `decision-lab` stack:
  a fresh container + named volume are created and removed by this script alone.
  Nothing here reads the dev .env or the running dev processes, so a green run
  here means green on a clean machine - which is the whole point.

.PARAMETER Python
  Python interpreter with the API deps installed. Defaults to the mainline
  worktree venv; override for CI (e.g. `uv run python`).

.PARAMETER SkipBuild
  Skip the web production build (fast inner loop only; never for a real gate).

.PARAMETER KeepContainer
  Leave the container running for post-mortem. Off by default.

.EXAMPLE
  .\qa_gate.ps1
#>
[CmdletBinding()]
param(
  [string]$Python = 'E:\Temp\xiayu\Documents\adventure-x\decision-lab-mainline-integration\services\api\.venv\Scripts\python.exe',
  [switch]$SkipBuild,
  [switch]$KeepContainer
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot 'services\api'
$WebDir = 'apps/web'

# A run-scoped identity so parallel or leftover runs never collide, and cleanup
# can target exactly what this run created.
$Stamp = Get-Date -Format 'yyyyMMddHHmmss'
$Container = "ludus-qa-db-$Stamp"
$Volume = "ludus-qa-db-vol-$Stamp"
$DbName = 'decision_lab'
$DbUser = 'decision_lab'
# Throwaway credential for an ephemeral container that is deleted at the end;
# not a secret, never reused, never persisted.
$DbPassword = "qa-$([guid]::NewGuid().ToString('N').Substring(0,16))"
$HostPort = Get-Random -Minimum 15432 -Maximum 25432

$script:Results = [ordered]@{}
$script:Failed = $false

function Write-Section($name) { Write-Host "`n=== $name ===" -ForegroundColor Cyan }

function Invoke-Stage {
  param([string]$Name, [scriptblock]$Body)
  Write-Section $Name
  try {
    & $Body
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "$Name exited $LASTEXITCODE" }
    $script:Results[$Name] = 'PASS'
    Write-Host "[PASS] $Name" -ForegroundColor Green
  }
  catch {
    $script:Results[$Name] = "FAIL: $($_.Exception.Message)"
    $script:Failed = $true
    Write-Host "[FAIL] $Name -> $($_.Exception.Message)" -ForegroundColor Red
  }
}

function Remove-QaContainer {
  Write-Section 'teardown'
  docker rm -f $Container 2>&1 | Out-Null
  docker volume rm $Volume 2>&1 | Out-Null
  Write-Host "[teardown] removed $Container + $Volume"
}

# --- environment for the API/pytest processes (all fixture, no live provider) --
$commonEnv = @{
  POSTGRES_HOST                = '127.0.0.1'
  POSTGRES_PORT                = "$HostPort"
  POSTGRES_DB                  = $DbName
  POSTGRES_USER                = $DbUser
  POSTGRES_PASSWORD            = $DbPassword
  DATABASE_URL                 = ''
  PYTHONPATH                   = $ApiRoot
  MODEL_PROVIDER               = 'fixture'
  FIXTURE_MODE                 = 'true'
  MODEL_API_KEY                = ''
  EXA_API_KEY                  = ''
  FIRECRAWL_API_KEY            = ''
  TAVILY_API_KEY               = ''
  # A known code so the invite-gated register tests can admit an account without
  # weakening the gate (this is sha256("qa-alpha-invite-code"), the same code
  # the pytest session fixture configures).
  SIGNUP_INVITE_CODE_HASHES    = ([System.BitConverter]::ToString((New-Object System.Security.Cryptography.SHA256Managed).ComputeHash([System.Text.Encoding]::UTF8.GetBytes('qa-alpha-invite-code'))).Replace('-','').ToLower())
}
function Set-CommonEnv { foreach ($k in $commonEnv.Keys) { Set-Item -Path "Env:$k" -Value $commonEnv[$k] } }

if (-not (Test-Path $Python)) { throw "Python interpreter not found: $Python" }

try {
  Write-Section 'one-shot postgres 16'
  docker run -d --name $Container `
    -e "POSTGRES_DB=$DbName" -e "POSTGRES_USER=$DbUser" -e "POSTGRES_PASSWORD=$DbPassword" `
    -p "${HostPort}:5432" -v "${Volume}:/var/lib/postgresql/data" `
    postgres:16-alpine | Out-Null
  Write-Host "[db] $Container on host port $HostPort"

  Write-Host '[db] waiting for readiness...'
  $ready = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    docker exec $Container pg_isready -U $DbUser -d $DbName 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
  }
  if (-not $ready) { throw 'postgres did not become ready in 40s' }

  Set-CommonEnv

  Invoke-Stage 'migrate' {
    Push-Location $ApiRoot
    try { & $Python -m alembic -c alembic.ini upgrade head; & $Python -m alembic -c alembic.ini check }
    finally { Pop-Location }
  }

  Invoke-Stage 'backend-suite' {
    Push-Location $ApiRoot
    try {
      & $Python -m pytest tests app/simulations/tests app/evidence/tests app/analyses/tests -q -W error -rxX
    }
    finally { Pop-Location }
  }

  Invoke-Stage 'web-lint' { Push-Location $RepoRoot; try { & pnpm --dir $WebDir lint } finally { Pop-Location } }
  Invoke-Stage 'web-typecheck' { Push-Location $RepoRoot; try { & pnpm --dir $WebDir typecheck } finally { Pop-Location } }
  Invoke-Stage 'web-unit' { Push-Location $RepoRoot; try { & pnpm --dir $WebDir test } finally { Pop-Location } }
  if (-not $SkipBuild) {
    Invoke-Stage 'web-build' {
      $env:API_PROXY_TARGET = 'http://127.0.0.1:8000'
      Push-Location $RepoRoot; try { & pnpm --dir $WebDir build } finally { Pop-Location }
    }
  }

  Invoke-Stage 'contract-neutrality' {
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) "ludus-qa-contracts-$Stamp"
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
      $freshOpenApi = Join-Path $tmp 'openapi.json'
      $freshTypes = Join-Path $tmp 'types.gen.ts'
      & $Python (Join-Path $RepoRoot 'packages\contracts\build_openapi.py') --output $freshOpenApi
      if ($LASTEXITCODE -ne 0) { throw 'openapi rebuild failed' }
      Push-Location $RepoRoot
      try { & pnpm --dir packages/contracts exec openapi-typescript $freshOpenApi -o $freshTypes }
      finally { Pop-Location }
      $committedOpenApi = Join-Path $RepoRoot 'packages\contracts\openapi.json'
      $committedTypes = Join-Path $RepoRoot 'packages\contracts\src\types.gen.ts'
      $oaDiff = Compare-Object (Get-Content $committedOpenApi) (Get-Content $freshOpenApi)
      $tyDiff = Compare-Object (Get-Content $committedTypes) (Get-Content $freshTypes)
      if ($oaDiff) { throw 'openapi.json drifted from the committed contract' }
      if ($tyDiff) { throw 'types.gen.ts drifted from the committed contract' }
    }
    finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
  }
}
finally {
  if (-not $KeepContainer) { Remove-QaContainer }
  else { Write-Host "[teardown] KeepContainer set; leaving $Container (port $HostPort) up" -ForegroundColor Yellow }
}

Write-Section 'QA GATE SUMMARY'
foreach ($k in $script:Results.Keys) {
  $v = $script:Results[$k]
  $color = if ($v -eq 'PASS') { 'Green' } else { 'Red' }
  Write-Host ("{0,-22} {1}" -f $k, $v) -ForegroundColor $color
}
if ($script:Failed) { Write-Host "`nQA GATE: FAIL" -ForegroundColor Red; exit 1 }
Write-Host "`nQA GATE: PASS" -ForegroundColor Green
exit 0

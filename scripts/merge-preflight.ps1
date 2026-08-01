[CmdletBinding()]
param(
    [string]$Branch = "",
    [switch]$Fix
)

# ============================================================================
# merge-preflight.ps1 — AGENTS.md §14/§19/§21 pre-merge validation gate
#
# Runs the composite checks required before any branch may be merged into
# main or submitted for integration. Exit 0 = all gates pass.
# ============================================================================

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$script:Failed = @()
$script:Passed = @()

function Add-Result([string]$Name, [bool]$Ok, [string]$Detail) {
    if ($Ok) {
        $script:Passed += $Name
        Write-Host "[PASS] $Name" -ForegroundColor Green
    }
    else {
        $script:Failed += $Name
        Write-Host "[FAIL] $Name : $Detail" -ForegroundColor Red
    }
}

Push-Location $RepositoryRoot
try {
    Write-Host "=== Merge Preflight Gate (AGENTS.md §14/§19/§21) ===" -ForegroundColor Cyan
    Write-Host ""

    # --- 0a. Canonical origin URL (§19) ---
    $originUrl = (git remote get-url origin 2>&1 | Select-Object -First 1)
    $canonical = "https://github.com/Ludus-AdventureX/Ludus.git"
    Add-Result "canonical-origin" ($originUrl -eq $canonical) "origin is '$originUrl'; AGENTS.md §19 requires '$canonical'"

    # --- 0b. Fresh live read of remote main SHA (§19/§21) ---
    $remoteMain = @(git ls-remote origin main 2>&1)
    $remoteMainSha = if ($LASTEXITCODE -eq 0 -and $remoteMain.Count -gt 0) { ($remoteMain[0] -split "\s+")[0] } else { "" }
    if ($remoteMainSha -match '^[0-9a-f]{40}$') {
        Add-Result "remote-main-fresh-read" $true ""
        Write-Host "       remote main = $remoteMainSha" -ForegroundColor DarkGray
        $localMainSha = (git rev-parse --verify --quiet main 2>&1 | Select-Object -First 1)
        Add-Result "local-main-not-behind-remote" ($localMainSha -eq $remoteMainSha) "local main $localMainSha != remote main $remoteMainSha; re-baseline before merging (§19 concurrent advancement)"
    }
    else {
        Add-Result "remote-main-fresh-read" $false "AGENTS.md §19: remote status is blocked; MUST NOT claim merge/publish results without a fresh live read"
        Add-Result "local-main-not-behind-remote" $false "cannot compare without a fresh remote read"
    }

    # --- 0c. Current branch is not a frozen Task 6 branch (§13) ---
    $currentBranch = (git branch --show-current 2>&1 | Select-Object -First 1)
    $frozen = @("codex/task-06-method-pack", "codex/qa-task-06-method-pack", "codex/integrate-task-06-method-pack")
    Add-Result "not-on-frozen-branch" ($frozen -notcontains $currentBranch) "AGENTS.md §13: '$currentBranch' is a completed Task 6 branch and MUST NOT receive further work"

    # --- 1. Working tree must be clean (§13) ---
    $dirty = @(git status --porcelain 2>&1)
    Add-Result "clean-worktree" ($dirty.Count -eq 0) "Uncommitted changes: $($dirty.Count) files"

    # --- 2. Contract drift check (§14, §21) ---
    $contractScript = Join-Path $PSScriptRoot "generate_contracts.ps1"
    if (Test-Path -LiteralPath $contractScript) {
        $oldEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $contractResult = @(& powershell -ExecutionPolicy Bypass -File $contractScript -Check 2>&1)
        $contractExitCode = $LASTEXITCODE
        $ErrorActionPreference = $oldEAP
        $contractOk = ($contractExitCode -eq 0) -and ($contractResult -contains "CONTRACT_DRIFT_OK")
        Add-Result "contract-drift" $contractOk "Run: scripts/generate_contracts.ps1 -Check"
    }
    else {
        Add-Result "contract-drift" $false "generate_contracts.ps1 not found"
    }

    # --- 3. Python lint (§14) ---
    $localUv = Join-Path $RepositoryRoot ".tools\uv\uv.exe"
    $uvCommand = if (Get-Command "uv" -ErrorAction SilentlyContinue) {
        (Get-Command "uv").Source
    }
    elseif (Test-Path -LiteralPath $localUv -PathType Leaf) {
        $localUv
    }
    else { "" }
    if (-not [string]::IsNullOrWhiteSpace($uvCommand)) {
        $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & $uvCommand run --project services/api ruff check services/api 2>&1 | Out-Null
        $lintExit = $LASTEXITCODE
        $ErrorActionPreference = $oldEAP
        Add-Result "python-lint" ($lintExit -eq 0) "Run: uv run --project services/api ruff check services/api"
    }
    else {
        Add-Result "python-lint" $false "uv is not available"
    }

    # --- 4. Python compile check (syntax validity) ---
    if (-not [string]::IsNullOrWhiteSpace($uvCommand)) {
        $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & $uvCommand run --project services/api python -m compileall -q services/api/src 2>&1 | Out-Null
        $compileExit = $LASTEXITCODE
        $ErrorActionPreference = $oldEAP
        Add-Result "python-compileall" ($compileExit -eq 0) "Run: uv run --project services/api python -m compileall -q services/api/src"
    }
    else {
        Add-Result "python-compileall" $false "uv is not available"
    }

    # --- 5. Decision OS contracts verification (§14) ---
    $verifyScript = Join-Path $PSScriptRoot "verify_decision_os_contracts.py"
    $projectPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
    if ((Test-Path -LiteralPath $verifyScript) -and (Test-Path -LiteralPath $projectPython)) {
        $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        $verifyResult = @(& $projectPython $verifyScript 2>&1)
        $verifyExitCode = $LASTEXITCODE
        $ErrorActionPreference = $oldEAP
        $verifyOk = ($verifyExitCode -eq 0) -and ($verifyResult -contains "decision-os-contracts: PASS")
        Add-Result "decision-os-contracts" $verifyOk "Run: python scripts/verify_decision_os_contracts.py"
    }
    else {
        Add-Result "decision-os-contracts" $false "verifier or .venv Python not found"
    }

    # --- 6. No root LICENSE file (§17) ---
    $licenseExists = Test-Path -LiteralPath (Join-Path $RepositoryRoot "LICENSE") -PathType Leaf
    Add-Result "no-root-license" (-not $licenseExists) "AGENTS.md §17: Root LICENSE MUST NOT exist in the private phase"

    # --- 7. No secrets in tracked files (§12) ---
    $trackedEnv = git ls-files -- "*.env" "*.key" "探讨/.env" "探讨/auth.json" 2>&1
    $secretFilesTracked = @($trackedEnv | Where-Object { $_ -and $_ -notmatch '\.example$' }).Count
    Add-Result "no-secrets-tracked" ($secretFilesTracked -eq 0) "Tracked secret/env files found: $secretFilesTracked"

    # --- 8. Frontend typecheck + build (§14) ---
    $webDir = Join-Path $RepositoryRoot "apps\web"
    if ((Test-Path -LiteralPath (Join-Path $webDir "package.json")) -and (Test-Path -LiteralPath (Join-Path $webDir "node_modules"))) {
        $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & pnpm --dir apps/web build 2>&1 | Out-Null
        $buildExit = $LASTEXITCODE
        $ErrorActionPreference = $oldEAP
        Add-Result "frontend-build" ($buildExit -eq 0) "Run: pnpm --dir apps/web build"
    }
    else {
        Add-Result "frontend-build" $false "apps/web dependencies not installed"
    }

    # --- Summary ---
    Write-Host ""
    Write-Host "=== Results ===" -ForegroundColor Cyan
    Write-Host "Passed: $($script:Passed.Count)  Failed: $($script:Failed.Count)"

    if ($script:Failed.Count -eq 0) {
        Write-Host ""
        Write-Host "MERGE_PREFLIGHT_OK" -ForegroundColor Green
        exit 0
    }
    else {
        Write-Host ""
        Write-Host "MERGE_PREFLIGHT_BLOCKED" -ForegroundColor Red
        Write-Host "Failed checks:" -ForegroundColor Yellow
        $script:Failed | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
        exit 1
    }
}
finally {
    Pop-Location
}

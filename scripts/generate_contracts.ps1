[CmdletBinding()]
param(
    [switch]$Check,
    [string]$ValidationRoot = ""
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ContractsRoot = Join-Path $RepositoryRoot "packages\contracts"
$CanonicalOpenApi = Join-Path $ContractsRoot "openapi.json"
$CanonicalTypes = Join-Path $ContractsRoot "src\types.gen.ts"
$LocalUv = Join-Path $RepositoryRoot ".tools\uv\uv.exe"
$UvCommand = if (Get-Command "uv" -ErrorAction SilentlyContinue) {
    (Get-Command "uv").Source
}
elseif (Test-Path -LiteralPath $LocalUv -PathType Leaf) {
    $LocalUv
}
else {
    ""
}
$env:UV_PROJECT_ENVIRONMENT = Join-Path $RepositoryRoot ".venv"

function Assert-LastExitCode([string]$Operation) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' is not available."
    }
}

function Assert-SameFile([string]$Expected, [string]$Actual, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Expected -PathType Leaf)) {
        throw "$Label canonical artifact is missing: $Expected"
    }
    if (-not (Test-Path -LiteralPath $Actual -PathType Leaf)) {
        throw "$Label regenerated artifact is missing: $Actual"
    }

    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $expectedText = [System.IO.File]::ReadAllText($Expected, $utf8).Replace("`r`n", "`n").Replace("`r", "`n")
    $actualText = [System.IO.File]::ReadAllText($Actual, $utf8).Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not [string]::Equals($expectedText, $actualText, [System.StringComparison]::Ordinal)) {
        throw "$Label drift detected between '$Expected' and '$Actual'."
    }
}

if ([string]::IsNullOrWhiteSpace($UvCommand)) { throw "Required command uv is not available." }
Assert-Command "pnpm"
Push-Location $RepositoryRoot
try {
    if ($Check) {
        if ([string]::IsNullOrWhiteSpace($ValidationRoot)) {
            if (-not [string]::IsNullOrWhiteSpace($env:DECISION_LAB_VALIDATION_DIR)) {
                $ValidationRoot = $env:DECISION_LAB_VALIDATION_DIR
            }
            else {
                $siblingValidation = Join-Path (Split-Path -Parent $RepositoryRoot) "decision-lab-G0"
                if (Test-Path -LiteralPath $siblingValidation -PathType Container) {
                    $ValidationRoot = $siblingValidation
                }
                else {
                    $ValidationRoot = Join-Path $RepositoryRoot ".contract-check"
                }
            }
        }

        $checkRoot = Join-Path $ValidationRoot "contracts-check"
        New-Item -ItemType Directory -Path $checkRoot -Force | Out-Null
        $checkOpenApi = Join-Path $checkRoot "openapi.json"
        $checkTypes = Join-Path $checkRoot "types.gen.ts"

        & $UvCommand run --python 3.12 --project services/api python scripts/export_openapi.py --output $checkOpenApi
        Assert-LastExitCode "OpenAPI regeneration"

        & pnpm --dir packages/contracts exec openapi-typescript $checkOpenApi -o $checkTypes
        Assert-LastExitCode "TypeScript contract regeneration"

        Assert-SameFile $CanonicalOpenApi $checkOpenApi "OpenAPI"
        Assert-SameFile $CanonicalTypes $checkTypes "TypeScript"
        Write-Output "CONTRACT_DRIFT_OK"
    }
    else {
        & $UvCommand run --python 3.12 --project services/api python scripts/export_openapi.py
        Assert-LastExitCode "OpenAPI export"

        & pnpm --dir packages/contracts generate
        Assert-LastExitCode "TypeScript contract generation"
        Write-Output "CONTRACT_GENERATION_OK"
    }
}
finally {
    Pop-Location
}
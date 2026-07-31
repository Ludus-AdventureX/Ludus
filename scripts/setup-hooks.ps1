[CmdletBinding()]
param(
    [switch]$Verify
)

# ============================================================================
# setup-hooks.ps1 — Activate .githooks enforcement for this repository
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/setup-hooks.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/setup-hooks.ps1 -Verify
# ============================================================================

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$HooksDir = Join-Path $RepositoryRoot ".githooks"

Push-Location $RepositoryRoot
try {
    if (-not (Test-Path -LiteralPath $HooksDir -PathType Container)) {
        throw ".githooks directory not found at $HooksDir"
    }

    if ($Verify) {
        $currentPath = git config --local core.hooksPath 2>$null
        if ($currentPath -eq ".githooks") {
            Write-Host "[OK] core.hooksPath is set to .githooks" -ForegroundColor Green
            Write-Host ""
            Write-Host "Active hooks:" -ForegroundColor Cyan
            Get-ChildItem -LiteralPath $HooksDir -File | ForEach-Object {
                Write-Host "  - $($_.Name)" -ForegroundColor White
            }
            exit 0
        }
        else {
            Write-Host "[NOT ACTIVE] core.hooksPath = '$currentPath'" -ForegroundColor Yellow
            Write-Host "Run without -Verify to activate."
            exit 1
        }
    }

    # Set core.hooksPath to use the versioned .githooks directory
    git config --local core.hooksPath .githooks
    Write-Host "[DONE] Git hooks activated" -ForegroundColor Green
    Write-Host ""
    Write-Host "  core.hooksPath = .githooks" -ForegroundColor White
    Write-Host ""
    Write-Host "Active hooks:" -ForegroundColor Cyan
    Get-ChildItem -LiteralPath $HooksDir -File | ForEach-Object {
        Write-Host "  - $($_.Name): $(Get-Content $_.FullName | Select-Object -First 1)" -ForegroundColor White
    }
    Write-Host ""
    Write-Host "Covered AGENTS.md rules:" -ForegroundColor Cyan
    Write-Host "  pre-commit:"
    Write-Host "    - §13 Block commits on frozen Task 6 branches"
    Write-Host "    - §19 Block direct commits on main (without override)"
    Write-Host "    - §12 Block committing secrets (.env, .key, API keys)"
    Write-Host "    - §17 Block committing root LICENSE file"
    Write-Host "  pre-push:"
    Write-Host "    - §17/§19 Block push to non-canonical remote"
    Write-Host "    - §13 Block push to frozen Task 6 branches"
    Write-Host "    - §19 Block direct push to main"
    Write-Host "    - §19/§21 Block force-push (non-fast-forward)"
    Write-Host ""
    Write-Host "To deactivate: git config --local --unset core.hooksPath"
}
finally {
    Pop-Location
}

[CmdletBinding()]
param(
    [string]$Project = "",
    [switch]$Inventory,
    [switch]$RemoveVolumes
)

# QA/gate resource recycling. Every QA or gate run that starts a compose stack
# MUST tear it down at the end, whether the gate passed or failed:
#   1. Start the stack with a run-scoped project name so its containers carry
#      the label com.docker.compose.project=<project>:
#        docker compose -p ludus-qa-<run-id> -f <compose-file> up -d
#   2. Inventory current containers first (read-only, no authorization needed):
#        powershell -ExecutionPolicy Bypass -File scripts/qa_teardown.ps1 -Inventory
#   3. After explicit confirmation, tear down only the stack this run started:
#        powershell -ExecutionPolicy Bypass -File scripts/qa_teardown.ps1 -Project ludus-qa-<run-id>
# Stopping or removing containers that this run did not start requires separate
# product-owner authorization (AGENTS.md section 18).

$ErrorActionPreference = "Stop"

function Invoke-Capture([string]$Command, [string[]]$Arguments) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = @(& $Command @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        $code = $LASTEXITCODE
    }
    catch {
        $output = @($_.Exception.Message)
        $code = 1
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    return [pscustomobject]@{ exit_code = $code; output = $output }
}

if ($null -eq (Get-Command "docker" -ErrorAction SilentlyContinue)) {
    Write-Output "QA_TEARDOWN_FAIL: docker is not available"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($Project)) {
    $Project = $env:LUDUS_QA_COMPOSE_PROJECT
}

$inventoryFormat = 'table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Label `com.docker.compose.project`}}'
$inventoryCapture = Invoke-Capture "docker" @("ps", "--format", $inventoryFormat)
if ($inventoryCapture.exit_code -ne 0) {
    Write-Output "QA_TEARDOWN_FAIL: docker ps failed"
    $inventoryCapture.output | ForEach-Object { Write-Output $_ }
    exit 1
}

Write-Output "== Running containers (compose project label) =="
$inventoryCapture.output | ForEach-Object { Write-Output $_ }

if ($Inventory -or [string]::IsNullOrWhiteSpace($Project)) {
    Write-Output ""
    Write-Output "QA_TEARDOWN_INVENTORY_ONLY"
    Write-Output "Teardown requires an explicit -Project <compose-project> started by this run."
    Write-Output "Containers not started by this run require separate authorization before stop/removal."
    exit 0
}

$projectFilter = "label=com.docker.compose.project=$Project"
$targetIds = Invoke-Capture "docker" @("ps", "-a", "--filter", $projectFilter, "-q")
$targetCount = @($targetIds.output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
if ($targetCount -eq 0) {
    Write-Output "QA_TEARDOWN_OK: no containers remain for project '$Project'"
    exit 0
}

Write-Output ""
Write-Output "Tearing down compose project '$Project' ($targetCount containers)..."
$downArguments = @("compose", "-p", $Project, "down", "--remove-orphans")
if ($RemoveVolumes) {
    $downArguments += "--volumes"
}
$downCapture = Invoke-Capture "docker" $downArguments
$downCapture.output | ForEach-Object { Write-Output $_ }
if ($downCapture.exit_code -ne 0) {
    Write-Output "QA_TEARDOWN_FAIL: docker compose down exited with code $($downCapture.exit_code)"
    exit 1
}

$leftoverIds = Invoke-Capture "docker" @("ps", "-a", "--filter", $projectFilter, "-q")
$leftoverCount = @($leftoverIds.output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
if ($leftoverCount -eq 0) {
    Write-Output "QA_TEARDOWN_OK: project '$Project' left no containers"
    exit 0
}

Write-Output "QA_TEARDOWN_LEFTOVER: $leftoverCount containers still carry project '$Project'"
exit 1

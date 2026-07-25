[CmdletBinding()]
param(
    [ValidateSet("six_agent_72h", "four_agent_108h", "three_agent_144h")]
    [string]$CapacityProfile = "",
    [switch]$Diagnostic,
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ContractsRoot = Join-Path $RepositoryRoot "packages\contracts"
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
$ProjectPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
$WorkspaceRoot = Split-Path -Parent $RepositoryRoot
$RepositoryPlanRoot = Join-Path $RepositoryRoot "docs\product-plan"
$SiblingPlanRoot = Join-Path $WorkspaceRoot "decision-lab-product-plan"
$PlanRoot = if (-not [string]::IsNullOrWhiteSpace($env:DECISION_LAB_PLAN_PATH)) {
    $env:DECISION_LAB_PLAN_PATH
}
elseif (Test-Path -LiteralPath $RepositoryPlanRoot -PathType Container) {
    $RepositoryPlanRoot
}
else {
    $SiblingPlanRoot
}
$LookRoot = if ([string]::IsNullOrWhiteSpace($env:DECISION_LAB_LOOK_PATH)) {
    Join-Path $WorkspaceRoot "look"
}
else {
    $env:DECISION_LAB_LOOK_PATH
}

$LocalEnvPath = Join-Path $RepositoryRoot ".env"
if (Test-Path -LiteralPath $LocalEnvPath -PathType Leaf) {
    foreach ($rawLine in Get-Content -LiteralPath $LocalEnvPath -Encoding UTF8) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($name -match '^[A-Za-z_][A-Za-z0-9_]*$') {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

if ([string]::IsNullOrWhiteSpace($CapacityProfile)) {
    $CapacityProfile = if ([string]::IsNullOrWhiteSpace($env:LUDUS_CAPACITY_PROFILE)) {
        "six_agent_72h"
    }
    else {
        $env:LUDUS_CAPACITY_PROFILE
    }
}

$CapacitySlots = @{
    six_agent_72h = 6
    four_agent_108h = 4
    three_agent_144h = 3
}

$script:Checks = @()

function Add-Check([string]$Name, [string]$State, [string]$Detail) {
    $script:Checks += [pscustomobject]@{
        name = $Name
        state = $State
        detail = $Detail
    }
    Write-Output ("[{0}] {1}: {2}" -f $State, $Name, $Detail)
}

function Test-CommandAvailable([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

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

function First-NonEmptyLine([object]$Capture) {
    $line = $Capture.output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1
    if ($null -eq $line) { return "no output" }
    return $line.Trim()
}

function Test-ConfiguredSecret([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return $false }
    $normalized = $Value.Trim().ToLowerInvariant()
    return -not (
        $normalized.Contains("<") -or
        $normalized.Contains("change-me") -or
        $normalized.Contains("changeme") -or
        $normalized.Contains("placeholder") -or
        $normalized.Contains("your-") -or
        $normalized.Contains("example")
    )
}

function Test-KeyMaterial32Bytes([string]$Value) {
    if (-not (Test-ConfiguredSecret $Value)) { return $false }
    $candidate = $Value.Trim()
    if ($candidate.StartsWith("base64:")) { $candidate = $candidate.Substring(7) }
    if ($candidate -match '^[0-9a-fA-F]{64}$') { return $true }
    try {
        $bytes = [Convert]::FromBase64String($candidate)
        return $bytes.Length -eq 32
    }
    catch {
        return $false
    }
}

function Test-SafeOrigin([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return $false }
    $uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri)) { return $false }
    if ($uri.Scheme -eq "https") { return $true }
    return $uri.Scheme -eq "http" -and $uri.Host -in @("localhost", "127.0.0.1", "::1")
}

Push-Location $RepositoryRoot
try {
    if (Test-CommandAvailable "git") {
        $gitVersion = Invoke-Capture "git" @("--version")
        Add-Check "git-cli" $(if ($gitVersion.exit_code -eq 0) { "PASS" } else { "FAIL" }) (First-NonEmptyLine $gitVersion)

        $topLevel = Invoke-Capture "git" @("rev-parse", "--show-toplevel")
        $normalizedExpected = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\')
        $normalizedActual = if ($topLevel.exit_code -eq 0) {
            [IO.Path]::GetFullPath((First-NonEmptyLine $topLevel)).TrimEnd('\')
        }
        else { "" }
        if ($normalizedActual -eq $normalizedExpected) {
            Add-Check "independent-git-repository" "PASS" $normalizedActual
        }
        else {
            Add-Check "independent-git-repository" "FAIL" "Expected $normalizedExpected; received $normalizedActual"
        }

        $origin = Invoke-Capture "git" @("remote", "get-url", "origin")
        if ($origin.exit_code -eq 0 -and (First-NonEmptyLine $origin) -eq "https://github.com/Ludus-AdventureX/Ludus.git") {
            Add-Check "git-origin" "PASS" "origin is the approved Ludus remote"
        }
        else {
            Add-Check "git-origin" "FAIL" "origin is missing or does not match the approved remote"
        }

        $worktrees = Invoke-Capture "git" @("worktree", "list", "--porcelain")
        $worktreeCount = @($worktrees.output | Where-Object { $_ -like "worktree *" }).Count
        $expectedSlots = $CapacitySlots[$CapacityProfile]
        if ($worktreeCount -ge $expectedSlots) {
            Add-Check "capacity-worktrees" "PASS" "$worktreeCount worktrees available for $CapacityProfile"
        }
        else {
            Add-Check "capacity-worktrees" "FAIL" "$CapacityProfile requires $expectedSlots independent worktrees; found $worktreeCount"
        }
    }
    else {
        Add-Check "git-cli" "FAIL" "git is not available"
        Add-Check "independent-git-repository" "FAIL" "cannot inspect without git"
        Add-Check "git-origin" "FAIL" "cannot inspect without git"
        Add-Check "capacity-worktrees" "FAIL" "cannot inspect without git"
    }

    if (Test-CommandAvailable "py") {
        $python = Invoke-Capture "py" @("-3.12", "--version")
        if ($python.exit_code -eq 0 -and (First-NonEmptyLine $python) -match 'Python 3\.12\.') {
            Add-Check "python-3.12" "PASS" (First-NonEmptyLine $python)
        }
        else {
            Add-Check "python-3.12" "FAIL" (First-NonEmptyLine $python)
        }
    }
    else {
        Add-Check "python-3.12" "FAIL" "Windows Python launcher 'py' is not available"
    }

    if (-not [string]::IsNullOrWhiteSpace($UvCommand)) {
        $uvVersion = Invoke-Capture $UvCommand @("--version")
        $uvPython = Invoke-Capture $UvCommand @("python", "find", "3.12")
        if ($uvVersion.exit_code -eq 0 -and $uvPython.exit_code -eq 0) {
            Add-Check "uv-python" "PASS" ((First-NonEmptyLine $uvVersion) + "; Python 3.12 resolved")
        }
        else {
            Add-Check "uv-python" "FAIL" "uv exists but cannot resolve Python 3.12"
        }
    }
    else {
        Add-Check "uv-python" "FAIL" "uv is not installed"
    }

    if (Test-CommandAvailable "node") {
        $nodeVersion = Invoke-Capture "node" @("--version")
        if ($nodeVersion.exit_code -eq 0 -and (First-NonEmptyLine $nodeVersion) -match '^v22\.') {
            Add-Check "node-22" "PASS" (First-NonEmptyLine $nodeVersion)
        }
        else {
            Add-Check "node-22" "FAIL" (First-NonEmptyLine $nodeVersion)
        }
    }
    else {
        Add-Check "node-22" "FAIL" "node is not available"
    }

    if (Test-CommandAvailable "pnpm") {
        $pnpmVersion = Invoke-Capture "pnpm" @("--version")
        if ($pnpmVersion.exit_code -eq 0 -and (First-NonEmptyLine $pnpmVersion) -match '^9\.') {
            Add-Check "pnpm-9" "PASS" (First-NonEmptyLine $pnpmVersion)
        }
        else {
            Add-Check "pnpm-9" "FAIL" (First-NonEmptyLine $pnpmVersion)
        }
    }
    else {
        Add-Check "pnpm-9" "FAIL" "pnpm is not available"
    }

    $dockerCliReady = $false
    $dockerDaemonReady = $false
    if (Test-CommandAvailable "docker") {
        $dockerVersion = Invoke-Capture "docker" @("--version")
        $composeVersion = Invoke-Capture "docker" @("compose", "version")
        $dockerCliReady = $dockerVersion.exit_code -eq 0 -and $composeVersion.exit_code -eq 0
        Add-Check "docker-compose-cli" $(if ($dockerCliReady) { "PASS" } else { "FAIL" }) (
            (First-NonEmptyLine $dockerVersion) + "; " + (First-NonEmptyLine $composeVersion)
        )

        $dockerInfo = Invoke-Capture "docker" @("info")
        $dockerDaemonReady = $dockerInfo.exit_code -eq 0
        Add-Check "docker-daemon" $(if ($dockerDaemonReady) { "PASS" } else { "FAIL" }) $(
            if ($dockerDaemonReady) { "daemon is reachable" } else { "daemon is not reachable" }
        )
    }
    else {
        Add-Check "docker-compose-cli" "FAIL" "docker is not available"
        Add-Check "docker-daemon" "FAIL" "docker is not available"
    }

    if ($dockerDaemonReady -and (Test-Path -LiteralPath (Join-Path $RepositoryRoot "compose.yaml"))) {
        $postgres = Invoke-Capture "docker" @("compose", "exec", "-T", "db", "postgres", "--version")
        $postgresLine = First-NonEmptyLine $postgres
        if (($postgres.exit_code -eq 0) -and ($postgresLine -match 'PostgreSQL\) 16\.')) {
            Add-Check "postgres-16" "PASS" $postgresLine
        }
        else {
            Add-Check "postgres-16" "FAIL" "the db service is not running as PostgreSQL 16"
        }
    }
    else {
        Add-Check "postgres-16" "FAIL" "Docker daemon or compose service is unavailable"
    }

    $requiredPlanFiles = @(
        "README.md",
        "agent-work-manifest.yaml",
        "docs\contract-changes\CCR-20260721-003.md",
        "28-contract-repair-completion-audit-20260721.md"
    )
    $missingPlanFiles = @($requiredPlanFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $PlanRoot $_) -PathType Leaf) })
    if ($missingPlanFiles.Count -eq 0) {
        Add-Check "canonical-plan" "PASS" "accepted CCR and final contract repair audit are present"
    }
    else {
        Add-Check "canonical-plan" "FAIL" ("missing: " + ($missingPlanFiles -join ", "))
    }

    $contractVerifier = Join-Path $RepositoryRoot "scripts\verify_decision_os_contracts.py"
    if ((Test-Path -LiteralPath $contractVerifier -PathType Leaf) -and (Test-Path -LiteralPath $ProjectPython -PathType Leaf)) {
        $contractCheck = Invoke-Capture $ProjectPython @($contractVerifier)
        if ($contractCheck.exit_code -eq 0 -and ($contractCheck.output -contains "decision-os-contracts: PASS")) {
            Add-Check "canonical-contract-validation" "PASS" "decision-os-contracts: PASS"
        }
        else {
            Add-Check "canonical-contract-validation" "FAIL" "contract verifier did not pass"
        }
    }
    else {
        Add-Check "canonical-contract-validation" "FAIL" "contract verifier or Python 3.12 is unavailable"
    }

    $waysManifest = Join-Path $RepositoryRoot "ways\hardtech-market-direction\1.1.0\manifest.yaml"
    if (Test-Path -LiteralPath $waysManifest -PathType Leaf) {
        $waysText = Get-Content -LiteralPath $waysManifest -Raw -Encoding UTF8
        if ($waysText -match '(?m)^version:\s*["'']?1\.1\.0["'']?\s*$') {
            Add-Check "ways-1.1.0" "PASS" "active method manifest is version 1.1.0"
        }
        else {
            Add-Check "ways-1.1.0" "FAIL" "manifest exists but does not declare version 1.1.0"
        }
    }
    else {
        Add-Check "ways-1.1.0" "FAIL" "active method manifest is missing"
    }

    $fixtureRoot = Join-Path $RepositoryRoot "fixtures\spherical-robot"
    $fixtureParts = @("seed", "external", "expected")
    $missingFixtureParts = @($fixtureParts | Where-Object { -not (Test-Path -LiteralPath (Join-Path $fixtureRoot $_) -PathType Container) })
    if ($missingFixtureParts.Count -eq 0) {
        Add-Check "fixture-boundaries" "PASS" "seed/external/expected directories are present"
    }
    else {
        Add-Check "fixture-boundaries" "FAIL" ("missing: " + ($missingFixtureParts -join ", "))
    }

    $gitIgnore = Join-Path $RepositoryRoot ".gitignore"
    $ignorePatterns = @(".env", "!.env.example", "*.key", ".venv/", "node_modules/", ".next/", "playwright-report/", "artifacts/")
    if (Test-Path -LiteralPath $gitIgnore -PathType Leaf) {
        $ignoreText = Get-Content -LiteralPath $gitIgnore -Raw -Encoding UTF8
        $missingIgnorePatterns = @($ignorePatterns | Where-Object { -not $ignoreText.Contains($_) })
        if ($missingIgnorePatterns.Count -eq 0) {
            Add-Check "gitignore-secret-boundary" "PASS" "required secret and generated paths are ignored"
        }
        else {
            Add-Check "gitignore-secret-boundary" "FAIL" ("missing patterns: " + ($missingIgnorePatterns -join ", "))
        }
    }
    else {
        Add-Check "gitignore-secret-boundary" "FAIL" ".gitignore is missing"
    }

    if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot "LICENSE"))) {
        Add-Check "private-license-boundary" "PASS" "no root LICENSE is present; LICENSING.md governs the private phase"
    }
    else {
        Add-Check "private-license-boundary" "FAIL" "a root LICENSE exists without a recorded approval"
    }

    $securityChecks = @(
        @{ name = "JWT_SECRET"; ok = (Test-ConfiguredSecret $env:JWT_SECRET) -and $env:JWT_SECRET.Length -ge 32; detail = "requires at least 32 non-placeholder characters" },
        @{ name = "CSRF_SECRET"; ok = (Test-ConfiguredSecret $env:CSRF_SECRET) -and $env:CSRF_SECRET.Length -ge 32; detail = "requires at least 32 non-placeholder characters" },
        @{ name = "CONNECTOR_MASTER_KEY"; ok = (Test-KeyMaterial32Bytes $env:CONNECTOR_MASTER_KEY); detail = "requires exactly 32 bytes encoded as base64 or 64 hex characters" },
        @{ name = "MODEL_API_KEY"; ok = (Test-ConfiguredSecret $env:MODEL_API_KEY); detail = "required for the real model probe" },
        @{ name = "WEB_ORIGIN"; ok = (Test-SafeOrigin $env:WEB_ORIGIN); detail = "requires HTTPS or local HTTP" }
    )
    foreach ($securityCheck in $securityChecks) {
        Add-Check ("secure-config-" + $securityCheck.name.ToLowerInvariant()) $(if ($securityCheck.ok) { "PASS" } else { "FAIL" }) $(
            if ($securityCheck.ok) { "configured without disclosure" } else { $securityCheck.detail }
        )
    }

    $externalProviderConfigured = (Test-ConfiguredSecret $env:EXA_API_KEY) -or
        (Test-ConfiguredSecret $env:FIRECRAWL_API_KEY) -or
        (Test-ConfiguredSecret $env:TAVILY_API_KEY)
    Add-Check "external-source-provider" $(if ($externalProviderConfigured) { "PASS" } else { "FAIL" }) $(
        if ($externalProviderConfigured) { "at least one audited provider key is configured" } else { "configure at least one of EXA_API_KEY, FIRECRAWL_API_KEY, or TAVILY_API_KEY" }
    )

    $configuredSlots = 0
    $slotParsed = [int]::TryParse($env:LUDUS_AGENT_SLOTS, [ref]$configuredSlots)
    $requiredSlots = $CapacitySlots[$CapacityProfile]
    if ($slotParsed -and $configuredSlots -eq $requiredSlots) {
        Add-Check "capacity-profile-config" "PASS" "$CapacityProfile declares $configuredSlots slots"
    }
    else {
        Add-Check "capacity-profile-config" "FAIL" "$CapacityProfile requires LUDUS_AGENT_SLOTS=$requiredSlots"
    }

    $snapshotScript = Join-Path $RepositoryRoot "scripts\snapshot_look.py"
    if ((Test-Path -LiteralPath $snapshotScript -PathType Leaf) -and (Test-Path -LiteralPath $LookRoot -PathType Container) -and (Test-Path -LiteralPath $ProjectPython -PathType Leaf)) {
        $snapshot = Invoke-Capture $ProjectPython @($snapshotScript, "--check")
        if ($snapshot.exit_code -eq 0) {
            Add-Check "look-v7-snapshot" "PASS" "immutable Look source snapshot check passed"
        }
        else {
            Add-Check "look-v7-snapshot" "FAIL" "snapshot script did not pass"
        }
    }
    else {
        Add-Check "look-v7-snapshot" "FAIL" "Task 1W snapshot script or Look source is unavailable"
    }

    $canonicalOpenApi = Join-Path $RepositoryRoot "packages\contracts\openapi.json"
    $canonicalTypes = Join-Path $RepositoryRoot "packages\contracts\src\types.gen.ts"
    if ((Test-Path -LiteralPath $canonicalOpenApi -PathType Leaf) -and
        (Test-Path -LiteralPath $canonicalTypes -PathType Leaf) -and
        (-not [string]::IsNullOrWhiteSpace($UvCommand)) -and
        ((Test-Path -LiteralPath (Join-Path $ContractsRoot "node_modules")) -or (Test-Path -LiteralPath (Join-Path $RepositoryRoot "node_modules")))) {
        $contractDrift = Invoke-Capture "powershell" @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "generate_contracts.ps1"), "-Check")
        if ($contractDrift.exit_code -eq 0 -and ($contractDrift.output -contains "CONTRACT_DRIFT_OK")) {
            Add-Check "openapi-typescript-drift" "PASS" "CONTRACT_DRIFT_OK"
        }
        else {
            Add-Check "openapi-typescript-drift" "FAIL" "contract regeneration differs or failed"
        }
    }
    else {
        Add-Check "openapi-typescript-drift" "FAIL" "generated artifacts or approved dependencies are not ready"
    }

    $webPackage = Join-Path $RepositoryRoot "apps\web\package.json"
    $webModules = Join-Path $RepositoryRoot "apps\web\node_modules"
    if ((Test-Path -LiteralPath $webPackage -PathType Leaf) -and (Test-Path -LiteralPath $webModules -PathType Container)) {
        $playwright = Invoke-Capture "pnpm" @("--dir", "apps/web", "exec", "playwright", "--version")
        Add-Check "playwright-browser-tooling" $(if ($playwright.exit_code -eq 0) { "PASS" } else { "FAIL" }) $(First-NonEmptyLine $playwright)
    }
    else {
        Add-Check "playwright-browser-tooling" "FAIL" "Task 1W dependencies/browser tooling are not installed"
    }
}
finally {
    Pop-Location
}

$failed = @($script:Checks | Where-Object { $_.state -eq "FAIL" })
$report = [ordered]@{
    schema_version = "1.0.0"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    repository = $RepositoryRoot
    plan_root = $PlanRoot
    look_root = $LookRoot
    capacity_profile = $CapacityProfile
    checks = $script:Checks
    passed = $failed.Count -eq 0
}

if (-not [string]::IsNullOrWhiteSpace($ReportPath)) {
    $resolvedReport = if ([IO.Path]::IsPathRooted($ReportPath)) { $ReportPath } else { Join-Path $RepositoryRoot $ReportPath }
    $reportParent = Split-Path -Parent $resolvedReport
    if (-not (Test-Path -LiteralPath $reportParent)) {
        New-Item -ItemType Directory -Path $reportParent -Force | Out-Null
    }
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $resolvedReport -Encoding UTF8
    Write-Output "PREFLIGHT_REPORT_WRITTEN $resolvedReport"
}

if ($failed.Count -eq 0) {
    Write-Output "PREFLIGHT_OK"
    exit 0
}

Write-Output ("PREFLIGHT_NOT_READY: {0} required checks failed" -f $failed.Count)
if ($Diagnostic) {
    exit 0
}
exit 1
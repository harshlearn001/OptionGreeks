<#
    OptionGreeks Daily Pipeline
#>

param(
    [string]$Python = "python",
    [string]$MarketForgeRoot = "H:\MarketForge",
    [string]$OutputRoot = "H:\OptionGreeks\data",
    [double]$RiskFreeRate = 0.06,
    [double]$DividendYield = 0.00,
    [string]$HvWindows = "10,20,30,60,90,252",
    [string]$IndicatorWindows = "252",
    [int]$Jobs = [Math]::Min(8, [Math]::Max(1, [Environment]::ProcessorCount - 2))
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

$ProjectRoot = Split-Path -Parent $PSScriptRoot

$LogDir = Join-Path $ProjectRoot "logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LogFile = Join-Path $LogDir (
    "optiongreeks_daily_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss")
)

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

function Write-Log {

    param(
        [string]$Message
    )

    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message

    Write-Host $line

    if ($script:LogFile) {
        Add-Content -Path $script:LogFile -Value $line
    }
}

# ---------------------------------------------------------------------
# Validate Python
# ---------------------------------------------------------------------

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = "python"
}

$pythonCmd = Get-Command $Python -ErrorAction SilentlyContinue

if (-not $pythonCmd) {
    throw "Python executable not found: $Python"
}

Write-Log "Python executable : $($pythonCmd.Source)"
Write-Log "Parallel jobs     : $Jobs"

# ---------------------------------------------------------------------
# Validate MarketForge
# ---------------------------------------------------------------------

if (-not (Test-Path $MarketForgeRoot)) {
    throw "MarketForge root not found: $MarketForgeRoot"
}

Write-Log "MarketForge root : $MarketForgeRoot"

# ---------------------------------------------------------------------
# Output folders
# ---------------------------------------------------------------------

@(
    "greeks",
    "hv",
    "indicators"
) | ForEach-Object {

    $dir = Join-Path $OutputRoot $_

    if (-not (Test-Path $dir)) {

        New-Item -ItemType Directory -Force -Path $dir | Out-Null

        Write-Log "Created directory : $dir"
    }
}

$PipelineStart = Get-Date

Write-Log "=========================================="
Write-Log "OptionGreeks Daily Pipeline Started"
Write-Log "=========================================="

# ---------------------------------------------------------------------
# Step Runner
# ---------------------------------------------------------------------

function Run-Step {

    param(
        [string]$Name,
        [string]$ScriptPath,
        [hashtable]$Parameters
    )

    Write-Log ""
    Write-Log "========== $Name =========="

    $stepStart = Get-Date

    & $ScriptPath @Parameters 2>&1 |
        Tee-Object -FilePath $LogFile -Append

    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed (ExitCode=$LASTEXITCODE)"
    }

    $elapsed = ((Get-Date) - $stepStart).TotalSeconds

    Write-Log "$Name completed in $([math]::Round($elapsed,2)) sec"
}

# ---------------------------------------------------------------------
# Build Greeks
# ---------------------------------------------------------------------

Run-Step `
    -Name "Greeks (INDICES)" `
    -ScriptPath (Join-Path $PSScriptRoot "build_greeks.ps1") `
    -Parameters @{
        Segment = "INDICES"
        Python = $Python
        MarketForgeRoot = $MarketForgeRoot
        OutputRoot = (Join-Path $OutputRoot "greeks")
        RiskFreeRate = $RiskFreeRate
        DividendYield = $DividendYield
        AllowFailures = $true
        Jobs = $Jobs
    }

Run-Step `
    -Name "Greeks (STOCKS)" `
    -ScriptPath (Join-Path $PSScriptRoot "build_greeks.ps1") `
    -Parameters @{
        Segment = "STOCKS"
        Python = $Python
        MarketForgeRoot = $MarketForgeRoot
        OutputRoot = (Join-Path $OutputRoot "greeks")
        RiskFreeRate = $RiskFreeRate
        DividendYield = $DividendYield
        AllowFailures = $true
        Jobs = $Jobs
    }

# ---------------------------------------------------------------------
# Build Historical Volatility
# ---------------------------------------------------------------------

Run-Step `
    -Name "HV (INDICES)" `
    -ScriptPath (Join-Path $PSScriptRoot "build_hv.ps1") `
    -Parameters @{
        Segment = "INDICES"
        Python = $Python
        MarketForgeRoot = $MarketForgeRoot
        OutputRoot = (Join-Path $OutputRoot "hv")
        Windows = $HvWindows
        Jobs = $Jobs
    }

Run-Step `
    -Name "HV (STOCKS)" `
    -ScriptPath (Join-Path $PSScriptRoot "build_hv.ps1") `
    -Parameters @{
        Segment = "STOCKS"
        Python = $Python
        MarketForgeRoot = $MarketForgeRoot
        OutputRoot = (Join-Path $OutputRoot "hv")
        Windows = $HvWindows
        Jobs = $Jobs
    }

# ---------------------------------------------------------------------
# Build Indicators
# ---------------------------------------------------------------------

Run-Step `
    -Name "Indicators (INDICES)" `
    -ScriptPath (Join-Path $PSScriptRoot "build_indicators.ps1") `
    -Parameters @{
        Segment = "INDICES"
        Python = $Python
        GreeksRoot = (Join-Path $OutputRoot "greeks")
        HvRoot = (Join-Path $OutputRoot "hv")
        OutputRoot = (Join-Path $OutputRoot "indicators")
        Windows = $IndicatorWindows
        Jobs = $Jobs
    }

Run-Step `
    -Name "Indicators (STOCKS)" `
    -ScriptPath (Join-Path $PSScriptRoot "build_indicators.ps1") `
    -Parameters @{
        Segment = "STOCKS"
        Python = $Python
        GreeksRoot = (Join-Path $OutputRoot "greeks")
        HvRoot = (Join-Path $OutputRoot "hv")
        OutputRoot = (Join-Path $OutputRoot "indicators")
        Windows = $IndicatorWindows
        Jobs = $Jobs
    }

# ---------------------------------------------------------------------
# Finish
# ---------------------------------------------------------------------

$totalMinutes = ((Get-Date) - $PipelineStart).TotalMinutes

Write-Log ""
Write-Log "=========================================="
Write-Log "Pipeline completed successfully"
Write-Log "Total runtime : $([math]::Round($totalMinutes,2)) minutes"
Write-Log "Log file      : $LogFile"
Write-Log "=========================================="

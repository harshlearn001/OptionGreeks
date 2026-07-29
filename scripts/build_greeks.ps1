param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("STOCKS", "INDICES")]
    [string]$Segment,

    [string]$Symbol,
    [string]$MarketForgeRoot = "H:\MarketForge",
    [string]$OutputRoot = "H:\OptionGreeks\data\greeks",
    [double]$RiskFreeRate = 0.06,
    [double]$DividendYield = 0.0,
    [switch]$AllowFailures,
    [int]$Jobs = 1,
    [string]$Python = "python"
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $ProjectRoot "src\build_greeks_from_marketforge.py"

$argsList = @(
    $ScriptPath,
    "--segment", $Segment,
    "--marketforge-root", $MarketForgeRoot,
    "--output-root", $OutputRoot,
    "--risk-free-rate", $RiskFreeRate,
    "--dividend-yield", $DividendYield,
    "--jobs", $Jobs
)

if ($Symbol) {
    $argsList += @("--symbol", $Symbol)
}

if ($AllowFailures) {
    $argsList += @("--allow-failures")
}

& $Python @argsList

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

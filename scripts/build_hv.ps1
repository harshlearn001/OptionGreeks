param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("STOCKS", "INDICES")]
    [string]$Segment,

    [string]$Symbol,
    [string]$MarketForgeRoot = "H:\MarketForge",
    [string]$OutputRoot = "H:\OptionGreeks\data\hv",
    [string]$Windows = "10,20,30,60,90,252",
    [int]$Jobs = 1,
    [string]$Python = "python"
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $ProjectRoot "src\build_hv_from_marketforge.py"

$argsList = @(
    $ScriptPath,
    "--segment", $Segment,
    "--marketforge-root", $MarketForgeRoot,
    "--output-root", $OutputRoot,
    "--windows", $Windows,
    "--jobs", $Jobs
)

if ($Symbol) {
    $argsList += @("--symbol", $Symbol)
}

& $Python @argsList

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

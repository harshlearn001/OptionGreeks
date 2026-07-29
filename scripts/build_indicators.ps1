param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("STOCKS", "INDICES")]
    [string]$Segment,

    [string]$Symbol,
    [string]$GreeksRoot = "H:\OptionGreeks\data\greeks",
    [string]$HvRoot = "H:\OptionGreeks\data\hv",
    [string]$OutputRoot = "H:\OptionGreeks\data\indicators",
    [string]$Windows = "252",
    [int]$Jobs = 1,
    [string]$Python = "python"
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $ProjectRoot "src\build_indicators.py"

$argsList = @(
    $ScriptPath,
    "--segment", $Segment,
    "--greeks-root", $GreeksRoot,
    "--hv-root", $HvRoot,
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

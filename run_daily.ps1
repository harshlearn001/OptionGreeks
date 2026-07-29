Write-Host "====================================="
Write-Host " OptionGreeks | DAILY PIPELINE"
Write-Host (" Start Time : {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
Write-Host "====================================="

$ROOT = $PSScriptRoot

Set-Location (Join-Path $ROOT "scripts")

.\daily_update_optiongreeks.ps1

if ($LASTEXITCODE -ne 0) {
    Write-Host "OptionGreeks pipeline failed." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "====================================="
Write-Host " OptionGreeks COMPLETED"
Write-Host (" End Time : {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
Write-Host "====================================="
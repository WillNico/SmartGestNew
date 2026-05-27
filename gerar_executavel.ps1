$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

python -m PyInstaller --noconfirm --clean SmartGest.spec

Write-Host ""
Write-Host "Executavel gerado em: $projectRoot\dist\SmartGest\SmartGest.exe"

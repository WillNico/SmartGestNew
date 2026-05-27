$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$targets = @(
    (Join-Path $projectRoot "build\SmartGest"),
    (Join-Path $projectRoot "dist\SmartGest")
)

foreach ($target in $targets) {
    $resolvedParent = Split-Path -Parent $target
    if ((Test-Path $target) -and (Resolve-Path $resolvedParent).Path.StartsWith((Resolve-Path $projectRoot).Path)) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

python -m PyInstaller --noconfirm --clean SmartGest.spec

Write-Host ""
Write-Host "Executavel gerado em: $projectRoot\dist\SmartGest\SmartGest.exe"

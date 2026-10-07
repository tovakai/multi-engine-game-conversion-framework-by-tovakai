# Build Multi-Engine Game Conversion Framework by Tovakai for Windows x64.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$py = Join-Path (Get-Location) ".venv-win\Scripts\python.exe"
if (-not (Test-Path $py)) {
  $py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
}
if (-not (Test-Path $py)) {
  $py = "python"
}

& $py -m pip install -e ".[gui,build]"

$appName = "Multi-Engine Game Conversion Framework by Tovakai"
& $py -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name "$appName" `
  --paths "." `
  --hidden-import customtkinter `
  --hidden-import tkinterdnd2 `
  --collect-all customtkinter `
  --collect-all tkinterdnd2 `
  "app\main.py"

$release = "dist\windows\$appName"
New-Item -ItemType Directory -Force -Path $release | Out-Null
if (Test-Path "dist\$appName") {
  Copy-Item -Recurse -Force "dist\$appName\*" $release
}

$readme = @"
Multi-Engine Game Conversion Framework by Tovakai
=================================================

1. Run the application.
2. Drop a Ren'Py, RPG Maker, or Godot game folder / ZIP.
3. Let the framework detect the engine.
4. Convert.
5. Copy the generated *-linux-aarch64.tar.gz to the target Linux ARM64 device.

RPG Maker and Godot runtimes are resolved automatically.
Ren'Py currently requires a matching ARM64 Ren'Py runtime folder.
"@
Set-Content -Path (Join-Path $release "README.txt") -Value $readme -Encoding UTF8

$zip = "dist\multi-engine-game-conversion-framework-by-tovakai-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $release -DestinationPath $zip -CompressionLevel Optimal

Write-Host "Built: $release\$appName.exe"
Write-Host "Zip:   $zip"

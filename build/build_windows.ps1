# Build Multi-Engine Game Conversion Framework by tovakai for Windows x64.
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

$appName = "Multi-Engine Game Conversion Framework by tovakai"
$legacyAppName = "Multi-Engine Game Conversion Framework by Tovakai"
$commit = (& git rev-parse --short HEAD 2>$null)
if (-not $commit) { $commit = "unknown" }

# Remove both current and legacy-named outputs so an old binary cannot survive
# a successful rebuild and masquerade as the fresh application.
foreach ($path in @(
  "dist\$appName",
  "dist\$legacyAppName",
  "dist\windows\$appName",
  "dist\windows\$legacyAppName",
  "build\$appName",
  "build\$legacyAppName"
)) {
  if (Test-Path $path) { Remove-Item -Recurse -Force $path }
}
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
Multi-Engine Game Conversion Framework by tovakai
=================================================

1. Run the application.
2. Drop a Ren'Py, RPG Maker, or Godot game folder / ZIP.
3. Let the framework detect the engine.
4. Convert.
5. Drop the generated *-linux-aarch64.zip into Frame Control or FrameDrop.

Supported runtimes are resolved automatically and cached when needed.
"@
Set-Content -Path (Join-Path $release "README.txt") -Value $readme -Encoding UTF8

$buildInfo = @"
commit=$commit
built=$(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")
"@
Set-Content -Path (Join-Path $release "BUILD.txt") -Value $buildInfo -Encoding UTF8


$zip = "dist\multi-engine-game-conversion-framework-by-tovakai-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $release -DestinationPath $zip -CompressionLevel Optimal

Write-Host "Built commit: $commit"
Write-Host "Built: $release\$appName.exe"
Write-Host "Zip:   $zip"

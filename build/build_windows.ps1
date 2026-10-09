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
if ($LASTEXITCODE -ne 0) { throw "Windows build dependencies installation failed" }

$appName = "Multi-Engine Game Conversion Framework by tovakai"
$legacyAppName = "Multi-Engine Game Conversion Framework by Tovakai"
$commit = (& git rev-parse --short HEAD 2>$null)
if (-not $commit) { $commit = "unknown" }
$sts2Tools = (& $py scripts/stage-sts2-tools.py)
if ($LASTEXITCODE -ne 0) { throw "Failed to stage STS2 backend tools" }

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
  --add-data "$sts2Tools;sts2-tools" `
  --hidden-import customtkinter `
  --hidden-import tkinterdnd2 `
  --collect-all customtkinter `
  --collect-all tkinterdnd2 `
  "app\main.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed; refusing to package a stale or partial executable" }
if (-not (Test-Path "dist\$appName\$appName.exe")) {
  throw "PyInstaller returned without producing dist\$appName\$appName.exe"
}

$release = "dist\windows\$appName"
New-Item -ItemType Directory -Force -Path $release | Out-Null
if (Test-Path "dist\$appName") {
  Copy-Item -Recurse -Force "dist\$appName\*" $release
}

$readme = @"
Multi-Engine Game Conversion Framework by tovakai
=================================================

1. Run the application.
2. Drop a supported Ren'Py, RPG Maker, or Godot game folder / ZIP.
3. Let the framework detect the engine.
4. Convert.
5. Transfer the generated Linux AArch64 package to your device.

Matching Ren'Py 7/8 ARM64 runtimes can be resolved automatically.
Legacy Ren'Py migration can require explicit approval; other backends
select compatible runtimes where available.

Experimental Slay the Spire 2 (v0.107.1 / 59260271):
1. Select a compatible STS2 game installation.
2. Complete Frame Setup once: trusted Frame connection, writable destination,
   and a compatible FMOD 2.03.15 Linux SDK.
3. Click Convert. The application builds and deploys native ARM64 output on Frame.
4. Accept Connect Steam, then press Play in the STS2 Steam entry.
   You do not need to edit Launch Options. Restore Steam recovers the saved setting.

The converter does not ask for proof or a declaration of game ownership.
STS2 requires genuine Steam launch context; this workflow does not alter
Steam authentication or grant middleware redistribution permissions.
STS2 remains experimental. Menu, audio and controller navigation have
been checked through the packaged Windows application and genuine Steam launch.
Extended gameplay, save/reload, achievements and Cloud behavior remain unverified.
The application does not distribute game files or proprietary SDK/native inputs.

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

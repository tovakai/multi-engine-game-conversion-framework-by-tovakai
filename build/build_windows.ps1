# Build Multi-Engine Game Conversion Framework by Tovakai for Windows x64.
# Run from the repository root.
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $repoRoot

$appName = "Multi-Engine Game Conversion Framework by Tovakai"
$py = $null

if ($env:VIRTUAL_ENV) {
  $activePy = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
  if (Test-Path $activePy) { $py = $activePy }
}
if (-not $py) {
  $windowsPy = Join-Path $repoRoot ".venv-win\Scripts\python.exe"
  if (Test-Path $windowsPy) { $py = $windowsPy }
}
if (-not $py) {
  $defaultPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
  if (Test-Path $defaultPy) { $py = $defaultPy }
}
if (-not $py) { $py = "python" }

& $py -m pip install -e ".[gui,build]"
if ($LASTEXITCODE -ne 0) {
  throw "Dependency installation failed with exit code $LASTEXITCODE"
}

$workPath = Join-Path $repoRoot ".pyinstaller-work"
$distPath = Join-Path $repoRoot "dist"
$entryPoint = Join-Path $repoRoot "app\main.py"
$rawBuild = Join-Path $distPath $appName
$release = Join-Path (Join-Path $distPath "windows") $appName

& taskkill.exe /IM "$appName.exe" /T /F 2>$null | Out-Null

if (Test-Path $workPath) { Remove-Item -Recurse -Force $workPath }
if (Test-Path $rawBuild) { Remove-Item -Recurse -Force $rawBuild }
if (Test-Path $release) { Remove-Item -Recurse -Force $release }

Write-Host "Building $appName"
Write-Host "Using Python: $py"

& $py -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --workpath $workPath `
  --specpath $workPath `
  --distpath $distPath `
  --name $appName `
  --paths $repoRoot `
  --hidden-import customtkinter `
  --hidden-import tkinterdnd2 `
  --collect-all customtkinter `
  --collect-all tkinterdnd2 `
  --collect-submodules renframe `
  --collect-submodules renpy_arm `
  --collect-submodules rpgmframe `
  --collect-submodules multi_engine_game_conversion_framework_by_tovakai `
  $entryPoint

if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$builtExe = Join-Path $rawBuild "$appName.exe"
if (-not (Test-Path $builtExe)) {
  throw "Expected executable was not created: $builtExe"
}

New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item -Recurse -Force (Join-Path $rawBuild "*") $release

$readme = @"
Multi-Engine Game Conversion Framework by Tovakai (Windows x64)
===============================================================

1. Run:
   Multi-Engine Game Conversion Framework by Tovakai.exe

2. Drop or browse to a supported game:
   - Ren'Py
   - RPG Maker XP / VX / VX Ace / MV / MZ
   - Godot

3. Click Convert.

4. Copy the generated Linux ARM64 archive to the target device and unpack it.

The converter resolves and verifies the engine-specific ARM64 runtime automatically.
Keep this entire application folder together.
"@
Set-Content -Path (Join-Path $release "README.txt") -Value $readme -Encoding UTF8

$zip = Join-Path $distPath "Multi-Engine-Game-Conversion-Framework-by-Tovakai-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $release -DestinationPath $zip -CompressionLevel Optimal

Write-Host ""
Write-Host "Built application:"
Write-Host "  $(Join-Path $release "$appName.exe")"
Write-Host "Release archive:"
Write-Host "  $zip"

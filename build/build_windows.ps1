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
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed ($LASTEXITCODE)" }

$appName = "Multi-Engine Game Conversion Framework by tovakai"
$legacyAppName = "Multi-Engine Game Conversion Framework by Tovakai"
$buildWorkspace = [IO.Path]::GetFullPath((Get-Location).Path).TrimEnd('\') + '\'
function Assert-BuildTarget([string]$target) {
  $resolvedTarget = [IO.Path]::GetFullPath((Join-Path $buildWorkspace $target))
  if (-not $resolvedTarget.StartsWith($buildWorkspace, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Build target escapes workspace: $resolvedTarget"
  }
  return $resolvedTarget
}
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
  $safeBuildTarget = Assert-BuildTarget $path
  if (Test-Path -LiteralPath $safeBuildTarget) { Remove-Item -LiteralPath $safeBuildTarget -Recurse -Force }
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
  --collect-data megcfbt `
  --collect-data gamemakerframe `
  "app\main.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }

$release = "dist\windows\$appName"
New-Item -ItemType Directory -Force -Path $release | Out-Null
if (Test-Path "dist\$appName") {
  Copy-Item -Recurse -Force "dist\$appName\*" $release
}

$readme = @"
Multi-Engine Game Conversion Framework by tovakai
=================================================

1. Run the application.
2. Drop a supported game folder / ZIP (Ren'Py, RPG Maker, Godot, Construct, GameMaker, LÖVE or AGS).
3. Let the framework detect the engine.
4. Convert.
5. Copy the generated *-linux-aarch64.zip to the target Linux ARM64 device.
6. Extract the ZIP and run ./install-to-steam.sh in the graphical desktop session.

RPG Maker and Godot runtimes are resolved automatically.
GameMaker, LÖVE and AGS use a matching ARM64 SDK bundle selected in the GUI
or configured once in the native runtime cache. Native addons require matching builds.
Ren'Py 7/8 runtimes resolve automatically, with a manual ARM64 override.
Original DDLC 1.1.1 / Ren'Py 6.99.12 has an opt-in experimental 7.5.3
full-engine migration. DDLC hardware/story compatibility is unverified.
"@
Set-Content -Path (Join-Path $release "README.txt") -Value $readme -Encoding UTF8

$buildInfo = @"
commit=$commit
built=$(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")
"@
Set-Content -Path (Join-Path $release "BUILD.txt") -Value $buildInfo -Encoding UTF8


$zip = "dist\multi-engine-game-conversion-framework-by-tovakai-windows-x64.zip"
$safeZipTarget = Assert-BuildTarget $zip
if (Test-Path -LiteralPath $safeZipTarget) { Remove-Item -LiteralPath $safeZipTarget -Force }
Compress-Archive -Path $release -DestinationPath $zip -CompressionLevel Optimal

Write-Host "Built commit: $commit"
Write-Host "Built: $release\$appName.exe"
Write-Host "Zip:   $zip"

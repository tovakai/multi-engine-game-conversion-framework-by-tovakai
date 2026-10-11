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
  --collect-data rpgmframe `
  --collect-data monoframe `
  --add-data "experiments/sts2-steamworks;sts2-tools" `
  "app\main.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }

$release = "dist\windows\$appName"
New-Item -ItemType Directory -Force -Path $release | Out-Null
if (Test-Path "dist\$appName") {
  Copy-Item -Recurse -Force "dist\$appName\*" $release
}

& $py build/release_metadata.py --application $release --platform windows-x64
if ($LASTEXITCODE -ne 0) { throw "Release packaging failed ($LASTEXITCODE)" }
Write-Host "GUI: $release\$appName.exe"

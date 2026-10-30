# Build Windows release folder and zip for GitHub Releases.
# Usage (from repo root): .\scripts\build_release.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Create .venv first: py -3 -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt pyinstaller"
}

& $Python -m pip install -q pyinstaller
& $Python -m PyInstaller scripts\nothing_here.spec --noconfirm --clean

$DistDir = Join-Path $Root "dist\NothingHere"
if (-not (Test-Path (Join-Path $DistDir "NothingHere.exe"))) {
    Write-Error "Build failed: NothingHere.exe not found in dist\NothingHere"
}

$Version = & $Python (Join-Path $Root "scripts\package_version.py")
if (-not $Version) {
    Write-Error "Could not read package version"
}
$ZipPath = Join-Path $Root "dist\NothingHere-$Version-win64.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $DistDir "*") -DestinationPath $ZipPath -Force

Write-Host ""
Write-Host "Done."
Write-Host "  Folder: dist\NothingHere\"
Write-Host "  Zip:    dist\NothingHere-$Version-win64.zip"
Write-Host ""
Write-Host "Test: run dist\NothingHere\NothingHere.exe (only one instance at a time)."

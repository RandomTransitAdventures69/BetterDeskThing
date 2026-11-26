$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "=== $Text ==="
}

Write-Step "Checking Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "python was not found on PATH. Install Python 3.10+ and try again."
}
& python -c "import sys; assert sys.version_info >= (3, 10), sys.version; print(sys.version)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.10+ is required."
}

Write-Step "Installing build dependencies"
& python -m pip install -r build-requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "Could not install build dependencies."
}

Write-Step "Cleaning old artifacts"
if (Test-Path -LiteralPath "build") {
    Remove-Item -Recurse -Force "build"
}
if (Test-Path -LiteralPath "dist\MyDeskThing") {
    Remove-Item -Recurse -Force "dist\MyDeskThing"
}
if (Test-Path -LiteralPath "dist\MyDeskThing.exe") {
    Remove-Item -Force "dist\MyDeskThing.exe"
}
if (-not (Test-Path -LiteralPath "dist")) {
    New-Item -ItemType Directory "dist" | Out-Null
}

Write-Step "Building onedir test build"
& python -m PyInstaller --noconfirm --clean MyDeskThing_onedir.spec
if ($LASTEXITCODE -ne 0) {
    throw "Onedir build failed."
}
if (-not (Test-Path -LiteralPath "dist\MyDeskThing\MyDeskThing.exe")) {
    throw "Onedir build did not produce dist\MyDeskThing\MyDeskThing.exe"
}

Write-Step "Building onefile release build"
& python -m PyInstaller --noconfirm --clean MyDeskThing.spec
if ($LASTEXITCODE -ne 0) {
    throw "Onefile build failed."
}
if (-not (Test-Path -LiteralPath "dist\MyDeskThing.exe")) {
    throw "Onefile build did not produce dist\MyDeskThing.exe"
}

Write-Step "Build complete"
Get-Item -LiteralPath "dist\MyDeskThing.exe" | Select-Object FullName, Length, LastWriteTime
Write-Host ""
Write-Host "Test it with:"
Write-Host "  .\dist\MyDeskThing.exe --status"
Write-Host "  .\dist\MyDeskThing.exe --self-test --port 8181"
Write-Host "  .\dist\MyDeskThing.exe"

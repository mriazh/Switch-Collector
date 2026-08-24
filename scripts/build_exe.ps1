param()

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location -LiteralPath $RepoRoot

$SpecFile = Join-Path $RepoRoot "switch_collector.spec"
$DistDir = Join-Path $RepoRoot "dist"
$ExpectedExeDir = Join-Path $DistDir "Switch-Collector"
$ExpectedExe = Join-Path $ExpectedExeDir "Switch-Collector.exe"
$ExpectedInternal = Join-Path $ExpectedExeDir "_internal"

function Get-PyInstaller {
    # Prefer a project virtual environment, then the active interpreter, then PATH.
    foreach ($VenvScripts in @(".venv\Scripts", ".venv312\Scripts", "venv\Scripts")) {
        $Candidate = Join-Path (Join-Path $RepoRoot $VenvScripts) "pyinstaller.exe"
        if (Test-Path -LiteralPath $Candidate) {
            return $Candidate
        }
    }

    $Found = Get-Command pyinstaller -ErrorAction SilentlyContinue
    if ($Found) {
        return $Found.Source
    }

    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Python) {
        $ModuleProbe = & $Python.Source -c "import PyInstaller, sys; print(PyInstaller.__file__)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ModuleProbe) {
            return $Python.Source
        }
    }

    return $null
}

$PyInstallerPath = Get-PyInstaller
if (-not $PyInstallerPath) {
    Write-Host "Error: pyinstaller is not available. Install it with: pip install pyinstaller" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $SpecFile)) {
    Write-Host "Error: switch_collector.spec is missing at $SpecFile." -ForegroundColor Red
    exit 1
}

foreach ($Stale in @("build", "dist")) {
    $StalePath = Join-Path $RepoRoot $Stale
    if (Test-Path $StalePath) {
        Write-Host "Cleaning stale $Stale directory..." -ForegroundColor Gray
        Remove-Item -Recurse -Force $StalePath
    }
}

Write-Host "Building Switch-Collector.exe from $SpecFile..." -ForegroundColor Cyan
Write-Host "Using PyInstaller: $PyInstallerPath" -ForegroundColor Gray

# Resolve the interpreter form so a plain python.exe also works.
if ($PyInstallerPath -like "*.exe") {
    & $PyInstallerPath -y $SpecFile
} else {
    & $PyInstallerPath -m PyInstaller -y $SpecFile
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $ExpectedExe)) {
    Write-Host "Error: Expected executable not found at $ExpectedExe." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $ExpectedInternal)) {
    Write-Host "Error: Expected runtime directory not found at $ExpectedInternal." -ForegroundColor Red
    exit 1
}

$InternalFileCount = @(Get-ChildItem -LiteralPath $ExpectedInternal -Recurse -File -Force).Count
$ExeSizeKB = [math]::Round((Get-Item -LiteralPath $ExpectedExe).Length / 1KB, 1)

Write-Host ""
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "  Executable : $ExpectedExe" -ForegroundColor Green
Write-Host "  Exe size   : $ExeSizeKB KB" -ForegroundColor Green
Write-Host "  _internal  : $InternalFileCount files" -ForegroundColor Green
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "Success! Build verified. Run .\scripts\package_portable.ps1 to bundle it." -ForegroundColor Green
exit 0

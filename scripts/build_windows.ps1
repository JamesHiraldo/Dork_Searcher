param(
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"

& $PythonCommand -m pip install -e ".[build]"
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }

& $PythonCommand -m PyInstaller --clean --noconfirm config\dork_searcher.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$executable = Resolve-Path -LiteralPath "dist\dork_searcher.exe"
$hash = Get-FileHash -LiteralPath $executable -Algorithm SHA256
$hash | Format-List
Write-Host "Built $executable" -ForegroundColor Green


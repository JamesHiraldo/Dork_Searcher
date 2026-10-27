param(
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"

& $PythonCommand -m pip install -e ".[build]"
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }
& $PythonCommand -m PyInstaller --clean --noconfirm --distpath Wayback_Atlas_App config\dork_searcher.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
& $PythonCommand -m pip wheel . --no-deps --no-build-isolation --wheel-dir Wayback_Atlas_App
if ($LASTEXITCODE -ne 0) { throw "Wheel build failed." }
$executable = Resolve-Path -LiteralPath "Wayback_Atlas_App\wayback_atlas.exe"
Get-FileHash -LiteralPath $executable -Algorithm SHA256 | Format-List
$releaseFiles = Get-ChildItem -LiteralPath "Wayback_Atlas_App" -File |
    Where-Object { $_.Extension -in @(".exe", ".whl") } |
    Sort-Object Name
$checksumLines = foreach ($releaseFile in $releaseFiles) {
    $digest = (Get-FileHash -LiteralPath $releaseFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$digest  $($releaseFile.Name)"
}
$checksumLines | Set-Content -LiteralPath "Wayback_Atlas_App\SHA256SUMS.txt" -Encoding ascii
Write-Host "Built $executable" -ForegroundColor Green


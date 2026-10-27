param(
    [string]$PythonCommand = "python",
    [string]$OutputDirectory = "dist"
)

$ErrorActionPreference = "Stop"

& $PythonCommand -m pip install -e ".[build]"
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }
& $PythonCommand -m PyInstaller --clean --noconfirm --distpath $OutputDirectory config\dork_searcher.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
& $PythonCommand -m pip wheel . --no-deps --no-build-isolation --wheel-dir $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw "Wheel build failed." }
$executable = Resolve-Path -LiteralPath (Join-Path $OutputDirectory "wayback_atlas.exe")
Get-FileHash -LiteralPath $executable -Algorithm SHA256 | Format-List
$atlasVersion = (& $PythonCommand -c "from src import __version__; print(__version__)").Trim()
if ($LASTEXITCODE -ne 0) { throw "Could not read application version." }
$releaseFiles = Get-Item -LiteralPath $executable,(Join-Path $OutputDirectory "wayback_atlas-$atlasVersion-py3-none-any.whl")
$checksumLines = foreach ($releaseFile in $releaseFiles) {
    $digest = (Get-FileHash -LiteralPath $releaseFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$digest  $($releaseFile.Name)"
}
$checksumLines | Set-Content -LiteralPath (Join-Path $OutputDirectory "SHA256SUMS.txt") -Encoding ascii
Write-Host "Built $executable" -ForegroundColor Green


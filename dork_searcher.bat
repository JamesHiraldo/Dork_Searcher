@echo off
setlocal
pushd "%~dp0"

where python >nul 2>nul
if not errorlevel 1 (
    python -m src.cli %*
    set "DORK_EXIT=%ERRORLEVEL%"
    popd
    exit /b %DORK_EXIT%
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m src.cli %*
    set "DORK_EXIT=%ERRORLEVEL%"
    popd
    exit /b %DORK_EXIT%
)

echo Python 3.10 or newer was not found on PATH.
popd
exit /b 1

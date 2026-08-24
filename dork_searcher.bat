@echo off
setlocal
pushd "%~dp0"

set "DORK_EXE=%CD%\Dork_Searcher_App\dork_searcher-2.0.0.exe"
if exist "%DORK_EXE%" goto run_exe

if exist "%CD%\.venv\Scripts\python.exe" (
    set DORK_PYTHON="%CD%\.venv\Scripts\python.exe"
    goto run_python
)

where python >nul 2>nul
if not errorlevel 1 (
    set "DORK_PYTHON=python"
    goto run_python
)
where py >nul 2>nul
if not errorlevel 1 (
    set "DORK_PYTHON=py -3"
    goto run_python
)

echo Dork Searcher could not find its packaged executable or Python 3.10+.
popd
exit /b 1

:run_exe
"%DORK_EXE%" %*
set "DORK_EXIT=%ERRORLEVEL%"
popd
exit /b %DORK_EXIT%

:run_python
%DORK_PYTHON% -c "import playwright" >nul 2>nul
if errorlevel 1 goto missing_dependencies
%DORK_PYTHON% -m src.cli %*
set "DORK_EXIT=%ERRORLEVEL%"
popd
exit /b %DORK_EXIT%

:missing_dependencies
echo Required Python packages are not installed in the selected interpreter.
echo Run: %DORK_PYTHON% -m pip install -e "."
echo Or launch: Dork_Searcher_App\dork_searcher-2.0.0.exe
popd
exit /b 1

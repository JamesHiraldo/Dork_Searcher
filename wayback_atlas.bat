@echo off
setlocal
pushd "%~dp0"
if exist "Wayback_Atlas_App\wayback_atlas.exe" goto run_exe
if exist ".venv-atlas\Scripts\python.exe" goto atlas_python
if exist ".venv\Scripts\python.exe" goto local_python
where python >nul 2>nul
if not errorlevel 1 goto system_python
where py >nul 2>nul
if not errorlevel 1 goto py_launcher
echo Python 3.10+ or the packaged Atlas executable is required.
popd
exit /b 1

:atlas_python
set ATLAS_PYTHON="%CD%\.venv-atlas\Scripts\python.exe"
goto run_python
:local_python
set ATLAS_PYTHON="%CD%\.venv\Scripts\python.exe"
goto run_python
:system_python
set "ATLAS_PYTHON=python"
goto run_python
:py_launcher
set "ATLAS_PYTHON=py -3"
goto run_python

:run_python
%ATLAS_PYTHON% -c "import rich,dns,httpx,requests" >nul 2>nul
if errorlevel 1 goto missing_dependencies
%ATLAS_PYTHON% -m src.cli %*
set "ATLAS_EXIT=%ERRORLEVEL%"
goto done

:run_exe
"%CD%\Wayback_Atlas_App\wayback_atlas.exe" %*
set "ATLAS_EXIT=%ERRORLEVEL%"
goto done

:missing_dependencies
echo The selected Python environment is incomplete or cannot start.
echo Recreate a portable project environment with: python -m venv .venv-atlas
echo Then run: .venv-atlas\Scripts\python.exe -m pip install -e "."
set "ATLAS_EXIT=1"

:done
popd
exit /b %ATLAS_EXIT%

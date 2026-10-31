@echo off
rem Compatibility launcher. Prefer wayback_recon.bat for new workflows.
call "%~dp0wayback_recon.bat" %*
exit /b %errorlevel%

@echo off
REM Dork Searcher - Command Line Wrapper
REM This batch file allows you to run dork_searcher from anywhere
REM Place this file in a folder that's in your PATH (e.g., C:\Windows\System32)

python "%~dp0src\dork_searcher.py" %*

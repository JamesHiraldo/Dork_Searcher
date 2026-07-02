@echo off
REM Dork Searcher - Command Line Wrapper
REM This batch file always runs the current CLI module from the repository root.
REM Place this file in a folder that's in your PATH (e.g., C:\Windows\System32)

pushd "%~dp0"
python -m src.cli %*
popd

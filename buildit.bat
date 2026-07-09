@echo off
REM Build PDF Studio. Run this INSIDE your activated venv.
REM Using "python -m PyInstaller" guarantees the venv's PyInstaller + packages
REM are used, not a global one that may be on PATH.
cd /d "%~dp0src"
python -m PyInstaller "PDF Studio.spec"
pause

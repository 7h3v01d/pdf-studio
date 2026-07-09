@echo off
REM Register PDF Studio as a handler for PDF/Word/Excel files (per-user).
cd /d "%~dp0src"
python register_file_types.py
pause

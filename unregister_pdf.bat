@echo off
REM Remove PDF Studio file associations (per-user).
cd /d "%~dp0src"
python register_file_types.py --unregister
pause

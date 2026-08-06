@echo off
setlocal EnableExtensions
REM Remove PDF Studio file associations (per-user).
cd /d "%~dp0"
call "tools\resolve_python311.bat" || goto :no_python
"%PDF_STUDIO_PYTHON_EXE%" src\register_file_types.py --unregister
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%

:no_python
echo [ERROR] A working Python 3.11 interpreter is required.
pause
exit /b 1

@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"

where py >nul 2>&1 || goto :no_python
py -3.11 -c "import sys; assert sys.version_info[:2] == (3, 11)" || goto :no_python

if not exist ".venv\Scripts\python.exe" (
  call :run py -3.11 -m venv .venv || goto :fail
)
call :run .venv\Scripts\python.exe -m pip install --upgrade pip || goto :fail
call :run .venv\Scripts\python.exe -m pip install -r requirements-build.txt || goto :fail
call :run .venv\Scripts\python.exe -m pip check || goto :fail
call :run .venv\Scripts\python.exe -m pytest ./tests -q || goto :fail

echo [OK] PDF Studio development environment is ready.
pause
exit /b 0

:run
%*
exit /b %ERRORLEVEL%

:no_python
echo [ERROR] Python 3.11 via the Windows py launcher is required.
goto :failed_exit

:fail
echo [ERROR] Setup failed.
:failed_exit
pause
exit /b 1

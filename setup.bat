@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"

call "tools\resolve_python311.bat" || goto :no_python
echo [INFO] Using Python: %PDF_STUDIO_PYTHON_EXE%

if exist ".venv\Scripts\python.exe" (
  call :run .venv\Scripts\python.exe -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" || goto :bad_venv
) else (
  call :run "%PDF_STUDIO_PYTHON_EXE%" -m venv .venv || goto :fail
)
call :run .venv\Scripts\python.exe -m pip install --upgrade pip || goto :fail
call :run .venv\Scripts\python.exe -m pip install -r requirements-build.txt || goto :fail
call :run .venv\Scripts\python.exe -m pip check || goto :fail
call :run .venv\Scripts\python.exe -m pytest ./tests -q || goto :fail

echo [OK] PDF Studio development environment is ready.
pause
exit /b 0

:run
echo ^> %*
%*
exit /b %ERRORLEVEL%

:bad_venv
echo [ERROR] The existing .venv is not based on Python 3.11.
echo [INFO] Remove the .venv folder and run setup.bat again.
goto :failed_exit

:no_python
echo [ERROR] A working Python 3.11 interpreter is required.
goto :failed_exit

:fail
echo [ERROR] Setup failed.
:failed_exit
pause
exit /b 1

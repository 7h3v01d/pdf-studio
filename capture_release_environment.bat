@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv is missing. Run setup.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip check || goto :fail
.venv\Scripts\python.exe -m pytest ./tests -v || goto :fail
.venv\Scripts\python.exe tools\capture_validated_environment.py || goto :fail
.venv\Scripts\python.exe tools\release_audit.py --require-lock || goto :fail
echo [OK] Exact versions captured from this passing Windows environment.
pause
exit /b 0
:fail
echo [ERROR] Environment capture failed.
pause
exit /b 1

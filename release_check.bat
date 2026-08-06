@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv is missing.
  pause
  exit /b 1
)
.venv\Scripts\python.exe tools\release_audit.py --public-release --require-lock
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo Public release remains blocked. See the failures above.
pause
exit /b %RC%

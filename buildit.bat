@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv is missing. Run setup.bat first.
  pause
  exit /b 1
)

call :run .venv\Scripts\python.exe -m pip check || goto :fail
call :run .venv\Scripts\python.exe tools\clean_release_tree.py || goto :fail
call :run .venv\Scripts\python.exe -m pytest ./tests -v || goto :fail
call :run .venv\Scripts\python.exe tools\capture_validated_environment.py || goto :fail
call :run .venv\Scripts\python.exe tools\clean_release_tree.py || goto :fail
call :run .venv\Scripts\python.exe tools\release_audit.py --require-lock || goto :fail
call :run .venv\Scripts\python.exe tools\generate_release_manifest.py --context internal-build || goto :fail

pushd src
call :run ..\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm "PDF Studio.spec" || (popd & goto :fail)
popd
call :run .venv\Scripts\python.exe tools\finalize_build.py || goto :fail

echo [OK] Internal build complete: src\dist\PDF Studio.exe
pause
exit /b 0

:run
echo ^> %*
%*
exit /b %ERRORLEVEL%

:fail
echo [ERROR] Build stopped.
pause
exit /b 1

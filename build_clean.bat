@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"

echo ============================================================
echo  PDF Studio - Clean Internal Build
echo ============================================================
echo.

where py >nul 2>&1 || goto :no_python
py -3.11 -c "import sys; assert sys.version_info[:2] == (3, 11)" || goto :no_python

if exist ".buildenv" rmdir /s /q ".buildenv" || goto :fail
if exist "src\build" rmdir /s /q "src\build" || goto :fail
if exist "src\dist" rmdir /s /q "src\dist" || goto :fail

call :run py -3.11 -m venv .buildenv || goto :fail
call :run .buildenv\Scripts\python.exe -m pip install --upgrade pip || goto :fail
call :run .buildenv\Scripts\python.exe -m pip install -r requirements-build.txt || goto :fail
call :run .buildenv\Scripts\python.exe -m pip check || goto :fail
call :run .buildenv\Scripts\python.exe -m pytest ./tests -v || goto :fail
call :run .buildenv\Scripts\python.exe tools\capture_validated_environment.py || goto :fail
if exist ".pytest_cache" rmdir /s /q ".pytest_cache" || goto :fail
call :run .buildenv\Scripts\python.exe tools\release_audit.py --require-lock || goto :fail
call :run .buildenv\Scripts\python.exe tools\generate_release_manifest.py --context internal-build || goto :fail

pushd src
call :run ..\.buildenv\Scripts\python.exe -m PyInstaller --clean --noconfirm "PDF Studio.spec" || (popd & goto :fail)
popd

call :run .buildenv\Scripts\python.exe tools\finalize_build.py || goto :fail

echo.
echo [OK] Internal build complete.
echo      Executable: src\dist\PDF Studio.exe
echo      Public distribution remains blocked by release\release_policy.json.
pause
exit /b 0

:run
echo ^> %*
%*
exit /b %ERRORLEVEL%

:no_python
echo [ERROR] Python 3.11 via the Windows py launcher is required.
goto :failed_exit

:fail
echo.
echo [ERROR] Build stopped. No success is being reported.
:failed_exit
pause
exit /b 1

@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"

if not exist ".venv\Scripts\python.exe" goto :missing
.venv\Scripts\python.exe tools\release_audit.py --public-release --require-lock || goto :blocked
.venv\Scripts\python.exe tools\verify_wheelhouse.py || goto :fail
call "tools\resolve_python311.bat" || goto :no_python
echo [INFO] Using Python: %PDF_STUDIO_PYTHON_EXE%

if exist ".releaseenv" rmdir /s /q ".releaseenv" || goto :fail
if exist "src\build" rmdir /s /q "src\build" || goto :fail
if exist "src\dist" rmdir /s /q "src\dist" || goto :fail
"%PDF_STUDIO_PYTHON_EXE%" -m venv .releaseenv || goto :fail
.releaseenv\Scripts\python.exe -m pip install --no-index --find-links=release\wheelhouse -r requirements-validated.lock -r requirements-build.lock || goto :fail
.releaseenv\Scripts\python.exe -m pip check || goto :fail
.releaseenv\Scripts\python.exe -m pytest ./tests -v || goto :fail
.releaseenv\Scripts\python.exe tools\generate_release_manifest.py --context public-release || goto :fail
pushd src
..\.releaseenv\Scripts\python.exe -m PyInstaller --clean --noconfirm "PDF Studio.spec" || (popd & goto :fail)
popd
.releaseenv\Scripts\python.exe tools\finalize_build.py || goto :fail
echo [OK] Release-approved build complete.
pause
exit /b 0

:blocked
echo [BLOCKED] Release policy or licensing gates are not satisfied.
pause
exit /b 1

:missing
echo [ERROR] .venv is missing. Run setup.bat first.
goto :failed_exit

:no_python
echo [ERROR] A working Python 3.11 interpreter is required.
goto :failed_exit

:fail
echo [ERROR] Release build failed.
:failed_exit
pause
exit /b 1

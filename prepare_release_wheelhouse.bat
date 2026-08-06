@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "requirements-validated.lock" goto :missing
if not exist "requirements-build.lock" goto :missing
if not exist ".venv\Scripts\python.exe" goto :missing
if exist "release\wheelhouse" rmdir /s /q "release\wheelhouse" || goto :fail
mkdir "release\wheelhouse" || goto :fail
.venv\Scripts\python.exe -m pip download --only-binary=:all: --dest release\wheelhouse -r requirements-validated.lock -r requirements-build.lock || goto :fail
.venv\Scripts\python.exe tools\hash_wheelhouse.py || goto :fail
.venv\Scripts\python.exe tools\verify_wheelhouse.py || goto :fail
echo [OK] Offline wheelhouse prepared and hashed.
pause
exit /b 0
:missing
echo [ERROR] Capture the validated environment first and ensure .venv exists.
:fail
pause
exit /b 1

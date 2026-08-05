@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv was not found.
    echo Create it with: python -m venv .venv
    echo Then install test requirements with:
    echo   .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m pytest tests -v
set "TEST_EXIT=%ERRORLEVEL%"

echo.
if "%TEST_EXIT%"=="0" (
    echo All tests passed.
) else (
    echo Tests failed with exit code %TEST_EXIT%.
)

pause
exit /b %TEST_EXIT%

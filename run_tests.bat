@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv was not found.
    echo Create it by running setup.bat.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m pytest tests -v
set "TEST_EXIT=%ERRORLEVEL%"

.venv\Scripts\python.exe tools\clean_release_tree.py
set "CLEAN_EXIT=%ERRORLEVEL%"

if not "%CLEAN_EXIT%"=="0" (
    echo.
    echo Generated-tree cleanup failed with exit code %CLEAN_EXIT%.
    set "FINAL_EXIT=%CLEAN_EXIT%"
) else (
    set "FINAL_EXIT=%TEST_EXIT%"
)

echo.
if "%FINAL_EXIT%"=="0" (
    echo All tests passed.
) else (
    echo Tests or cleanup failed with exit code %FINAL_EXIT%.
)

pause
exit /b %FINAL_EXIT%

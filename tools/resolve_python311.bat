@echo off
setlocal EnableExtensions DisableDelayedExpansion

REM Resolve a real Python 3.11 interpreter without requiring the optional
REM Windows py launcher. The resolved full path is returned in the caller's
REM PDF_STUDIO_PYTHON_EXE environment variable.

set "PROJECT_ROOT=%~dp0.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"
set "RESOLVED="

REM Explicit operator override. Use a full path to python.exe.
if defined PDF_STUDIO_PYTHON call :try_candidate "%PDF_STUDIO_PYTHON%"
if defined RESOLVED goto :found

REM Prefer the project's validated virtual environment when it exists.
call :try_candidate "%PROJECT_ROOT%\.venv\Scripts\python.exe"
if defined RESOLVED goto :found

REM Search PATH. Invalid Windows Store aliases are rejected by the version test.
for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined RESOLVED call :try_candidate "%%~fP"
if defined RESOLVED goto :found

REM Common CPython 3.11 installation locations.
call :try_candidate "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if defined RESOLVED goto :found
call :try_candidate "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
if defined RESOLVED goto :found
call :try_candidate "%ProgramFiles%\Python311\python.exe"
if defined RESOLVED goto :found
call :try_candidate "%ProgramFiles(x86)%\Python311\python.exe"
if defined RESOLVED goto :found
call :try_candidate "C:\Python311\python.exe"
if defined RESOLVED goto :found

echo [ERROR] Python 3.11 could not be located.
echo [INFO] The Windows py launcher is NOT required.
echo [INFO] Set PDF_STUDIO_PYTHON to the full path of your Python 3.11 python.exe,
echo        then run the command again. Example:
echo        set "PDF_STUDIO_PYTHON=C:\Users\YourName\AppData\Local\Programs\Python\Python311\python.exe"
endlocal
exit /b 1

:try_candidate
set "CANDIDATE=%~1"
if not defined CANDIDATE exit /b 1
if not exist "%CANDIDATE%" exit /b 1
"%CANDIDATE%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
for %%P in ("%CANDIDATE%") do set "RESOLVED=%%~fP"
exit /b 0

:found
endlocal & set "PDF_STUDIO_PYTHON_EXE=%RESOLVED%"
exit /b 0

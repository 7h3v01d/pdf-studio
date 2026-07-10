@echo off
REM Foolproof clean build: creates a fresh, isolated venv with only the
REM packages PDF Studio needs, then builds the .exe. Avoids pulling in unrelated
REM global packages (PyQt5, pygame, scipy, editable projects, etc.).
setlocal
cd /d "%~dp0"

echo Creating clean build venv (.buildenv)...
py -3.11 -m venv .buildenv || python -m venv .buildenv
call .buildenv\Scripts\activate.bat

echo Installing build + runtime dependencies...
python -m pip install --upgrade pip
python -m pip install pyinstaller
python -m pip install -r requirements.txt

echo Building...
cd src
python -m PyInstaller "PDF Studio.spec"

echo.
echo Done. The exe is in src\dist\.
pause

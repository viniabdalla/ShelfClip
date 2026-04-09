@echo off
cd /d "%~dp0"
set PY_CMD=py

where %PY_CMD% >nul 2>nul
if errorlevel 1 set PY_CMD=python

echo Installing PyInstaller...
%PY_CMD% -m pip install pyinstaller
echo.
echo Generating icon...
%PY_CMD% generate_icon.py
echo.
echo Building ShelfClip.exe...
%PY_CMD% -m PyInstaller --onefile --windowed --name ShelfClip --icon=icon.ico --clean main.py
echo.
echo Done! Check the dist folder.
pause

@echo off
cd /d "%~dp0"
mkdir installer_output 2>nul
echo Building installer...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
echo.
if exist installer_output\ShelfClip_Setup.exe (
    echo SUCCESS! Installer created at:
    echo %~dp0installer_output\ShelfClip_Setup.exe
) else (
    echo FAILED - check errors above
)
pause

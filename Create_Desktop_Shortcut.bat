@echo off
cd /d "%~dp0"
if exist "%~dp0AetherFTP.exe" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1" -ExePath "%~dp0AetherFTP.exe"
) else if exist "%~dp0dist\AetherFTP.exe" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1" -ExePath "%~dp0dist\AetherFTP.exe"
) else (
    echo AetherFTP.exe not found. Extract the release ZIP or run Install_AetherFTP.bat.
    pause
    exit /b 1
)
if errorlevel 1 (
    pause
    exit /b 1
)
echo Desktop shortcut created.

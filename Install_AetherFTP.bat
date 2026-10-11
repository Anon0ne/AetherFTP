@echo off
setlocal
cd /d "%~dp0"
title AetherFTP Windows Installer
where powershell.exe >nul 2>&1
if errorlevel 1 (
 echo ERROR: Windows PowerShell was not found.
 pause
 exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Installation failed with exit code %RESULT%.
pause
exit /b %RESULT%

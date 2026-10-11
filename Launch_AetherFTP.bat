@echo off
cd /d "%~dp0"
if exist "dist\AetherFTP.exe" (start "" "%~dp0dist\AetherFTP.exe" & exit /b 0)
if exist ".venv\Scripts\pythonw.exe" (start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0aetherftp.py" & exit /b 0)
echo AetherFTP not installed. Run Install_AetherFTP.bat first.
pause
exit /b 1

# AetherFTP v0.3 — Windows build kit

Double-click **Install_AetherFTP.bat**. It checks for Python 3.10+, installs Python 3.12 using winget if necessary, creates an isolated environment, installs requirements, builds `dist\AetherFTP.exe` using PyInstaller, and creates Desktop and home-directory shortcuts. Internet is needed for initial dependency installation. **Launch_AetherFTP.bat** starts the installed app.

Server Book stores server profiles in `%APPDATA%\AetherFTP\servers.json`; saved passwords use Windows DPAPI. Never share an exported server-book database assuming credentials are portable. Plain FTP is not encrypted; use SFTP or FTPS where possible.

This archive contains source and Windows build scripts, **not a precompiled Windows executable**. The Windows build and runtime require validation on a Windows computer.

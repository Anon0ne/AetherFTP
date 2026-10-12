# Windows installation and updates

[Back to README](../README.md) · [Usage](USAGE.md)

## Ready-to-run release

1. Open [GitHub Releases](https://github.com/Anon0ne/AetherFTP/releases) and download `AetherFTP-Windows-v0.1.1b.zip` and optionally `SHA256SUMS.txt`.
2. Extract the entire ZIP to a permanent folder. Do not run the EXE directly inside the ZIP.
3. Run `AetherFTP.exe`. Python and a separate Qt installation are not required.
4. Run `Create_Desktop_Shortcut.bat` to create the Windows Desktop shortcut. Its target and icon come from the EXE in this folder.

The executable is not currently code-signed. Windows may show an unknown-publisher prompt. Verify the download source and checksum before deciding whether to run it; do not disable Windows security globally.

To verify the ZIP in PowerShell:

```powershell
Get-FileHash -LiteralPath .\AetherFTP-Windows-v0.1.1b.zip -Algorithm SHA256
```

Compare the result with the matching ZIP entry in `SHA256SUMS.txt` from the same release. GitHub also provides SHA-256 asset digests. No administrator access is required for the portable application or per-user shortcut.

## Updating

Finish or stop transfers and close any remote editing sessions. Exit the old version before replacing files. Extract the new release into a new permanent folder, launch it, then rerun its shortcut helper. Once the new version works and no process uses the old folder, remove the old executable folder.

User settings and profiles remain under `%APPDATA%\AetherFTP`, outside the executable folder. DPAPI passwords remain tied to the same Windows user. Do not put application-data files into a release ZIP. Back up private data privately before changing versions; never upload it to GitHub.

## Installing from source

Download the GitHub source archive or clone the repository, then extract/open it. This is different from the ready-to-run Windows ZIP.

Run `Install_AetherFTP.bat`. It creates `.venv`, installs `requirements.txt`, runs automated tests, builds `dist\AetherFTP.exe`, checks packaged startup and creates Desktop/user-home shortcuts. It can install Python 3.12 through winget if Python 3.10+ is unavailable. Internet access and sufficient free disk space are needed for setup and building; Python installation may require Windows approval.

Run `Launch_AetherFTP.bat` afterward. It prefers `dist\AetherFTP.exe`, otherwise launches source using the existing virtual environment. Manual commands are in [Building](BUILDING.md).

## Removing the app

Close the app, delete its extracted folder and remove its shortcuts. This leaves user data intact. To remove user data, separately delete `%APPDATA%\AetherFTP` and the saved `AetherFTP/<profile-id>` generic credentials in Windows Credential Manager after confirming they are no longer needed. Temporary editing files may contain remote file contents.

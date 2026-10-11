# AetherFTP 0.4.0

A modern Windows FTP/FTPS/SFTP client inspired by Marauder V8 styling.
Project builder: **Anon0ne**.

## Install and launch

Run **Install_AetherFTP.bat** to create a Python environment, install dependencies, run tests, and build `dist\AetherFTP.exe`. Run **Launch_AetherFTP.bat** to launch. Python 3.10+ is supported; the installer can install Python 3.12 through winget. Initial setup requires internet access.

For development:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe aetherftp.py
```

## Connections and transfers

Each connection tab has independent credentials, paths and a sequential transfer queue. Select multiple files to upload or download. Drop files from Explorer onto the remote file pane to upload. Directory transfers, queue cancellation, persisted queues, and internal pane-to-pane drag-and-drop are future work.

Enable **Resume partial files** only when the destination contains the exact initial bytes of the same source file. Resume verifies sizes but does not verify file identity or hashes. Upload resume requires an existing remote file. FTP servers must support SIZE and REST; unsupported resume fails without a fallback overwrite. Failed transfers remain visible and can be requeued using the file selection controls. Finish queued work before disconnecting or closing a tab.

Use SFTP or FTPS whenever possible. FTPS validates certificates using system trust. SFTP rejects unknown host keys; enroll a verified key in `%USERPROFILE%\.ssh\known_hosts` outside the application before connecting. Plain FTP transmits credentials and data without encryption.

## Server Book and privacy

Profiles are stored in `%APPDATA%\AetherFTP\servers.json`. Choose no password storage, Windows Credential Manager (generic credentials under `AetherFTP/<profile-id>`), or encrypted DPAPI storage. DPAPI credentials belong to the current Windows user. Existing v0.3 profiles remain readable. Blank password fields retain an existing saved password when editing; choosing **Do not save** removes it.

Rotating JSON logs live in `%APPDATA%\AetherFTP\logs`. Logs record event and exception types without raw server responses, credentials or server addresses. GUI error messages intentionally show exception types; verify connection settings and permissions when troubleshooting.

Never commit profiles, passwords, tokens, private keys or generated builds. Use feature branches and run tests before commits. `.github/workflows/windows.yml` validates Windows tests, builds the EXE, verifies packaged startup, and uploads a build artifact. Build artifacts are available from successful Actions runs; create GitHub releases only after the corresponding commit's build is verified. CI does not publish releases automatically.

## Validation limits

Protocol behavior is covered by isolated adapter tests. Real-server interoperability, disconnect recovery, and visual checks at enlarged system fonts require additional testing before a public release. See `CHANGELOG.md` for version history.

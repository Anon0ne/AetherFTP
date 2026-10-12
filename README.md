# AetherFTP 0.6.0

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

Each connection tab has independent credentials and paths. A shared scheduler controls concurrent transfers across tabs. File panes expand with the window. Use **Transfer activity** at the bottom to show or hide the queue and event log. Select multiple files to upload or download. Drag selected files or folders from the local pane, or drop them from Explorer, onto the remote pane to upload into its current directory. Folder uploads preserve their name, nested contents and empty directories; each file has its own queue progress bar. Folder scanning happens in the background, queue rows are added incrementally, and the remote pane refreshes once after the batch. Links and junctions are skipped, with a count in the Event Log. Recursive downloads, queue cancellation and persisted queues are future work.

Enable **Resume partial files** only when the destination contains the exact initial bytes of the same source file. Resume verifies sizes but does not verify file identity or hashes. Upload resume requires an existing remote file. FTP servers must support SIZE and REST; unsupported resume fails without a fallback overwrite. Failed transfers remain visible and can be requeued using the file selection controls. Finish queued work before disconnecting or closing a tab.

Use SFTP or FTPS whenever possible. FTPS validates certificates using system trust. SFTP rejects unknown host keys; enroll a verified key in `%USERPROFILE%\.ssh\known_hosts` outside the application before connecting. Plain FTP transmits credentials and data without encryption.

## Server Book and privacy

Profiles are stored in `%APPDATA%\AetherFTP\servers.json`. Choose no password storage, Windows Credential Manager (generic credentials under `AetherFTP/<profile-id>`), or encrypted DPAPI storage. DPAPI credentials belong to the current Windows user. Existing v0.3 profiles remain readable. Blank password fields retain an existing saved password when editing; choosing **Do not save** removes it.

Rotating JSON logs live in `%APPDATA%\AetherFTP\logs`. Logs record connection steps, operation statuses, transfer timings and redacted server error replies. Known connection hostnames, usernames and passwords are redacted from exception messages. Review logs before sharing; unexpected server replies can contain other private information. GUI error messages intentionally show exception types; verify connection settings and permissions when troubleshooting.

Never commit profiles, passwords, tokens, private keys or generated builds. Use feature branches and run tests before commits. `.github/workflows/windows.yml` validates Windows tests, builds the EXE, verifies packaged startup, and uploads a build artifact. Build artifacts are available from successful Actions runs; create GitHub releases only after the corresponding commit's build is verified. CI does not publish releases automatically.

## Validation limits

Protocol behavior is covered by isolated adapter tests. Real-server interoperability, disconnect recovery, and visual checks at enlarged system fonts require additional testing before a public release. See `CHANGELOG.md` for version history.

## Transfer progress and timing

Queue rows show a purple/cyan bar with centered percentage and live transfer rate in decimal MB/s (1 MB = 1,000,000 bytes). The queue opens when transfers are added; it can still be collapsed. Completed rows show the average transfer rate. Unknown total sizes display a dash instead of a percentage until completion. Resume rates count only newly transferred bytes.

The Event log tab shows each file’s start/completion/failure time, elapsed seconds, transferred bytes and average MB/s. Its visible history keeps the latest 1,000 lines; persistent rotating logs continue separately. Transfer timing records in persistent JSON logs contain UTC timestamps and transfer IDs without filenames, paths, hosts or credentials. Connection diagnostics can include redacted server error replies. The row tooltip contains the matching transfer ID. Timing excludes waiting in the queue and includes protocol setup for that transfer. Failed transfers retain their partial progress and timing record.

## FTPES connection URLs

FTPES uses explicit TLS: AUTH TLS before login and PROT P for encrypted data transfers. The legacy FTPS option uses the same explicit-TLS behavior; implicit FTPS is not supported. Certificate and hostname verification remain enabled.

Paste a URL such as `ftpes://sampleuser@example.invalid:2990/files/sample.txt` into Host / IP and leave the field. AetherFTP fills the protocol, host, username and port, clears the previous password, and sets the remote directory to `/files`. Enter the password separately and click Connect. The named file is selected in the remote pane; use Download to transfer it. Directory URLs should end with `/`. No connection URL is automatically saved to the Server Book.

## Connection diagnostics

The Event log tab records TCP connection, AUTH TLS and certificate verification, negotiated TLS version, login, PROT P, binary mode, directory-listing status and protected data handshakes. Errors open this tab automatically and include the failing operation plus the server reply or SSL message, with known credentials redacted. FTPES/FTPS data sockets reuse the control connection’s TLS session; certificate checks remain enabled.

Session reuse solves compatibility with servers that require it, but does not bypass certificate problems, authentication failures or blocked passive data ports. Python’s SSLSession API has limitations with TLS 1.3; the negotiated TLS version and exact redacted handshake error help diagnose remaining interoperability problems.

## Folder uploads and server write errors

Select a folder and click Upload, or drag it from the local pane/Explorer onto the remote pane. Confirm the current remote destination. AetherFTP queues directory creation first, then contained files with individual progress and timings. Existing directories are accepted only after verifying they are directories. Existing matching files can be replaced after the batch confirmation; unrelated remote files are retained. Resume remains opt-in and requires existing matching partial files; leave it off for a new folder upload.

The Event Log shows the remote destination for every attempted transfer. A `553 Could not create file` response is a server rejection of file creation, separate from folder selection: check the chosen remote directory, account write permissions, quota/free space and filename conflicts. The app keeps creation and transfer failures visible.

## Network settings

Open **Menu → Settings** to choose concurrent uploads and concurrent downloads independently (1–8 each). Limits apply across all tabs in that application window. Default limits are one upload and one download. Each worker uses its own reusable FTP/FTPES/FTPS/SFTP connection; browsing retains a separate connection per tab. The server must permit these simultaneous logins. Conflicting writes to the same destination are serialized. Folder files wait until their remote directory creation jobs have finished.

Set upload and download bandwidth separately in decimal MB/s; **Unlimited** (0) disables that limit. Each directional limit is shared across all transfers in that window. Pacing occurs at transfer blocks, so short buffering bursts are possible. Bandwidth changes apply immediately. Increasing concurrency starts additional eligible work; lowering it lets existing transfers finish before applying the lower limit to new files.

Preferences are stored without credentials in `%APPDATA%\AetherFTP\settings.json` and restored at startup. **Menu → Exit** uses the existing queue-active guard.

# AetherFTP 0.1.1b

A modern Windows FTP/FTPS/SFTP client inspired by Marauder V8 styling.
Project builder: **Anon0ne**.

## Install and launch

Download the Windows ZIP from [GitHub Releases](https://github.com/Anon0ne/AetherFTP/releases), extract it into a permanent folder, and run **AetherFTP.exe**. Run **Create_Desktop_Shortcut.bat** to add an AetherFTP shortcut to your Windows Desktop with the new purple/cyan icon. Keep the extracted folder in place so the shortcut continues to work.

Run **Install_AetherFTP.bat** to create a Python environment, install dependencies, run tests, and build `dist\AetherFTP.exe`. Run **Launch_AetherFTP.bat** to launch. Python 3.10+ is supported; the installer can install Python 3.12 through winget. Initial setup requires internet access.

For development:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe aetherftp.py
```

## Connections and transfers

Each connection tab has independent credentials and paths. A shared scheduler controls concurrent transfers across tabs. File panes expand with the window. Use **Transfer activity** at the bottom to show or hide the queue and event log. Select multiple files to upload or download. Drag selected files or folders from the local pane, or drop them from Explorer, onto the remote pane to upload into its current directory. Folder uploads preserve their name, nested contents and empty directories; each file has its own queue progress bar. Folder scanning happens in the background, queue rows are added incrementally, and the remote pane refreshes once after the batch. Links and junctions are skipped, with a count in the Event Log. Use **Menu > Pause transfers** to pause transfers and **Resume transfers** to continue. **Stop transfers** cancels queued work, interrupts active transfer connections and stops folder scanning. Partial files remain available for a later resumed transfer. Reconnect before queuing new work after Stop. Closing with pending operations offers **Stop and exit**, then closes when workers finish; connection setup can take up to its timeout. Recursive downloads and persisted queues are future work.

Enable **Resume partial files** only when the destination contains the exact initial bytes of the same source file. Resume verifies sizes but does not verify file identity or hashes. Upload resume requires an existing remote file. FTP servers must support SIZE and REST; unsupported resume fails without a fallback overwrite. Failed transfers remain visible and can be requeued using the file selection controls. Finish queued work before disconnecting or closing a tab.

Use SFTP or FTPS whenever possible. FTPS validates certificates using system trust. SFTP rejects unknown host keys; enroll a verified key in `%USERPROFILE%\.ssh\known_hosts` outside the application before connecting. Plain FTP transmits credentials and data without encryption.

## Server Book and privacy

Profiles are stored in `%APPDATA%\AetherFTP\servers.json`. Choose no password storage, Windows Credential Manager (generic credentials under `AetherFTP/<profile-id>`), or encrypted DPAPI storage. DPAPI credentials belong to the current Windows user. Existing v0.3 profiles remain readable. Blank password fields retain an existing saved password when editing; choosing **Do not save** removes it.

Rotating JSON logs live in `%APPDATA%\AetherFTP\logs`. Logs record connection steps, operation statuses, transfer timings and redacted server error replies. Known connection hostnames, usernames and passwords are redacted from exception messages. Review logs before sharing; unexpected server replies can contain other private information. GUI error messages intentionally show exception types; verify connection settings and permissions when troubleshooting.

Never commit profiles, passwords, tokens, private keys or generated builds. Use feature branches and run tests before commits. `.github/workflows/windows.yml` validates Windows tests, builds the EXE, verifies packaged startup, and uploads a build artifact. Build artifacts are available from successful Actions runs; create GitHub releases only after the corresponding commit's build is verified. CI does not publish releases automatically.

## Validation limits

Protocol behavior is covered by isolated adapter tests. Automated tests isolate protocol adapters; broader real-server interoperability, disconnect recovery, and enlarged-font checks remain ongoing. See `CHANGELOG.md` for version history.

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

## Adjustable activity panel

Open **Transfer activity**, then drag the divider above it up or down. Queue and Event Log share the panel. The entire bottom section is capped at 35% of the file workspace, leaving the file lists usable. Collapsing and reopening it retains its height within the current window limits.

Transfer connections are reused during active batches and closed when the queue drains. Each connected tab retains its browsing connection. Server limits apply to all clients from your IP, so lower concurrency if the server returns 421. A TLS directory-listing failure triggers one reconnect attempt; certificate verification errors are never bypassed.

See [ROADMAP.md](ROADMAP.md) for proposed features.

## Filename filters

**Menu → Filename filters** sets include/exclude glob patterns for the current tab. Separate patterns with semicolons. For example, include `*.txt; *.zip`, or exclude `build; __pycache__; *.pyc`. Matching is case-insensitive. Both file panes hide excluded entries, and recursive upload planning prunes excluded folders and files. Include patterns select files while keeping directories navigable; exclusion rules can also hide/prune directories. Filters reset when the tab is closed.

## Paired bookmarks and synchronized browsing

Connect, choose your local and remote folders, then open **Menu → Paired bookmarks** to save the pair under a name. Bookmarks are scoped to server/protocol/username and stored privately in `%APPDATA%\AetherFTP\bookmarks.json`; passwords are never stored in bookmarks. Open restores both paths after the remote listing succeeds; Delete removes a bookmark.

Enable **Menu → Synchronized browsing** at the current folder pair. Navigating either pane maps the relative path to the other pane. The matching local folder must exist and the remote listing must succeed before both panes change. Navigation outside the root pair is rejected; disable synchronization to choose new roots. Opening a bookmark while synchronized replaces the root pair. This feature navigates folders; it does not copy or delete files.

## Remote editing

Select one remote file and choose **Menu → Edit selected remote file**. AetherFTP downloads a temporary local copy through the transfer queue, then opens it explicitly in Windows Notepad. Saving the file triggers an upload confirmation once the tab is idle. Declining leaves the local copy available; **Menu → Remote editing sessions → Upload changes** retries manually. Reopen editor opens the same local copy.

An edited upload uses a stable snapshot, downloads the current server copy and compares its SHA-256 digest with the original download. If they differ, it refuses to overwrite the server file; stop the editing session and download a new copy to reconcile changes. FTP/SFTP cannot guarantee an atomic compare-and-write, so a server change after the check can still race with the upload. The verification download adds network traffic and respects the download bandwidth cap. Edited uploads never resume, even if the general Resume option is enabled.

Close Notepad and use **Remote editing sessions → Stop editing** to discard the temporary copy and finish the session. Active editing sessions prevent tab closure, exit, disconnect and reconnection to a different server, so local changes cannot be discarded silently or uploaded to a different server. Temporary files contain the edited content and remain under the user's application-data editing directory until the session is stopped. A crash may leave copies there for manual recovery/cleanup. Bookmarks and editing contents must not be committed or shared with diagnostic logs.

## Windows compatibility folders

AetherFTP resolves the current Windows user's `My Documents` compatibility junction to its actual target when browsing locally, including typed paths and bookmarked paths. The local path box shows the destination after opening it. Windows access controls remain unchanged, and permission errors on the destination are still respected. Recursive uploads continue to skip links/junctions; open the destination and select its real files/folders to transfer them.

## Remote right-click actions

Right-click in the server pane while connected to create a **New file** (empty), create a **New folder**, or **Refresh**. Right-click one selected file and choose **Edit in Notepad** to use the confirmed remote-editing workflow. New names cannot contain path separators or Windows-reserved characters. New SFTP files use exclusive creation; FTP creation checks the server listing first and rejects existing names. FTP does not provide an atomic exclusive-create operation, so avoid simultaneous creation of the same filename by other clients.

## Application icon

The approved folder/server artwork and opposing transfer arrows use AetherFTP's purple/cyan palette. Source artwork, Windows ICO sizes and the design prompt are in `assets/`. `tools/build_icon.py` converts the PNG to a multi-size ICO using Qt. BAT installation and GitHub Actions embed the icon and package it for the window/taskbar.

# Changelog

## Unreleased

- Resolve the current user's legacy My Documents junction to its real target for local navigation, without changing filesystem permissions.

- Keep local folders readable when a child entry is missing or inaccessible; retain the current folder on navigation failure.

- Begin next-release file tools: per-tab filename include/exclude filters, with excluded folders pruned from upload plans.
- Add private server-scoped paired bookmarks with save, open and delete controls.
- Add synchronized browsing rooted at the current local/remote pair; update both panes only after a successful listing.
- Add Notepad remote editing sessions, save detection, confirmed re-uploads, snapshot transfers and content conflict checks.
- Use the normal transfer queue, directional bandwidth limits and destination locks for editing transfers; block reconnect/exit until editing sessions are stopped.

## 0.1.0b - 2026-10-12

First public beta. Earlier 0.3-0.6 versions below were local development milestones.

- Add a draggable divider for the Queue/Event Log panel, capped at 35% of the file workspace height.
- Retain the chosen height when collapsing and reopening transfer activity.
- Close transfer connections when the queue drains, preserving reuse during active batches.
- Retry a failed TLS directory listing once on a fresh browsing connection; certificate failures remain fatal.
- Start a fresh visible queue for new work after the previous batch is fully idle, retaining timing/log history.

## 0.6.0 — 2026-10-12

- Add a Menu drop-down with Settings and Exit.
- Persist separate upload/download concurrency limits (1–8) and aggregate MB/s bandwidth limits per Windows user.
- Share transfer limits across tabs and use an independent, reusable connection for each active worker.
- Apply bandwidth changes immediately; lower concurrency after current files finish.
- Preserve folder creation dependencies, per-file progress, failure accounting and one final folder refresh.
- Serialize conflicting destination writes and retain responsive queue batching.


## 0.5.1 — 2026-10-12

- Build folder upload queues incrementally with bounded UI work per tick.
- Limit event processing per tick so progress/log backlogs cannot monopolize the GUI.
- Refresh remote files once after a folder batch instead of once per uploaded file.
- Bound the visible Event Log to 1,000 lines while retaining persistent logging.
- Add a 1,000-file queue stress test that checks GUI timer responsiveness and a single final refresh.


## 0.5.0 — 2026-10-11

- Upload folders recursively, preserving nested paths and empty directories.
- Drag files and folders from the local pane or Explorer into the server pane.
- Plan uploads in the background and queue remote directory creation before per-file transfers.
- Verify existing remote directories instead of hiding permission failures.
- Skip symlinks and junctions and exclude the parent-navigation row from uploads.
- Show exact remote transfer destinations in the Event Log for debugging server write errors.


## 0.4.4 — 2026-10-11

- Reuse the authenticated TLS control session for protected FTPES/FTPS data connections.
- Close a data socket if its TLS handshake fails.
- Log connection steps, negotiated TLS version, operation statuses, and data handshake steps.
- Display server error replies and SSL details with known credentials redacted; open Event log on failure.


## 0.4.3 — 2026-10-11

- Add an explicit FTPES protocol option and retain FTPS as an explicit-TLS alias.
- Negotiate AUTH TLS before login and protect FTP data connections with PROT P.
- Accept connection URLs in the host field with custom ports, users and remote paths.
- Open a file URL’s parent directory and select the named file after connection.
- Reject URL-embedded passwords and control characters; validate FTPES profiles.


## 0.4.2 — 2026-10-11

- Add purple/cyan inline queue progress bars with centered percentage and live MB/s.
- Show the queue when transfers are added and scroll to the running transfer.
- Log timestamped start, completion and failure events, duration, byte count and average MB/s.
- Exclude existing resumed bytes from transfer-rate measurements.


## 0.4.1 — 2026-10-11

- Restore compact connection toolbar and original-style purple/cyan file panels.
- Give file lists the expanding window space; collapse transfer activity by default.
- Move new-tab and refresh actions into compact header controls.


## 0.4.0 — 2026-10-11

- Pin PySide6 6.8.3 for verified Windows packaging.
- Replace Tkinter with a PySide6 interface preserving dark purple/cyan styling.
- Add independent connection tabs, per-tab serialized transfer queues, multi-select transfers, and Explorer file drops for uploads.
- Add opt-in FTP/FTPS/SFTP resume with size validation. Resume requires matching source and destination prefixes.
- Add Windows Credential Manager storage alongside optional Windows DPAPI encryption and legacy profile loading.
- Validate profile schemas and prohibit plaintext secret fields.
- Verify FTPS certificates and retain strict SFTP known-host verification.
- Add rotating structured logs that omit credentials, paths, hostnames, and raw server responses.
- Add automated tests and Windows CI with packaged startup verification and downloadable build artifacts.
- Credit project builder Anon0ne.

## 0.3.0

- Initial Windows source, Tkinter interface, Server Book with DPAPI, and BAT installer/build support.

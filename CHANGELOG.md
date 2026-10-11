# Changelog

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

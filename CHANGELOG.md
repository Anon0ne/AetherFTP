# Changelog

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

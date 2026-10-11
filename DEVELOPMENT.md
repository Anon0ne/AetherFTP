# Development notes

## v0.3 inspection

Reviewed all source, requirements, BAT launch/install scripts, PowerShell installer, README and ignore rules before modifying the application. Baseline Python modules compiled successfully. There were no existing automated tests or prior Git commits.

Findings addressed in v0.4: FTPS certificate validation, missing profile schema validation, DPAPI pointer cleanup declaration, failed connection resource cleanup, relative FTP listing restoration, single-session UI, UI-only logging, and missing CI.

## Verification

Windows Python 3.12: automated tests include real DPAPI encryption/decryption and isolated protocol/credential adapters. All 17 tests passed. The Windows one-file EXE built successfully and its startup check exited with code 0 using pinned PySide6 6.8.3. Source and packaged startup are checked with `--smoke-test`. Installer PowerShell syntax is checked with the PowerShell parser. GUI rendering is inspected at the host DPI. Credential Manager adapter calls are mocked in automated tests. A separate real Windows Credential Manager save/read/delete roundtrip passed with a unique disposable credential, removed immediately afterward. No personal credentials are used.

## Remaining work

- Test against controlled real FTP/FTPS/SFTP servers, including interrupted transfers and REST support.
- Add internal pane-to-pane drag-and-drop, recursive directory transfers, queue pause/cancel and persisted recovery.
- Test Credential Manager lifecycle and migration with disposable credentials on a dedicated Windows test machine.
- Expand keyboard, accessibility, enlarged-font and narrow-window validation.
- Restore GitHub authentication, create a private repository, and verify hosted Actions before publishing a release.

Source history uses Justin Funderburk's supplied author identity. Product builder credit is Anon0ne.

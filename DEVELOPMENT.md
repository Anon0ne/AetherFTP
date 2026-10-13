# Development notes

## v0.3 inspection

Reviewed all source, requirements, BAT launch/install scripts, PowerShell installer, README and ignore rules before modifying the application. Baseline Python modules compiled successfully. There were no existing automated tests or prior Git commits.

Findings addressed in v0.4: FTPS certificate validation, missing profile schema validation, DPAPI pointer cleanup declaration, failed connection resource cleanup, relative FTP listing restoration, single-session UI, UI-only logging, and missing CI.

## Verification

Windows Python 3.12: automated tests include real DPAPI encryption/decryption and isolated protocol/credential adapters. All 17 tests passed. The Windows one-file EXE built successfully and its startup check exited with code 0 using pinned PySide6 6.8.3. Source and packaged startup are checked with `--smoke-test`. Installer PowerShell syntax is checked with the PowerShell parser. GUI rendering is inspected at the host DPI. Credential Manager adapter calls are mocked in automated tests. A separate real Windows Credential Manager save/read/delete roundtrip passed with a unique disposable credential, removed immediately afterward. No personal credentials are used.

## Remaining work

- Test against controlled real FTP/FTPS/SFTP servers, including interrupted transfers and REST support.
- Add individual queue controls and persisted recovery. Local-to-server pane drag-and-drop and recursive folder uploads are implemented in 0.5.0.
- Test Credential Manager lifecycle and migration with disposable credentials on a dedicated Windows test machine.
- Expand keyboard, accessibility, enlarged-font and narrow-window validation.
- Verify hosted Windows Actions for each release before publishing.

Source history uses Justin Funderburk's supplied author identity. Product builder credit is Anon0ne.

## v0.6.1 verification

55 automated tests cover the adjustable activity height cap, idle worker connection cleanup, bounded TLS listing recovery and safe queue clearing. Product builder credit remains Anon0ne. See ROADMAP.md for proposed features.

## 0.1.1b verification

94 tests cover the released file tools, remote creation safeguards, real Qt context-menu actions, private bookmarks, synchronization, edit conflict checks, compatibility-folder navigation icon resources, pause/resume, cancellation, socket interruption and exit accounting. Standard ICO sizes are 16, 24, 32, 48, 64, 128 and 256 pixels. Windows CI verifies source startup and the packaged icon-bearing application before publication. PowerShell installer and shortcut scripts pass syntax validation.

## 0.1.2b verification

117 tests cover remote traversal, recursive downloads, Windows destination safety, conflict preflight, deletion ordering, actual Qt drop events, destination dialogs and search cancellation/rendering, alongside prior regressions. Adapter tests use disposable trees; broad live-server validation remains ongoing. Windows CI must pass for the exact release commit before publication.

## 0.1.3 Official

Promotes the user-validated 0.1.2b feature set without functional changes. The release version and stable installation documentation are updated. Run the 117-test regression suite and verify Windows source/build/packaged startup for the exact 0.1.3 commit before publishing.

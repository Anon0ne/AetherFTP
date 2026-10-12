# AetherFTP roadmap

Project builder: **Anon0ne**.

This is a proposal, not a list of implemented features. FileZilla's documented client features include bookmarks, filename filters, directory comparison, synchronized browsing, remote search and remote editing, alongside its protocol and queue features. References: https://filezilla-project.org/client_features.php and the project author's source README at https://github.com/botg/FileZilla3/blob/master/README.

## Delivered in 0.1.1b

Filename filters, paired bookmarks, synchronized browsing, Notepad remote editing with confirmed uploads and conflict checks, remote right-click file/folder creation, Windows compatibility-folder fixes, a distinct application icon, and Desktop shortcut support, global Pause/Resume and Stop controls, and Stop and exit.

## Reliable queue control

1. Add individual transfer/batch pause, cancellation and retry controls beyond the delivered global controls.
2. Save pending queues between launches, without saving credentials in the queue; require reconnection before recovery.
3. Recursive folder downloads with the same responsive batching as uploads.
4. Per-server connection budgets covering browsing, uploads and downloads together; show current usage and explain server 421 limits.
5. Failed/successful queue filters, batch totals, ETA and retry counts.

## File management

- Color-coded directory comparison by size/date, with a preview before transferring changed files.
- Remote Search button above the server pane: filename/glob search in the current directory, optional subfolders, background traversal, Stop support and scanned-folder counts. Results show full path, size and modified time, with open-folder, download and edit actions. Start with the existing browsing connection to avoid additional server login pressure.
- Local text search beyond the implemented glob filters.
- Remote rename, delete and permission controls, with confirmations for destructive operations (mkdir is implemented).
- Configurable external editors beyond the implemented Notepad workflow.

## AetherFTP additions

- Connection diagnostics showing TLS negotiation, certificate identity and connection usage, with a redacted support export.
- Transfer history with duration, average/peak speed, retry count and per-server trends stored locally.
- Optional checksum verification where the protocol/server supports it; clearly distinguish size checks from verified content.
- Scheduled bandwidth profiles for work hours and overnight batches.
- Preview-based folder synchronization with explicit conflict rules and an opt-in deletion policy.

Keep the purple/cyan interface spacious. Put advanced controls in Settings and context menus. Validate each milestone with automated tests and a packaged Windows startup check before release.

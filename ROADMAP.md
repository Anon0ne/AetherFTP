# AetherFTP roadmap

Project builder: **Anon0ne**.

This is a proposal, not a list of implemented features. FileZilla's documented client features include bookmarks, filename filters, directory comparison, synchronized browsing, remote search and remote editing, alongside its protocol and queue features. References: https://filezilla-project.org/client_features.php and the project author's source README at https://github.com/botg/FileZilla3/blob/master/README.

## Next release: file navigation and editing

Start after publishing 0.1.0b: filename filters, paired local/remote bookmarks and synchronized browsing, followed by remote editing with change detection and explicit re-upload confirmation.

Work started on `codex/next-release-file-tools`: filename include/exclude filters for both panes and recursive upload planning. This work is not included in the published 0.1.0b executable. Bookmarks, synchronized browsing and remote editing are the next steps.

## Reliable queue control

1. Pause, cancel and retry individual transfers or whole batches, with explicit partial-file handling.
2. Save pending queues between launches, without saving credentials in the queue; require reconnection before recovery.
3. Recursive folder downloads with the same responsive batching as uploads.
4. Per-server connection budgets covering browsing, uploads and downloads together; show current usage and explain server 421 limits.
5. Failed/successful queue filters, batch totals, ETA and retry counts.

## File management

- Bookmarks for paired local/remote paths and optional synchronized browsing.
- Color-coded directory comparison by size/date, with a preview before transferring changed files.
- Local and remote search, filename filters, and include/exclude rules for folder batches.
- Remote rename, delete, mkdir and permission controls, with confirmations for destructive operations.
- Open remote files in an external editor, detect edits and confirm re-upload with conflict checks.

## AetherFTP additions

- Connection diagnostics showing TLS negotiation, certificate identity and connection usage, with a redacted support export.
- Transfer history with duration, average/peak speed, retry count and per-server trends stored locally.
- Optional checksum verification where the protocol/server supports it; clearly distinguish size checks from verified content.
- Scheduled bandwidth profiles for work hours and overnight batches.
- Preview-based folder synchronization with explicit conflict rules and an opt-in deletion policy.

Keep the purple/cyan interface spacious. Put advanced controls in Settings and context menus. Validate each milestone with automated tests and a packaged Windows startup check before release.

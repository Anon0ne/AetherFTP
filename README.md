# AetherFTP

![Windows validation](https://github.com/Anon0ne/AetherFTP/actions/workflows/windows.yml/badge.svg)
[![Latest release](https://img.shields.io/github/v/release/Anon0ne/AetherFTP?include_prereleases)](https://github.com/Anon0ne/AetherFTP/releases)

A Windows FTP/FTPES/FTPS/SFTP client with a spacious dark purple/cyan interface inspired by Marauder V8 styling. Built with Python and PySide6/Qt. **Project builder: Anon0ne.**

Current release: **0.1.1b**, a public beta. [Download the Windows ZIP](https://github.com/Anon0ne/AetherFTP/releases/download/v0.1.1b/AetherFTP-Windows-v0.1.1b.zip) · [Release notes](https://github.com/Anon0ne/AetherFTP/releases/tag/v0.1.1b) · [Changelog](CHANGELOG.md)

## Install in minutes

1. Download the Windows ZIP from the release link above. Choose the packaged ZIP, rather than GitHub's source-code archive, for the ready-to-run application.
2. Extract **all files** into a permanent folder that your Windows user can write to.
3. Double-click **AetherFTP.exe**. The packaged application includes its runtime; Python is not required.
4. Run **Create_Desktop_Shortcut.bat** from that folder to add the purple/cyan Desktop shortcut. Keep the folder in place afterward.
5. Enter your server connection details, click **Connect**, choose a local file and remote destination, then click **UPLOAD**.

[Full installation and update guide](docs/INSTALLATION.md) · [Setup and usage guide](docs/USAGE.md) · [Troubleshooting](docs/TROUBLESHOOTING.md)

## Features

| Area | Available in 0.1.1b |
| --- | --- |
| Connections | FTP, explicit TLS via FTPES/FTPS, SFTP, connection URLs, multiple tabs |
| Server Book | Profiles with no saved password, Windows Credential Manager, or Windows-user DPAPI encryption |
| Transfers | Background queue, recursive folder uploads, empty directories, local/Explorer drag-and-drop uploads, file downloads, opt-in resume |
| Network settings | Separate upload/download concurrency of 1–8 each; shared directional bandwidth limits in MB/s |
| Queue control | Pause/Resume, Stop, Stop and exit, fresh visible queue after completed work |
| Progress | Purple/cyan percentage bars, live MB/s, per-file duration and average speed |
| Navigation | Include/exclude filename filters, paired bookmarks, synchronized browsing |
| Remote tools | Right-click New file, New folder, Refresh and Edit in Notepad; confirmed save uploads and conflict checks |
| Interface | Adjustable activity divider capped at 35% of file workspace, custom Windows icon and Desktop shortcut |
| Diagnostics | Connection steps, redacted server errors, Event log and rotating structured JSON logs |

## Current limits

This beta supports explicit TLS, not implicit FTPS. Recursive folder downloads, saved queues, individual transfer retry controls, directory comparison and recursive remote search are planned. Resume checks sizes, not file identity; use it only for matching partial files. SFTP requires a verified host key in your Windows user's `known_hosts`. Real-server interoperability testing remains ongoing.

[Roadmap](ROADMAP.md) · [Detailed behavior and safeguards](docs/USAGE.md)

## Privacy and local data

Profiles, settings, bookmarks and rotating logs live under `%APPDATA%\AetherFTP`. Password storage is optional. Never commit credentials, private keys, user server profiles or generated builds. Review diagnostic logs before sharing; server replies can contain private information. See [usage and privacy details](docs/USAGE.md#server-book-and-privacy).

## Build and contribute

Use **Install_AetherFTP.bat** from the source checkout to install dependencies, run tests, build the EXE and create shortcuts. Python 3.12 is the verified development baseline; the installer accepts Python 3.10+.

[Development, build and release instructions](docs/BUILDING.md) · [Contributing](CONTRIBUTING.md) · [Development validation notes](DEVELOPMENT.md)

Windows Actions runs tests, source startup, the executable build and packaged startup verification on pushes and pull requests. Successful runs provide an EXE artifact. Releases are published only after the corresponding commit passes build verification; CI does not publish automatically.

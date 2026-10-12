# Contributing to AetherFTP

Project builder: **Anon0ne**.

Use a feature branch and describe the problem, resulting behavior and validation in your pull request. Preserve the spacious purple/cyan interface. Keep advanced controls in settings or context menus.

Follow [environment and build instructions](docs/BUILDING.md). Run automated tests before commits; add meaningful regression coverage for transfer, concurrency, cancellation and security changes. For UI changes, verify real user flows and packaged startup as appropriate. Use disposable servers/credentials for interoperability testing.

Never commit passwords, tokens, private keys, personal server profiles, application data, logs, virtual environments or generated builds. Check staged changes before committing. Product builder credit remains Anon0ne; use your own Git author identity for commits.

Update usage documentation and `CHANGELOG.md` when behavior changes. Releases require successful Windows build verification for the exact published commit. See [ROADMAP.md](ROADMAP.md) for priorities. Report bugs with version, reproduction steps and reviewed/redacted diagnostic output in [GitHub Issues](https://github.com/Anon0ne/AetherFTP/issues).

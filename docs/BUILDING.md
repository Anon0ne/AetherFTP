# Development, builds and releases

[Back to README](../README.md) · [Contributing](../CONTRIBUTING.md)

## Environment

Windows with Python 3.12 is the verified baseline. The source installer accepts Python 3.10+. PySide6 6.8.3 is pinned; Paramiko, keyring, pytest and PyInstaller use the bounds in `requirements.txt`. Git is needed for contribution; GitHub CLI is used for publishing. These dependencies require internet access during setup.

```powershell
git clone https://github.com/Anon0ne/AetherFTP.git
cd AetherFTP
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe aetherftp.py
```

Tests use isolated protocol adapters and disposable test data. They do not require production server passwords. Broader real-server testing is tracked in [DEVELOPMENT.md](../DEVELOPMENT.md).

## Build a Windows EXE

The BAT installer performs the complete test/build/startup sequence. For a manual build, run tests first, then:

```powershell
.\.venv\Scripts\python.exe aetherftp.py --smoke-test
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name AetherFTP --icon assets/aetherftp.ico --add-data "assets/aetherftp.ico;assets" aetherftp.py
$check = Start-Process -FilePath .\dist\AetherFTP.exe -ArgumentList '--smoke-test' -WindowStyle Hidden -PassThru
if (-not $check.WaitForExit(30000)) { $check.Kill(); throw 'Startup timeout' }
if ($check.ExitCode -ne 0) { throw 'Startup failed' }
.\create_shortcut.ps1 -ExePath .\dist\AetherFTP.exe
```

Stop if any Python command exits unsuccessfully. The hidden startup check verifies application initialization and icon loading; it does not establish server connectivity. To regenerate the multi-size ICO from its approved PNG, run `.\.venv\Scripts\python.exe tools\build_icon.py`.

## GitHub Actions

[Windows validation](https://github.com/Anon0ne/AetherFTP/actions/workflows/windows.yml) runs on pushes, pull requests and manual dispatch:

1. Install Python 3.12 and requirements on `windows-latest`.
2. Run pytest and source startup verification.
3. Build the one-file windowed EXE with the custom icon.
4. Run packaged startup with a 30-second timeout.
5. Upload the `AetherFTP-Windows` EXE artifact.

An Actions artifact is a development build. It is not automatically a public release. Verify the run's full commit SHA before using its artifact for a release. The 0.1.1b release passed 94 automated tests and packaged startup on [its verified build](https://github.com/Anon0ne/AetherFTP/actions/runs/38212540567).

## Release procedure

1. Develop on a feature branch. Update `version.py`, `CHANGELOG.md` and affected user documentation. Use semantic version components and clearly label prereleases; existing beta tags are `v0.1.0b` and `v0.1.1b`.
2. Run tests and startup checks before committing. Review the tracked files for credentials, personal server information and generated builds.
3. Push the reviewed commit and confirm the Windows workflow succeeds for that exact SHA. Do not publish on a failed or still-running build.
4. Download the matching Actions artifact into a clean staging folder. Include the EXE, README, changelog, roadmap, `Create_Desktop_Shortcut.bat`, `create_shortcut.ps1` and `docs/` so packaged documentation links work. Exclude profiles, logs, editing copies and credentials.
5. Verify the downloaded EXE startup. Create the Windows ZIP and SHA-256 checksums for the EXE and ZIP.
6. Write release notes covering changes, installation, validation, known limits and rollback. Publish with GitHub CLI using the exact verified commit:

```powershell
gh release create <tag> <windows-zip> <checksums-file> --repo Anon0ne/AetherFTP --target <verified-commit-sha> --title '<release-title>' --notes-file <release-notes-file> --prerelease
```

7. Verify the uploaded asset names/digests and release link. Retain prior GitHub releases for rollback. Remove obsolete local builds only after their processes have exited and shortcuts point to the new version.

CI does not change saved profiles or publish releases automatically. Documentation-only updates do not replace an already verified release executable.

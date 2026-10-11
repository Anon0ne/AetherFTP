$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
try {
    $python = $null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -c "import sys; assert sys.version_info >= (3, 10)" 2>$null
        if ($LASTEXITCODE -eq 0) { $python = 'py' }
    }
    if (-not $python -and (Get-Command python -ErrorAction SilentlyContinue)) {
        & python -c "import sys; assert sys.version_info >= (3, 10)" 2>$null
        if ($LASTEXITCODE -eq 0) { $python = 'python' }
    }
    if (-not $python) {
        Write-Host 'Python 3.10+ not detected. Installing Python 3.12 with winget...'
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12 from python.org and rerun this installer (winget unavailable).' }
        & winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
        $paths = @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "$env:ProgramFiles\Python312\python.exe")
        $found = $paths | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($found) { $python = $found } else { throw 'Python installed. Open a new terminal and run this installer again.' }
    }
    Write-Host 'Creating isolated environment...'
    if ($python -eq 'py') { & py -3 -m venv .venv } else { & $python -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed.' }
    $venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & $venvPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Automated tests failed; build stopped.' }
    Write-Host 'Building Windows EXE...'
    & $venvPython -m PyInstaller --noconfirm --clean --onefile --windowed --name AetherFTP --paths $PSScriptRoot aetherftp.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    $exe = Join-Path $PSScriptRoot 'dist\AetherFTP.exe'
    if (-not (Test-Path $exe)) { throw 'EXE was not created.' }
    $check = Start-Process -FilePath $exe -ArgumentList '--smoke-test' -WindowStyle Hidden -PassThru
    if (-not $check.WaitForExit(30000)) { $check.Kill(); throw 'Packaged startup timed out.' }
    if ($check.ExitCode -ne 0) { throw 'Packaged startup failed.' }
    $shell = New-Object -ComObject WScript.Shell
    foreach ($linkPath in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'AetherFTP.lnk'), (Join-Path $env:USERPROFILE 'AetherFTP.lnk'))) {
        $shortcut = $shell.CreateShortcut($linkPath)
        $shortcut.TargetPath = $exe
        $shortcut.WorkingDirectory = Split-Path $exe
        $shortcut.Save()
    }
    Write-Host "SUCCESS: $exe"
    Write-Host 'Desktop and user-home shortcuts created.'
    exit 0
} catch {
    Write-Host "INSTALL ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

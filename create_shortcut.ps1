param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [switch]$HomeShortcut
)
$ErrorActionPreference = 'Stop'
$exe = (Resolve-Path -LiteralPath $ExePath).Path
if ([IO.Path]::GetExtension($exe) -ne '.exe') { throw 'Shortcut target must be an executable.' }
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
if (-not $desktop -or -not (Test-Path -LiteralPath $desktop)) { throw 'Windows Desktop folder unavailable.' }
$links = @((Join-Path $desktop 'AetherFTP.lnk'))
if ($HomeShortcut) { $links += (Join-Path $env:USERPROFILE 'AetherFTP.lnk') }
$shell = New-Object -ComObject WScript.Shell
foreach ($linkPath in $links) {
    $shortcut = $shell.CreateShortcut($linkPath)
    $shortcut.TargetPath = $exe
    $shortcut.WorkingDirectory = Split-Path $exe
    $shortcut.IconLocation = "$exe,0"
    $shortcut.Description = 'AetherFTP file transfer client - Built by Anon0ne'
    $shortcut.Save()
    Write-Output "Shortcut created: $linkPath"
}

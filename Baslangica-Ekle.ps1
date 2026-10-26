# Run this on the TARGET computer only, after copying the entire application folder.
$ErrorActionPreference = 'Stop'
$okanScript = Join-Path $PSScriptRoot 'kiosk.vbs'
if (-not (Test-Path -LiteralPath $okanScript)) { throw 'kiosk.vbs bulunamadi.' }
$okanStartup = [Environment]::GetFolderPath('Startup')
$okanShell = New-Object -ComObject WScript.Shell
$okanLink = $okanShell.CreateShortcut((Join-Path $okanStartup 'Okan Durak.lnk'))
$okanLink.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$okanLink.Arguments = '"' + $okanScript + '"'
$okanLink.WorkingDirectory = $PSScriptRoot
$okanLink.Description = 'Okan Durak - Tam ekran kiosk'
$okanLink.WindowStyle = 7
$okanLink.Save()
Write-Host 'Kiosk kisayolu bu kullanicinin Baslangic klasorune eklendi.'
Write-Host 'Bir sonraki Windows oturum acilisinda otomatik baslayacak.'

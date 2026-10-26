$ErrorActionPreference = 'Stop'
$okanLink = Join-Path ([Environment]::GetFolderPath('Startup')) 'Okan Durak.lnk'
if (Test-Path -LiteralPath $okanLink) {
    Remove-Item -LiteralPath $okanLink
    Write-Host 'Okan Durak baslangic kisayolu kaldirildi.'
} else {
    Write-Host 'Okan Durak baslangic kisayolu bulunamadi.'
}

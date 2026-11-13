$out=Join-Path $env:LOCALAPPDATA 'Temp\inodefence-host2-validation-20261110\windows-time-start.txt'
Start-Transcript -LiteralPath $out -Force
try {
 'UTC_BEFORE=' + [DateTime]::UtcNow.ToString('o')
 'ADMIN=' + ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
 'BEFORE_SERVICE'; Get-Service W32Time | Select-Object Name,Status,StartType | Format-List
 try { Start-Service W32Time -ErrorAction Stop; 'START_SERVICE=OK' } catch { 'START_SERVICE=ERROR ' + $_.Exception.Message }
 'COMMAND=w32tm /resync'; w32tm.exe /resync; 'EXIT=' + $LASTEXITCODE
 'AFTER_STATUS'; w32tm.exe /query /status; 'EXIT=' + $LASTEXITCODE
 'AFTER_SERVICE'; Get-Service W32Time | Select-Object Name,Status,StartType | Format-List
 'UTC_AFTER=' + [DateTime]::UtcNow.ToString('o')
} finally { Stop-Transcript }

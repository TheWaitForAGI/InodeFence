$out=Join-Path $env:LOCALAPPDATA 'Temp\inodefence-host2-validation-20261110\windows-time-resync.txt'
Start-Transcript -LiteralPath $out -Force
try {
 'UTC_BEFORE=' + [DateTime]::UtcNow.ToString('o')
 'ADMIN=' + ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
 'BEFORE_SOURCE'; w32tm.exe /query /source; 'EXIT=' + $LASTEXITCODE
 'COMMAND=w32tm /resync'; w32tm.exe /resync; 'EXIT=' + $LASTEXITCODE
 'AFTER_SOURCE'; w32tm.exe /query /source; 'EXIT=' + $LASTEXITCODE
 'AFTER_STATUS'; w32tm.exe /query /status; 'EXIT=' + $LASTEXITCODE
 'UTC_AFTER=' + [DateTime]::UtcNow.ToString('o')
} finally { Stop-Transcript }

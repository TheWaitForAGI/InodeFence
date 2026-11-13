$out=Join-Path $env:LOCALAPPDATA 'Temp\inodefence-host2-validation-20261110\windows-time-admin.txt'
Start-Transcript -LiteralPath $out -Force
try {
 'UTC=' + [DateTime]::UtcNow.ToString('o')
 'ADMIN=' + ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
 foreach ($args1 in @(@('/query','/status','/verbose'), @('/query','/source'), @('/query','/peers'), @('/query','/configuration'))) {
  'COMMAND=w32tm ' + ($args1 -join ' ')
  & w32tm.exe @args1
  'EXIT=' + $LASTEXITCODE
 }
} finally { Stop-Transcript }

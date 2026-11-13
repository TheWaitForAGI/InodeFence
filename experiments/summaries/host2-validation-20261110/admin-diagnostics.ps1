$ErrorActionPreference = 'Continue'
$out = Join-Path $env:LOCALAPPDATA 'Temp\inodefence-host2-validation-20261110\admin-diagnostics.txt'
Start-Transcript -LiteralPath $out -Force
try {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  'ADMIN=' + ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  'UTC=' + [DateTime]::UtcNow.ToString('o')
  foreach ($path in @('HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate', 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU', 'HKLM:\SOFTWARE\Microsoft\PolicyManager\current\device\Update', 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired', 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending')) {
    'REGISTRY=' + $path
    if (Test-Path -LiteralPath $path) { Get-ItemProperty -LiteralPath $path | Format-List * } else { 'NOT_FOUND_OR_INACCESSIBLE' }
  }
  'PENDING_RENAME_PRESENT=' + [bool](Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -Name PendingFileRenameOperations -ErrorAction SilentlyContinue)
  Get-ScheduledTask -TaskPath '\Microsoft\Windows\UpdateOrchestrator\' -ErrorAction Continue | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo -ErrorAction SilentlyContinue; [pscustomobject]@{Name=$_.TaskName; State=$_.State; NextRunTime=$i.NextRunTime} } | Format-Table -AutoSize
} finally { Stop-Transcript }

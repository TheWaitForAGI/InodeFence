# Read-only Windows data. A missing property is UNKNOWN, not a safety assertion.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
function Probe($Action) {
    try { @{ status = 'measured'; value = (& $Action) } }
    catch { @{ status = 'UNKNOWN'; error = $_.Exception.Message } }
}
$result = [ordered]@{
    os = Probe { Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber }
    cpu = Probe { @(Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors) }
    memory = Probe { (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory }
    volumes = Probe { @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID, Size, FreeSpace) }
    power = Probe { Add-Type -AssemblyName System.Windows.Forms; [string][System.Windows.Forms.SystemInformation]::PowerStatus.PowerLineStatus }
    sleep = Probe { $v = @(powercfg /query SCHEME_CURRENT SUB_SLEEP); if ($LASTEXITCODE -ne 0) { throw 'powercfg failed' }; @($v | ForEach-Object { [string]$_ }) }
    update_services = Probe { @(Get-Service wuauserv,usosvc | Select-Object Name, Status, StartType) }
    update_ux = Probe { Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings' | Select-Object ActiveHoursStart, ActiveHoursEnd, PauseUpdatesExpiryTime, PauseQualityUpdatesEndTime, PauseFeatureUpdatesEndTime }
    update_policy = Probe { $p = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate'; if (-not (Test-Path $p)) { throw 'Windows Update policy not configured' }; Get-ItemProperty $p | Select-Object * }
    update_au_policy = Probe { $p = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'; if (-not (Test-Path $p)) { throw 'AU policy not configured' }; Get-ItemProperty $p | Select-Object * }
    update_mdm = Probe { $p = 'HKLM:\SOFTWARE\Microsoft\PolicyManager\current\device\Update'; if (-not (Test-Path $p)) { throw 'effective MDM update policy not available' }; Get-ItemProperty $p | Select-Object * }
    reboot_required = Probe { (New-Object -ComObject Microsoft.Update.SystemInfo).RebootRequired }
    reboot_tasks = Probe { @(Get-ScheduledTask | Where-Object { $_.TaskName -match 'Reboot|Restart' } | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; [PSCustomObject]@{ Path=$_.TaskPath; Name=$_.TaskName; State=$_.State; Next=$i.NextRunTime } }) }
    docker_settings = Probe { $p = Join-Path $env:APPDATA 'Docker\settings-store.json'; Get-Content -Raw $p | ConvertFrom-Json | Select-Object WslEngineEnabled, dataFolder, diskImageLocation }
    docker_default_vhdx = Probe { $p = Join-Path $env:LOCALAPPDATA 'Docker\wsl\disk\docker_data.vhdx'; Get-Item $p | Select-Object FullName, Length }
    wsl_config = Probe { @(Get-Content (Join-Path $env:USERPROFILE '.wslconfig') | ForEach-Object { [string]$_ }) }
}
$result | ConvertTo-Json -Depth 4

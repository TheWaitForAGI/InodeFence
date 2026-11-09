# Read-only Windows inventory. Does not launch Docker or a WSL distribution.
# Run in PowerShell: powershell -NoProfile -File scripts/host_inventory.ps1
$ErrorActionPreference = 'Stop'
function Collect($Name, $Action) {
    try { @{ status = 'VERIFIED'; value = (& $Action) } }
    catch { @{ status = 'UNKNOWN'; error = "Could not read $Name" } }
}
$result = [ordered]@{
    purpose = 'environment inventory only; no execution approval'
    os = Collect 'OS' { Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber }
    cpu = Collect 'CPU' { @(Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors) }
    memory = Collect 'memory' { (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory }
    volumes = Collect 'volumes' { @(Get-Volume | Where-Object DriveLetter | Select-Object DriveLetter, FileSystem, Size, SizeRemaining) }
    power_scheme = Collect 'power scheme' { @(powercfg /getactivescheme); if ($LASTEXITCODE -ne 0) { throw 'powercfg failed' } }
    sleep_settings = Collect 'sleep settings' { @(powercfg /query SCHEME_CURRENT SUB_SLEEP); if ($LASTEXITCODE -ne 0) { throw 'powercfg failed' } }
    sleep_states = Collect 'sleep states' { @(powercfg /availablesleepstates); if ($LASTEXITCODE -ne 0) { throw 'powercfg failed' } }
    updates = Collect 'update settings' {
        $policy = Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU' -ErrorAction SilentlyContinue
        $ux = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings' -ErrorAction SilentlyContinue
        @{ policy = $policy | Select-Object NoAutoUpdate, AUOptions, NoAutoRebootWithLoggedOnUsers; active_hours = $ux | Select-Object ActiveHoursStart, ActiveHoursEnd, RestartNotificationsAllowed2 }
    }
    docker_desktop = Collect 'Docker Desktop installation' {
        $path = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
        if (-not (Test-Path -LiteralPath $path)) { throw 'not found at default path' }
        (Get-Item -LiteralPath $path).VersionInfo | Select-Object ProductVersion, FileVersion
    }
    docker_settings = Collect 'Docker Desktop settings' {
        $path = Join-Path $env:APPDATA 'Docker\settings-store.json'
        if (-not (Test-Path -LiteralPath $path)) { throw 'settings unavailable' }
        $settings = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        @{ wsl_engine_enabled = $settings.WslEngineEnabled; auto_start = $settings.AutoStart; disk_location = 'UNKNOWN'; update_state = 'UNKNOWN' }
    }
    docker_logs = Collect 'Docker log metadata' {
        $path = Join-Path $env:LOCALAPPDATA 'Docker\log'
        if (-not (Test-Path -LiteralPath $path)) { throw 'log location unavailable' }
        $measure = Get-ChildItem -LiteralPath $path -File -Recurse -ErrorAction Stop | Measure-Object LastWriteTime -Minimum -Maximum
        @{ count = $measure.Count; oldest = if ($measure.Minimum) { $measure.Minimum.ToString("o") } else { $null }; newest = if ($measure.Maximum) { $measure.Maximum.ToString("o") } else { $null } }
    }
    wsl_version = Collect 'WSL version' { [Console]::OutputEncoding = [Text.Encoding]::Unicode; try { @(wsl --version); if ($LASTEXITCODE -ne 0) { throw 'wsl failed' } } finally { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } }
    wsl_distributions = Collect 'WSL distributions' { [Console]::OutputEncoding = [Text.Encoding]::Unicode; try { @(wsl --list --verbose); if ($LASTEXITCODE -ne 0) { throw 'wsl failed' } } finally { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } }
    wsl_config = Collect 'WSL config' {
        $path = Join-Path $env:USERPROFILE '.wslconfig'
        if (-not (Test-Path -LiteralPath $path)) { throw 'config unavailable' }
        @(Get-Content -LiteralPath $path | Where-Object { $_ -match '^\s*(\[|processors\s*=|memory\s*=|swap\s*=)' } | ForEach-Object { $_.ToString() })
    }
    docker_engine = @{ status = 'UNKNOWN'; value = 'separate approval required' }
    image_id = @{ status = 'UNKNOWN'; value = 'separate approval required' }
    remaining_resources = @{ status = 'UNKNOWN'; value = 'separate approval required' }
}
$result | ConvertTo-Json -Depth 8

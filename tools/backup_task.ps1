# Registers the Windows scheduled task "PenWorks Backup": tools\backup.py every day at 20:00.
# Run once, by hand, from any folder:  powershell -NoProfile -ExecutionPolicy Bypass -File tools\backup_task.ps1
# Settings follow "Supabase KeepAlive" (her own account, only when she is signed in, StartWhenAvailable, no admin
# rights) with three differences, each for a reason:
#   - pythonw.exe instead of a console program, so no window pops up at 20:00 (the script writes its result to files)
#   - it may start and keep going on battery: a laptop unplugged at 20:00 would otherwise skip the night entirely
#   - a 2-hour time limit instead of 72 hours: a run normally takes seconds, a stuck one should not linger
$ErrorActionPreference = 'Stop'

$project = Split-Path -Parent $PSScriptRoot
$script  = Join-Path $project 'tools\backup.py'

# Her Python is the Microsoft Store one. This per-package alias survives Python updates, unlike the versioned
# folder under C:\Program Files\WindowsApps that sys.executable points into.
$pyw = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\pythonw.exe'
if (-not (Test-Path $pyw)) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if (-not $cmd) { throw 'pythonw.exe not found: is Python 3.12 installed?' }
    $pyw = $cmd.Source
}

$action    = New-ScheduledTaskAction -Execute $pyw -Argument "-E -P `"$script`"" -WorkingDirectory $project
$trigger   = New-ScheduledTaskTrigger -Daily -At '20:00'
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                 -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName 'PenWorks Backup' -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description 'Nightly read-only backup of PenWorks into penworks\backup (tools\backup.py).' -Force | Out-Null

Write-Output "Registered 'PenWorks Backup': daily 20:00, $pyw -E -P `"$script`""

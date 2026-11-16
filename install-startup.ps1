$ErrorActionPreference = 'Stop'
$bridgeRoot = $PSScriptRoot
$python = Join-Path $bridgeRoot '.venv\Scripts\pythonw.exe'
$script = Join-Path $bridgeRoot 'bridge.py'
$taskName = 'Bluetti AC50B to Home Assistant'

if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath (Join-Path $bridgeRoot 'config.json'))) {
    throw 'Create the virtual environment and config.json before installing startup.'
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw "Task '$taskName' already exists. Remove it explicitly before installing a replacement."
}

$action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $script + '"') -WorkingDirectory $bridgeRoot
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'Read AC50B Bluetooth sensors and publish monitoring readings to Home Assistant every 30 seconds.'
Start-ScheduledTask -TaskName $taskName

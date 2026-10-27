param(
    [Parameter(Mandatory = $true)][string]$Site,
    [int]$EveryMinutes = 60,
    [string]$StartAt = "06:00"
)
$root = Split-Path -Parent $PSScriptRoot
$bat = Join-Path $PSScriptRoot "run_site.bat"
$taskName = "EFEFO_$($Site.ToUpper())"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`" $Site" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At $StartAt -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -StartWhenAvailable
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Da tao Task Scheduler '$taskName' chay moi $EveryMinutes phut."

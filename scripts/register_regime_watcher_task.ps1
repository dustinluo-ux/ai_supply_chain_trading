# Registers regime_watcher.py as a Windows Task Scheduler task that runs at system startup.
# Run once as Administrator: powershell -ExecutionPolicy Bypass -File scripts\register_regime_watcher_task.ps1

$TaskName    = "AITrading_RegimeWatcher"
$Python      = "C:\Users\dusro\anaconda3\envs\wealth\python.exe"
$ScriptRoot  = Split-Path -Parent $PSScriptRoot  # project root
$Script      = Join-Path $ScriptRoot "src\monitoring\regime_watcher.py"
$LogDir      = Join-Path $ScriptRoot "logs"
$LogFile     = Join-Path $LogDir "regime_watcher.log"

# Ensure log dir exists
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task: $TaskName"
}

# Action: run python regime_watcher.py, redirect stdout+stderr to log
$Action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "`"$Script`"" `
    -WorkingDirectory $ScriptRoot

# Trigger: at system startup + 60s delay (gives network time to come up)
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Trigger.Delay = "PT60S"

# Settings: restart on failure, run whether logged on or not
$Settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -MultipleInstances IgnoreNew

# Principal: run as current user
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "AI Supply Chain Trading — polls regime_status.json every 60s, fires Telegram alerts on change" | Out-Null

Write-Host "Registered Task Scheduler task: $TaskName"
Write-Host "  Python : $Python"
Write-Host "  Script : $Script"
Write-Host "  Log    : $LogFile (note: Task Scheduler does not auto-redirect; regime_watcher.py logs to stderr)"
Write-Host ""
Write-Host "To start immediately (without rebooting):"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To check status:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Select-Object State"
Write-Host ""
Write-Host "To stop:"
Write-Host "  Stop-ScheduledTask -TaskName '$TaskName'"

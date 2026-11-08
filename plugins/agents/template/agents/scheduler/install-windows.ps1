<#
.SYNOPSIS
  Windows installer for the agent scheduler: Task Scheduler tasks that run the scheduler inside WSL.

.DESCRIPTION
  The scheduler is bash + Python (tick.sh, gate.py, health.py ...), so on Windows it runs
  inside WSL (Windows Subsystem for Linux). Claude Code, python3 and bash must be installed
  INSIDE the WSL distro and the workspace should live in the WSL file system
  (e.g. /home/<you>/<workspace>); a Claude Code installed on Windows itself is not used.

  Registers up to three tasks for the current user (names match install-linux.sh):
    <workspace>-agent-scheduler  every 10 min + at logon   wsl.exe -e bash -lc '<dir>/tick.sh'
    <workspace>-health-check     hourly at :30             python3 <dir>/health.py      (if automations.json exists)
    <workspace>-token-check      hourly at :00             python3 <dir>/tokencheck.py  (if credentials.json exists)
  Settings: a task never starts while its previous run is still going (IgnoreNew), a run
  missed while the PC slept or was off starts as soon as possible (StartWhenAvailable),
  runs on battery, no time limit. Tasks run only while you are logged on.

  Idempotent: re-running replaces these tasks. Not run automatically: review it (or its
  -Print output), then run it yourself from Windows PowerShell:
    powershell -ExecutionPolicy Bypass -File install-windows.ps1 -Print
    powershell -ExecutionPolicy Bypass -File install-windows.ps1
    powershell -ExecutionPolicy Bypass -File install-windows.ps1 -Uninstall

.PARAMETER SchedulerDir
  Linux path of agents/scheduler inside WSL, e.g. /home/<you>/<workspace>/agents/scheduler.
  Default: this script's folder, translated with `wsl.exe wslpath -a`.

.PARAMETER Distro
  WSL distribution to run in (wsl.exe -d <name>). Default: your default distro.

.PARAMETER Jobs
  tick, health, token. Default: tick, plus health when automations.json exists and token
  when credentials.json exists (all three for -Print and -Uninstall).

.PARAMETER Print
  Print the tasks (command line, triggers, settings) and change nothing. -WhatIf does the
  same. Works in PowerShell 7 on any OS, so the output can be reviewed before installing.

.PARAMETER Uninstall
  Remove the tasks. Logs and state inside WSL are kept.

.PARAMETER Headless
  Launch through `conhost.exe --headless` so no console window flashes every 10 minutes.
  Needs a recent Windows 10/11 conhost; untested, off by default.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$SchedulerDir,
  [string]$Distro,
  [ValidateSet('tick', 'health', 'token')][string[]]$Jobs,
  [switch]$Print,
  [switch]$Uninstall,
  [switch]$Headless
)
$ErrorActionPreference = 'Stop'
if ($WhatIfPreference) { $Print = $true }

$onWindows = ($env:OS -eq 'Windows_NT')
$here = $PSScriptRoot

function Invoke-Wsl([string]$BashCommand) {
  # Runs a bash -lc command in the selected distro; returns its stdout, sets $LASTEXITCODE.
  $wslArgs = @()
  if ($Distro) { $wslArgs += @('-d', $Distro) }
  $wslArgs += @('-e', 'bash', '-lc', $BashCommand)
  & wsl.exe @wslArgs
}

function Quote-Sh([string]$s) { "'" + ($s -replace "'", "'\''") + "'" }

# ── where the scheduler lives inside WSL ────────────────────────────────
if (-not $SchedulerDir) {
  if ($onWindows -and (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    $wslArgs = @()
    if ($Distro) { $wslArgs += @('-d', $Distro) }
    $SchedulerDir = (& wsl.exe @wslArgs -e wslpath -a $here | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $SchedulerDir) { throw "Could not translate '$here' with wslpath. Pass -SchedulerDir /home/<you>/<workspace>/agents/scheduler." }
  } elseif ($Print) {
    $SchedulerDir = '/home/<you>/<workspace>/agents/scheduler'
    Write-Warning "wsl.exe not available here: printing with the placeholder $SchedulerDir (pass -SchedulerDir to use a real path)."
  } else {
    throw 'WSL (wsl.exe) not found. Install WSL and, inside it, Claude Code; see agents/scheduler/README.md.'
  }
}
$SchedulerDir = $SchedulerDir.TrimEnd('/')
if ($SchedulerDir.Contains('"')) { throw 'SchedulerDir must not contain a double quote.' }

# Workspace slug = folder two levels up, lowercased, non [a-z0-9] → '-' (same as the bash installers for ASCII names).
$parts = $SchedulerDir.Split('/') | Where-Object { $_ -ne '' }
$wsName = if ($parts.Count -ge 3) { $parts[$parts.Count - 3] } else { 'workspace' }
$slug = ($wsName.ToLower() -replace '[^a-z0-9]', '-')

$names = @{ tick = "$slug-agent-scheduler"; health = "$slug-health-check"; token = "$slug-token-check" }

if (-not $Jobs) {
  $Jobs = @('tick')
  if ($Print -or $Uninstall -or (Test-Path (Join-Path $here 'automations.json'))) { $Jobs += 'health' }
  if ($Print -or $Uninstall -or (Test-Path (Join-Path $here 'credentials.json'))) { $Jobs += 'token' }
}

# ── the command each task runs ──────────────────────────────────────────
function Get-BashCommand([string]$job) {
  $d = $SchedulerDir
  $logs = Quote-Sh "$d/logs"
  switch ($job) {
    'tick'   { "mkdir -p $logs && $(Quote-Sh "$d/tick.sh") >> $(Quote-Sh "$d/logs/tick.out.log") 2>&1" }
    'health' { "mkdir -p $logs && python3 $(Quote-Sh "$d/health.py") >> $(Quote-Sh "$d/logs/health.timer.log") 2>&1" }
    'token'  { "mkdir -p $logs && python3 $(Quote-Sh "$d/tokencheck.py") >> $(Quote-Sh "$d/logs/tokencheck.timer.log") 2>&1" }
  }
}
function Get-TaskAction([string]$job) {
  # One Windows command line. The bash command sits inside double quotes (one argv entry
  # for wsl.exe) and uses only single quotes inside, so Windows argument parsing keeps it whole.
  $wslArgs = ''
  if ($Distro) { $wslArgs = "-d `"$Distro`" " }
  $wslArgs += "-e bash -lc `"$(Get-BashCommand $job)`""
  if ($Headless) { return @{ Execute = 'conhost.exe'; Argument = "--headless wsl.exe $wslArgs" } }
  return @{ Execute = 'wsl.exe'; Argument = $wslArgs }
}
$triggerText = @{
  tick   = 'every 10 minutes from 00:00 today, indefinitely; and at logon of the current user'
  health = 'hourly at :30 from 00:30 today, indefinitely'
  token  = 'hourly at :00 from 00:00 today, indefinitely'
}

# ── -Print / -WhatIf ────────────────────────────────────────────────────
if ($Print) {
  Write-Output '# install-windows.ps1 -Print: nothing is changed.'
  Write-Output "# WSL scheduler dir: $SchedulerDir   distro: $(if ($Distro) { $Distro } else { '(default)' })"
  Write-Output "# jobs: $($Jobs -join ', ')"
  foreach ($job in $Jobs) {
    $name = $names[$job]
    Write-Output ''
    if ($Uninstall) {
      Write-Output "Unregister-ScheduledTask -TaskName '$name' -Confirm:`$false"
      continue
    }
    $a = Get-TaskAction $job
    Write-Output "# ----- task: $name -----"
    Write-Output "Execute:   $($a.Execute)"
    Write-Output "Arguments: $($a.Argument)"
    Write-Output "Triggers:  $($triggerText[$job])"
    Write-Output 'Settings:  MultipleInstances=IgnoreNew; StartWhenAvailable; AllowStartIfOnBatteries; DontStopIfGoingOnBatteries; ExecutionTimeLimit=none'
    Write-Output 'Principal: current user, Interactive (only while logged on), RunLevel Limited'
    Write-Output "Check:     schtasks /Query /TN `"$name`"   (health.py: set `"windows_task`": `"$name`" in automations.json)"
  }
  exit 0
}

if (-not $onWindows) { throw 'Installing needs Windows (Task Scheduler). Use -Print to review the tasks on this machine.' }

# ── -Uninstall ──────────────────────────────────────────────────────────
if ($Uninstall) {
  foreach ($job in $Jobs) {
    $name = $names[$job]
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
      Unregister-ScheduledTask -TaskName $name -Confirm:$false
      Write-Output "Removed task $name"
    }
  }
  Write-Output "Uninstalled ($($Jobs -join ', ')). Logs and state inside WSL are kept."
  exit 0
}

# ── pre-flight inside WSL ───────────────────────────────────────────────
$d = $SchedulerDir
Invoke-Wsl "test -x $(Quote-Sh "$d/tick.sh") && test -f $(Quote-Sh "$d/../scheduled-tasks.md")" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "In WSL: $d/tick.sh is missing or not executable, or agents/scheduled-tasks.md is missing. Run /agents:init in the workspace inside WSL and chmod +x the .sh files." }
Invoke-Wsl 'command -v python3 >/dev/null' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'In WSL: python3 not found. Install it inside the distro (e.g. sudo apt install python3).' }
# No double quotes in commands passed to wsl.exe: Windows PowerShell 5.1 mangles them for native programs.
Invoke-Wsl 'command -v claude >/dev/null || test -x $HOME/.local/bin/claude || test -x $HOME/.claude/bin/claude' | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Warning 'Claude Code (claude) was not found inside WSL. Install it INSIDE the distro; the Windows install is not used. Ticks will log "CLI not found" until then.' }
if ($Jobs -contains 'health') {
  if (-not (Test-Path (Join-Path $here 'automations.json'))) { throw 'automations.json missing: copy automations.example.json to automations.json and edit it.' }
  Invoke-Wsl "python3 $(Quote-Sh "$d/health.py") --dry-run --force-daily --assume-awake >/dev/null" | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'health.py dry run failed inside WSL, not installing.' }
}
if ($Jobs -contains 'token') {
  if (-not (Test-Path (Join-Path $here 'credentials.json'))) { throw 'credentials.json missing: copy credentials.example.json to credentials.json and edit it.' }
  Invoke-Wsl "python3 $(Quote-Sh "$d/tokencheck.py") --dry-run --assume-awake >/dev/null" | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'tokencheck.py dry run failed inside WSL, not installing.' }
}

# ── register ────────────────────────────────────────────────────────────
$today = (Get-Date).Date
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
  -LogonType Interactive -RunLevel Limited
foreach ($job in $Jobs) {
  $name = $names[$job]
  $a = Get-TaskAction $job
  $action = New-ScheduledTaskAction -Execute $a.Execute -Argument $a.Argument
  switch ($job) {
    'tick' {
      $triggers = @(
        (New-ScheduledTaskTrigger -Once -At $today -RepetitionInterval (New-TimeSpan -Minutes 10)),
        (New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name))
      )
    }
    'health' { $triggers = @(New-ScheduledTaskTrigger -Once -At $today.AddMinutes(30) -RepetitionInterval (New-TimeSpan -Hours 1)) }
    'token'  { $triggers = @(New-ScheduledTaskTrigger -Once -At $today -RepetitionInterval (New-TimeSpan -Hours 1)) }
  }
  if ($PSCmdlet.ShouldProcess($name, 'Register scheduled task')) {
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $settings `
      -Principal $principal -Description "Agent scheduler ($job) for workspace $slug, runs in WSL" -Force | Out-Null
    Write-Output "Installed task $name ($($triggerText[$job]))"
  }
}
Write-Output "Verify: schtasks /Query /TN `"$($names['tick'])`"   ·   in WSL: tail -5 $d/logs/cron.log"
Write-Output 'Remove: powershell -ExecutionPolicy Bypass -File install-windows.ps1 -Uninstall'

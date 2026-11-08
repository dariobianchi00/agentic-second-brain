#!/usr/bin/env bash
set -euo pipefail

# Idempotent launchd installer for the agent scheduler. macOS only (launchd).
# Ships with the `agents` plugin; copy agents/scheduler/ into the workspace first.
#
# Schedule: StartInterval 600 (every 10 min) + RunAtLoad true.
# Was: hourly StartCalendarInterval at :07, RunAtLoad false. launchd queues a missed
# calendar slot and fires it on the next wake, INCLUDING a DarkWake (Power Nap /
# maintenance wake, lid closed, ~10 s), which started `claude -p` just before the
# Mac went back to sleep and froze the run for hours.
#
# StartInterval does NOT queue missed runs (launchd.plist(5): a firing due while the
# system is asleep "will be missed"). That is acceptable here: with a 10-min interval
# a wake is covered within ~10 min, RunAtLoad covers load/login, and gate.py looks
# back over missed slots, so a task skipped while asleep is still due on the next
# tick. launchd never starts a second instance of a job while one is running; an
# interval that fires mid-run is dropped (launchd.plist(5)), so a long Claude run
# cannot overlap itself. tick.sh also refuses to launch Claude during a DarkWake.
#
# The job runs tick.sh. tick.sh sources nvm (launchd has a bare PATH, and npx-based MCP
# servers need node), runs gate.py against the register, and starts `claude -p` (under
# `caffeinate -i`) only when a task is actually due AND the Mac is fully awake. An idle
# tick costs one log line, not a Claude run.
#
# This DRAFT is not run automatically. Review it, then run it yourself:
#   bash agents/scheduler/install-launchd.sh
# To remove:
#   launchctl unload -w ~/Library/LaunchAgents/com.<workspace>.agent-scheduler.plist

# Resolve workspace root (two levels up from this script) and derive the label from its folder name
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"
SLUG="$(basename "$WORKSPACE" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n' '-')"
LABEL="com.${SLUG}.agent-scheduler"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ ! -f "$WORKSPACE/agents/scheduled-tasks.md" ]]; then
    echo "Error: Cannot find agents/scheduled-tasks.md in $WORKSPACE"
    exit 1
fi

TICK="$SCRIPT_DIR/tick.sh"
if [[ ! -x "$TICK" ]]; then
    echo "Error: $TICK missing or not executable"
    exit 1
fi

LOGS_DIR="$WORKSPACE/agents/scheduler/logs"
mkdir -p "$LOGS_DIR"

echo "Workspace:  $WORKSPACE"
echo "Tick:       $TICK"
echo "Plist:      $PLIST"

# Unload any existing job so this is idempotent
if [[ -f "$PLIST" ]]; then
    launchctl unload -w "$PLIST" 2>/dev/null || true
fi

mkdir -p "$(dirname "$PLIST")"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-lc</string>
        <string>"$TICK" &gt;&gt; "$LOGS_DIR/launchd.out.log" 2&gt;&amp;1</string>
    </array>

    <!-- Every 10 min. Missed intervals during sleep are NOT queued; the next tick
         after wake (within 10 min) catches up via gate.py. Never overlaps a running tick. -->
    <key>StartInterval</key>
    <integer>600</integer>

    <!-- Also tick on load/login. -->
    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$LOGS_DIR/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>$LOGS_DIR/launchd.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl load -w "$PLIST"

echo ""
echo "Installed and loaded. Scheduler ticks every 10 min and at load; Claude runs only when a task is due and the Mac is fully awake."
echo "Verify: launchctl list | grep $LABEL"
echo "Logs:   $LOGS_DIR/cron.log"

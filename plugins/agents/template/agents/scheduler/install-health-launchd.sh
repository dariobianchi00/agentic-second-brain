#!/usr/bin/env bash
# Install the health-check LaunchAgent. macOS only (launchd).
# Daily automation health check (health.py). Plain Python, no Claude.
# Fires hourly at :30. health.py decides what to do: every fully-awake run checks that the
# scheduler is still ticking; the first fully-awake run at/after 08:30 sends the daily report.
#
# Idempotent. Not run automatically — review it, then run it yourself:
#   bash agents/scheduler/install-health-launchd.sh
#   bash agents/scheduler/install-health-launchd.sh --print-plist   # show the plist, install nothing
# Needs agents/scheduler/automations.json (copy automations.example.json and edit it).
# Remove:
#   launchctl unload -w ~/Library/LaunchAgents/com.<workspace>.health-check.plist
#   rm ~/Library/LaunchAgents/com.<workspace>.health-check.plist
set -euo pipefail

SCHED="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$SCHED/../.." && pwd)"
SLUG="$(basename "$WORKSPACE" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n' '-')"
LABEL="com.${SLUG}.health-check"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS_DIR="$SCHED/logs"

xml() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' <<< "$1"; }

plist() {
  cat <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$(xml "$SCHED/health.py")</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$(xml "$WORKSPACE")</string>

    <!-- Hourly at :30. A slot missed while asleep fires once on wake; in a DarkWake
         the script exits without doing anything and the next hour picks it up. -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Minute</key>
        <integer>30</integer>
    </dict>

    <key>RunAtLoad</key>
    <false/>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin</string>
    </dict>

    <key>StandardOutPath</key>
    <string>$(xml "$LOGS_DIR/health.launchd.log")</string>
    <key>StandardErrorPath</key>
    <string>$(xml "$LOGS_DIR/health.launchd.log")</string>
</dict>
</plist>
PLIST_EOF
}

if [[ "${1:-}" == "--print-plist" ]]; then plist; exit 0; fi

[[ "$(uname)" == "Darwin" ]] || { echo "Error: macOS only (launchd)."; exit 1; }
[[ -f "$SCHED/health.py" ]] || { echo "Error: $SCHED/health.py missing"; exit 1; }
[[ -f "$SCHED/automations.json" ]] || { echo "Error: $SCHED/automations.json missing — copy automations.example.json to automations.json and edit it"; exit 1; }

echo "Pre-flight: dry run (nothing sent, no state written)"
/usr/bin/python3 "$SCHED/health.py" --dry-run --force-daily --assume-awake >/dev/null \
  || { echo "Error: health.py dry run failed — not installing"; exit 1; }

mkdir -p "$LOGS_DIR" "$(dirname "$DEST")"
TMP="$(mktemp)"
plist > "$TMP"
plutil -lint "$TMP" >/dev/null || { echo "Error: generated plist is invalid"; rm -f "$TMP"; exit 1; }
[[ -f "$DEST" ]] && launchctl unload -w "$DEST" 2>/dev/null || true
mv "$TMP" "$DEST"
launchctl load -w "$DEST"

echo "Installed $DEST — runs hourly at :30; daily report at the first full-wake run >= 08:30."
echo "Verify: launchctl list | grep $LABEL"
echo "Logs:   $LOGS_DIR/health.log  ·  $LOGS_DIR/health.launchd.log"

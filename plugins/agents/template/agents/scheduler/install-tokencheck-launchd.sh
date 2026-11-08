#!/usr/bin/env bash
# Install the token-check LaunchAgent. macOS only (launchd).
# Weekly token check (tokencheck.py). Plain Python, no Claude.
# Fires hourly at :00. tokencheck.py runs its checks once per ISO week, at the first
# fully-awake run at/after Monday 08:00 (run.at in credentials.json); other runs are no-ops.
#
# Idempotent. Not run automatically — review it, then run it yourself:
#   bash agents/scheduler/install-tokencheck-launchd.sh
#   bash agents/scheduler/install-tokencheck-launchd.sh --print-plist   # show the plist, install nothing
# Needs agents/scheduler/credentials.json (copy credentials.example.json and edit it).
# Remove:
#   launchctl unload -w ~/Library/LaunchAgents/com.<workspace>.token-check.plist
#   rm ~/Library/LaunchAgents/com.<workspace>.token-check.plist
set -euo pipefail

SCHED="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$SCHED/../.." && pwd)"
SLUG="$(basename "$WORKSPACE" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n' '-')"
LABEL="com.${SLUG}.token-check"
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
        <string>$(xml "$SCHED/tokencheck.py")</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$(xml "$WORKSPACE")</string>

    <!-- Hourly at :00. A slot missed while asleep fires once on wake; in a DarkWake
         the script exits without doing anything and the next hour picks it up. -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>RunAtLoad</key>
    <false/>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin</string>
    </dict>

    <key>StandardOutPath</key>
    <string>$(xml "$LOGS_DIR/tokencheck.launchd.log")</string>
    <key>StandardErrorPath</key>
    <string>$(xml "$LOGS_DIR/tokencheck.launchd.log")</string>
</dict>
</plist>
PLIST_EOF
}

if [[ "${1:-}" == "--print-plist" ]]; then plist; exit 0; fi

[[ "$(uname)" == "Darwin" ]] || { echo "Error: macOS only (launchd)."; exit 1; }
[[ -f "$SCHED/tokencheck.py" ]] || { echo "Error: $SCHED/tokencheck.py missing"; exit 1; }
[[ -f "$SCHED/credentials.json" ]] || { echo "Error: $SCHED/credentials.json missing — copy credentials.example.json to credentials.json and edit it"; exit 1; }

echo "Pre-flight: dry run (nothing sent, no state written)"
/usr/bin/python3 "$SCHED/tokencheck.py" --dry-run --assume-awake \
  || { echo "Error: tokencheck.py dry run failed — not installing"; exit 1; }

mkdir -p "$LOGS_DIR" "$(dirname "$DEST")"
TMP="$(mktemp)"
plist > "$TMP"
plutil -lint "$TMP" >/dev/null || { echo "Error: generated plist is invalid"; rm -f "$TMP"; exit 1; }
[[ -f "$DEST" ]] && launchctl unload -w "$DEST" 2>/dev/null || true
mv "$TMP" "$DEST"
launchctl load -w "$DEST"

echo "Installed $DEST — fires hourly at :00; the check runs once a week at the first full wake >= Monday 08:00."
echo "Verify: launchctl list | grep $LABEL"
echo "Logs:   $LOGS_DIR/tokencheck.log  ·  $LOGS_DIR/tokencheck.launchd.log"

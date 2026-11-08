#!/bin/bash
# notify.sh — shared notifier for every scheduler automation (tick.sh, runrecord.py,
# health.py, tokencheck.py). Sends ONE plain-text message to the principal's own
# Telegram chat. Telegram is OPTIONAL: with no token configured the message is
# printed to stdout and appended to the notify log, and the exit code is 4.
#
# Telegram config, first match wins (never put the token on a command line):
#   1. env TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
#   2. agents/scheduler/notify.env (copy notify.env.example; keep it out of git)
#      — override the path with NOTIFY_ENV_FILE
#   3. the Claude Code Telegram channel plugin, if installed:
#      ~/.claude/channels/telegram/.env (token) + access.json (first allowFrom chat)
# The only recipient is that one chat. curl reads the URL (with the token) from
# stdin, so the token never appears in `ps`.
#
# Usage: notify.sh "message text"
#        notify.sh --file <path>       # message from a file
#        notify.sh -                   # message from stdin
# Telegram's limit is 4096 characters: longer text is cut at a line break and
# ends with "…[truncated]".
#
# NOTIFY_DRY_RUN=1    print the message instead of sending (exit 0). Also appends
#                     it to $NOTIFY_DRY_RUN_LOG when that is set (tests).
# NOTIFY_DRY_RUN=fail same, but exit 1 as if the send failed (tests).
# NOTIFY_LOG          where unsent messages go (default: $SCHED_LOGS_DIR/notify.log,
#                     else agents/scheduler/logs/notify.log)
#
# Exit: 0 sent · 1 send failed · 2 empty message / bad usage · 4 Telegram not configured (logged)
set -euo pipefail

case "${1:-}" in
  --file) [ -n "${2:-}" ] && [ -r "$2" ] || { echo "notify: --file needs a readable path" >&2; exit 2; }
          MSG="$(cat "$2")" ;;
  -)      MSG="$(cat)" ;;
  *)      MSG="${1:-}" ;;
esac
printf '%s' "$MSG" | grep -q '[^[:space:]]' || { echo "notify: empty message" >&2; exit 2; }

# Safe truncation: count UTF-16 units like Telegram does, never split a character.
MSG="$(NOTIFY_MSG="$MSG" python3 -c '
import os
m = os.environ["NOTIFY_MSG"]
LIMIT, TAIL = 4096, "\n…[truncated]"
u16 = lambda s: len(s.encode("utf-16-le")) // 2
if u16(m) > LIMIT:
    budget = LIMIT - u16(TAIL)
    while u16(m) > budget:
        m = m[: max(len(m) - max((u16(m) - budget) // 2, 1), 0)]
    cut = m.rfind("\n")
    if cut > len(m) * 0.8:
        m = m[:cut]
    m = m.rstrip() + TAIL
print(m, end="")
')"

if [ -n "${NOTIFY_DRY_RUN:-}" ] && [ "${NOTIFY_DRY_RUN}" != "0" ]; then
  printf 'notify[dry-run]:\n%s\n' "$MSG"
  if [ -n "${NOTIFY_DRY_RUN_LOG:-}" ]; then
    printf '%s\n<<<END>>>\n' "$MSG" >> "$NOTIFY_DRY_RUN_LOG"
  fi
  [ "$NOTIFY_DRY_RUN" = "fail" ] && { echo "notify: FAILED — dry-run failure" >&2; exit 1; }
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
env_value() {  # $1 = file, $2 = var name; prints the value or nothing
  [ -r "$1" ] || return 0
  grep -E "^$2=" "$1" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'"' ' || true
}
TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${TELEGRAM_CHAT_ID:-}"
CONF="${NOTIFY_ENV_FILE:-$SCRIPT_DIR/notify.env}"
[ -z "$TOKEN" ] && TOKEN="$(env_value "$CONF" TELEGRAM_BOT_TOKEN)"
[ -z "$CHAT_ID" ] && CHAT_ID="$(env_value "$CONF" TELEGRAM_CHAT_ID)"
if [ -z "${NOTIFY_ENV_FILE:-}" ]; then  # optional fallback: Claude Code Telegram channel plugin
  PLUGIN_DIR="$HOME/.claude/channels/telegram"
  [ -z "$TOKEN" ] && TOKEN="$(env_value "$PLUGIN_DIR/.env" TELEGRAM_BOT_TOKEN)"
  [ -z "$CHAT_ID" ] && CHAT_ID="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['allowFrom'][0])" "$PLUGIN_DIR/access.json" 2>/dev/null || true)"
fi

if [ -z "$TOKEN" ] || [ -z "$CHAT_ID" ]; then
  LOG="${NOTIFY_LOG:-${SCHED_LOGS_DIR:-$SCRIPT_DIR/logs}/notify.log}"
  printf 'notify[no-telegram]:\n%s\n' "$MSG"
  if mkdir -p "$(dirname "$LOG")" 2>/dev/null; then
    printf '%s notify (Telegram not configured):\n%s\n<<<END>>>\n' "$(date '+%Y-%m-%d %H:%M')" "$MSG" >> "$LOG" || true
  fi
  echo "notify: Telegram not configured — message logged to $LOG" >&2
  exit 4
fi

# URL (with token) goes to curl via stdin config, so it never appears in `ps`.
RESP="$(printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$TOKEN" | \
  curl -sS --max-time 20 -X POST -K - \
  --data-urlencode "chat_id=${CHAT_ID}" \
  --data-urlencode "text=${MSG}" \
  --data-urlencode "disable_web_page_preview=true" 2>&1 || true)"

if printf '%s' "$RESP" | grep -q '"ok":true'; then
  echo "notify: sent"
else
  echo "notify: FAILED — $(printf '%s' "$RESP" | sed -E 's/bot[0-9]+:[A-Za-z0-9_-]+/bot***/g' | head -c 300)" >&2
  exit 1
fi

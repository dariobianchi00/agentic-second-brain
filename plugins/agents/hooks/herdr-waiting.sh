#!/bin/sh
# agents plugin: "needs <principal>" marker for the Herdr sidebar
# Stop: show the pane's pending ask on the Herdr sidebar (custom token $ask)
#   and play Herdr's needs-attention sound when Claude's final message
#   1. has a line "⏳ NEEDS <principal>: <ask>" (exact marker), or
#   2. (fallback, the model forgot the marker; never on a session-close reply
#      with "Session-end checks") has, in its last 8 non-empty lines, a line
#      ending in "?" or naming a pending decision ("pending your", "your call",
#      "your answer", "kill / keep"). The last such line wins, "?" prefix.
#   Otherwise clear the token.
# UserPromptSubmit: clear the token and print a one-line reminder of the
#   marker rule, so it is fresh in context on every turn.
# SessionEnd: clear the token.
# No-op outside Herdr (HERDR_ENV / HERDR_PANE_ID unset). Never blocks.
# Convention: master template/agents/CONVENTIONS.md § Herdr (2026-11-01).

set -u
mode="${1:-stop}"
input="$(cat 2>/dev/null || true)"
[ "${HERDR_ENV:-}" = "1" ] && [ -n "${HERDR_PANE_ID:-}" ] || exit 0
herdr="${HERDR_BIN_PATH:-herdr}"
command -v "$herdr" >/dev/null 2>&1 || exit 0

clear_ask() {
  "$herdr" pane report-metadata "$HERDR_PANE_ID" --source sb:waiting --clear-token ask >/dev/null 2>&1 || true
}

if [ "$mode" = "prompt" ]; then
  clear_ask
  cwd="$(printf '%s' "$input" | sed -n 's/.*"cwd":[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
  [ -n "$cwd" ] || cwd="$PWD"
  conv="$cwd/agents/CONVENTIONS.md"
  [ -f "$conv" ] || conv="$cwd/Agents/CONVENTIONS.md"
  principal=""
  [ -f "$conv" ] && principal="$(sed -n '1,/^---$/!d;s/^principal:[[:space:]]*//p' "$conv" | head -1)"
  [ -n "$principal" ] || principal="you"
  echo "[needs-marker] If this reply ends waiting on $principal (a question, approval or choice), make its LAST line: ⏳ NEEDS $principal: <the ask, ≤ 70 chars>. Not on replies that only report work done."
  exit 0
fi

[ "$mode" = "stop" ] || { clear_ask; exit 0; }

ask="$(printf '%s' "$input" | python3 -I -c '
import json, re, sys
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
msg = data.get("last_assistant_message") or ""
src = "field"
if not msg and data.get("transcript_path"):
    # Older Claude Code builds omit last_assistant_message: read the last
    # assistant text from the session transcript instead.
    src = "transcript"
    try:
        for raw in open(data["transcript_path"], encoding="utf-8"):
            try:
                d = json.loads(raw)
            except Exception:
                continue
            if d.get("type") != "assistant":
                continue
            texts = [c.get("text", "") for c in d.get("message", {}).get("content", []) if isinstance(c, dict) and c.get("type") == "text"]
            if any(texts):
                msg = "\n".join(texts)
    except Exception:
        pass
lines = [" ".join(l.replace("*", "").replace("`", "").split()) for l in msg.splitlines()]
lines = [l for l in lines if l]
hit = ""
for s in lines:
    if s.startswith("⏳ NEEDS ") and ":" in s:
        hit = s.split(":", 1)[1].strip()
closing = any("session-end checks" in s.lower() for s in lines)
if not hit and not closing:
    cue = re.compile(r"(\?\s*\)?$|pending your|your call|your answer|kill ?/ ?keep)", re.I)
    for s in lines[-8:]:
        if cue.search(s):
            hit = "? " + re.sub(r"^(\d+\.|[-*])\s*", "", s)
hit = hit[:74] + ("…" if len(hit) > 74 else "")
try:
    import os, time
    log = os.path.expanduser("~/.claude/agents-state/herdr-waiting.log")
    with open(log, "a", encoding="utf-8") as f:
        f.write("%s pane=%s src=%s msg_chars=%d ask=%r\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), os.environ.get("HERDR_PANE_ID", ""), src, len(msg), hit))
except Exception:
    pass
print(hit)
' 2>/dev/null)"

if [ -z "$ask" ]; then
  clear_ask
  exit 0
fi

"$herdr" pane report-metadata "$HERDR_PANE_ID" --source sb:waiting --token "ask=⏳ $ask" --ttl-ms 86400000 >/dev/null 2>&1 || true
"$herdr" notification show "Needs you" --body "$ask" --sound request >/dev/null 2>&1 || true
exit 0

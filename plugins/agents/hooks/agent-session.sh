#!/bin/sh
# agents plugin: agent-session notices (W2.21 inbox, W5.1a session span)
# Runs on UserPromptSubmit. Prints at most two short lines that Claude sees as context:
#
#   [inbox] <agent>: N new — <entry> | <entry> | +K more ...
#       UNPROCESSED entries in THIS session's agent's own memory/scheduled/inbox.md
#       that this session has not been shown yet. Only the owning agent's inbox is
#       ever read, so a work-scope session can never see a firewalled (personal) inbox.
#   [session span] <agent>: this session ran <start> → <today> ...
#       On a close/wrap prompt of a session that crossed midnight, so the session
#       memory carries the `spans:` line the vault health check reads.
#
# Which agent owns the session (no model cooperation needed):
#   1. the prompt itself: `/agents:start <name> ...` (raw or <command-name> form);
#   2. else the transcript (hook input `transcript_path`): the last `/agents:start`
#      command message in it (sessions opened before this hook, resumed sessions).
# `/agents:start <name> peer <file>` marks a peer session: never notified.
#
# State per Claude Code session in ~/.claude/agents-state/ (override AGENTS_STATE_DIR):
#   <session>.agent   line 1 agent dir relative to agents/ (or "-"), line 2 unused (0), line 3 peer flag (0/1), line 4 agent start date YYYY-MM-DD
#   <session>.inbox   inbox entry lines already shown (or seeded at startup)
#
# No-op outside an agent workspace (no agents/CONVENTIONS.md). Never fails the prompt:
# every path exits 0. Dates: AGENTS_TODAY=YYYY-MM-DD pins "today" (tests).

input="$(cat 2>/dev/null || true)"

get() { printf '%s' "$input" | sed -n "s/.*\"$1\":[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -1; }

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

today() { if [ -n "${AGENTS_TODAY:-}" ]; then printf '%s' "$AGENTS_TODAY"; else date +%F; fi; }

# UTC "YYYY-MM-DDTHH:MM:SS" -> local YYYY-MM-DD (BSD or GNU date); empty on failure.
utc_to_local_date() {
  s=$(date -j -u -f '%Y-%m-%dT%H:%M:%S' "$1" +%s 2>/dev/null) || s=$(date -u -d "$1" +%s 2>/dev/null) || return 0
  if date -r 0 >/dev/null 2>&1; then date -r "$s" +%F 2>/dev/null; else date -d "@$s" +%F 2>/dev/null; fi
}

# Frontmatter value of key $1 in conventions file $2.
fm() { sed -n '1,/^---$/!d;s/^'"$1"':[[:space:]]*//p' "$2" 2>/dev/null | head -1; }

# Resolve an agent name to "<scope>/<dir>" or "<dir>" under $adir (case-insensitive).
resolve_agent() {
  want=$(lower "$1")
  [ -n "$want" ] || return 0
  for ctx in "$adir"/*/context.md "$adir"/*/*/context.md; do
    [ -f "$ctx" ] || continue
    d=$(dirname "$ctx")
    if [ "$(lower "$(basename "$d")")" = "$want" ]; then
      printf '%s' "${d#"$adir"/}"
      return 0
    fi
  done
}

# "<name> <rest...>" -> sets new_agent, new_peer, new_close
parse_start_args() {
  set -f; set -- $1; set +f
  new_agent=$(resolve_agent "${1:-}")
  new_peer=0; new_close=0
  case "$(lower "${2:-}")" in
    peer) new_peer=1 ;;
    close|end|wrap) new_close=1 ;;
  esac
}

summarise() {
  # One inbox entry line -> short label: drop heading/bullet markers, the
  # UNPROCESSED marker, backticks, "(tick)"; trim dashes; cut at a word near 90 chars.
  printf '%s\n' "$1" | sed -E \
    -e 's/^#+[[:space:]]*//' -e 's/^[-*][[:space:]]*//' \
    -e 's/\*\*UNPROCESSED\*\*//g' -e 's/UNPROCESSED//g' -e 's/`//g' -e 's/\(tick\)//g' \
    -e 's/[[:space:]]+/ /g' -e 's/— *—/—/g' -e 's/^ *— *//' -e 's/ *— *$//' -e 's/^ +//' -e 's/ +$//' \
    -e 's/^(.{90}[^ ]*) .+$/\1 …/'
}

main() {
  session="$(get session_id)"
  cwd="$(get cwd)"
  [ -n "$session" ] || return 0
  [ -n "$cwd" ] || cwd="$PWD"

  adir="$cwd/agents"
  [ -f "$adir/CONVENTIONS.md" ] || adir="$cwd/Agents"
  conv="$adir/CONVENTIONS.md"
  [ -f "$conv" ] || return 0

  sdir="${AGENTS_STATE_DIR:-${HOME}/.claude/agents-state}"
  mkdir -p "$sdir" 2>/dev/null || return 0
  stamp="$sdir/$session.agent"
  shown="$sdir/$session.inbox"
  if [ ! -f "$stamp" ]; then
    find "$sdir" -type f \( -name '*.agent' -o -name '*.inbox' \) -mtime +30 -exec rm -f {} + 2>/dev/null
  fi

  agent="-"; peer=0; start=""
  if [ -f "$stamp" ]; then
    agent=$(sed -n 1p "$stamp"); peer=$(sed -n 3p "$stamp"); start=$(sed -n 4p "$stamp")
    [ -n "$agent" ] || agent="-"
    [ "$peer" = "1" ] || peer=0
  fi
  td=$(today)

  # --- 1. the prompt -------------------------------------------------------
  prompt="$(get prompt)"
  closing=0; started=0; new_agent=""
  args=$(printf '%s' "$prompt" | sed -n 's/^[[:space:]]*\/agents:start[[:space:]][[:space:]]*\(.*\)$/\1/p' | head -1)
  [ -n "$args" ] || args=$(printf '%s' "$prompt" | sed -n 's/.*<command-name>\/agents:start<\/command-name>.*<command-args>\([^<]*\)<\/command-args>.*/\1/p' | head -1)
  if [ -n "$args" ]; then
    parse_start_args "$args"
    if [ -n "$new_agent" ]; then
      started=1; closing=$new_close
      if [ "$new_agent" != "$agent" ]; then start="$td"; fi
      agent="$new_agent"; peer=$new_peer
    fi
  fi
  case "$prompt" in
    /agents:close*|/agents:wrap*|*'<command-name>/agents:close</command-name>'*|*'<command-name>/agents:wrap</command-name>'*) closing=1 ;;
  esac

  # --- 2. the transcript (catch-up for sessions the prompt did not name) ---
  tp="$(get transcript_path)"
  if [ "$started" = "0" ] && [ -n "$tp" ] && [ -f "$tp" ]; then
    # grep the file itself (fast even at 60 MB; piping through tail is not)
    line=$(LC_ALL=C grep -F '"content":"<command-message>agents:start</command-message>\n<command-name>/agents:start</command-name>\n<command-args>' "$tp" 2>/dev/null | tail -1)
    if [ -n "$line" ]; then
      targs=$(printf '%s' "$line" | sed -n 's/.*<command-name>\/agents:start<\/command-name>\\n<command-args>\([^<]*\)<\/command-args>.*/\1/p' | head -1)
      parse_start_args "$targs"
      if [ -n "$new_agent" ] && [ "$new_agent" != "$agent" ]; then
        ts=$(printf '%s' "$line" | sed -n 's/.*"timestamp":"\([0-9-]*T[0-9:]*\)[^"]*".*/\1/p' | head -1)
        start=""; [ -n "$ts" ] && start=$(utc_to_local_date "$ts")
        agent="$new_agent"; peer=$new_peer
      fi
    fi
  fi
  [ -n "$start" ] || start="$td"
  printf '%s\n%s\n%s\n%s\n' "$agent" "0" "$peer" "$start" > "$stamp" 2>/dev/null

  [ "$agent" != "-" ] || return 0
  [ "$peer" = "0" ] || return 0
  name=$(basename "$agent")

  # --- 3. firewall / Work Mode: a firewalled-scope agent stays silent while the flag is on
  scope=""
  case "$agent" in */*) scope="${agent%%/*}" ;; esac
  fw=$(fm firewalled-scope "$conv")
  if [ -n "$scope" ] && [ -n "$fw" ] && [ "$(lower "$scope")" = "$(lower "$fw")" ] \
     && [ "$(fm work-mode "$conv")" = "on" ]; then
    flag=$(fm work-mode-flag "$conv")
    [ -n "$flag" ] && [ -e "$cwd/$flag" ] && return 0
  fi

  # --- 4. session span on close ---------------------------------------------
  if [ "$closing" = "1" ]; then
    if [ "$start" != "$td" ]; then
      printf '[session span] %s: this session ran %s → %s. The session memory MUST carry a line starting `spans: %s → %s` (session-end step 4), or the days in between show as gaps.\n' "$name" "$start" "$td" "$start" "$td"
    fi
    return 0
  fi

  # --- 5. inbox ---------------------------------------------------------------
  inbox="$adir/$agent/memory/scheduled/inbox.md"
  [ -f "$inbox" ] || return 0
  cur=$(awk '
    /^[[:space:]]*```/ { fence = !fence; next }
    fence { next }
    /UNPROCESSED[[:space:]]*(→|->)/ { next }
    /^(#+|[-*])[ \t]/ && /UNPROCESSED/ { print }
  ' "$inbox" 2>/dev/null)
  [ -n "$cur" ] || return 0
  [ -f "$shown" ] || : > "$shown"
  if [ "$started" = "1" ]; then
    # startup step 16 drains the inbox itself: seed, do not notify
    printf '%s\n' "$cur" >> "$shown"
    return 0
  fi
  new=$(printf '%s\n' "$cur" | grep -F -x -v -f "$shown" 2>/dev/null)
  [ -n "$new" ] || return 0
  printf '%s\n' "$new" >> "$shown"

  n=$(printf '%s\n' "$new" | wc -l | tr -d ' ')
  labels=""; i=0
  while IFS= read -r l; do
    i=$((i + 1))
    [ "$i" -le 3 ] || break
    s=$(summarise "$l")
    if [ -z "$labels" ]; then labels="$s"; else labels="$labels | $s"; fi
  done <<EOF
$new
EOF
  [ "$n" -gt 3 ] && labels="$labels | +$((n - 3)) more"
  printf '[inbox] %s: %s new — %s. Surface these first (read memory/scheduled/inbox.md, drain as startup step 16), then answer.\n' "$name" "$n" "$labels"
}

main 2>/dev/null || true
exit 0

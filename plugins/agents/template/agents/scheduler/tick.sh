#!/usr/bin/env bash
# Scheduler tick. Runs on macOS (launchd: install-launchd.sh), Linux (systemd user
# timer or cron: install-linux.sh) and Windows via WSL (Task Scheduler calls
# `wsl.exe -e bash -lc tick.sh`: install-windows.ps1). The timer calls this every
# 10 minutes and at login. Most ticks are idle: one cheap gate line, no Claude.
#
# Platform: SCHED_PLATFORM=macos|linux|wsl overrides detection (tests). Only macOS
# has the wake check (pmset) and caffeinate; on Linux/WSL both are skipped: systemd,
# cron and Task Scheduler do not fire while the machine is suspended, so a tick
# that runs is treated as awake.
#
# Step 1 is a cheap gate (gate.py, no Claude): parse agents/scheduled-tasks.md and
# decide whether any enabled task is due right now. If none is, log one line and exit.
# Step 2 runs the harness headlessly on agents/scheduler/prompt.md only when something is due.
#
# Harness = the coding-agent CLI that runs the tick. Read from `harness:` in the
# frontmatter of agents/CONVENTIONS.md (claude | codex | gemini | opencode; default
# claude). Override with AGENT_HARNESS=<name>. AGENT_HARNESS_CMD="<cmd and flags>"
# replaces the whole command; the prompt is appended as its last argument.
#
# Wake check (macOS only): the harness only starts on a FULL wake. launchd also fires
# during DarkWake (Power Nap / maintenance wakes, lid closed, ~2-10 s) and the Mac
# drops back to sleep mid-run, freezing the harness for hours.
# Signal: `pmset -g systemstate` capabilities. Full wake = "CPU Graphics Audio
# Network" (pmset log tag [CDNVA]); DarkWake has no Graphics ([CDNP]). Clamshell
# mode with an external display awake is a full wake, so Graphics is present.
# In a DarkWake the tick logs one "deferred" line and exits 0; the gate keeps the
# task due, so a later tick picks it up. If the probe itself fails we fail OPEN
# (run) and log it. TICK_SKIP_WAKE_CHECK=1 bypasses the check for manual runs.
#
# macOS: the run is wrapped in `caffeinate -i` so the Mac does not idle-sleep
# mid-run. It does NOT stop a lid-close sleep on battery without an external display.
# Linux/WSL: no equivalent is added (systemd-inhibit needs polkit rights for sleep
# locks); keep the machine from suspending during scheduled runs yourself.
#
# Retry cap + outcome reporting: after the harness exits, `runrecord.py postrun`
# checks each task the gate named. Last run not updated = a failed attempt: counted
# per task per slot in state/attempts.json, a `failed` run record is written under
# runs/<scope>/YYYY-MM/, and ONE ❌ alert (notify.sh: Telegram if configured, else
# the notify log) goes out when the cap (SCHED_MAX_ATTEMPTS, default 3) is
# reached; gate.py then holds that slot. A harness that cannot start (CLI missing,
# unknown harness) counts as a failed attempt too. DarkWake deferrals are NOT
# attempts. A run that updated Last run but wrote no run record gets a ⚠️ record
# + message. Tasks report their own outcome via `runrecord.py report` (prompt.md).
#
# Env overrides (tests): SCHED_REGISTER, SCHED_LOGS_DIR, SCHED_STATE_FILE,
# SCHED_RUNS_DIR, SCHED_PLATFORM, TICK_PMSET_BIN, TICK_CAFFEINATE_BIN,
# NOTIFY_DRY_RUN=1 (print instead of sending).
#
# Usage: bash agents/scheduler/tick.sh              # normal tick
#        bash agents/scheduler/tick.sh --dry-run    # print what is due + wake state, never call the harness
#        bash agents/scheduler/tick.sh --wake-check # print the wake probe result only (no gate, no log)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"
REGISTER="${SCHED_REGISTER:-$WORKSPACE/agents/scheduled-tasks.md}"
LOGS_DIR="${SCHED_LOGS_DIR:-$SCRIPT_DIR/logs}"
PMSET="${TICK_PMSET_BIN:-/usr/bin/pmset}"
CAFFEINATE="${TICK_CAFFEINATE_BIN:-/usr/bin/caffeinate}"

# macos | linux | wsl. WSL = Linux kernel with "microsoft" in its version string.
detect_platform() {
  if [[ -n "${SCHED_PLATFORM:-}" ]]; then echo "$SCHED_PLATFORM"; return; fi
  case "$(uname -s 2>/dev/null)" in
    Darwin) echo macos ;;
    Linux)  if grep -qi microsoft /proc/version 2>/dev/null; then echo wsl; else echo linux; fi ;;
    *)      echo linux ;;  # other Unix: same rules as Linux (no wake probe, no caffeinate)
  esac
}
PLATFORM="$(detect_platform)"
mkdir -p "$LOGS_DIR"
# Shared with gate.py / runrecord.py and inherited by the harness (its runrecord calls).
export SCHED_REGISTER="$REGISTER" SCHED_LOGS_DIR="$LOGS_DIR"
cd "$WORKSPACE"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Wake probe. Sets WAKE_REASON. Returns 0 = fully awake, 1 = DarkWake, 2 = probe error.
WAKE_REASON=""
wake_check() {
  local out caps
  if [[ "$PLATFORM" != "macos" ]]; then
    WAKE_REASON="no wake probe on $PLATFORM (assume awake: the timer does not fire while suspended)"; return 0
  fi
  if [[ ! -x "$PMSET" ]]; then WAKE_REASON="probe error: $PMSET missing"; return 2; fi
  if ! out="$("$PMSET" -g systemstate 2>&1)"; then
    WAKE_REASON="probe error: pmset -g systemstate failed: $(printf '%s' "$out" | head -1)"; return 2
  fi
  if ! printf '%s\n' "$out" | grep -q '^Current System Capabilities are:'; then
    WAKE_REASON="probe error: unrecognised pmset output: $(printf '%s' "$out" | head -1)"; return 2
  fi
  caps="$(printf '%s\n' "$out" | sed -n 's/^Current System Capabilities are:[[:space:]]*//p' | head -1 | sed 's/[[:space:]]*$//')"
  case " $caps " in
    *" Graphics "*) WAKE_REASON="full wake, capabilities: $caps"; return 0 ;;
    *)              WAKE_REASON="DarkWake, capabilities: ${caps:-none}"; return 1 ;;
  esac
}

if [[ "${1:-}" == "--wake-check" ]]; then
  wrc=0; wake_check || wrc=$?
  echo "wake_check rc=$wrc ($WAKE_REASON)"
  exit 0
fi

# nvm: launchd/systemd/cron start with a bare PATH; npx-based MCP servers need node.
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
# shellcheck disable=SC1091
[[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1 || true

if ! command -v python3 >/dev/null; then
  echo "$(date '+%Y-%m-%d %H:%M') gate: python3 missing, cannot evaluate register" >> "$LOGS_DIR/cron.log"
  exit 1
fi

TICK_STARTED="$(date '+%Y-%m-%dT%H:%M:%S%z' | sed -E 's/([0-9]{2})([0-9]{2})$/\1:\2/')"
export SCHED_TICK_STARTED="$TICK_STARTED"
export SCHED_TICK_ID="${TICK_STARTED}-$$"  # tags run records written during this tick
# gate and postrun share one "now", so both see the same slot
DUE="$(python3 "$SCRIPT_DIR/gate.py" "$REGISTER" "$TICK_STARTED")" || rc=$?
rc=${rc:-0}
if [[ $rc -eq 2 ]]; then
  echo "$(date '+%Y-%m-%d %H:%M') gate: no register at agents/scheduled-tasks.md" >> "$LOGS_DIR/cron.log"
  exit 0
fi

if [[ -z "$DUE" ]]; then
  echo "$(date '+%Y-%m-%d %H:%M') gate: no tasks due" >> "$LOGS_DIR/cron.log"
  $DRY_RUN && echo "no tasks due"
  exit 0
fi

if $DRY_RUN; then
  echo "due: $DUE"
  echo "platform: $PLATFORM"
  wrc=0; wake_check || wrc=$?
  echo "wake: rc=$wrc ($WAKE_REASON)$([[ "${TICK_SKIP_WAKE_CHECK:-}" == "1" ]] && echo ' [TICK_SKIP_WAKE_CHECK=1: would be ignored]')"
  STATE_FILE="${SCHED_STATE_FILE:-$SCRIPT_DIR/state/attempts.json}"
  if [[ -s "$STATE_FILE" ]]; then echo "attempts state ($STATE_FILE):"; sed 's/^/  /' "$STATE_FILE"; else echo "attempts state: none"; fi
  exit 0
fi

# Only launch on a full wake (after the gate so idle ticks stay one cheap line).
WAKE_NOTE=""
if [[ "${TICK_SKIP_WAKE_CHECK:-}" == "1" ]]; then
  WAKE_NOTE=" (wake check skipped: TICK_SKIP_WAKE_CHECK=1)"
else
  wrc=0; wake_check || wrc=$?
  if [[ $wrc -eq 1 ]]; then
    echo "$(date '+%Y-%m-%d %H:%M') gate: due=[$DUE] deferred: not fully awake ($WAKE_REASON)" >> "$LOGS_DIR/cron.log"
    exit 0
  elif [[ $wrc -ne 0 ]]; then
    WAKE_NOTE=" (wake check failed open: $WAKE_REASON)"
  fi
fi

# Which harness runs the tick
HARNESS="${AGENT_HARNESS:-}"
if [[ -z "$HARNESS" && -f "$WORKSPACE/agents/CONVENTIONS.md" ]]; then
  HARNESS="$(sed -n '1,/^---$/!d;s/^harness:[[:space:]]*//p' "$WORKSPACE/agents/CONVENTIONS.md" | sed 's/[[:space:]]*#.*//' | head -1)"
fi
HARNESS="${HARNESS:-claude}"

# Framework root for non-plugin harnesses: with `extends: plugin` the master
# conventions and reference files live there. Newest Claude plugin cache is the fallback.
if [[ -n "${AGENT_FRAMEWORK_ROOT:-}" ]]; then
  export AGENT_FRAMEWORK_ROOT
else
  newest="$(ls -d "$HOME"/.claude/plugins/cache/*/agents/* 2>/dev/null | sort -V | tail -1 || true)"
  [[ -n "$newest" ]] && export AGENT_FRAMEWORK_ROOT="$newest"
fi

# Post-run check: runs whether the harness ran, failed or never started.
postrun() {  # $1 = harness exit code, $2 = file with this run's harness output (may be empty)
  python3 "$SCRIPT_DIR/runrecord.py" postrun --due "$DUE" --started "$TICK_STARTED" \
    --harness-rc "$1" ${2:+--harness-log "$2"} >> "$LOGS_DIR/cron.log" 2>&1 \
    || echo "$(date '+%Y-%m-%d %H:%M') gate: postrun check failed (rc=$?)" >> "$LOGS_DIR/cron.log"
}

# Find the harness CLI
find_bin() {
  if command -v "$1" >/dev/null 2>&1; then command -v "$1"
  elif [[ -x "$HOME/.claude/bin/$1" ]]; then echo "$HOME/.claude/bin/$1"
  elif [[ -x "/usr/local/bin/$1" ]]; then echo "/usr/local/bin/$1"
  elif [[ -x "$HOME/.local/bin/$1" ]]; then echo "$HOME/.local/bin/$1"
  elif [[ -x "$HOME/.npm-global/bin/$1" ]]; then echo "$HOME/.npm-global/bin/$1"
  elif [[ -x "/opt/homebrew/bin/$1" ]]; then echo "/opt/homebrew/bin/$1"
  fi
}

PROMPT="Read agents/scheduler/prompt.md and follow its instructions exactly. The gate script found these tasks due now: $DUE. Verify against the register, then execute only due tasks."

if [[ -n "${AGENT_HARNESS_CMD:-}" ]]; then
  read -r -a CMD <<< "$AGENT_HARNESS_CMD"
  TAIL=()
  HARNESS="custom (${CMD[0]})"
else
  BIN="$(find_bin "$HARNESS")"
  if [[ -z "$BIN" ]]; then
    echo "$(date '+%Y-%m-%d %H:%M') gate: due=[$DUE] but $HARNESS CLI not found" >> "$LOGS_DIR/cron.log"
    postrun 127 ""
    exit 1
  fi
  # Unattended run: no one can answer an approval prompt, so each harness gets its
  # own "skip approvals" flag. Same trust level as before, only the CLI differs.
  case "$HARNESS" in
    claude)   CMD=("$BIN" -p); TAIL=(--dangerously-skip-permissions --max-turns 50) ;;
    codex)    CMD=("$BIN" exec -C "$WORKSPACE" --dangerously-bypass-approvals-and-sandbox); TAIL=() ;;
    gemini)   CMD=("$BIN" --approval-mode yolo); TAIL=() ;;
    opencode) CMD=("$BIN" run --auto --dir "$WORKSPACE"); TAIL=() ;;
    *)
      echo "$(date '+%Y-%m-%d %H:%M') gate: due=[$DUE] but harness '$HARNESS' is unknown (claude|codex|gemini|opencode)" >> "$LOGS_DIR/cron.log"
      postrun 127 ""
      exit 1 ;;
  esac
fi

# macOS caffeinate -i: hold an idle-sleep assertion for exactly the life of the harness
# process. Not on Linux/WSL (see header).
CAFF=()
[[ "$PLATFORM" == "macos" && -x "$CAFFEINATE" ]] && CAFF=("$CAFFEINATE" -i)

echo "$(date '+%Y-%m-%d %H:%M') gate: due=[$DUE] — starting $HARNESS$WAKE_NOTE" >> "$LOGS_DIR/cron.log"
# ${ARR[@]+...} keeps bash 3.2 (macOS /bin/bash) happy with an empty array under set -u
LOG_OFFSET="$(wc -c < "$LOGS_DIR/cron.log" | tr -d ' ')"
HARNESS_RC=0
${CAFF[@]+"${CAFF[@]}"} "${CMD[@]}" "$PROMPT" ${TAIL[@]+"${TAIL[@]}"} >> "$LOGS_DIR/cron.log" 2>&1 || HARNESS_RC=$?
echo "$(date '+%Y-%m-%d %H:%M') gate: harness exited rc=$HARNESS_RC" >> "$LOGS_DIR/cron.log"

# This run's harness output only (for the "Last output" line of a ❌ alert).
RUN_OUT="$(mktemp "${TMPDIR:-/tmp}/tick-run.XXXXXX")"
tail -c +"$((LOG_OFFSET + 1))" "$LOGS_DIR/cron.log" | grep -v ' gate: harness exited rc=' > "$RUN_OUT" || true
postrun "$HARNESS_RC" "$RUN_OUT"
rm -f "$RUN_OUT"
exit "$HARNESS_RC"

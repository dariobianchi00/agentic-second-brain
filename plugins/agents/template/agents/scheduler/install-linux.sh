#!/usr/bin/env bash
# Linux installer for the agent scheduler, the health check and the token check.
# Also works inside WSL when systemd or cron runs there (see install-windows.ps1 for the
# Task Scheduler route, which needs neither).
#
# What it installs (same schedule as the macOS launchd jobs):
#   tick    tick.sh every 10 min + shortly after login/boot   (always)
#   health  health.py hourly at :30 (daily report + tick-stale alert)   (if automations.json exists)
#   token   tokencheck.py hourly at :00 (runs once a week)              (if credentials.json exists)
#
# Backend: systemd user timers when `systemctl --user` works, else crontab lines.
#   systemd: units in ~/.config/systemd/user/<workspace>-{agent-scheduler,health-check,token-check}.{service,timer}
#            Output goes to the journal (journalctl --user -u <unit>); the scripts keep their own logs.
#            Persistent=true runs a slot missed while suspended or powered off once, on resume.
#            A timer never starts its service while the previous run is still active.
#            Timers run while you are logged in; to keep them running after logout:
#            `loginctl enable-linger "$USER"`.
#   cron:    one line per job, tagged `# <workspace>-<job>`. The tick line is wrapped in
#            `flock -n` so a long run never overlaps the next tick. cron skips slots while
#            the machine is suspended; the next tick catches up (gate.py looks back 7 days).
#
# Usage:
#   bash agents/scheduler/install-linux.sh                 # install (auto backend)
#   bash agents/scheduler/install-linux.sh --print         # print units + crontab lines, change nothing
#   bash agents/scheduler/install-linux.sh --uninstall     # remove timers/units and crontab lines
#   bash agents/scheduler/install-linux.sh --cron          # force cron   (--systemd forces systemd)
#   bash agents/scheduler/install-linux.sh tick health     # only these jobs (tick | health | token | all)
# Idempotent: re-running replaces the units / crontab lines it owns and nothing else.
# Not run automatically: review it (or its --print output), then run it yourself.
set -euo pipefail

usage() { sed -n '2,/^set -euo pipefail$/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'; }

PRINT=false; UNINSTALL=false; BACKEND=auto; JOBS=()
for arg in "$@"; do
  case "$arg" in
    --print|--dry-run) PRINT=true ;;
    --uninstall) UNINSTALL=true ;;
    --cron) BACKEND=cron ;;
    --systemd) BACKEND=systemd ;;
    tick|health|token) JOBS+=("$arg") ;;
    all) JOBS+=(tick health token) ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

SCHED="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$SCHED/../.." && pwd)"
SLUG="$(basename "$WORKSPACE" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n' '-')"
LOGS_DIR="$SCHED/logs"
STATE_DIR="$SCHED/state"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

name_of() {  # job → unit / marker base name
  case "$1" in
    tick) echo "${SLUG}-agent-scheduler" ;;
    health) echo "${SLUG}-health-check" ;;
    token) echo "${SLUG}-token-check" ;;
  esac
}

# Which jobs: explicit list, else tick + whichever registries exist (all three for --print/--uninstall).
EXPLICIT=false
if [[ ${#JOBS[@]} -gt 0 ]]; then
  EXPLICIT=true
else
  JOBS=(tick)
  if $PRINT || $UNINSTALL || [[ -f "$SCHED/automations.json" ]]; then JOBS+=(health); fi
  if $PRINT || $UNINSTALL || [[ -f "$SCHED/credentials.json" ]]; then JOBS+=(token); fi
fi
has_job() { local j; for j in "${JOBS[@]}"; do [[ "$j" == "$1" ]] && return 0; done; return 1; }

# ── escaping ─────────────────────────────────────────────────────────────
# systemd ExecStart= argument inside double quotes: \ " C-escaped, % and $ doubled.
sd_arg() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/%/%%/g' -e 's/\$/$$/g'; }
# crontab command: single-quote for sh, then escape % (cron turns a bare % into a newline).
cron_q() { printf "'%s'" "$(printf '%s' "$1" | sed -e "s/'/'\\\\''/g")" | sed -e 's/%/\\%/g'; }

# ── systemd units ────────────────────────────────────────────────────────
exec_line() {  # job → ExecStart value
  case "$1" in
    tick)   printf '/bin/bash -l "%s"' "$(sd_arg "$SCHED/tick.sh")" ;;
    health) printf '/usr/bin/env python3 "%s"' "$(sd_arg "$SCHED/health.py")" ;;
    token)  printf '/usr/bin/env python3 "%s"' "$(sd_arg "$SCHED/tokencheck.py")" ;;
  esac
}
log_of() {
  case "$1" in
    tick) echo "$LOGS_DIR/tick.out.log" ;;
    health) echo "$LOGS_DIR/health.timer.log" ;;
    token) echo "$LOGS_DIR/tokencheck.timer.log" ;;
  esac
}
service_unit() {  # stdout/stderr go to the journal: journalctl --user -u <name>
  local job="$1"
  printf '[Unit]\nDescription=Agent scheduler: %s (%s)\n\n[Service]\nType=oneshot\nExecStart=%s\n' \
    "$job" "$SLUG" "$(exec_line "$job")"
  # A scheduled Claude run can take a while: never time it out (health.py flags "hung" after 3 h awake).
  [[ "$job" == tick ]] && printf 'TimeoutStartSec=infinity\n'
  return 0
}
timer_unit() {
  local job="$1" name; name="$(name_of "$1")"
  printf '[Unit]\nDescription=Agent scheduler timer: %s (%s)\n\n[Timer]\n' "$job" "$SLUG"
  case "$job" in
    tick)   printf 'OnCalendar=*:0/10\nOnStartupSec=2min\n' ;;
    health) printf 'OnCalendar=*:30\n' ;;
    token)  printf 'OnCalendar=*:00\n' ;;
  esac
  printf 'Persistent=true\nAccuracySec=1min\nUnit=%s.service\n\n[Install]\nWantedBy=timers.target\n' "$name"
}

# ── crontab lines ────────────────────────────────────────────────────────
FLOCK="$(command -v flock || true)"
cron_cmd() {  # job → command part of the crontab line
  local lock=""
  case "$1" in
    tick)
      [[ -n "$FLOCK" ]] && lock="$(cron_q "$FLOCK") -n $(cron_q "$STATE_DIR/tick.lock") "
      printf '%s/bin/bash -l %s >> %s 2>&1' "$lock" "$(cron_q "$SCHED/tick.sh")" "$(cron_q "$(log_of tick)")" ;;
    health) printf '/usr/bin/env python3 %s >> %s 2>&1' "$(cron_q "$SCHED/health.py")" "$(cron_q "$(log_of health)")" ;;
    token)  printf '/usr/bin/env python3 %s >> %s 2>&1' "$(cron_q "$SCHED/tokencheck.py")" "$(cron_q "$(log_of token)")" ;;
  esac
}
cron_lines() {  # job → its crontab line(s), each ending in "# <marker>"
  local job="$1" marker; marker="$(name_of "$1")"
  case "$job" in
    tick)   printf '*/10 * * * * %s # %s\n@reboot sleep 120; %s # %s\n' "$(cron_cmd tick)" "$marker" "$(cron_cmd tick)" "$marker" ;;
    health) printf '30 * * * * %s # %s\n' "$(cron_cmd health)" "$marker" ;;
    token)  printf '0 * * * * %s # %s\n' "$(cron_cmd token)" "$marker" ;;
  esac
}
strip_markers() {  # stdin crontab → stdout without the selected jobs' lines
  local args=() j
  for j in "${JOBS[@]}"; do args+=(-e "# $(name_of "$j")\$"); done
  grep -v "${args[@]}" || true
}

# ── backend detection ────────────────────────────────────────────────────
systemd_user_ok() { command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; }
if [[ "$BACKEND" == auto ]]; then
  if systemd_user_ok; then BACKEND=systemd; elif command -v crontab >/dev/null 2>&1; then BACKEND=cron; else BACKEND=none; fi
fi

# ── --print ──────────────────────────────────────────────────────────────
if $PRINT; then
  echo "# install-linux.sh --print: nothing is changed."
  echo "# workspace: $WORKSPACE"
  echo "# backend on this machine: $BACKEND   (systemd when 'systemctl --user' works, else cron)"
  echo "# jobs: ${JOBS[*]}"
  if $UNINSTALL; then
    echo
    echo "# --uninstall would run:"
    for j in "${JOBS[@]}"; do
      n="$(name_of "$j")"
      echo "systemctl --user disable --now $n.timer"
      echo "rm -f '$UNIT_DIR/$n.timer' '$UNIT_DIR/$n.service'"
    done
    echo "systemctl --user daemon-reload"
    printf '# and remove crontab lines ending in:'; for j in "${JOBS[@]}"; do printf ' "# %s"' "$(name_of "$j")"; done; echo
    exit 0
  fi
  echo
  echo "# ===== systemd user units ($UNIT_DIR) ====="
  for j in "${JOBS[@]}"; do
    n="$(name_of "$j")"
    echo; echo "# ----- $n.service -----"; service_unit "$j"
    echo; echo "# ----- $n.timer -----"; timer_unit "$j"
  done
  echo
  echo "# then: systemctl --user daemon-reload && systemctl --user enable --now <name>.timer"
  echo
  echo "# ===== crontab fallback (crontab -l) ====="
  [[ -z "$FLOCK" ]] && echo "# flock not found on this machine: the tick line below has no overlap lock (install util-linux)"
  for j in "${JOBS[@]}"; do cron_lines "$j"; done
  exit 0
fi

# ── --uninstall ──────────────────────────────────────────────────────────
if $UNINSTALL; then
  if command -v systemctl >/dev/null 2>&1; then
    for j in "${JOBS[@]}"; do
      n="$(name_of "$j")"
      systemctl --user disable --now "$n.timer" >/dev/null 2>&1 || true
      if [[ -f "$UNIT_DIR/$n.timer" || -f "$UNIT_DIR/$n.service" ]]; then
        rm -f "$UNIT_DIR/$n.timer" "$UNIT_DIR/$n.service"; echo "Removed systemd units $n.{timer,service}"
      fi
    done
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi
  if command -v crontab >/dev/null 2>&1 && crontab -l >/dev/null 2>&1; then
    before="$(crontab -l)"; after="$(printf '%s\n' "$before" | strip_markers)"
    if [[ "$before" != "$after" ]]; then printf '%s\n' "$after" | crontab -; echo "Removed crontab lines for: ${JOBS[*]}"; fi
  fi
  echo "Uninstalled (${JOBS[*]}). Logs and state in $SCHED are kept."
  exit 0
fi

# ── install ──────────────────────────────────────────────────────────────
[[ -f "$WORKSPACE/agents/scheduled-tasks.md" ]] || { echo "Error: cannot find agents/scheduled-tasks.md in $WORKSPACE"; exit 1; }
[[ -x "$SCHED/tick.sh" ]] || { echo "Error: $SCHED/tick.sh missing or not executable (chmod +x it)"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Error: python3 not found"; exit 1; }
if [[ "$BACKEND" == none ]]; then
  echo "Error: neither 'systemctl --user' nor crontab is available. Install cron (e.g. the cron or cronie package) or enable systemd."
  exit 1
fi
if has_job health; then
  [[ -f "$SCHED/automations.json" ]] || { echo "Error: $SCHED/automations.json missing (copy automations.example.json and edit it)"; exit 1; }
  echo "Pre-flight: health.py dry run (nothing sent, no state written)"
  python3 "$SCHED/health.py" --dry-run --force-daily --assume-awake >/dev/null || { echo "Error: health.py dry run failed, not installing"; exit 1; }
fi
if has_job token; then
  [[ -f "$SCHED/credentials.json" ]] || { echo "Error: $SCHED/credentials.json missing (copy credentials.example.json and edit it)"; exit 1; }
  echo "Pre-flight: tokencheck.py dry run (nothing sent, no state written)"
  python3 "$SCHED/tokencheck.py" --dry-run --assume-awake >/dev/null || { echo "Error: tokencheck.py dry run failed, not installing"; exit 1; }
fi
$EXPLICIT || { [[ -f "$SCHED/automations.json" ]] || echo "Skipping health: no automations.json"; [[ -f "$SCHED/credentials.json" ]] || echo "Skipping token: no credentials.json"; }

mkdir -p "$LOGS_DIR" "$STATE_DIR"
echo "Workspace: $WORKSPACE"
echo "Backend:   $BACKEND"

# Drop this workspace's crontab lines for these jobs either way (no double scheduling).
if command -v crontab >/dev/null 2>&1 && crontab -l >/dev/null 2>&1; then
  CURRENT="$(crontab -l)"
else
  CURRENT=""
fi
KEPT="$(printf '%s\n' "$CURRENT" | strip_markers | sed -e '/^$/d')"

if [[ "$BACKEND" == systemd ]]; then
  if [[ -n "$CURRENT" && "$KEPT" != "$(printf '%s\n' "$CURRENT" | sed -e '/^$/d')" ]]; then
    printf '%s\n' "$KEPT" | crontab -; echo "Removed old crontab lines for: ${JOBS[*]}"
  fi
  mkdir -p "$UNIT_DIR"
  for j in "${JOBS[@]}"; do
    n="$(name_of "$j")"
    service_unit "$j" > "$UNIT_DIR/$n.service"
    timer_unit "$j" > "$UNIT_DIR/$n.timer"
  done
  systemctl --user daemon-reload
  for j in "${JOBS[@]}"; do
    n="$(name_of "$j")"
    systemctl --user enable --now "$n.timer" >/dev/null
    echo "Installed $UNIT_DIR/$n.timer"
  done
  echo "Verify: systemctl --user list-timers | grep $SLUG"
  if command -v loginctl >/dev/null 2>&1 && [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || true)" != "yes" ]]; then
    echo "Note: timers run only while you are logged in. To keep them running: loginctl enable-linger \"$USER\""
  fi
else
  [[ -n "$FLOCK" ]] || echo "Warning: flock not found (util-linux). A tick that runs longer than 10 min may overlap the next one."
  { [[ -n "$KEPT" ]] && printf '%s\n' "$KEPT"; for j in "${JOBS[@]}"; do cron_lines "$j"; done; } | crontab -
  for j in "${JOBS[@]}"; do echo "Installed crontab line(s) # $(name_of "$j")"; done
  echo "Verify: crontab -l | grep $SLUG"
fi
echo "Logs: $LOGS_DIR/cron.log (one gate line per tick)$([[ "$BACKEND" == systemd ]] && echo "; timer output: journalctl --user -u $SLUG-agent-scheduler")"
echo "Remove: bash $SCHED/install-linux.sh --uninstall"

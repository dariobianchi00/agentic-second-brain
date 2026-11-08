#!/usr/bin/env bash
# Plain-cron installer for the scheduler tick, kept for older instructions that call it.
# It now forwards to `install-linux.sh --cron tick`: one crontab line every 10 minutes
# (plus @reboot), wrapped in flock, replacing any line an older setup.sh wrote.
# Works on any Unix with crontab. Prefer:
#   macOS   bash agents/scheduler/install-launchd.sh
#   Linux   bash agents/scheduler/install-linux.sh        (systemd user timers, cron fallback)
#   Windows install-windows.ps1 (Task Scheduler → WSL)
#
# Usage: bash agents/scheduler/setup.sh [--print | --uninstall]
set -euo pipefail
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install-linux.sh" --cron tick "$@"

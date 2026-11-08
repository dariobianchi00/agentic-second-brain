"""Tests for the platform branches: macOS / Linux / WSL.
Simulates the platform with SCHED_PLATFORM=macos|linux|wsl; fake pmset, caffeinate,
systemctl, crontab, schtasks and flock; temp workspaces only. Nothing is installed
(the installers run in --print mode, or against a fake crontab), nothing is sent.
This does NOT prove the Linux/Windows installers work on a real machine: it checks the
generated units, crontab lines and task commands, and the platform logic in the scripts.
Run: python3 -I agents/scheduler/test_platform.py
"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import health  # noqa: E402

TICK = os.path.join(HERE, "tick.sh")
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    if not cond:
        print(f"FAIL  {name}  {str(detail)[:800]}")


def script(path, body):
    with open(path, "w") as f:
        f.write(body)
    os.chmod(path, 0o755)
    return path


TMP = tempfile.mkdtemp(prefix="platform-test-")
j = lambda *p: os.path.join(TMP, *p)
CLEAN = {k: v for k, v in os.environ.items() if k not in (
    "SCHED_PLATFORM", "TICK_SKIP_WAKE_CHECK", "SCHED_TICK_STARTED", "SCHED_TICK_ID", "SCHED_MAX_ATTEMPTS", "AGENT_HARNESS")}

# ───── 1. tick.sh wake probe per platform ─────
PMSET = '#!/bin/bash\necho "Current System Capabilities are: $PMSET_CAPS"\n'
script(j("pmset"), PMSET)


def wake(platform, pmset=j("pmset"), caps="CPU Graphics Audio Network"):
    e = dict(CLEAN, SCHED_PLATFORM=platform, TICK_PMSET_BIN=pmset, PMSET_CAPS=caps, SCHED_LOGS_DIR=j("wake-logs"))
    return subprocess.run(["/bin/bash", TICK, "--wake-check"], env=e, capture_output=True, text=True).stdout


out = wake("linux", pmset=j("missing-pmset"))
check("tick linux: no pmset needed, assume awake (rc=0)", "rc=0" in out and "no wake probe on linux" in out, out)
out = wake("wsl", pmset=j("missing-pmset"))
check("tick wsl: assume awake (rc=0)", "rc=0" in out and "no wake probe on wsl" in out, out)
out = wake("linux", caps="CPU Network")
check("tick linux: pmset DarkWake output ignored", "rc=0" in out, out)
out = wake("macos", pmset=j("missing-pmset"))
check("tick macos: pmset missing → probe error, fail open (rc=2)", "rc=2" in out and "missing" in out, out)
out = wake("macos", caps="CPU Network")
check("tick macos: DarkWake → rc=1", "rc=1" in out and "DarkWake" in out, out)
out = wake("macos")
check("tick macos: full wake → rc=0", "rc=0" in out and "full wake" in out, out)

# ───── 2. tick.sh full run: caffeinate + wake deferral per platform ─────
REG = """# reg

### t1
- **Schedule:** `0 0 * * *`
- **Agent:** Coach
- **Execution:** direct
- **Enabled:** true
- **Last run:** 2020-01-01T00:00:00+00:00
"""
os.makedirs(j("ws", "personal", "coach"))
open(j("ws", "CONVENTIONS.md"), "w").write("---\nextends: plugin\n---\n# c\n")
script(j("stub.sh"), '#!/bin/bash\necho x >> "$STUB_COUNT"\nexit 0\n')
script(j("caffeinate"), '#!/bin/bash\necho x >> "$CAFF_MARK"\nshift\nexec "$@"\n')


def tick_run(platform, caps="CPU Graphics Audio Network"):
    d = tempfile.mkdtemp(dir=TMP)
    reg = os.path.join(d, "scheduled-tasks.md")
    open(reg, "w").write(REG)
    e = dict(CLEAN, SCHED_PLATFORM=platform, SCHED_REGISTER=reg, SCHED_LOGS_DIR=os.path.join(d, "logs"),
             SCHED_STATE_FILE=os.path.join(d, "attempts.json"), SCHED_RUNS_DIR=os.path.join(d, "runs"),
             NOTIFY_DRY_RUN="1", AGENT_HARNESS_CMD=j("stub.sh"), TICK_PMSET_BIN=j("pmset"), PMSET_CAPS=caps,
             TICK_CAFFEINATE_BIN=j("caffeinate"), CAFF_MARK=os.path.join(d, "caff"), STUB_COUNT=os.path.join(d, "count"))
    subprocess.run(["/bin/bash", TICK], env=e, capture_output=True, text=True)
    cron = open(os.path.join(d, "logs", "cron.log")).read()
    return os.path.exists(os.path.join(d, "count")), os.path.exists(os.path.join(d, "caff")), cron


ran, caff, cron = tick_run("linux", caps="CPU Network")
check("tick linux: harness runs even when pmset would say DarkWake", ran, cron)
check("tick linux: no caffeinate", not caff, cron)
ran, caff, cron = tick_run("wsl")
check("tick wsl: harness runs without caffeinate", ran and not caff, cron)
ran, caff, cron = tick_run("macos")
check("tick macos: harness runs under caffeinate", ran and caff, cron)
ran, caff, cron = tick_run("macos", caps="CPU Network")
check("tick macos: DarkWake → deferred, harness not started", not ran and "deferred" in cron, cron)

# ───── 3. health.py platform logic (in-process) ─────
def with_env(**kw):
    saved = {k: os.environ.get(k) for k in kw}
    os.environ.update({k: v for k, v in kw.items() if v is not None})
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
    return saved


def restore(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


PMSET_LOG = '#!/bin/bash\nif [ "$2" = "log" ]; then echo "2026-10-19 08:00:00 +0800 Wake                \tx"; else echo "Current System Capabilities are: CPU Network"; fi\n'
script(j("pmset-log"), PMSET_LOG)
s = with_env(SCHED_PLATFORM="linux", HEALTH_PMSET_BIN=j("pmset-log"))
check("health: SCHED_PLATFORM override", health.platform() == "linux")
aw, why = health.fully_awake_now()
check("health linux: awake assumed (pmset DarkWake ignored)", aw and "no wake probe on linux" in why, why)
check("health linux: pmset log not read", health.read_pmset_log() == "")
restore(s)
s = with_env(SCHED_PLATFORM="macos", HEALTH_PMSET_BIN=j("pmset-log"))
check("health macos: DarkWake → not awake", health.fully_awake_now()[0] is False)
check("health macos: pmset log read", "Wake" in health.read_pmset_log())
restore(s)
s = with_env(SCHED_PLATFORM=None)
check("health: detection on this machine", health.platform() == ("macos" if sys.platform == "darwin" else health.platform()))
restore(s)

# fake systemctl / crontab / schtasks: exit code from env
script(j("systemctl"), '#!/bin/bash\n[ "$3" = "$FAKE_ENABLED_UNIT" ]\n')
script(j("crontab"), '#!/bin/bash\n[ -f "$FAKE_CRONTAB" ] || exit 1\ncat "$FAKE_CRONTAB"\n')
script(j("schtasks.exe"), '#!/bin/bash\n[ "$3" = "$FAKE_WIN_TASK" ]\n')
open(j("crontab.txt"), "w").write("*/10 * * * * /bin/bash -l '/x/tick.sh' # ws-agent-scheduler\n")
open(j("plist"), "w").write("x")
FAKES = dict(HEALTH_SYSTEMCTL_BIN=j("systemctl"), HEALTH_CRONTAB_BIN=j("crontab"), HEALTH_SCHTASKS_BIN=j("schtasks.exe"),
             FAKE_CRONTAB=j("crontab.txt"))
ENTRY = {"id": "agent-scheduler", "kind": "timer-job", "plist": j("plist"), "systemd_timer": "ws-agent-scheduler.timer",
         "cron_marker": "ws-agent-scheduler", "windows_task": "ws-agent-scheduler", "checks": ["timer", "tick"]}


def timer(platform, entry, **kw):
    s = with_env(**dict(FAKES, SCHED_PLATFORM=platform, **kw))
    try:
        return health.check_timer(None, entry)
    finally:
        restore(s)


r, note = timer("macos", ENTRY)
check("timer macos: plist present", r is None and note == "plist present", note)
r, note = timer("macos", dict(ENTRY, plist=j("nope.plist")))
check("timer macos: plist missing → FAIL plist", r and r["code"] == "plist", r)
r, note = timer("macos", {"id": "x", "checks": ["timer"], "systemd_timer": "a.timer"})
check("timer macos: no plist field → skipped OK", r is None and "skipped" in note, note)
r, note = timer("linux", ENTRY, FAKE_ENABLED_UNIT="ws-agent-scheduler.timer")
check("timer linux: systemd timer enabled", r is None and "systemd timer" in note, note)
r, note = timer("linux", ENTRY, FAKE_ENABLED_UNIT="other")
check("timer linux: systemd not enabled but crontab line present → OK", r is None and "crontab" in note, note)
r, note = timer("linux", dict(ENTRY, cron_marker="ws-other"), FAKE_ENABLED_UNIT="other")
check("timer linux: neither → FAIL timer", r and r["code"] == "timer" and "install-linux.sh" in r["fix"], r)
r, note = timer("linux", dict(ENTRY, cron_marker="ws-other", fix={"timer": "MY-FIX"}), FAKE_ENABLED_UNIT="other")
check("timer linux: registry fix wins", r and r["fix"] == "MY-FIX", r)
r, note = timer("linux", {"id": "x", "checks": ["plist"], "plist": j("nope.plist")})
check("timer linux: only a plist field → skipped OK (old registries keep working)", r is None and "skipped" in note, note)
r, note = timer("linux", {"id": "x", "checks": ["timer"], "cron_marker": "ws-agent"})
check("timer linux: marker must match the whole tag", r is not None, (r, note))
r, note = timer("linux", {"id": "x", "checks": ["timer"], "systemd_timer": "ws-x.timer"},
                HEALTH_SYSTEMCTL_BIN=j("no-systemctl"), HOME=j("home"))
check("timer linux: no systemctl + no unit file → FAIL", r and r["code"] == "timer", r)
os.makedirs(j("home", ".config", "systemd", "user"))
open(j("home", ".config", "systemd", "user", "ws-x.timer"), "w").write("[Timer]\n")
r, note = timer("linux", {"id": "x", "checks": ["timer"], "systemd_timer": "ws-x.timer"},
                HEALTH_SYSTEMCTL_BIN=j("no-systemctl"), HOME=j("home"))
check("timer linux: no systemctl → unit file fallback", r is None, (r, note))
r, note = timer("wsl", ENTRY, FAKE_WIN_TASK="ws-agent-scheduler")
check("timer wsl: Windows task present", r is None and "scheduled task" in note, note)
r, note = timer("wsl", dict(ENTRY, cron_marker="ws-other"), FAKE_WIN_TASK="nope", FAKE_ENABLED_UNIT="nope")
check("timer wsl: task missing → FAIL with Windows fix", r and r["code"] == "timer" and "install-windows.ps1" in r["fix"], r)
r, note = timer("wsl", ENTRY, FAKE_WIN_TASK="nope", FAKE_ENABLED_UNIT="nope")
check("timer wsl: falls back to cron inside WSL", r is None and "crontab" in note, note)

# full dry run on "linux": wall-clock note, timer found, nothing written
os.makedirs(j("hc", "logs"))
open(j("hc", "reg.md"), "w").write("# reg\n")
open(j("hc", "cron.log"), "w").write("2026-10-20 09:20 gate: no tasks due\n")
json.dump({"version": 1, "scheduler_tasks": {"register": j("hc", "reg.md"), "cron_log": j("hc", "cron.log")},
           "automations": [dict(ENTRY, log=j("hc", "cron.log"))]}, open(j("hc", "automations.json"), "w"))
e = dict(CLEAN, **FAKES, SCHED_PLATFORM="linux", FAKE_ENABLED_UNIT="ws-agent-scheduler.timer",
         HEALTH_REGISTRY=j("hc", "automations.json"), HEALTH_STATE_FILE=j("hc", "state.json"), HEALTH_LOG=j("hc", "health.log"),
         HEALTH_PMSET_BIN=j("missing-pmset"), HEALTH_WORKSPACE=j("hc"), HEALTH_NETWORK="1", HEALTH_BOOTTIME="off",
         SCHED_REGISTER=j("hc", "reg.md"), SCHED_RUNS_DIR=j("hc", "runs"), SCHED_STATE_FILE=j("hc", "attempts.json"),
         NOTIFY_DRY_RUN="1")
e.pop("SCHED_LOGS_DIR", None)
r = subprocess.run([sys.executable, os.path.join(HERE, "health.py"), "--dry-run", "--force-daily", "--now", "2026-10-20T09:30:00+08:00"],
                   env=e, capture_output=True, text=True)
check("health linux dry run: exit 0", r.returncode == 0, r.stdout + r.stderr)
check("health linux dry run: wall-clock note", "no sleep data on linux" in r.stdout, r.stdout)
check("health linux dry run: timer + tick green", "✅ [general] agent-scheduler: last tick" in r.stdout, r.stdout)
check("health linux dry run: no state written", not os.path.exists(j("hc", "state.json")))

# ───── 4. install-linux.sh (print mode + fake crontab) ─────
WS = j("My Work 100%")
os.makedirs(os.path.join(WS, "agents"))
shutil.copytree(HERE, os.path.join(WS, "agents", "scheduler"),
                ignore=shutil.ignore_patterns("logs", "state", "runs", "__pycache__", "*.json", "notify.env"))
open(os.path.join(WS, "agents", "scheduled-tasks.md"), "w").write("# reg\n")
INST = os.path.join(WS, "agents", "scheduler", "install-linux.sh")
SETUP = os.path.join(WS, "agents", "scheduler", "setup.sh")
# Sandboxed PATH: symlinks to the core tools the installer needs, never the real
# crontab / systemctl / flock / loginctl. j("bin") adds fake crontab + flock on top.
os.makedirs(j("bin"))
os.makedirs(j("nobin"))
os.makedirs(j("core"))
for tool in ("bash", "sed", "grep", "tr", "basename", "dirname", "cat", "mkdir", "rm", "sleep", "uname", "env", "python3"):
    real = shutil.which(tool)
    if real:
        os.symlink(real, j("core", tool))
script(j("bin", "flock"), "#!/bin/bash\nshift 2\nexec \"$@\"\n")
script(j("bin", "crontab"), '#!/bin/bash\nif [ "$1" = "-l" ]; then [ -f "$FAKE_CRONTAB" ] || exit 1; cat "$FAKE_CRONTAB"; else cat > "$FAKE_CRONTAB"; fi\n')
base_path = j("core")
for forbidden in ("crontab", "systemctl", "flock", "loginctl"):
    assert not os.path.exists(j("core", forbidden)), forbidden


def inst(args, path, prog=INST, **kw):
    assert "/usr/bin" not in path.split(":") and "/bin" not in path.split(":"), path  # never reach a real crontab
    e = dict(CLEAN, PATH=path, HOME=j("home"), FAKE_CRONTAB=j("cron-installed.txt"), **kw)
    e.pop("XDG_CONFIG_HOME", None)
    return subprocess.run(["/bin/bash", prog] + args, env=e, capture_output=True, text=True)


r = inst(["--print"], j("nobin") + ":" + base_path)
p = r.stdout
check("linux --print: exit 0", r.returncode == 0, r.stderr)
check("linux --print: three services + timers", all(f"my-work-100--{n}.{k}" in p for n in ("agent-scheduler", "health-check", "token-check") for k in ("service", "timer")), p)
check("linux --print: tick every 10 min + at startup, persistent", "OnCalendar=*:0/10" in p and "OnStartupSec=2min" in p and p.count("Persistent=true") == 3, p)
check("linux --print: health :30, token :00", "OnCalendar=*:30" in p and "OnCalendar=*:00" in p, p)
check("linux --print: ExecStart quoted, % doubled", 'ExecStart=/bin/bash -l "' + WS.replace("%", "%%") + '/agents/scheduler/tick.sh"' in p, p)
check("linux --print: python jobs via /usr/bin/env python3", 'ExecStart=/usr/bin/env python3 "' in p, p)
check("linux --print: only tick has no timeout", p.count("TimeoutStartSec=infinity") == 1, p)
check("linux --print: cron lines escape % and carry markers",
      "My Work 100\\%/agents/scheduler/tick.sh'" in p and "# my-work-100--agent-scheduler" in p
      and "# my-work-100--health-check" in p and "# my-work-100--token-check" in p, p)
check("linux --print: cron tick every 10 min + @reboot", re.search(r"^\*/10 \* \* \* \* ", p, re.M) and "@reboot sleep 120; " in p, p)
check("linux --print: no flock → warning, no lock", "flock not found" in p and "flock" not in p.split("crontab fallback")[1].split("\n", 2)[2], p)
check("linux --print: changes nothing", not os.path.exists(j("home", ".config", "systemd", "user", "my-work-100--agent-scheduler.timer"))
      and not os.path.exists(j("cron-installed.txt")))
r = inst(["--print"], j("bin") + ":" + base_path)
check("linux --print: flock wraps the tick line", re.search(r"^\*/10 \* \* \* \* '[^']*flock' -n '[^']*tick\.lock' /bin/bash -l ", r.stdout, re.M), r.stdout)
r = inst(["--print", "--uninstall"], j("nobin") + ":" + base_path)
check("linux --print --uninstall: lists removals", "systemctl --user disable --now my-work-100--agent-scheduler.timer" in r.stdout
      and '"# my-work-100--token-check"' in r.stdout, r.stdout)
r = inst(["--bogus"], j("nobin") + ":" + base_path)
check("linux: unknown argument → exit 2", r.returncode == 2, r.stdout + r.stderr)

# cron install against a fake crontab (no systemctl on PATH)
open(j("cron-installed.txt"), "w").write("0 5 * * * /usr/bin/true # someone-else\n7 * * * * /old/tick.sh >> /old/log 2>&1 # my-work-100--agent-scheduler\n")
r = inst(["--cron"], j("bin") + ":" + base_path)
ct = open(j("cron-installed.txt")).read()
check("linux --cron install: exit 0", r.returncode == 0, r.stdout + r.stderr)
check("linux --cron install: foreign line kept, old setup.sh line replaced",
      "# someone-else" in ct and "/old/tick.sh" not in ct and ct.count("# my-work-100--agent-scheduler") == 2, ct)
check("linux --cron install: health/token skipped without registries", "health-check" not in ct and "Skipping health" in r.stdout, r.stdout)
r = inst(["--cron"], j("bin") + ":" + base_path)
check("linux --cron install: idempotent", open(j("cron-installed.txt")).read() == ct, open(j("cron-installed.txt")).read())
r = inst(["--uninstall"], j("bin") + ":" + base_path)
check("linux --uninstall: only our lines removed", open(j("cron-installed.txt")).read().strip() == "0 5 * * * /usr/bin/true # someone-else",
      open(j("cron-installed.txt")).read())
r = inst(["--print"], j("nobin") + ":" + base_path, prog=SETUP)
check("setup.sh forwards to install-linux.sh --cron tick", "jobs: tick" in r.stdout and "health-check" not in r.stdout, r.stdout + r.stderr)
r = inst([], j("nobin") + ":" + base_path)
check("linux install: no systemd and no crontab → clear error", r.returncode == 1 and "neither" in r.stdout, r.stdout)

# ───── 5. install-windows.ps1 (static; -Print run only when pwsh is installed) ─────
ps = open(os.path.join(HERE, "install-windows.ps1"), encoding="utf-8").read()
for needle, what in (("SupportsShouldProcess", "-WhatIf support"), ("[switch]$Print", "-Print"), ("[switch]$Uninstall", "-Uninstall"),
                     ("Unregister-ScheduledTask", "uninstall cmdlet"), ("-MultipleInstances IgnoreNew", "no overlap"),
                     ("-StartWhenAvailable", "catch up after sleep"), ("'-e', 'bash', '-lc'", "wsl.exe -e bash -lc (pre-flight)"),
                     ('-e bash -lc `"', "wsl.exe -e bash -lc (task)"), ("New-TimeSpan -Minutes 10", "10-minute tick"),
                     ("-AtLogOn", "tick at logon"), ("INSIDE the WSL distro", "Claude Code inside WSL")):
    check(f"windows ps1: {what}", needle in ps, needle)


def win_argv(cmdline):
    """Split a command line the way the MS C runtime / CommandLineToArgvW does."""
    args, cur, i, inq, have = [], "", 0, False, False
    while i < len(cmdline):
        c = cmdline[i]
        if c == "\\":
            n = 0
            while i < len(cmdline) and cmdline[i] == "\\":
                n += 1; i += 1
            if i < len(cmdline) and cmdline[i] == '"':
                cur += "\\" * (n // 2)
                if n % 2:
                    cur += '"'; i += 1
            else:
                cur += "\\" * n
            have = True
            continue
        if c == '"':
            inq = not inq; have = True
        elif c in " \t" and not inq:
            if have:
                args.append(cur); cur, have = "", False
        else:
            cur += c; have = True
        i += 1
    if have:
        args.append(cur)
    return args


pwsh = shutil.which("pwsh")
if pwsh:
    r = subprocess.run([pwsh, "-NoProfile", "-File", os.path.join(HERE, "install-windows.ps1"), "-Print",
                        "-SchedulerDir", "/home/u/My Work/agents/scheduler"], capture_output=True, text=True)
    check("windows -Print: exit 0", r.returncode == 0, r.stdout + r.stderr)
    m = re.search(r"^Arguments: (.*)$", r.stdout, re.M)
    argv = win_argv(m.group(1)) if m else []
    check("windows -Print: bash command is one argv entry for wsl.exe",
          argv[:3] == ["-e", "bash", "-lc"] and len(argv) == 4 and "'/home/u/My Work/agents/scheduler/tick.sh'" in argv[3], argv)
else:
    print("note: pwsh not installed: install-windows.ps1 -Print not executed (static checks only)")
check("win_argv sanity", win_argv('-e bash -lc "a \'b c\' 2>&1"') == ["-e", "bash", "-lc", "a 'b c' 2>&1"])

shutil.rmtree(TMP, ignore_errors=True)
passed = sum(1 for _, ok in results if ok)
print(f"{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)

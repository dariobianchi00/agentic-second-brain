#!/usr/bin/env python3
"""Daily automation health check. Plain script — no Claude. macOS only (pmset, launchd).

Reads the registry (automations.json; start from automations.example.json) + every enabled
task in agents/scheduled-tasks.md and checks: ran in its window · last status not failed ·
retry cap not reached · output artifact fresh · log fresh · server answers · launchd plist
present · MCP server registered / credential files present / endpoint reachable · scheduler
still ticking.

Sleep-aware: a laptop is often asleep overnight and catches up on wake. "Missed" and "stale"
are judged in AWAKE time, not wall-clock: full-wake intervals are rebuilt from `pmset -g log`
(Wake [CDNVA] → next Sleep/DarkWake/Shutdown; DarkWake does not count, the scheduler defers
in DarkWake by design). A task due at 07:00 with the lid closed until 11:28 is "missed" only
once the Mac has been fully awake for the grace window (scheduler tasks 90 min,
registry-tunable) after the slot. If the pmset log can't be read, it falls back to
wall-clock and says so in the message.

Schedule (launchd, hourly at :30 — install with install-health-launchd.sh):
  * every run, fully awake only: scheduler tick stale > 3 h of awake time → urgent alert
    (once per stale episode, repeated every resend_days while unchanged).
  * daily report: the first fully-awake run at/after 08:30. If an item is still inside its
    awake grace window ("pending"), the report waits for a later hourly run (until 20:30)
    so the day's ONE message carries everything.
  * notify.sh (Telegram, or the notify log when Telegram is not configured): only if a
    failure is new / changed, or an unchanged failure was last sent >= resend_days (3) ago.
    Monday always sends: an all-clear "N/N green" (proof of life) or the failure digest.
  * run record via runrecord.py write (task automation-health-check), one per scope that
    has findings (the default scope if all green); a scope's record only holds its own items.

Usage:
  health.py                       # scheduled run (launchd)
  health.py --dry-run [--force-daily] [--assume-awake]
                                  # print findings + the message; no send, no state, no records
  health.py --force-daily         # run the daily report now even if done / before 08:30
  --now ISO                       # pin "now" (tests)

Env overrides (tests): HEALTH_REGISTRY, HEALTH_STATE_FILE, HEALTH_LOG, HEALTH_PMSET_BIN,
HEALTH_CLAUDE_JSON, HEALTH_WORKSPACE, HEALTH_BOOTTIME (epoch, "off"), HEALTH_NETWORK (1/0),
SCHED_REGISTER, SCHED_RUNS_DIR, SCHED_STATE_FILE, SCHED_LOGS_DIR, SCHED_DEFAULT_SCOPE,
NOTIFY_SH, NOTIFY_DRY_RUN. Stdlib only, Python 3.9 (/usr/bin/python3).
"""
import argparse, datetime as dt, json, os, re, socket, subprocess, sys, tempfile
import urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # no __pycache__ in a synced vault
sys.path.insert(0, HERE)
import gate  # noqa: E402
import runrecord  # noqa: E402

TASK_ID = "automation-health-check"
OK, FAIL, WARN, PENDING, SKIP = "OK", "FAIL", "WARN", "PENDING", "SKIP"
ICON = {OK: "✅", FAIL: "❌", WARN: "⚠️", PENDING: "⏳", SKIP: "·"}


def env(name, default):
    return os.environ.get(name) or default


WORKSPACE = lambda: env("HEALTH_WORKSPACE", os.path.dirname(os.path.dirname(HERE)))
REGISTRY = lambda: env("HEALTH_REGISTRY", os.path.join(HERE, "automations.json"))
STATE_FILE = lambda: env("HEALTH_STATE_FILE", os.path.join(HERE, "state", "health.json"))
HEALTH_LOG = lambda: env("HEALTH_LOG", os.path.join(HERE, "logs", "health.log"))
PMSET = lambda: env("HEALTH_PMSET_BIN", "/usr/bin/pmset")
CLAUDE_JSON = lambda: env("HEALTH_CLAUDE_JSON", os.path.expanduser("~/.claude.json"))
RUNS_DIR = lambda: env("SCHED_RUNS_DIR", os.path.join(HERE, "runs"))
ATTEMPTS = lambda: env("SCHED_STATE_FILE", gate.DEFAULT_STATE)
NOTIFY = lambda: env("NOTIFY_SH", os.path.join(HERE, "notify.sh"))
DEF = lambda: runrecord.default_scope()
DELIVERED = runrecord.DELIVERED


def resolve(p, date=None):
    if date:
        p = p.replace("{date}", date)
    p = os.path.expanduser(p)
    return p if os.path.isabs(p) else os.path.join(WORKSPACE(), p)


def rel(p):
    ws = WORKSPACE()
    return os.path.relpath(p, ws) if os.path.abspath(p).startswith(ws + os.sep) else p


def mtime(p, tz):
    try:
        return dt.datetime.fromtimestamp(os.path.getmtime(p), tz)
    except OSError:
        return None


def hm(d):
    return d.strftime("%a %H:%M") if d else "?"


def hrs(sec):
    return f"{sec / 3600:.1f}h"


# ───────────────────────── power timeline (sleep handling) ─────────────────────────
EV = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}) (.+?)\s*\t")
ANYTS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}) ")


class Power:
    """Full-wake intervals. awake(a, b) = seconds the Mac was fully awake in [a, b]."""

    def __init__(self, intervals, coverage, blind, note=""):
        self.intervals, self.coverage, self.blind, self.note = intervals, coverage, blind, note

    def awake(self, a, b):
        if b <= a:
            return 0.0
        if self.blind:
            return (b - a).total_seconds()
        tot = 0.0
        for s, e in self.intervals:
            lo, hi = max(a, s), min(b, e)
            if hi > lo:
                tot += (hi - lo).total_seconds()
        return tot


def parse_power(text, now, awake_now, boottime=None):
    events, coverage = [], None
    for line in text.splitlines():
        m = ANYTS.match(line)
        if not m:
            continue
        if coverage is None:
            coverage = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z")
        m = EV.match(line)
        if not m:
            continue
        typ = m.group(2).strip()
        if typ in ("Wake", "DarkWake", "Sleep") or typ.startswith("Shutdown") or typ == "Restart":
            events.append((dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z"), typ))
    if not events:
        return Power([], None, True, "sleep data unavailable — judged on wall-clock time")
    if boottime and coverage and boottime > coverage:
        events.append((boottime, "Boot"))
    events.sort(key=lambda x: x[0])
    intervals, state, start = [], None, None
    for t, typ in events:
        if typ in ("Wake", "Boot"):
            if state != "full":
                state, start = "full", t
        else:
            if state == "full":
                intervals.append((start, t))
            state = "dark" if typ == "DarkWake" else "asleep"
    if state == "full":
        intervals.append((start, now))
    elif awake_now:  # fully awake now but the log hasn't caught up: count from the last event
        intervals.append((events[-1][0], now))
    return Power(intervals, coverage, False)


def read_pmset_log():
    try:
        r = subprocess.run([PMSET(), "-g", "log"], capture_output=True, text=True, timeout=60)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def fully_awake_now():
    """(bool, reason). Same signal as tick.sh: Graphics capability = full wake. Fails open."""
    try:
        r = subprocess.run([PMSET(), "-g", "systemstate"], capture_output=True, text=True, timeout=20)
        m = re.search(r"^Current System Capabilities are:\s*(.*)$", r.stdout, re.M)
        if not m:
            return True, "probe error (failed open)"
        caps = m.group(1).split()
        return ("Graphics" in caps), " ".join(caps)
    except (OSError, subprocess.TimeoutExpired) as e:
        return True, f"probe error (failed open): {e}"


def boottime(tz):
    v = os.environ.get("HEALTH_BOOTTIME")
    if v == "off":
        return None
    try:
        if v:
            return dt.datetime.fromtimestamp(float(v), tz)
        out = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"sec = (\d+)", out)
        return dt.datetime.fromtimestamp(int(m.group(1)), tz) if m else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


# ───────────────────────── scheduler evidence ─────────────────────────
GATE_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) gate: (.*)$")


def cron_state(path, tz):
    """last_tick, running=(start, [due]) or None, deferred=[(time, [due])]."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 1024 * 1024))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return None, None, []
    last, running, deferred = None, None, []
    for line in text.splitlines():
        m = GATE_LINE.match(line)
        if not m:
            continue
        t = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        msg = m.group(2)
        last = t
        due = re.search(r"due=\[([^\]]*)\]", msg)
        due = due.group(1).split() if due else []
        if "— starting" in msg or "- starting" in msg:
            running = (t, due)
            continue
        # launchd never runs two ticks of the job at once, so ANY later gate line means the
        # previous harness is gone (older tick.sh versions logged no "harness exited").
        running = None
        if "deferred" in msg:
            deferred.append((t, due))
    return last, running, deferred


def run_records(task, scope, tz):
    """[(started, status, path)] sorted by started."""
    out = []
    root = os.path.join(RUNS_DIR(), scope)
    if not os.path.isdir(root):
        return out
    pat = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}_" + re.escape(task) + r"(_\d+)?\.md$")
    for month in sorted(os.listdir(root)):
        d = os.path.join(root, month)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not pat.match(name):
                continue
            p = os.path.join(d, name)
            try:
                txt = open(p, encoding="utf-8").read(2000)
            except OSError:
                continue
            st = re.search(r"^status:\s*(\S+)", txt, re.M)
            sd = re.search(r"^started:\s*(\S+)", txt, re.M)
            try:
                started = runrecord.parse_iso(sd.group(1)) if sd else None
            except ValueError:
                started = None
            if started:
                out.append((started.astimezone(tz), st.group(1) if st else "", p))
    return sorted(out)


SECTION = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2})")


def classify(text):
    low = text.lower()
    if "fail" in low:
        return "failed"
    if "partial" in low:
        return "partial"
    if "skip" in low:
        return None
    if any(w in low for w in ("success", "ok", "done", "no-op")):
        return "success"
    return None


def log_rows(task, tz, since):
    """Status rows for `task` in the monthly scheduler log(s), in sections at/after `since`.
    Fallback evidence for tasks that log a row but write no run record."""
    out = []
    logs = env("SCHED_LOGS_DIR", os.path.join(HERE, "logs"))
    months = sorted({since.strftime("%Y-%m"), dt.datetime.now(tz).strftime("%Y-%m")})
    for m in months:
        try:
            lines = open(os.path.join(logs, m + ".md"), encoding="utf-8").read().splitlines()
        except OSError:
            continue
        sec = None
        for line in lines:
            s = SECTION.match(line)
            if s:
                sec = dt.datetime.strptime(s.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                continue
            if sec is None or sec < since or not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            names = [n.strip().strip("`") for n in cells[0].split("·")]
            if task in names:
                st = classify(cells[1])
                if st:
                    out.append((sec, st, None))
    return out


# ───────────────────────── checks ─────────────────────────
class Ctx:
    def __init__(self, now, power, registry, network):
        self.now, self.power, self.reg, self.network = now, power, registry, network
        self.tz = now.tzinfo
        st = registry.get("scheduler_tasks", {})
        self.register = env("SCHED_REGISTER", resolve(st.get("register", "agents/scheduled-tasks.md")))
        logs = os.environ.get("SCHED_LOGS_DIR")
        self.cron_log = os.path.join(logs, "cron.log") if logs else resolve(st.get("cron_log", "agents/scheduler/logs/cron.log"))
        self.last_tick, self.running, self.deferred = cron_state(self.cron_log, self.tz)


def R(item, scope, status, code="", detail="", since=None, fix="", severity="fail"):
    if status == FAIL and severity == "warn":
        status = WARN
    return {"item": item, "scope": scope, "status": status, "code": code, "detail": detail,
            "since": since.isoformat(timespec="minutes") if isinstance(since, dt.datetime) else since,
            "fix": fix}


def fix_for(entry_fix, code, fallback=None):
    entry_fix = entry_fix or {}
    return entry_fix.get(code) or (fallback or {}).get(code) or entry_fix.get("default") or ""


def check_tick(ctx, a):
    """Scheduler hasn't ticked in > N h of AWAKE time."""
    limit = float(ctx.reg.get("tick_stale_awake_hours", 3)) * 3600
    scope, fx = a.get("scope", DEF()), a.get("fix")
    if ctx.running:
        start, due = ctx.running
        aw = ctx.power.awake(start, ctx.now)
        if aw > limit:
            return R(a["id"], scope, FAIL, "hung", f"harness started {hm(start)} for [{' '.join(due)}], no exit after {hrs(aw)} awake",
                     start, fix_for(fx, "hung"))
        return R(a["id"], scope, OK, detail=f"harness running since {hm(start)}")
    if ctx.last_tick is None:
        return R(a["id"], scope, FAIL, "tick-stale", f"no gate lines in {rel(ctx.cron_log)}", None, fix_for(fx, "tick-stale"))
    aw = ctx.power.awake(ctx.last_tick, ctx.now)
    if aw > limit:
        return R(a["id"], scope, FAIL, "tick-stale", f"last tick {hm(ctx.last_tick)}, {hrs(aw)} awake since (limit {limit / 3600:g}h)",
                 ctx.last_tick, fix_for(fx, "tick-stale"))
    return R(a["id"], scope, OK, detail=f"last tick {hm(ctx.last_tick)}")


def check_plist(ctx, a):
    p = resolve(a["plist"])
    if os.path.exists(p):
        return None
    return R(a["id"], a.get("scope", DEF()), FAIL, "plist", f"plist missing: {p}", None, fix_for(a.get("fix"), "plist"))


def check_slot_job(ctx, a):
    """launchd calendar job: output (or log) written after the latest slot, once awake grace passed."""
    scope, fx = a.get("scope", DEF()), a.get("fix")
    slot = gate.task_slot(f"- **Schedule:** `{a['schedule']}`", ctx.now)
    if slot is None:
        return R(a["id"], scope, OK, detail="no slot in the last 7 days")
    date = slot.strftime("%Y-%m-%d")
    outs = [resolve(p, date) for p in a.get("outputs", [])]
    om = [mtime(p, ctx.tz) for p in outs]
    lm = mtime(resolve(a["log"]), ctx.tz) if a.get("log") else None
    grace = float(a.get("grace_awake_min", 30)) * 60
    aw = ctx.power.awake(slot, ctx.now)
    if outs and all(m and m >= slot for m in om):
        return R(a["id"], scope, OK, detail=f"output {hm(min(om))} ≥ slot {hm(slot)}")
    if aw < grace:
        return R(a["id"], scope, PENDING, detail=f"slot {hm(slot)}: {aw / 60:.0f}/{grace / 60:.0f} awake min elapsed")
    if lm and lm >= slot:
        stale = [rel(p) for p, m in zip(outs, om) if not (m and m >= slot)]
        return R(a["id"], scope, FAIL, "failed", f"ran (log {hm(lm)}) but did not write {', '.join(stale)}", slot, fix_for(fx, "failed"))
    return R(a["id"], scope, FAIL, "missed", f"missed: slot {hm(slot)} not run after {hrs(aw)} awake", slot, fix_for(fx, "missed"))


def check_http(ctx, a):
    scope, url = a.get("scope", DEF()), a["url"]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=5) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        return R(a["id"], scope, FAIL, "down", f"{url} not answering ({getattr(e, 'reason', e)})", None, fix_for(a.get("fix"), "down"))
    if code >= 500:
        return R(a["id"], scope, FAIL, "down", f"{url} HTTP {code}", None, fix_for(a.get("fix"), "down"))
    return R(a["id"], scope, OK, detail=f"HTTP {code}")


def mcp_config(name):
    try:
        d = json.load(open(CLAUDE_JSON(), encoding="utf-8"))
    except (OSError, ValueError):
        return None, "cannot read ~/.claude.json"
    if name in (d.get("mcpServers") or {}):
        return d["mcpServers"][name], ""
    ws = WORKSPACE()
    for proj, v in (d.get("projects") or {}).items():
        if (proj == ws or proj.startswith(ws + os.sep)) and name in ((v or {}).get("mcpServers") or {}):
            return v["mcpServers"][name], ""
    return None, "not registered"


def check_mcp(ctx, a):
    scope, fx, checks = a.get("scope", DEF()), a.get("fix"), a.get("checks", [])
    cfg, why = mcp_config(a["server"])
    if cfg is None:
        return R(a["id"], scope, FAIL, "mcp-registered", f"{a['server']}: {why}", None, fix_for(fx, "mcp-registered"))
    if "mcp-credentials" in checks:
        # env vars of the server config that name credential files: the entry's
        # `credential_env` list, else every env var ending in _PATH or _FILE
        envv = cfg.get("env") or {}
        keys = a.get("credential_env") or [k for k in envv if k.endswith(("_PATH", "_FILE"))]
        miss = [k for k in keys if k in envv and not os.path.exists(os.path.expanduser(envv[k]))]
        if miss:
            return R(a["id"], scope, FAIL, "mcp-credentials", f"{a['server']}: file missing for {', '.join(miss)}", None, fix_for(fx, "mcp-credentials"))
    if "mcp-reachable" in checks and cfg.get("url"):
        if not ctx.network:
            return R(a["id"], scope, SKIP, detail="network down — reachability not checked")
        try:
            urllib.request.urlopen(urllib.request.Request(cfg["url"], method="GET"), timeout=5).close()
        except urllib.error.HTTPError:
            pass  # any HTTP answer = reachable (auth not tested)
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            return R(a["id"], scope, FAIL, "mcp-reachable", f"{a['server']} endpoint unreachable ({getattr(e, 'reason', e)})", None, fix_for(fx, "mcp-reachable"))
    return R(a["id"], scope, OK, detail="registered")


def check_sched_tasks(ctx):
    st = ctx.reg.get("scheduler_tasks", {})
    try:
        text = open(ctx.register, encoding="utf-8").read()
    except OSError:
        return [R("scheduler-register", DEF(), FAIL, "register", f"cannot read {rel(ctx.register)}", None,
                  "Restore agents/scheduled-tasks.md")]
    attempts = gate.load_state(ATTEMPTS())
    cap = gate.max_attempts()
    out = []
    overrides = st.get("overrides", {})
    for tid, block in gate.parse_tasks(text):
        if not gate.enabled(block):
            continue  # disabled tasks are ignored
        ov = overrides.get(tid, {})
        fx = dict(st.get("fix", {}))
        fx.update(ov.get("fix", {}))
        scope = runrecord.scope_for(gate.field(block, "Agent"))
        slot = gate.task_slot(block, ctx.now)
        if slot is None:
            out.append(R(tid, scope, OK, detail="no slot in the last 7 days"))
            continue
        if gate.before_created(block, slot):
            out.append(R(tid, scope, OK, detail="new task: first slot not reached"))
            continue
        cond = gate.field(block, "Only if")
        if cond and not gate.only_if(cond, os.path.dirname(os.path.abspath(ctx.register))):
            out.append(R(tid, scope, OK, detail=f"idle: precondition not met ({cond.strip('`')})"))
            continue  # a task with no work (precondition false) is not "missed"
        key = gate.slot_key(slot)
        last = gate.parse_last(gate.field(block, "Last run"), ctx.tz)
        ran = last is not None and last.astimezone(ctx.tz) >= slot
        ev = [r for r in run_records(tid, scope, ctx.tz) if r[0] >= slot] + log_rows(tid, ctx.tz, slot)
        ev.sort(key=lambda r: (r[0], r[2] is not None))  # same time: run record wins
        status = ev[-1][1] if ev else None
        rec = next((r[2] for r in reversed(ev) if r[2]), None)
        where = f" → {rel(rec)}" if rec else ""
        e = attempts.get(tid)
        e = e if isinstance(e, dict) and e.get("slot") == key else {}
        n = int(e.get("attempts", 0) or 0)
        if n >= cap and not e.get("done") and not ran:
            out.append(R(tid, scope, FAIL, "retry-cap", f"{n}/{cap} failed attempts for the {hm(slot)} slot — held until next slot{where}",
                         e.get("last_attempt") or slot, fx.get("retry-cap", "")))
            continue
        if ran:
            stale = []
            for p in ov.get("outputs", []):
                fp = resolve(p, slot.strftime("%Y-%m-%d"))
                m = mtime(fp, ctx.tz)
                if not (m and m >= slot):
                    stale.append(rel(fp))
            if status == "failed":
                out.append(R(tid, scope, FAIL, "failed", f"last run ({hm(last)}) reported failed{where}", last, fx.get("failed", "")))
            elif stale and not (ov.get("output_on_news") and status == "success"):  # no news = no write
                out.append(R(tid, scope, FAIL, "output-stale", f"ran {hm(last)} but not refreshed: {', '.join(stale)}", last, fx.get("output-stale", "")))
            elif status == "partial":
                out.append(R(tid, scope, WARN, "partial", f"last run ({hm(last)}) partial{where}", last, fx.get("failed", "")))
            else:
                out.append(R(tid, scope, OK, detail=f"ran {hm(last)} for slot {hm(slot)}" + (f" ({status})" if status else "")))
            continue
        # Last run not updated for this slot
        if ctx.running and tid in ctx.running[1] and ctx.running[0] >= slot:
            out.append(R(tid, scope, PENDING, detail=f"running since {hm(ctx.running[0])}"))
            continue
        if status == "failed":
            out.append(R(tid, scope, FAIL, "failed", f"reported failed for the {hm(slot)} slot{where}", slot, fx.get("failed", "")))
            continue
        if e.get("done") or status in ("success", "partial"):
            out.append(R(tid, scope, WARN, "no-last-run", f"reported {status or 'done'} but Last run not updated{where}", slot, fx.get("no-record", "")))
            continue
        grace = float(ov.get("grace_awake_min", st.get("grace_awake_min", 90))) * 60
        aw = ctx.power.awake(slot, ctx.now)
        if aw < grace:
            out.append(R(tid, scope, PENDING, detail=f"due {hm(slot)}: {aw / 60:.0f}/{grace / 60:.0f} awake min elapsed"))
            continue
        nd = sum(1 for t, due in ctx.deferred if t >= slot and tid in due)
        extra = (f"; {nd} tick(s) deferred (DarkWake)" if nd else "") + (f"; {n} failed attempt(s)" if n else "")
        out.append(R(tid, scope, FAIL, "missed", f"missed: due {hm(slot)}, not run after {hrs(aw)} awake{extra}", slot, fx.get("missed", "")))
    return out


def run_checks(ctx):
    results = []
    for a in ctx.reg.get("automations", []):
        checks = a.get("checks", [])
        if not checks:
            continue
        if a["kind"] == "mcp":
            results.append(check_mcp(ctx, a))
            continue
        r = check_plist(ctx, a) if "plist" in checks else None
        if r is None:
            if "tick" in checks:
                r = check_tick(ctx, a)
            elif "slot" in checks:
                r = check_slot_job(ctx, a)
            elif "http" in checks:
                r = check_http(ctx, a)
            else:
                r = R(a["id"], a.get("scope", DEF()), OK, detail="plist present")
        results.append(r)
    results += check_sched_tasks(ctx)
    return results


# ───────────────────────── message / dedupe ─────────────────────────
def fkey(r):
    return f"{r['item']}|{r['code']}"


def short_since(s):
    return s[5:10] if s else "?"


def decide(results, state, today, resend_days):
    """→ (trigger: bool, new_keys: set). Trigger if any failure is new/changed, or an
    unchanged one was last sent >= resend_days ago."""
    known = state.get("failures", {})
    new, trigger = set(), False
    for r in results:
        if r["status"] != FAIL:
            continue
        k = fkey(r)
        if k not in known:
            new.add(k)
            trigger = True
            continue
        ls = known[k].get("last_sent")
        if not ls or (today - dt.date.fromisoformat(ls)).days >= resend_days:
            trigger = True
    return trigger, new


def compose(results, state, now, power, new_keys, scope=None):
    rs = [r for r in results if scope is None or r["scope"] == scope]
    counted = [r for r in rs if r["status"] != SKIP]
    fails = [r for r in rs if r["status"] == FAIL]
    warns = [r for r in rs if r["status"] == WARN]
    pend = [r for r in rs if r["status"] == PENDING]
    green = sum(1 for r in counted if r["status"] == OK)
    day = now.strftime("%Y-%m-%d %a")
    head = "✅" if not fails else "🩺"
    lines = [f"{head} Health check — {day} · {green}/{len(counted)} green"
             + (f" · {len(fails)} failing" if fails else "") + (f" · {len(warns)} warning(s)" if warns else "")
             + (f" · {len(pend)} pending" if pend else "")]
    known = state.get("failures", {})
    for r in fails:
        k = fkey(r)
        since = known.get(k, {}).get("first_seen") or r["since"] or now.isoformat(timespec="minutes")
        tag = " 🆕" if k in new_keys else f" · since {short_since(since)}"
        lines.append(f"❌ {r['item']} — {r['detail']}{tag}")
        if r["fix"]:
            lines.append(f"   fix: {r['fix']}")
    for r in warns:
        lines.append(f"⚠️ {r['item']} — {r['detail']}")
    for r in pend:
        lines.append(f"⏳ {r['item']} — {r['detail']}")
    cur = {fkey(r) for r in fails}
    resolved = sorted({k.split("|")[0] for k, v in known.items() if k not in cur and (scope is None or v.get("scope") == scope)})
    if resolved:
        lines.append("✅ resolved: " + ", ".join(resolved))
    if power.blind:
        lines.append(f"({power.note})")
    return "\n".join(lines)


def send(msg):
    try:
        r = subprocess.run(["/bin/bash", NOTIFY(), "-"], input=msg, text=True, capture_output=True, timeout=60)
        sys.stderr.write(r.stdout + r.stderr)
        return {0: "sent", 4: "logged"}.get(r.returncode, "failed")  # 4 = no Telegram, logged
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"health: notify error: {e}", file=sys.stderr)
        return "failed"


def write_record(scope, status, telegram, body, started=None):
    fd, tmp = tempfile.mkstemp(prefix="health-msg.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "runrecord.py"), "write", "--task", TASK_ID,
                            "--status", status, "--telegram", telegram, "--scope", scope, "--agent", "health-check",
                            "--message-file", tmp] + (["--started", started.isoformat()] if started else []), capture_output=True, text=True, timeout=60,
                           env={k: v for k, v in os.environ.items() if k not in ("SCHED_TICK_ID", "SCHED_TICK_STARTED")})
        return r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else f"(run record failed: {r.stderr.strip()[:200]})"
    finally:
        os.unlink(tmp)


def scope_status(results, scope):
    rs = [r for r in results if r["scope"] == scope]
    if any(r["status"] == FAIL for r in rs):
        return "failed"
    if any(r["status"] == WARN for r in rs):
        return "partial"
    return "success"


# ───────────────────────── state ─────────────────────────
def load_state():
    try:
        d = json.load(open(STATE_FILE(), encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    p = STATE_FILE()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".health.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


def log(line, now):
    p = HEALTH_LOG()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{now.strftime('%Y-%m-%d %H:%M')} health: {line}\n")
    except OSError:
        pass


def network_up():
    v = os.environ.get("HEALTH_NETWORK")
    if v in ("0", "1"):
        return v == "1"
    try:
        socket.setdefaulttimeout(5)
        socket.getaddrinfo("api.telegram.org", 443)
        return True
    except OSError:
        return False
    finally:
        socket.setdefaulttimeout(None)


def hhmm(s):
    h, m = s.split(":")
    return int(h), int(m)


# ───────────────────────── main ─────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="Daily automation health check (macOS)")
    ap.add_argument("--dry-run", action="store_true", help="print findings + message; no send, no state, no run records")
    ap.add_argument("--force-daily", action="store_true", help="run the daily report now")
    ap.add_argument("--assume-awake", action="store_true", help="skip the full-wake check")
    ap.add_argument("--now", help="ISO datetime (tests)")
    a = ap.parse_args(argv)

    now = dt.datetime.fromisoformat(a.now) if a.now else dt.datetime.now().astimezone().replace(microsecond=0)
    if now.tzinfo is None:
        now = now.astimezone()
    awake, why = (True, "assumed") if a.assume_awake else fully_awake_now()
    if not awake:
        log(f"deferred: not fully awake ({why})", now)
        if a.dry_run:
            print(f"deferred: not fully awake ({why})")
        return 0
    try:
        registry = json.load(open(REGISTRY(), encoding="utf-8"))
    except (OSError, ValueError) as e:
        msg = f"❌ {TASK_ID} — {now:%Y-%m-%d}\nRegistry unreadable: {e}\n   fix: check {rel(REGISTRY())} is valid JSON"
        if a.dry_run:
            print(msg)
            return 1
        send(msg)
        log(f"registry unreadable: {e}", now)
        return 1

    power = parse_power(read_pmset_log(), now, awake, boottime(now.tzinfo))
    ctx = Ctx(now, power, registry, network_up())
    state = {} if a.dry_run and not os.path.exists(STATE_FILE()) else load_state()
    today = now.date()
    resend = int(registry.get("resend_days", 3))

    # Every run: scheduler tick staleness → urgent alert, once per stale episode.
    sched = next((x for x in registry.get("automations", []) if "tick" in x.get("checks", [])), None)
    tick_r = check_tick(ctx, sched) if sched else None
    tick_msg = None
    if tick_r and tick_r["status"] == FAIL:
        ta = state.get("tick_alert", {})
        episode = tick_r["since"] or "none"
        if ta.get("episode") != episode or (today - dt.date.fromisoformat(ta.get("sent", "1970-01-01"))).days >= resend:
            tick_msg = (f"🚨 Scheduler not ticking — {now:%Y-%m-%d %H:%M}\n{tick_r['detail']}\n   fix: {tick_r['fix']}"
                        + (f"\n({power.note})" if power.blind else ""))
    if tick_msg:
        if a.dry_run:
            print("--- tick-stale alert (would send) ---\n" + tick_msg)
        else:
            tg = send(tick_msg)
            write_record(sched.get("scope", DEF()), "failed", tg, tick_msg, now)
            if tg in DELIVERED:
                state["tick_alert"] = {"episode": tick_r["since"] or "none", "sent": today.isoformat()}
            log(f"tick-stale alert: {tick_r['detail']} (telegram {tg})", now)
    elif tick_r and tick_r["status"] != FAIL:
        state.pop("tick_alert", None)

    # Daily report gate
    dh, dm = hhmm(registry.get("daily_at", "08:30"))
    ch, cm = hhmm(registry.get("daily_cutoff", "20:30"))
    daily = state.get("daily", {})
    done_today = daily.get("date") == today.isoformat() and daily.get("done")
    if not a.force_daily and (done_today or (now.hour, now.minute) < (dh, dm)):
        if not a.dry_run:
            state["last_run"] = now.isoformat()
            save_state(state)
            if not tick_msg:
                log("ok (tick check only)" if not done_today else "ok (daily already done; tick check only)", now)
        elif not tick_msg:
            print("daily report not due (use --force-daily); tick check: " + (tick_r["detail"] if tick_r else "n/a"))
        return 0

    results = run_checks(ctx)
    pend = [r for r in results if r["status"] == PENDING]
    if pend and not a.force_daily and (now.hour, now.minute) < (ch, cm):
        if not a.dry_run:
            state["last_run"] = now.isoformat()
            state["daily"] = {"date": today.isoformat(), "done": False, "pending": [r["item"] for r in pend],
                              "tries": daily.get("tries", 0) if daily.get("date") == today.isoformat() else 0}
            save_state(state)
            log(f"daily waiting: {len(pend)} pending ({', '.join(r['item'] for r in pend)})", now)
        return 0

    trigger, new_keys = decide(results, state, today, resend)
    monday = now.weekday() == 0
    fails = [r for r in results if r["status"] == FAIL]
    send_it = trigger or monday
    msg = compose(results, state, now, power, new_keys)
    if not fails and monday:
        pass  # Monday all-clear: compose() already says "N/N green"
    elif fails and not trigger and monday:
        msg += f"\n(alive check — failures above unchanged since last report)"

    if a.dry_run:
        print("--- findings ---")
        for r in results:
            print(f"{ICON[r['status']]} [{r['scope']}] {r['item']}: {r['code'] + ' — ' if r['code'] else ''}{r['detail']}")
        print(f"--- power: {'BLIND ' + power.note if power.blind else f'{len(power.intervals)} full-wake intervals since {power.coverage:%Y-%m-%d %H:%M}'}")
        print(f"--- decision: {'SEND' if send_it else 'no message'} (trigger={trigger}, monday={monday}, new={sorted(new_keys)})")
        print("--- message ---\n" + msg)
        return 0

    tg = send(msg) if send_it else "none"
    if fails and not send_it:
        tg = "suppressed"
    # run records: one per scope with findings (scope-firewalled body); default scope if all clear
    scopes = sorted({r["scope"] for r in results if r["status"] in (FAIL, WARN)}) or [DEF()]
    recs = []
    for sc in scopes:
        body = compose(results, state, now, power, new_keys, scope=sc)
        if tg == "suppressed":
            body += "\n\n(Telegram suppressed: failures unchanged and reported < %d days ago.)" % resend
        elif tg == "none":
            body += "\n\n(No Telegram: nothing failing, not Monday.)"
        recs.append(write_record(sc, scope_status(results, sc), tg, body, now))

    # state: failures carried with first_seen / last_sent
    known = state.get("failures", {})
    newf = {}
    for r in fails:
        k = fkey(r)
        prev = known.get(k, {})
        newf[k] = {"scope": r["scope"], "code": r["code"], "detail": r["detail"],
                   "first_seen": prev.get("first_seen") or r["since"] or now.isoformat(timespec="minutes"),
                   "last_sent": today.isoformat() if tg in DELIVERED else prev.get("last_sent")}
    tries = (daily.get("tries", 0) if daily.get("date") == today.isoformat() else 0) + (1 if send_it else 0)
    if tg == "failed" and tries < 3:
        state["daily"] = {"date": today.isoformat(), "done": False, "tries": tries}  # retry send next hourly run
    else:
        state["failures"] = newf
        state["daily"] = {"date": today.isoformat(), "done": True, "tries": tries, "telegram": tg}
    state["last_run"] = now.isoformat()
    save_state(state)
    green = sum(1 for r in results if r["status"] == OK)
    log(f"daily: {green}/{sum(1 for r in results if r['status'] != SKIP)} green, {len(fails)} failing; telegram {tg}; records {', '.join(recs)}", now)
    print(msg if send_it else f"no message (telegram {tg})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

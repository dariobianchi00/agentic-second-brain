"""Tests for health.py (daily automation health check).
Fixtures only: fake pmset (log + systemstate), fake register/run records/attempts/cron.log,
fake registry, fake ~/.claude.json, local HTTP server, fictional agents (personal/coach,
work/analyst, work/planner). NOTIFY_DRY_RUN=1 everywhere — nothing is ever sent.
Never touches a real workspace's state.
Run: python3 -I agents/scheduler/test_health.py
"""
import datetime as dt, glob, http.server, json, os, re, shutil, socket, subprocess, sys, tempfile, threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import health  # noqa: E402

HEALTH = os.path.join(HERE, "health.py")
TZ = dt.timezone(dt.timedelta(hours=8))
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    if not cond:
        print(f"FAIL  {name}  {str(detail)[:600]}")


def T(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=TZ) if "+" not in s else dt.datetime.fromisoformat(s)


def pm_line(t, typ, msg="x"):
    return f"{t} +0800 {typ:<20}\t{msg}"


def pmlog(events):
    """events: [("2026-10-19 01:00:00", "Sleep"), ...] plus noise lines."""
    out = ["PM ASL data store: /var/log/powermanagement", pm_line("2026-10-12 00:00:00", "Assertions", "noise")]
    for t, typ in events:
        out.append(pm_line(t, typ, "Wake from Deep Idle [CDNVA]" if typ == "Wake" else "m"))
        out.append(pm_line(t, "Wake Requests", "[process=mDNSResponder]"))
    return "\n".join(out) + "\n"


# Mac fully awake since Sun 08:00 (no sleep since) — "always awake" timeline for most tests
AWAKE = [("2026-10-11 08:00:00", "Wake")]
# Lid closed overnight: sleep Sun 23:00, DarkWakes, lid open Mon 11:28
NIGHT = [("2026-10-18 08:00:00", "Wake"), ("2026-10-18 23:00:00", "Sleep"),
         ("2026-10-19 07:15:00", "DarkWake"), ("2026-10-19 07:15:10", "Sleep"),
         ("2026-10-19 09:40:00", "DarkWake"), ("2026-10-19 09:42:00", "Sleep"),
         ("2026-10-19 11:28:00", "Wake")]

PMSET = """#!/bin/bash
if [ "$2" = "log" ]; then cat "$FAKE_PMSET_LOG"; else echo "Current System Capabilities are: ${FAKE_PMSET_CAPS:-CPU Graphics Audio Network}"; fi
"""

REG_TASKS = """# reg

### tp
- **Schedule:** `0 7 * * *`
- **Agent:** Coach
- **Execution:** agent
- **Enabled:** true
- **Last run:** {tp_last}

### tm
- **Schedule:** `0 7 * * *`
- **Agent:** Analyst
- **Execution:** direct
- **Enabled:** true
- **Last run:** {tm_last}

### td
- **Schedule:** `0 7 * * *`
- **Agent:** Planner
- **Enabled:** false
- **Last run:** never
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


SERVER = http.server.HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
UP_URL = f"http://127.0.0.1:{SERVER.server_address[1]}/"
_s = socket.socket(); _s.bind(("127.0.0.1", 0)); DOWN_URL = f"http://127.0.0.1:{_s.getsockname()[1]}/"; _s.close()


class Env:
    def __init__(self, pm=AWAKE, tp_last="never", tm_last="never", url=UP_URL, mcp_ok=True):
        self.d = tempfile.mkdtemp(prefix="health-test-")
        j = lambda *p: os.path.join(self.d, *p)
        for sub in ("logs", "state", "runs", "out", "la", "personal/coach", "work/analyst", "work/planner"):
            os.makedirs(j(sub))
        self.pmlog = j("pmset.log"); open(self.pmlog, "w").write(pmlog(pm) if pm else "")
        open(j("pmset"), "w").write(PMSET); os.chmod(j("pmset"), 0o755)
        self.reg = j("scheduled-tasks.md")
        self.set_register(tp_last, tm_last)
        open(j("la", "sched.plist"), "w").write("x")
        open(j("la", "news.plist"), "w").write("x")
        open(j("la", "dash.plist"), "w").write("x")
        open(j("creds.json"), "w").write("{}")
        open(j("oauth.json"), "w").write("{}")
        cj = {"mcpServers": {"mail-x": {"type": "stdio", "env": {"MAIL_CREDENTIALS_PATH": j("creds.json") if mcp_ok else j("nope.json"),
                                                                  "MAIL_OAUTH_PATH": j("oauth.json"), "MAIL_MODE": "readonly"}}}}
        self.claude_json = j("claude.json"); json.dump(cj, open(self.claude_json, "w"))
        self.registry = {
            "version": 1, "daily_at": "08:30", "daily_cutoff": "20:30", "resend_days": 3, "tick_stale_awake_hours": 3,
            "scheduler_tasks": {"register": self.reg, "cron_log": j("logs", "cron.log"), "grace_awake_min": 90,
                                "fix": {"missed": "FIX-MISSED", "retry-cap": "FIX-CAP", "failed": "FIX-FAILED"},
                                "overrides": {"tp": {"outputs": [j("out", "tp_{date}.md")]}}},
            "automations": [
                {"id": "agent-scheduler", "kind": "launchd-job", "scope": "work", "plist": j("la", "sched.plist"),
                 "schedule": "every 10 min", "log": j("logs", "cron.log"), "checks": ["plist", "tick"],
                 "fix": {"tick-stale": "FIX-TICK", "hung": "FIX-HUNG"}},
                {"id": "news-fetch", "kind": "launchd-job", "scope": "personal", "plist": j("la", "news.plist"),
                 "schedule": "0 7 * * *", "grace_awake_min": 30, "outputs": [j("out", "staged.md")], "log": j("logs", "news.log"),
                 "checks": ["plist", "slot"], "fix": {"missed": "FIX-NEWS"}},
                {"id": "dash", "kind": "server", "scope": "personal", "plist": j("la", "dash.plist"), "url": url,
                 "schedule": "always", "checks": ["plist", "http"], "fix": {"down": "FIX-DOWN"}},
                {"id": "mcp:mail-x", "kind": "mcp", "scope": "personal", "server": "mail-x", "schedule": "on demand",
                 "checks": ["mcp-registered", "mcp-credentials"]},
                {"id": "self", "kind": "launchd-job", "schedule": "hourly", "checks": []},
            ]}
        self.save_registry()
        self.sent_log = j("sent.log")
        self.env = dict(os.environ, SCHED_PLATFORM="macos", HEALTH_REGISTRY=j("automations.json"), HEALTH_STATE_FILE=j("state", "health.json"),
                        HEALTH_LOG=j("logs", "health.log"), HEALTH_PMSET_BIN=j("pmset"), HEALTH_CLAUDE_JSON=self.claude_json,
                        HEALTH_WORKSPACE=self.d, HEALTH_BOOTTIME="off", HEALTH_NETWORK="1",
                        SCHED_REGISTER=self.reg, SCHED_RUNS_DIR=j("runs"), SCHED_STATE_FILE=j("state", "attempts.json"),
                        SCHED_LOGS_DIR=j("logs"), FAKE_PMSET_LOG=self.pmlog, NOTIFY_DRY_RUN="1", NOTIFY_DRY_RUN_LOG=self.sent_log)
        for k in ("SCHED_TICK_ID", "SCHED_TICK_STARTED", "SCHED_DEFAULT_SCOPE"):
            self.env.pop(k, None)
        self.cron(["2026-10-19 08:50 gate: no tasks due"])
        self.j = j

    def save_registry(self):
        json.dump(self.registry, open(os.path.join(self.d, "automations.json"), "w"), indent=1)

    def set_register(self, tp_last, tm_last):
        open(self.reg, "w").write(REG_TASKS.format(tp_last=tp_last, tm_last=tm_last))

    def cron(self, lines):
        open(os.path.join(self.d, "logs", "cron.log"), "w").write("\n".join(lines) + "\n")

    def touch(self, path, when):
        if not os.path.exists(path):
            open(path, "w").write("x")
        ts = T(when).timestamp()
        os.utime(path, (ts, ts))

    def record(self, task, scope, started, status):
        d = os.path.join(self.d, "runs", scope, started[:7]); os.makedirs(d, exist_ok=True)
        name = f"{started[:10]}_{started[11:13]}{started[14:16]}_{task}.md"
        open(os.path.join(d, name), "w").write(f"---\ntask: {task}\nscope: {scope}\nstatus: {status}\nstarted: {started}:00+08:00\n---\nbody\n")

    def good_outputs(self, day="2026-10-19", at="07:20"):
        self.touch(self.j("out", f"tp_{day}.md"), f"{day}T{at}:00+08:00")
        self.touch(self.j("out", "staged.md"), f"{day}T07:05:00+08:00")

    def all_green(self, day="2026-10-19"):
        self.set_register(f"{day}T07:20:00+08:00", f"{day}T07:25:00+08:00")
        self.good_outputs(day)
        self.record("tp", "personal", f"{day}T07:10", "success")
        self.record("tm", "work", f"{day}T07:10", "success")
        self.cron([f"{day} 08:50 gate: no tasks due"])

    def run(self, now, *args, **envx):
        e = dict(self.env, **envx)
        r = subprocess.run([sys.executable, HEALTH, "--now", now] + list(args), capture_output=True, text=True, env=e, timeout=120)
        return r

    def sent(self):
        try:
            return [m for m in open(self.sent_log).read().split("<<<END>>>\n") if m.strip()]
        except OSError:
            return []

    def state(self):
        try:
            return json.load(open(self.j("state", "health.json")))
        except OSError:
            return {}

    def records(self, scope="*"):
        return sorted(glob.glob(os.path.join(self.d, "runs", scope, "*", "*_automation-health-check*.md")))

    def done(self):
        shutil.rmtree(self.d, ignore_errors=True)


def findings(r):
    return r.stdout.split("--- findings ---", 1)[-1].split("--- power")[0]


def line_for(r, item):
    return next((l for l in findings(r).splitlines() if f"] {item}:" in l), "")


# ───── 1. power timeline unit tests ─────
now = T("2026-10-19T12:00:00")
p = health.parse_power(pmlog(NIGHT), now, True)
check("power: not blind", not p.blind)
check("power: overnight sleep not counted (07:00→11:28 = 0)", p.awake(T("2026-10-19T07:00:00"), T("2026-10-19T11:28:00")) == 0, p.awake(T("2026-10-19T07:00:00"), T("2026-10-19T11:28:00")))
check("power: DarkWake not counted", p.awake(T("2026-10-19T09:40:00"), T("2026-10-19T09:42:00")) == 0)
check("power: open interval runs to now (11:28→12:00 = 32 min)", abs(p.awake(T("2026-10-19T07:00:00"), now) - 32 * 60) < 1)
check("power: Sunday day counted", abs(p.awake(T("2026-10-18T09:00:00"), T("2026-10-18T10:00:00")) - 3600) < 1)
pb = health.parse_power("", now, True)
check("power: empty log → blind wall-clock", pb.blind and pb.awake(T("2026-10-19T07:00:00"), now) == 5 * 3600)
p2 = health.parse_power(pmlog([("2026-10-19 01:00:00", "Sleep")]), now, True, boottime=T("2026-10-19T10:00:00"))
check("power: boot after sleep starts an awake interval", abs(p2.awake(T("2026-10-19T07:00:00"), now) - 2 * 3600) < 1)
p3 = health.parse_power(pmlog([("2026-10-19 01:00:00", "Sleep")]), now, False)
check("power: asleep, not awake now → 0", p3.awake(T("2026-10-19T07:00:00"), now) == 0)
check("classify: 'success (partial reads)' → partial", health.classify("success (partial reads)") == "partial")
check("classify: 'failed (not started)' → failed", health.classify("failed (not started)") == "failed")
check("classify: skipped → None", health.classify("skipped") is None)

# ───── 2. sleep-aware missed detection ─────
e = Env(pm=NIGHT, tp_last="2026-10-18T07:20:00+08:00", tm_last="2026-10-18T07:20:00+08:00")
e.cron(["2026-10-19 07:15 gate: due=[tp tm] deferred: not fully awake (DarkWake)", "2026-10-19 11:40 gate: no tasks due"])
r = e.run("2026-10-19T11:45:00+08:00", "--dry-run", "--force-daily")
check("sleep: lid closed till 11:28 → tp PENDING at 11:45, not missed", "⏳" in line_for(r, "tp") and "missed" not in line_for(r, "tp"), findings(r))
check("sleep: no FAIL for tasks at 11:45", "❌" not in line_for(r, "tp") + line_for(r, "tm"))
r = e.run("2026-10-19T13:30:00+08:00", "--dry-run", "--force-daily")
check("sleep: 2h awake after slot → tp missed", "missed" in line_for(r, "tp") and "❌" in line_for(r, "tp"), findings(r))
check("sleep: missed detail counts DarkWake deferrals", "deferred" in line_for(r, "tp"), line_for(r, "tp"))
check("sleep: missed message carries fix", "FIX-MISSED" in r.stdout)
check("sleep: disabled task td ignored", "td" not in [l.split("] ")[-1].split(":")[0] for l in findings(r).splitlines() if "] " in l])
check("dry-run: no state written", not os.path.exists(e.j("state", "health.json")))
check("dry-run: nothing sent", e.sent() == [])
check("dry-run: no run record", e.records() == [])
e.done()

e = Env(pm=None, tp_last="2026-10-18T07:20:00+08:00", tm_last="2026-10-18T07:20:00+08:00")
r = e.run("2026-10-19T11:45:00+08:00", "--dry-run", "--force-daily")
check("blind: no pmset data → wall-clock → missed + note", "missed" in line_for(r, "tp") and "wall-clock" in r.stdout, r.stdout)
e.done()

# ───── 3. ran: status / outputs / retry cap / running ─────
e = Env()
e.all_green()
r = e.run("2026-10-19T09:00:00+08:00", "--dry-run", "--force-daily")
check("green: tp OK", "✅" in line_for(r, "tp"), findings(r))
check("green: tm OK", "✅" in line_for(r, "tm"))
check("green: news-fetch OK", "✅" in line_for(r, "news-fetch"), line_for(r, "news-fetch"))
check("green: dash OK", "✅" in line_for(r, "dash"))
check("green: mcp OK", "✅" in line_for(r, "mcp:mail-x"))
check("green: tick OK", "✅" in line_for(r, "agent-scheduler"))
check("green: scope comes from the agent folder", "[personal] tp:" in findings(r) and "[work] tm:" in findings(r), findings(r))
os.remove(e.j("out", "tp_2026-10-19.md"))
r = e.run("2026-10-19T09:00:00+08:00", "--dry-run", "--force-daily")
check("output missing → output-stale", "output-stale" in line_for(r, "tp"), line_for(r, "tp"))
e.registry["scheduler_tasks"]["overrides"]["tp"]["output_on_news"] = True
e.save_registry()
e.record("tp", "personal", "2026-10-19T07:22", "partial")
r = e.run("2026-10-19T09:00:00+08:00", "--dry-run", "--force-daily")
check("output_on_news, run not successful → still output-stale", "output-stale" in line_for(r, "tp"), line_for(r, "tp"))
e.record("tp", "personal", "2026-10-19T07:24", "success")
r = e.run("2026-10-19T09:00:00+08:00", "--dry-run", "--force-daily")
check("output_on_news + successful run → OK", "✅" in line_for(r, "tp"), line_for(r, "tp"))
del e.registry["scheduler_tasks"]["overrides"]["tp"]["output_on_news"]
e.save_registry()
e.good_outputs()
e.record("tp", "personal", "2026-10-19T07:30", "failed")
r = e.run("2026-10-19T09:00:00+08:00", "--dry-run", "--force-daily")
check("latest run record failed → failed", "❌" in line_for(r, "tp") and "failed" in line_for(r, "tp"), line_for(r, "tp"))
e.record("tp", "personal", "2026-10-19T07:40", "partial")
r = e.run("2026-10-19T09:00:00+08:00", "--dry-run", "--force-daily")
check("latest run record partial → warning", "⚠️" in line_for(r, "tp"), line_for(r, "tp"))
e.done()

e = Env(tp_last="2026-10-18T07:20:00+08:00")
json.dump({"tp": {"slot": "2026-10-19T07:00+08:00", "attempts": 3, "last_attempt": "2026-10-19T07:30:00+08:00"}},
          open(e.j("state", "attempts.json"), "w"))
r = e.run("2026-10-19T07:45:00+08:00", "--dry-run", "--force-daily")
check("retry cap reached → FAIL retry-cap (even inside grace)", "retry-cap" in line_for(r, "tp") and "FIX-CAP" in r.stdout, line_for(r, "tp"))
e.done()

e = Env(tp_last="2026-10-18T07:20:00+08:00")
e.cron(["2026-10-19 07:10 gate: due=[tp tm] — starting claude"])
r = e.run("2026-10-19T09:30:00+08:00", "--dry-run", "--force-daily")
check("harness running → tp pending, not missed", "running since" in line_for(r, "tp"), line_for(r, "tp"))
e.cron(["2026-10-19 07:10 gate: due=[tp tm] — starting claude", "2026-10-19 07:50 gate: no tasks due"])
r = e.run("2026-10-19T09:30:00+08:00", "--dry-run", "--force-daily")
check("later gate line = harness gone → tp missed", "missed" in line_for(r, "tp"), line_for(r, "tp"))
e.cron(["2026-10-19 07:10 gate: due=[tp tm] — starting claude"])
r = e.run("2026-10-19T11:30:00+08:00", "--dry-run", "--force-daily")
check("harness running > 3h awake → hung", "hung" in line_for(r, "agent-scheduler"), line_for(r, "agent-scheduler"))
e.done()

e = Env(tp_last="2026-10-18T07:20:00+08:00")
os.makedirs(e.j("logs"), exist_ok=True)
with open(e.j("logs", "2026-10.md"), "w") as f:
    f.write("## 2026-10-19 07:10\n\n| Task | Status | Detail |\n|---|---|---|\n| tp · tm | failed | mail server down |\n")
r = e.run("2026-10-19T07:40:00+08:00", "--dry-run", "--force-daily")
check("monthly log fallback: failed row → FAIL failed", "❌" in line_for(r, "tp") and "reported failed" in line_for(r, "tp"), line_for(r, "tp"))
e.done()

# ───── 4. launchd slot job, server, mcp ─────
e = Env(url=DOWN_URL, mcp_ok=False)
e.all_green()
os.utime(e.j("out", "staged.md"), (T("2026-10-18T07:05:00").timestamp(),) * 2)
e.touch(e.j("logs", "news.log"), "2026-10-19T07:01:00")
r = e.run("2026-10-19T09:00:00+08:00", "--dry-run", "--force-daily")
check("slot job: log fresh, output stale → failed", "did not write" in line_for(r, "news-fetch"), line_for(r, "news-fetch"))
check("server down → FAIL down + fix", "❌" in line_for(r, "dash") and "FIX-DOWN" in r.stdout, line_for(r, "dash"))
check("mcp creds file missing (any *_PATH env) → FAIL", "MAIL_CREDENTIALS_PATH" in line_for(r, "mcp:mail-x"), line_for(r, "mcp:mail-x"))
e.registry["automations"][3]["credential_env"] = ["MAIL_OAUTH_PATH"]
e.save_registry()
r = e.run("2026-10-19T09:00:00+08:00", "--dry-run", "--force-daily")
check("mcp credential_env narrows the check", "✅" in line_for(r, "mcp:mail-x"), line_for(r, "mcp:mail-x"))
os.remove(e.j("logs", "news.log"))
r = e.run("2026-10-19T09:00:00+08:00", "--dry-run", "--force-daily")
check("slot job: nothing after slot → missed", "missed" in line_for(r, "news-fetch") and "FIX-NEWS" in r.stdout, line_for(r, "news-fetch"))
os.remove(e.j("la", "news.plist"))
r = e.run("2026-10-19T09:00:00+08:00", "--dry-run", "--force-daily")
check("plist missing → FAIL plist", "plist missing" in line_for(r, "news-fetch"), line_for(r, "news-fetch"))
e.done()

# ───── 5. tick staleness (awake-time based) + urgent alert dedupe ─────
e = Env(pm=[("2026-10-19 06:00:00", "Wake"), ("2026-10-19 08:05:00", "Sleep"), ("2026-10-19 14:00:00", "Wake")])
e.cron(["2026-10-19 08:00 gate: no tasks due"])
r = e.run("2026-10-19T14:30:00+08:00", "--dry-run")
check("tick: 6.5h wall-clock but 35 min awake → no alert", "Scheduler not ticking" not in r.stdout, r.stdout)
e.done()
e = Env()
e.cron(["2026-10-19 04:00 gate: no tasks due"])
r = e.run("2026-10-19T08:00:00+08:00")
s = e.sent()
check("tick: 4h awake without tick → urgent alert before 08:30", len(s) == 1 and "Scheduler not ticking" in s[0] and "FIX-TICK" in s[0], s)
check("tick: alert writes a run record in the scheduler's scope", len(e.records("work")) == 1)
r = e.run("2026-10-19T08:10:00+08:00")
check("tick: same stale episode not re-sent", len(e.sent()) == 1, e.sent())
e.cron(["2026-10-19 04:00 gate: no tasks due", "2026-10-19 08:15 gate: no tasks due"])
e.run("2026-10-19T08:20:00+08:00")
check("tick: recovered → episode cleared", "tick_alert" not in e.state())
e.done()

# ───── 6. daily gating, dedupe, resend, Monday all-clear, scopes ─────
e = Env()
e.all_green("2026-10-20")  # Tuesday
r = e.run("2026-10-20T08:00:00+08:00")
check("daily: before 08:30 → no report", e.sent() == [] and not e.state().get("daily"), e.state())
r = e.run("2026-10-20T09:30:00+08:00")
check("daily: Tuesday all green → no Telegram", e.sent() == [], e.sent())
check("daily: green day still writes a run record", len(e.records()) == 1)
check("daily: marked done", e.state().get("daily", {}).get("done") is True)
e.done()

e = Env()
e.all_green("2026-10-19")  # Monday
r = e.run("2026-10-19T09:30:00+08:00")
s = e.sent()
check("Monday all-clear: N/N green sent", len(s) == 1 and re.search(r"(\d+)/\1 green", s[0]) and s[0].startswith("✅"), s)
e.done()

e = Env(url=DOWN_URL, tp_last="2026-10-19T07:20:00+08:00", tm_last="2026-10-19T07:25:00+08:00")
e.good_outputs("2026-10-20")
e.set_register("2026-10-20T07:20:00+08:00", "2026-10-20T07:25:00+08:00")
e.record("tm", "work", "2026-10-20T07:10", "failed")
e.cron(["2026-10-20 08:50 gate: no tasks due"])
r = e.run("2026-10-20T09:30:00+08:00")
s = e.sent()
check("failure day: ONE message with both failures grouped", len(s) == 1 and "dash" in s[0] and "tm —" in s[0], s)
check("failure: new failures tagged 🆕", s and s[0].count("🆕") == 2, s)
check("failure: since-when + fix present", s and "fix: FIX-DOWN" in s[0] and "fix: FIX-FAILED" in s[0])
mv, pe = e.records("work"), e.records("personal")
check("mixed scopes → one run record per scope", len(mv) == 1 and len(pe) == 1, (mv, pe))
mvt = open(mv[0]).read() if mv else ""
check("scope firewall: work record has no personal items", "dash" not in mvt and "tm —" in mvt and "tp —" not in mvt, mvt)
check("run record status failed + telegram sent", "status: failed" in mvt and "telegram: sent" in mvt)
r = e.run("2026-10-20T10:30:00+08:00")
check("same day: no second message", len(e.sent()) == 1)
# next day, same failures (tm failed again, dash still down)
e.set_register("2026-10-21T07:20:00+08:00", "2026-10-21T07:25:00+08:00")
e.good_outputs("2026-10-21")
e.record("tm", "work", "2026-10-21T07:10", "failed")
e.cron(["2026-10-21 08:50 gate: no tasks due"])
e.run("2026-10-21T09:30:00+08:00")
check("unchanged next day → suppressed (no message)", len(e.sent()) == 1, e.sent())
sup = [p for p in e.records() if "2026-10-21" in p]
check("suppressed day still writes record (telegram suppressed)", sup and all("telegram: suppressed" in open(p).read() for p in sup), sup)
first_seen = e.state().get("failures", {}).get("dash|down", {}).get("first_seen", "")
check("first_seen carried over", first_seen.startswith("2026-10-20"), e.state())
# day 3 unchanged + tm recovers → resolved, still suppressed
e.set_register("2026-10-22T07:20:00+08:00", "2026-10-22T07:25:00+08:00")
e.good_outputs("2026-10-22")
e.record("tm", "work", "2026-10-22T07:10", "success")
e.cron(["2026-10-22 08:50 gate: no tasks due"])
e.run("2026-10-22T09:30:00+08:00")
check("day 3: only ongoing unchanged failure → still suppressed", len(e.sent()) == 1, e.sent())
# day 4 (Fri): 3 days since last send → re-sent, ongoing tagged with since
e.set_register("2026-10-23T07:20:00+08:00", "2026-10-23T07:25:00+08:00")
e.good_outputs("2026-10-23")
e.cron(["2026-10-23 08:50 gate: no tasks due"])
e.run("2026-10-23T09:30:00+08:00")
s = e.sent()
check("3 days unchanged → re-sent", len(s) == 2, s)
check("re-sent shows 'since' not 🆕", len(s) == 2 and "since 10-20" in s[1] and "🆕" not in s[1], s[-1:])
# day 5: dash recovers, new failure appears → sent, lists resolved
e.registry["automations"][2]["url"] = UP_URL
e.save_registry()
e.set_register("2026-10-24T07:20:00+08:00", "2026-10-18T07:25:00+08:00")
e.good_outputs("2026-10-24")
e.cron(["2026-10-24 08:50 gate: no tasks due"])
e.run("2026-10-24T09:30:00+08:00")
s = e.sent()
check("changed (new failure) → sent with resolved line", len(s) == 3 and "tm —" in s[2] and "resolved: dash" in s[2], s[-1:])
e.done()

# pending holds the daily report until the grace passes (or the cutoff)
e = Env(pm=NIGHT, tp_last="2026-10-18T07:20:00+08:00", tm_last="2026-10-18T07:20:00+08:00")
e.good_outputs("2026-10-19")
r = e.run("2026-10-19T11:30:00+08:00")
check("pending → daily waits (no message, not done)", e.sent() == [] and e.state().get("daily", {}).get("done") is False, e.state())
e.cron(["2026-10-19 13:20 gate: no tasks due"])
r = e.run("2026-10-19T13:30:00+08:00")
s = e.sent()
check("after grace → one message with the missed tasks", len(s) == 1 and "missed" in s[0] and "tp —" in s[0] and "tm —" in s[0], s)
e.done()

e = Env(pm=NIGHT, tp_last="2026-10-18T07:20:00+08:00", tm_last="2026-10-18T07:20:00+08:00")
e.good_outputs("2026-10-19")
e.cron(["2026-10-19 20:50 gate: no tasks due"])
# laptop opened only at 20:40: still pending at the 20:30 cutoff → finalize anyway (Monday → sent)
open(e.pmlog, "w").write(pmlog([("2026-10-18 23:00:00", "Sleep"), ("2026-10-19 20:40:00", "Wake")]))
r = e.run("2026-10-19T20:55:00+08:00")
check("cutoff: pending at 20:30+ → report finalized", e.state().get("daily", {}).get("done") is True and len(e.sent()) == 1 and "pending" in e.sent()[0], (e.state(), e.sent()))
e.done()

# DarkWake now → nothing happens
e = Env()
e.cron(["2026-10-19 01:00 gate: no tasks due"])
r = e.run("2026-10-19T09:30:00+08:00", FAKE_PMSET_CAPS="CPU Network Disk")
check("DarkWake: exits without checks, state or messages", r.returncode == 0 and e.sent() == [] and not os.path.exists(e.j("state", "health.json")), r.stdout + r.stderr)
check("DarkWake: logged as deferred", "deferred" in open(e.j("logs", "health.log")).read())
e.done()

# notify failure → retried next run (max 3 tries/day)
e = Env(url=DOWN_URL)
e.all_green("2026-10-20")
r = e.run("2026-10-20T09:30:00+08:00", NOTIFY_DRY_RUN="fail")
check("send failed → daily not done, retried", e.state().get("daily", {}).get("done") is False, e.state())
e.run("2026-10-20T10:30:00+08:00")
check("retry succeeds next run", e.state().get("daily", {}).get("done") is True and len(e.sent()) == 2, (e.state(), e.sent()))
e.done()

# no Telegram configured → message goes to the notify log, counts as delivered
e = Env(url=DOWN_URL)
e.all_green("2026-10-20")
nlog = e.j("logs", "notify.log")
r = e.run("2026-10-20T09:30:00+08:00", NOTIFY_DRY_RUN="", NOTIFY_ENV_FILE=e.j("missing.env"), NOTIFY_LOG=nlog,
          TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="")
check("no Telegram: report logged, daily done", e.state().get("daily", {}).get("telegram") == "logged"
      and e.state().get("daily", {}).get("done") is True and os.path.exists(nlog) and "dash" in open(nlog).read(),
      (e.state(), r.stderr[-300:]))
e.done()

# ───── 7. the example registry (and the real one, once created) parses and is well-formed ─────
def register_text():
    for p in (os.path.join(HERE, "..", "scheduled-tasks.md"), os.path.join(HERE, "scheduled-tasks.md")):
        if os.path.exists(p):
            return open(p, encoding="utf-8").read()
    return ""
for name in ("automations.example.json", "automations.json"):
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        continue
    real = json.load(open(path, encoding="utf-8"))
    ids = [a["id"] for a in real["automations"]]
    check(f"{name}: unique ids", len(ids) == len(set(ids)))
    check(f"{name}: every entry has kind/schedule", all(a.get("kind") and a.get("schedule") for a in real["automations"]))
    check(f"{name}: kinds valid", all(a["kind"] in ("timer-job", "launchd-job", "scheduler-task", "server", "mcp", "check") for a in real["automations"]))
    check(f"{name}: overrides name register tasks",
          set(real["scheduler_tasks"].get("overrides", {})) <= {t for t, _ in __import__("gate").parse_tasks(register_text())})

SERVER.shutdown()
passed = sum(1 for _, ok in results if ok)
print(f"{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)

"""Tests for runrecord.py (run records, Telegram dedupe), notify.sh (dry run, truncation)
and tick.sh post-run failure detection + retry cap.
Never sends anything: NOTIFY_DRY_RUN=1 everywhere, harness = stub script.
Fixture workspace (multi-domain): personal/coach/ and work/analyst/ next to the register,
CONVENTIONS.md with `firewalled-scope: personal`.
Run: python3 -I agents/scheduler/test_runrecord.py
"""
import datetime, glob, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TICK = os.environ.get("TICK_SH") or os.path.join(HERE, "tick.sh")
RR = os.path.join(HERE, "runrecord.py")
NOTIFY = os.path.join(HERE, "notify.sh")

STUB = r'''#!/bin/bash
# fake harness: behaviour from $STUB_MODE; counts invocations
echo x >> "$STUB_COUNT"
now="$(date '+%Y-%m-%dT%H:%M:%S%z' | sed -E 's/([0-9]{2})([0-9]{2})$/\1:\2/')"
set_last() { /usr/bin/python3 - "$SCHED_REGISTER" "$now" <<'PY'
import re, sys
p, now = sys.argv[1], sys.argv[2]
s = open(p).read()
open(p, "w").write(re.sub(r"^- \*\*Last run:\*\*.*$", "- **Last run:** " + now, s, flags=re.M))
PY
}
report() { printf '%s\n' "$2" | python3 "$RR" report --task t1 --status "$1" --output "Some Dir/out file.md"; }
case "$STUB_MODE" in
  fail)          echo "boom: MCP timeout bot123456:SECRETtoken"; exit 1 ;;
  ok-report)     set_last; report success "✅ t1 — today
did the thing"; exit 0 ;;
  ok-silent)     set_last; exit 0 ;;
  report-only)   report success "✅ t1 — today"; exit 0 ;;
  fail-report)   report failed "❌ t1 — today
could not reach the mail server"; exit 0 ;;
esac
'''

PMSET = '''#!/bin/bash
echo "Current System Capabilities are: $PMSET_CAPS"
'''

REG = """# reg

### t1
- **Schedule:** `0 0 * * *`
- **Agent:** Coach
- **Execution:** agent
- **Enabled:** true
- **Last run:** 2020-01-01T00:00:00+08:00

### t2
- **Schedule:** `0 0 * * *`
- **Agent:** Analyst
- **Enabled:** false
- **Last run:** never
"""

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    if not cond:
        print(f"FAIL  {name} {detail}")


class Env:
    def __init__(self):
        self.d = tempfile.mkdtemp(prefix="sched-test-")
        self.reg = os.path.join(self.d, "scheduled-tasks.md")
        open(self.reg, "w").write(REG)
        open(os.path.join(self.d, "CONVENTIONS.md"), "w").write("---\nextends: plugin\nfirewalled-scope: personal\n---\n# c\n")
        for sc, ag in (("personal", "coach"), ("work", "analyst"), ("work", "planner")):
            os.makedirs(os.path.join(self.d, sc, ag))
        for name, body in (("stub.sh", STUB), ("pmset", PMSET)):
            p = os.path.join(self.d, name)
            open(p, "w").write(body)
            os.chmod(p, 0o755)
        self.env = dict(os.environ, SCHED_PLATFORM="macos",
                        SCHED_REGISTER=self.reg,
                        SCHED_LOGS_DIR=os.path.join(self.d, "logs"),
                        SCHED_STATE_FILE=os.path.join(self.d, "state", "attempts.json"),
                        SCHED_RUNS_DIR=os.path.join(self.d, "runs"),
                        NOTIFY_DRY_RUN="1",
                        NOTIFY_DRY_RUN_LOG=os.path.join(self.d, "sent.log"),
                        AGENT_HARNESS_CMD=os.path.join(self.d, "stub.sh"),
                        TICK_PMSET_BIN=os.path.join(self.d, "pmset"),
                        PMSET_CAPS="CPU Graphics Audio Network",
                        STUB_COUNT=os.path.join(self.d, "count"),
                        RR=RR, STUB_MODE="fail")
        for k in ("TICK_SKIP_WAKE_CHECK", "SCHED_TICK_STARTED", "SCHED_MAX_ATTEMPTS", "AGENT_HARNESS"):
            self.env.pop(k, None)

    def tick(self, **kw):
        e = dict(self.env, **kw)
        return subprocess.run(["/bin/bash", TICK], env=e, capture_output=True, text=True)

    def rr(self, args, stdin="", **kw):
        return subprocess.run([sys.executable, RR] + args, env=dict(self.env, **kw),
                              input=stdin, capture_output=True, text=True)

    def invocations(self):
        try:
            return len(open(self.env["STUB_COUNT"]).read().split())
        except OSError:
            return 0

    def sent(self):
        try:
            return [m.strip("\n") for m in open(self.env["NOTIFY_DRY_RUN_LOG"]).read().split("<<<END>>>") if m.strip()]
        except OSError:
            return []

    def state(self):
        try:
            return json.load(open(self.env["SCHED_STATE_FILE"]))
        except OSError:
            return {}

    def records(self, scope="personal"):
        return sorted(glob.glob(os.path.join(self.d, "runs", scope, "*", "*.md")))

    def cron(self):
        try:
            return open(os.path.join(self.d, "logs", "cron.log")).read()
        except OSError:
            return ""

    def done(self):
        shutil.rmtree(self.d, ignore_errors=True)


def fm(path):
    t = open(path).read()
    head, body = t.split("\n---\n", 1)
    return head, body


# 1. harness fails 3x → 3 failed records, ONE ❌ at the cap, 4th tick holds the slot
e = Env()
for i in range(3):
    e.tick()
check("cap: 3 harness invocations", e.invocations() == 3, e.invocations())
st = e.state().get("t1", {})
check("cap: attempts=3 alerted", st.get("attempts") == 3 and st.get("alerted") is True, st)
recs = e.records()
check("cap: 3 failed run records", len(recs) == 3 and all("status: failed" in open(r).read() for r in recs), recs)
tg = [re.search(r"^telegram: (\S+)", open(r).read(), re.M).group(1) for r in recs]
check("cap: telegram none,none,sent", sorted(tg) == ["none", "none", "sent"], tg)
msgs = e.sent()
check("cap: exactly one alert", len(msgs) == 1, msgs)
m = msgs[0] if msgs else ""
check("cap: alert shape", m.startswith("❌ t1 — ") and "3/3" in m and "Last output: boom" in m and "\n→ " in m, m)
check("cap: token scrubbed", "SECRETtoken" not in m and "bot***" in m, m)
e.tick()
check("cap: 4th tick does not run harness", e.invocations() == 3, e.invocations())
check("cap: 4th tick logs no tasks due", e.cron().rstrip().endswith("gate: no tasks due"), e.cron()[-200:])
check("cap: still one alert", len(e.sent()) == 1)
mlog = glob.glob(os.path.join(e.d, "logs", "20*.md"))
check("cap: monthly log rows", mlog and open(mlog[0]).read().count("| t1 | failed |") == 3, mlog)
head, body = fm([r for r in recs if "telegram: sent" in open(r).read()][0])
check("cap: record body == telegram text", body.strip() == m.strip(), (body, m))
check("cap: record frontmatter", all(k in head for k in ("task: t1", "scope: personal", 'agent: "Coach"', "started: ", "finished: ", "outputs: []")), head)
e.done()

# 2. DarkWake ticks are not attempts
e = Env()
for i in range(4):
    e.tick(PMSET_CAPS="CPU Network")
check("darkwake: no invocation", e.invocations() == 0)
check("darkwake: no attempts", e.state() == {}, e.state())
check("darkwake: deferred logged", e.cron().count("deferred: not fully awake") == 4)
e.tick()
check("darkwake: full wake then fail = attempt 1", e.state().get("t1", {}).get("attempts") == 1, e.state())
check("darkwake: no alert below cap", e.sent() == [])
e.done()

# 3. success with report → one ✅, record success, state clean
e = Env()
r = e.tick(STUB_MODE="ok-report")
recs = e.records()
check("ok: one record", len(recs) == 1, recs)
head, body = fm(recs[0]) if recs else ("", "")
check("ok: record success+sent+outputs", "status: success" in head and "telegram: sent" in head and '  - "Some Dir/out file.md"' in head, head)
check("ok: one ✅ message w/ link", len(e.sent()) == 1 and e.sent()[0].startswith("✅ t1") and "\n→ " in e.sent()[0], e.sent())
check("ok: state clean", "t1" not in e.state(), e.state())
check("ok: tick exit 0", r.returncode == 0, r.returncode)
e.tick(STUB_MODE="ok-report")
check("ok: not rerun same slot", e.invocations() == 1)
e.done()

# 4. ran but no report → ⚠️ partial
e = Env()
e.tick(STUB_MODE="ok-silent")
recs = e.records()
check("silent: partial record", len(recs) == 1 and "status: partial" in open(recs[0]).read(), recs)
check("silent: ⚠️ sent", len(e.sent()) == 1 and e.sent()[0].startswith("⚠️ t1"), e.sent())
e.done()

# 5. reported success but Last run not updated → done, held for the slot
e = Env()
e.tick(STUB_MODE="report-only")
check("done: state done", e.state().get("t1", {}).get("done") is True, e.state())
e.tick(STUB_MODE="report-only")
check("done: not rerun", e.invocations() == 1, e.invocations())
check("done: single message", len(e.sent()) == 1, e.sent())
e.done()

# 6. task reports its own failure every attempt (no Last run) → still ONE alert per slot
e = Env()
for i in range(4):
    e.tick(STUB_MODE="fail-report")
check("selffail: 3 invocations", e.invocations() == 3, e.invocations())
check("selffail: one alert total", len(e.sent()) == 1 and e.sent()[0].startswith("❌ t1"), e.sent())
tg = sorted(re.search(r"^telegram: (\S+)", open(r).read(), re.M).group(1) for r in e.records())
check("selffail: records sent+suppressed", tg.count("sent") == 1 and tg.count("suppressed") == 2 and "failed" not in tg, tg)
e.done()

# 7. harness cannot start → counted as an attempt (rc 127)
e = Env()
env = dict(e.env); env.pop("AGENT_HARNESS_CMD")
for i in range(3):
    subprocess.run(["/bin/bash", TICK], env=dict(env, AGENT_HARNESS="bogus"), capture_output=True)
st = e.state().get("t1", {})
check("nostart: 3 attempts rc127", st.get("attempts") == 3 and st.get("last_rc") == 127, st)
check("nostart: one alert", len(e.sent()) == 1 and "harness exit 127" in e.sent()[0], e.sent())
e.done()

# 8. runrecord unit: scope mapping, unregistered task dedupe by day, telegram failure
e = Env()
r = e.rr(["write", "--task", "t2", "--status", "partial", "--telegram", "none"], "body text")
check("write: Analyst → work (folder scope)", r.returncode == 0 and len(e.records("work")) == 1, r.stderr)
r = e.rr(["write", "--task", "x", "--agent", "PLANNER", "--status", "success", "--telegram", "sent"], "hi")
check("write: --agent Planner → work (case-insensitive)", len(e.records("work")) == 2)
r = e.rr(["write", "--task", "zzz", "--status", "success", "--telegram", "none"], "")
check("write: unknown agent → firewalled scope", any("_zzz.md" in x for x in e.records()), e.records())
fname = os.path.basename(e.records("work")[0])
check("write: filename pattern", re.match(r"^\d{4}-\d{2}-\d{2}_\d{4}_(t2|x)\.md$", fname), fname)
for i in range(2):
    r = e.rr(["report", "--task", "news-fetch", "--scope", "personal", "--agent", "launchd", "--status", "failed"], "❌ news-fetch — d\ncrash")
check("report: unregistered failure deduped per day", len([m for m in e.sent() if "news-fetch" in m]) == 1, e.sent())
r = e.rr(["report", "--task", "t1", "--status", "success"], "✅ t1 — d", NOTIFY_DRY_RUN="fail")
check("report: telegram failure → exit 1 + recorded", r.returncode == 1 and "telegram: failed" in r.stdout, (r.returncode, r.stdout, r.stderr))
r = e.rr(["report", "--task", "t1", "--status", "success"], "  \n")
check("report: empty message rejected", r.returncode == 2)
r = e.rr(["report", "--task", "t1", "--status", "success"], "✅ t1 — d\n→ Knowledge/x.md")
check("report: keeps caller's → line", e.sent()[-1].count("→ ") == 1 and e.sent()[-1].endswith("Knowledge/x.md"), e.sent()[-1])
# no Telegram configured: notify.sh logs the message, the record says telegram: logged
nlog = os.path.join(e.d, "notify.log")
r = e.rr(["report", "--task", "t1", "--status", "success"], "✅ t1 — no telegram", NOTIFY_DRY_RUN="",
         NOTIFY_ENV_FILE=os.path.join(e.d, "missing.env"), NOTIFY_LOG=nlog, TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="")
check("report: no Telegram → telegram: logged, exit 0", r.returncode == 0 and "telegram: logged" in r.stdout, (r.returncode, r.stdout, r.stderr))
check("report: no Telegram → message in notify log", os.path.exists(nlog) and "✅ t1 — no telegram" in open(nlog).read())
e.done()

# 8b. scope resolution without a firewall / single-domain layout
e = Env()
os.unlink(os.path.join(e.d, "CONVENTIONS.md"))
os.makedirs(os.path.join(e.d, "helper"))  # single-domain agent folder: agents/helper/
r = e.rr(["write", "--task", "a", "--agent", "Helper", "--status", "success", "--telegram", "none"], "")
check("scope: single-domain agent → general", len(e.records("general")) == 1, e.records("general"))
r = e.rr(["write", "--task", "b", "--agent", "Nobody", "--status", "success", "--telegram", "none"], "")
check("scope: unknown agent, no firewall → general", len(e.records("general")) == 2)
r = e.rr(["write", "--task", "c", "--agent", "Nobody", "--status", "success", "--telegram", "none"], "", SCHED_DEFAULT_SCOPE="misc")
check("scope: SCHED_DEFAULT_SCOPE overrides general", len(e.records("misc")) == 1)
e.done()

# 9. notify.sh truncation respects 4096 UTF-16 units
long = ("📰 headline line " * 20 + "\n") * 60
r = subprocess.run(["/bin/bash", NOTIFY, "-"], input=long, capture_output=True, text=True, env=dict(os.environ, NOTIFY_DRY_RUN="1"))
out = r.stdout.split("notify[dry-run]:\n", 1)[1].rstrip("\n")
check("notify: ≤4096 utf16", len(out.encode("utf-16-le")) // 2 <= 4096 and out.endswith("…[truncated]"), len(out.encode("utf-16-le")) // 2)
r = subprocess.run(["/bin/bash", NOTIFY, ""], capture_output=True, text=True, env=dict(os.environ, NOTIFY_DRY_RUN="1"))
check("notify: empty → exit 2", r.returncode == 2)
r = subprocess.run(["/bin/bash", NOTIFY, "hello"], capture_output=True, text=True,
                   env=dict(os.environ, NOTIFY_DRY_RUN="", NOTIFY_ENV_FILE="/nonexistent/notify.env", TELEGRAM_BOT_TOKEN="",
                            TELEGRAM_CHAT_ID="", NOTIFY_LOG=os.path.join(tempfile.mkdtemp(), "n.log")))
check("notify: no Telegram → exit 4, printed", r.returncode == 4 and "notify[no-telegram]:\nhello" in r.stdout, (r.returncode, r.stdout))

passed = sum(1 for _, ok in results if ok)
print(f"{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)

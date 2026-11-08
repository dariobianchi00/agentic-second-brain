"""Tests for tokencheck.py (weekly token check).
Mocked checks only: fake Google token endpoint (patched http()), local HTTP server for bearer
checks, fake CLIs, fake `claude mcp list`, fake pmset, temp registry/state/runs. NOTIFY_DRY_RUN=1
everywhere — nothing is ever sent, no real credential is read, no real workspace state is touched.
Scopes in the fixtures are fictional: "work" and "personal".
Run: python3 -I agents/scheduler/test_tokencheck.py
"""
import base64, datetime as dt, glob, http.server, json, os, re, shutil, subprocess, sys, tempfile, threading
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import tokencheck as tc  # noqa: E402
os.environ["SCHED_PLATFORM"] = "macos"  # fixtures exercise the macOS DarkWake path; test_platform.py covers Linux/WSL

TZ = dt.timezone(dt.timedelta(hours=8))
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    if not cond:
        print(f"FAIL  {name}  {str(detail)[:800]}")


def T(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=TZ)


TMP = tempfile.mkdtemp(prefix="tokencheck-test-")
J = lambda *p: os.path.join(TMP, *p)
SECRET_RT = "1//0gFAKErefreshTOKENvalue_abcdefghijklmnop"
SECRET_CS = "GOCSPX-fakeClientSecret123456"
SECRET_BEARER = "ntn_FAKEexampleTOKENabcdefghijklmnopqrst"


def write(p, content):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content if isinstance(content, str) else json.dumps(content))
    return p


# ───── 1. scrub ─────
s = tc.scrub("bot123456:AAH-xyz_ABC ya29.a0AfB_x 1//0gABC-def gho_abcDEF123 Bearer abc.def eyJhbGciOi.eyJzdWIi.sig "
             + "x" * 40 + " ok")
check("scrub: no secret survives", not re.search(r"AAH-xyz|ya29\.a0|1//0g|gho_abc|Bearer abc|eyJhbG|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", s), s)
check("scrub: normal words kept", s.endswith("ok"), s)
check("scrub: truncates", len(tc.scrub("word " * 100, 50)) == 50)

# ───── 2. claude mcp list parsing (line format of `claude mcp list`, fictional servers) ─────
LISTING = """Checking MCP server health…

claude.ai Mail: https://mail.example.com/mcp/v1 - ✔ Connected
claude.ai Analytics: https://mcp.analytics.example.com/mcp - ! Needs authentication
plugin:chat:chat: https://mcp.chat.example.com/mcp (HTTP) - ! Needs authentication
plugin:team-tools:calendar:  (HTTP) - - Not configured
mail-local: npx -y example-mail-mcp - ✔ Connected
plugin:notify:notify: bun run --cwd /x/notify/0.0.7 --shell=bun --silent start - ✔ Connected
reports: https://reports.example.com/api/mcp (HTTP) - ✘ Failed to connect — invalid_request: The token request is invalid.
"""
p = tc.parse_mcp_list(LISTING)
check("mcp parse: names with colons", p.get("plugin:chat:chat") == "! Needs authentication" and "plugin:notify:notify" in p, p)
check("mcp parse: name with space", p.get("claude.ai Mail") == "✔ Connected", p)
check("mcp parse: failed reason", p.get("reports", "").startswith("✘ Failed to connect — invalid_request"), p)
check("mcp parse: not configured", p.get("plugin:team-tools:calendar") == "- Not configured", p)
check("mcp parse: header line ignored", len(p) == 7, sorted(p))


def cred(cid, check_, scope="work", **kw):
    d = {"id": cid, "name": cid, "scope": scope, "relogin": f"RELOGIN-{cid}", "check": check_}
    d.update(kw)
    return d


NOW = T("2026-10-19 09:00:00")
NEXT = T("2026-10-26 08:00:00")
ctx_mcp = lambda listing, err=None: {"now": NOW, "tz": TZ, "timeout": 5, "mcp": lambda: (listing, err)}
for server, want, name in [("claude.ai Mail", tc.OK, "connected → OK"), ("claude.ai Analytics", tc.DEAD, "needs auth → DEAD"),
                           ("reports", tc.DEAD, "failed → DEAD"), ("plugin:team-tools:calendar", tc.UNKNOWN, "not configured → UNKNOWN"),
                           ("nope", tc.DEAD, "absent → DEAD")]:
    r = tc.check_claude_mcp(cred("x", {"kind": "claude_mcp", "server": server}), ctx_mcp(p))
    check(f"claude_mcp: {name}", r["status"] == want, r)
r = tc.check_claude_mcp(cred("m", {"kind": "claude_mcp", "server": "reports"}), ctx_mcp(p))
check("claude_mcp: failure reason in detail", "invalid_request" in r["detail"], r)
r = tc.check_claude_mcp(cred("x", {"kind": "claude_mcp", "server": "claude.ai Mail"}), ctx_mcp({}, "claude CLI not found"))
check("claude_mcp: listing error → UNKNOWN", r["status"] == tc.UNKNOWN and "not found" in r["detail"], r)

# fake claude binary for claude_mcp_list()
fake_claude = write(J("bin", "claude"), "#!/bin/bash\n[ \"$1 $2\" = \"mcp list\" ] && cat <<'X'\n" + LISTING + "X\n")
os.chmod(fake_claude, 0o755)
os.environ["TOKEN_CLAUDE_BIN"] = fake_claude
listing, err = tc.claude_mcp_list(10)
check("claude_mcp_list: runs the CLI and parses", err is None and listing.get("mail-local") == "✔ Connected", (listing, err))
write(J("bin", "claude-empty"), "#!/bin/bash\necho 'boom'; exit 3\n"); os.chmod(J("bin", "claude-empty"), 0o755)
os.environ["TOKEN_CLAUDE_BIN"] = J("bin", "claude-empty")
listing, err = tc.claude_mcp_list(10)
check("claude_mcp_list: no lines → error", listing == {} and "exit 3" in (err or ""), err)
os.environ["TOKEN_CLAUDE_BIN"] = fake_claude

# ───── 3. google_refresh (patched http) ─────
keys = write(J("g", "keys.json"), {"installed": {"client_id": "cid.apps", "client_secret": SECRET_CS, "token_uri": "https://oauth2.googleapis.com/token"}})
flat_creds = write(J("g", "flat.json"), {"access_token": "ya29.old", "refresh_token": SECRET_RT, "expiry_date": 0})
gd_creds = write(J("g", "gdrive.json"), [{"scopes": ["x"], "token": {"access_token": "ya29.o", "refresh_token": SECRET_RT, "expires_at": [1]}}])
gd_keys = write(J("g", "gd_secret.json"), {"client_id": "cid", "client_secret": SECRET_CS})
dm_creds = write(J("g", "dm.json"), {"version": 1, "accounts": {"default": {"refreshToken": SECRET_RT}}, "defaultAccount": "default"})
# short-lived token file: issued 2026-10-14 09:00 (+3599 s access expiry), 7-day refresh lifetime → expires 10-21 08:59:59
issued = T("2026-10-14 09:00:00").timestamp()
short_creds = write(J("g", "short.json"), {"refresh_token": SECRET_RT, "expires_in": 3599, "expiry_date": int((issued + 3599) * 1000),
                                     "refresh_token_expires_in": 604799})

calls = []


def fake_http(responses):
    def f(req, timeout):
        calls.append(req)
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    return f


real_http = tc.http
ctx = {"now": NOW, "tz": TZ, "timeout": 5, "mcp": None}
tc.http = fake_http([(200, {"access_token": "ya29.new", "expires_in": 3599})])
r = tc.check_google_refresh(cred("g", {"kind": "google_refresh", "format": "flat", "creds": flat_creds, "keys": keys}), ctx)
check("google: 200 → OK", r["status"] == tc.OK and r["expires"] is None, r)
body = calls[-1].data.decode()
check("google: posts a refresh_token grant to token_uri", "grant_type=refresh_token" in body and calls[-1].full_url == "https://oauth2.googleapis.com/token", calls[-1].full_url)
check("google: no secret in result", SECRET_RT not in json.dumps(r) and SECRET_CS not in json.dumps(r) and "ya29" not in json.dumps(r))
check("google: creds file not modified", json.load(open(flat_creds))["access_token"] == "ya29.old")

tc.http = fake_http([(200, {"access_token": "ya29.new", "refresh_token_expires_in": 2 * 86400})])
r = tc.check_google_refresh(cred("g", {"kind": "google_refresh", "format": "flat", "creds": flat_creds, "keys": keys}), ctx)
check("google: refresh_token_expires_in → expires", r["expires"] == (NOW + dt.timedelta(days=2)).isoformat(timespec="minutes"), r)

tc.http = fake_http([(200, {"access_token": "ya29.new"})])
r = tc.check_google_refresh(cred("short", {"kind": "google_refresh", "format": "gmail", "creds": short_creds, "keys": keys, "expiry_from_file": True}), ctx)
check("google: expiry_from_file (issue time + refresh lifetime), 'gmail' alias of flat", r["expires"] and r["expires"].startswith("2026-10-21T08:59"), r)

tc.http = fake_http([(400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})])
r = tc.check_google_refresh(cred("short", {"kind": "google_refresh", "format": "gmail", "creds": short_creds, "keys": keys, "expiry_from_file": True}),
                            {"now": T("2026-10-22 09:00:00"), "tz": TZ, "timeout": 5})
check("google: invalid_grant → DEAD with expired date", r["status"] == tc.DEAD and "invalid_grant" in r["detail"] and "expired 2026-10-21" in r["detail"], r)

tc.http = fake_http([(500, None)])
r = tc.check_google_refresh(cred("g", {"kind": "google_refresh", "format": "flat", "creds": flat_creds, "keys": keys}), ctx)
check("google: 500 → UNKNOWN", r["status"] == tc.UNKNOWN and "500" in r["detail"], r)

tc.http = fake_http([urllib.error.URLError("no route")])
r = tc.check_google_refresh(cred("g", {"kind": "google_refresh", "format": "flat", "creds": flat_creds, "keys": keys}), ctx)
check("google: network error → UNKNOWN", r["status"] == tc.UNKNOWN and "unreachable" in r["detail"], r)

r = tc.check_google_refresh(cred("g", {"kind": "google_refresh", "format": "gmail", "creds": J("g", "missing.json"), "keys": keys}), ctx)
check("google: missing creds file → DEAD", r["status"] == tc.DEAD and "missing" in r["detail"], r)

for fmt, cp, kp in (("gdrive3", gd_creds, gd_keys), ("drivemcp", dm_creds, keys)):
    calls.clear()
    tc.http = fake_http([(200, {"access_token": "ya29.n"})])
    r = tc.check_google_refresh(cred("d", {"kind": "google_refresh", "format": fmt, "creds": cp, "keys": kp}), ctx)
    check(f"google: format {fmt} → OK and refresh token sent", r["status"] == tc.OK and "refresh_token=1%2F%2F0gFAKE" in calls[-1].data.decode(), r)
tc.http = real_http

# ───── 4. http_bearer (local server) ─────
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        ok = self.headers.get("Authorization") == "Bearer " + SECRET_BEARER or self.path.startswith("/bot" + "123:GOOD")
        self.send_response(200 if ok else 401)
        self.end_headers()
        self.wfile.write(b'{"ok": true}' if ok else b'{"error": "nope"}')

    def log_message(self, *a):
        pass


SRV = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{SRV.server_address[1]}"
tok_file = write(J("t", "mcp.json"), {"mcpServers": {"notes": {"env": {"NOTES_API_KEY": SECRET_BEARER}}}})
bad_file = write(J("t", "bad.json"), {"mcpServers": {"notes": {"env": {"NOTES_API_KEY": "wrong"}}}})
env_file = write(J("t", ".env"), "OTHER=1\nTELEGRAM_BOT_TOKEN=123:GOOD\n")
spec = lambda f: {"kind": "http_bearer", "url": BASE + "/v1/me", "token": {"file": f, "path": ["mcpServers", "notes", "env", "NOTES_API_KEY"]}}
r = tc.check_http_bearer(cred("n", spec(tok_file)), ctx)
check("bearer: good token → OK", r["status"] == tc.OK, r)
r = tc.check_http_bearer(cred("n", spec(bad_file)), ctx)
check("bearer: rejected → DEAD", r["status"] == tc.DEAD and "401" in r["detail"], r)
r = tc.check_http_bearer(cred("n", spec(J("t", "nofile.json"))), ctx)
check("bearer: token missing → DEAD, no value", r["status"] == tc.DEAD and "token not found" in r["detail"], r)
r = tc.check_http_bearer(cred("tg", {"kind": "http_bearer", "url": BASE + "/bot{token}/getMe", "token": {"env_file": env_file, "var": "TELEGRAM_BOT_TOKEN"}}), ctx)
check("bearer: {token} in URL path (Telegram) → OK, token not in result", r["status"] == tc.OK and "GOOD" not in json.dumps(r), r)
r = tc.check_http_bearer(cred("n", {"kind": "http_bearer", "url": "http://127.0.0.1:1/x", "token": {"file": tok_file, "path": ["mcpServers", "notes", "env", "NOTES_API_KEY"]}}), ctx)
check("bearer: unreachable → UNKNOWN", r["status"] == tc.UNKNOWN, r)

# ───── 5. cmd + jwt_exp ─────
write(J("bin", "okcli"), "#!/bin/bash\necho fine\n"); os.chmod(J("bin", "okcli"), 0o755)
write(J("bin", "deadcli"), "#!/bin/bash\necho 'Session expired. Run: examplecli login' >&2; exit 1\n"); os.chmod(J("bin", "deadcli"), 0o755)
exp_ts = int(T("2026-10-23 14:59:00").timestamp())
jwt = "eyJhbGciOiJIUzI1NiJ9." + base64.urlsafe_b64encode(json.dumps({"sub": "x", "exp": exp_ts}).encode()).decode().rstrip("=") + ".sig"
kcfg = write(J("t", "examplecli.json"), {"api_url": "u", "access_token": jwt})
r = tc.check_cmd(cred("k", {"kind": "cmd", "argv": [J("bin", "okcli")], "jwt_exp": {"file": kcfg, "key": "access_token"}}), ctx)
check("cmd: rc 0 → OK + JWT exp read", r["status"] == tc.OK and r["expires"].startswith("2026-10-23T14:59"), r)
r = tc.check_cmd(cred("k", {"kind": "cmd", "argv": [J("bin", "deadcli")]}), ctx)
check("cmd: rc 1 → DEAD with first output line", r["status"] == tc.DEAD and "Session expired" in r["detail"], r)
r = tc.check_cmd(cred("k", {"kind": "cmd", "argv": ["definitely-not-a-cli-xyz"]}), ctx)
check("cmd: missing CLI → UNKNOWN", r["status"] == tc.UNKNOWN and "not found" in r["detail"], r)

# ───── 6. run_checks: EXPIRING, crash isolation, unknown kind ─────
tc.CHECKERS["fake"] = lambda c, ctx: tc.res(c, c["check"]["status"], c["check"].get("detail", ""),
                                           dt.datetime.fromisoformat(c["check"]["exp"]) if c["check"].get("exp") else None)
tc.CHECKERS["boom"] = lambda c, ctx: 1 / 0
rs = tc.run_checks([cred("soon", {"kind": "fake", "status": tc.OK, "exp": "2026-10-23T14:59:00+08:00"}),
                    cred("later", {"kind": "fake", "status": tc.OK, "exp": "2026-10-30T14:59:00+08:00"}),
                    cred("crash", {"kind": "boom"}), cred("weird", {"kind": "nope"})], NOW, NEXT)
st = {r["id"]: r["status"] for r in rs}
check("run_checks: expiry before next weekly run → EXPIRING", st["soon"] == tc.EXPIRING, st)
check("run_checks: expiry after next weekly run → OK", st["later"] == tc.OK, st)
check("run_checks: crashing check → UNKNOWN, others still run", st["crash"] == tc.UNKNOWN and st["weird"] == tc.UNKNOWN, st)
os.environ["TOKEN_CLAUDE_BIN"] = fake_claude
rs = tc.run_checks([cred("a", {"kind": "claude_mcp", "server": "claude.ai Mail"}), cred("b", {"kind": "claude_mcp", "server": "reports"})], NOW, NEXT)
check("run_checks: claude_mcp via one shared listing", [r["status"] for r in rs] == [tc.OK, tc.DEAD], rs)

# ───── 7. compose ─────
RS = [tc.res(cred("mv-dead", {}, "work"), tc.DEAD, "refresh rejected (invalid_grant)"),
      tc.res(cred("pe-dead", {}, "personal"), tc.DEAD, "HTTP 401"),
      tc.res(cred("mv-exp", {}, "work"), tc.EXPIRING, "", T("2026-10-23 14:59:00")),
      tc.res(cred("pe-unk", {}, "personal"), tc.UNKNOWN, "unreachable"),
      tc.res(cred("mv-ok", {}, "work"), tc.OK, "", T("2026-11-30 10:00:00")),
      tc.res(cred("pe-ok", {}, "personal"), tc.OK)]
m = tc.compose(RS, NOW)
check("compose: header counts", m.splitlines()[0] == "🔑 Token check — 2026-10-19 Mon · 2/6 ok · 2 dead · 1 expiring · 1 unknown", m.splitlines()[0])
check("compose: dead lines carry the re-login command", "❌ mv-dead — refresh rejected (invalid_grant)\n   ↳ RELOGIN-mv-dead" in m, m)
check("compose: expiring line with date + command", "⚠️ mv-exp — expires Fri 10-23 14:59" in m and "RELOGIN-mv-exp" in m, m)
check("compose: ok list with expiry tag", "✅ mv-ok (→11-30), pe-ok" in m, m)
mv = tc.compose(RS, NOW, scope="work")
check("compose: work scope has no personal items", "pe-" not in mv and "mv-dead" in mv and "[work]" in mv, mv)
check("compose: all ok → ✅ header", tc.compose([RS[-1]], NOW).startswith("✅ Token check"))
check("scope_status", tc.scope_status(RS, "work") == "failed" and tc.scope_status(RS[2:3], "work") == "partial"
      and tc.scope_status(RS[4:5], "work") == "success")

# ───── 8. schedule ─────
check("week_slot: Wed → that week's Monday 08:00", tc.week_slot(T("2026-10-21 15:00:00")) == T("2026-10-19 08:00:00"))
check("week_slot: Sunday → previous Monday", tc.week_slot(T("2026-10-25 23:00:00")) == T("2026-10-19 08:00:00"))

# ───── 9. main end-to-end (fake checks, dry-run notifier) ─────
PMSET = "#!/bin/bash\necho \"Current System Capabilities are: ${FAKE_PMSET_CAPS:-CPU Graphics Audio Network}\"\n"


class Env:
    def __init__(self, creds=None):
        self.d = tempfile.mkdtemp(prefix="tokencheck-main-", dir=TMP)
        j = self.j = lambda *p: os.path.join(self.d, *p)
        write(j("pmset"), PMSET); os.chmod(j("pmset"), 0o755)
        creds = creds or [cred("mv-gmail", {"kind": "fake", "status": tc.DEAD, "detail": "refresh rejected (invalid_grant)"}, "work"),
                          cred("pe-gmail", {"kind": "fake", "status": tc.OK}, "personal"),
                          cred("pe-drive", {"kind": "fake", "status": tc.DEAD, "detail": "HTTP 401"}, "personal"),
                          cred("off", {"kind": "fake", "status": tc.DEAD}, "work", enabled=False)]
        write(j("credentials.json"), {"version": 1, "run": {"at": "08:00"}, "credentials": creds})
        write(j("register.md"), "# empty\n")
        self.sent_log = j("sent.log")
        self.vars = {"TOKEN_REGISTRY": j("credentials.json"), "TOKEN_STATE_FILE": j("state", "tokencheck.json"), "TOKEN_LOG": j("logs", "tokencheck.log"),
                     "HEALTH_PMSET_BIN": j("pmset"), "HEALTH_NETWORK": "1", "SCHED_RUNS_DIR": j("runs"), "SCHED_REGISTER": j("register.md"),
                     "NOTIFY_DRY_RUN": "1", "NOTIFY_DRY_RUN_LOG": self.sent_log, "FAKE_PMSET_CAPS": ""}

    def run(self, now, *args, **extra):
        saved = dict(os.environ)
        os.environ.update(self.vars)
        os.environ.update(extra)
        for k in ("SCHED_TICK_ID", "SCHED_TICK_STARTED"):
            os.environ.pop(k, None)
        import io, contextlib
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = tc.main(["--now", now] + list(args))
        finally:
            os.environ.clear(); os.environ.update(saved)
        return rc, out.getvalue()

    def sent(self):
        try:
            return [m for m in open(self.sent_log, encoding="utf-8").read().split("<<<END>>>\n") if m.strip()]
        except OSError:
            return []

    def state(self):
        try:
            return json.load(open(self.j("state", "tokencheck.json")))
        except OSError:
            return {}

    def records(self, scope="*"):
        return sorted(glob.glob(self.j("runs", scope, "*", "*.md")))

    def logtext(self):
        try:
            return open(self.j("logs", "tokencheck.log")).read()
        except OSError:
            return ""


e = Env()
write(e.j("state", "tokencheck.json"), {"week": "2026-10-12", "done": True})
rc, out = e.run("2026-10-18T20:00:00+08:00")
check("main: Sunday after last week's run → silent no-op", rc == 0 and e.sent() == [] and e.logtext() == "", (out, e.logtext()))
rc, out = e.run("2026-10-19T07:59:00+08:00")
check("main: Monday 07:59 → silent no-op", e.sent() == [] and e.logtext() == "")

rc, out = e.run("2026-10-19T08:00:00+08:00", FAKE_PMSET_CAPS="CPU Network Disk")
check("main: DarkWake at 08:00 → deferred, logged, nothing sent", e.sent() == [] and "deferred: not fully awake" in e.logtext() and e.state().get("week") == "2026-10-12")
rc, out = e.run("2026-10-19T09:00:00+08:00", HEALTH_NETWORK="0")
check("main: network down → deferred", e.sent() == [] and "network down" in e.logtext())

rc, out = e.run("2026-10-19T11:00:00+08:00")
sent = e.sent()
check("main: first full wake ≥ Mon 08:00 → ONE message", rc == 0 and len(sent) == 1, (out, sent))
check("main: message lists dead with re-login, skips disabled", sent and "❌ mv-gmail" in sent[0] and "RELOGIN-pe-drive" in sent[0] and "off" not in sent[0], sent)
stt = e.state()
check("main: state marks the week done", stt.get("week") == "2026-10-19" and stt.get("done") is True and stt.get("telegram") == "sent", stt)
mvr, per = e.records("work"), e.records("personal")
check("main: one run record per scope", len(mvr) == 1 and len(per) == 1, (mvr, per))
if mvr and per:
    mvt, pet = open(mvr[0]).read(), open(per[0]).read()
    check("main: record frontmatter (task/status/telegram)", "task: weekly-token-check" in mvt and "status: failed" in mvt and "telegram: sent" in mvt, mvt)
    check("main: work record has no personal credential (scope firewall)", "pe-" not in mvt, mvt)
    check("main: personal record has only personal items", "mv-gmail" not in pet and "pe-drive" in pet, pet)
    check("main: record name runs/<scope>/YYYY-MM/<date>_<HHMM>_<task>.md", re.search(r"/runs/work/2026-10/2026-10-19_1100_weekly-token-check\.md$", mvr[0]), mvr[0])
check("main: log line summarises", "1 ok, 2 dead" in e.logtext() and "telegram sent" in e.logtext(), e.logtext())

rc, out = e.run("2026-10-19T12:00:00+08:00")
rc, out = e.run("2026-10-21T12:00:00+08:00")
check("main: later runs the same week → no-op", len(e.sent()) == 1 and len(e.records()) == 2)
rc, out = e.run("2026-10-26T08:00:00+08:00")
check("main: next Monday 08:00 → runs again", len(e.sent()) == 2)

# Monday missed entirely (lid closed) → caught up Wednesday
e = Env()
rc, out = e.run("2026-10-21T10:00:00+08:00")
check("main: Monday missed → caught up on the next full wake (Wed)", len(e.sent()) == 1 and e.state().get("week") == "2026-10-19")

# notify failure → retried next hour, max 3 tries per week
e = Env()
e.run("2026-10-19T09:00:00+08:00", NOTIFY_DRY_RUN="fail")
s1 = e.state()
check("main: send failed → not done, retried", s1.get("done") is False and s1.get("tries") == 1 and s1.get("telegram") == "failed", s1)
check("main: failed send still writes records (telegram: failed)", any("telegram: failed" in open(p).read() for p in e.records()))
e.run("2026-10-19T10:00:00+08:00", NOTIFY_DRY_RUN="fail")
e.run("2026-10-19T11:00:00+08:00", NOTIFY_DRY_RUN="fail")
s3 = e.state()
check("main: gives up after 3 tries", s3.get("done") is True and s3.get("tries") == 3, s3)
e.run("2026-10-19T12:00:00+08:00")
check("main: no 4th try", len(e.sent()) == 3, len(e.sent()))

# --dry-run: nothing written; --only: no state
e = Env()
rc, out = e.run("2026-10-19T09:00:00+08:00", "--dry-run")
check("main: --dry-run → table + message printed, nothing sent/written", "--- results ---" in out and "--- message ---" in out
      and e.sent() == [] and e.state() == {} and e.records() == [], out)
rc, out = e.run("2026-10-20T09:00:00+08:00", "--only", "pe-gmail")
check("main: --only → runs just those, sends, no state", len(e.sent()) == 1 and "pe-drive" not in e.sent()[0] and e.state() == {}, (e.sent(), e.state()))

# all green → ✅ header, success records
e = Env([cred("a", {"kind": "fake", "status": tc.OK}, "work")])
e.run("2026-10-19T09:00:00+08:00")
check("main: all ok → ✅ message + success record", e.sent() and e.sent()[0].startswith("✅ Token check")
      and "status: success" in open(e.records()[0]).read())

# unreadable registry → one ❌ alert
e = Env()
write(e.j("credentials.json"), "{not json")
rc, out = e.run("2026-10-19T09:00:00+08:00")
check("main: unreadable registry → ❌ alert", rc == 1 and e.sent() and "registry unreadable" in e.sent()[0], e.sent())

# no Telegram configured → logged, week closed
e = Env()
rc, out = e.run("2026-10-19T09:00:00+08:00", NOTIFY_DRY_RUN="", NOTIFY_ENV_FILE=e.j("missing.env"), NOTIFY_LOG=e.j("logs", "notify.log"),
                TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="")
stt = e.state()
check("main: no Telegram → telegram logged, week done", stt.get("telegram") == "logged" and stt.get("done") is True
      and "mv-gmail" in open(e.j("logs", "notify.log")).read(), stt)
check("main: no Telegram → records say logged", e.records() and all("telegram: logged" in open(p).read() for p in e.records()))

# ───── 10. the example registry (and the real one, once created) + launchd installer ─────
for name in ("credentials.example.json", "credentials.json"):
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        continue
    cs = json.load(open(path))["credentials"]
    ids = [c["id"] for c in cs]
    check(f"{name}: unique ids", len(ids) == len(set(ids)))
    check(f"{name}: every entry has a known check kind + relogin",
          all(c["check"].get("kind") in tc.CHECKERS and c.get("relogin") for c in cs),
          [c["id"] for c in cs if not (c["check"].get("kind") in tc.CHECKERS and c.get("relogin"))])
    raw = open(path).read()
    check(f"{name}: no secret-shaped values", not re.search(r"bot\d+:|gh[opsu]_[A-Za-z0-9]|ya29\.|1//0|GOCSPX|ntn_|secret_[A-Za-z0-9]|eyJ[A-Za-z0-9_-]{10,}", raw))
inst = os.path.join(HERE, "install-tokencheck-launchd.sh")
syn = subprocess.run(["bash", "-n", inst], capture_output=True, text=True)
check("installer: bash syntax OK", syn.returncode == 0, syn.stderr)
pl = subprocess.run(["bash", inst, "--print-plist"], capture_output=True, text=True)
check("installer: --print-plist runs tokencheck.py hourly at :00",
      f"<string>{os.path.join(HERE, 'tokencheck.py')}</string>" in pl.stdout and "<key>Minute</key>\n        <integer>0</integer>" in pl.stdout, pl.stdout)
if shutil.which("plutil"):
    lint = subprocess.run(["plutil", "-lint", "-"], input=pl.stdout, capture_output=True, text=True)
    check("installer: generated plist is valid", lint.returncode == 0, lint.stdout + lint.stderr)

SRV.shutdown()
shutil.rmtree(TMP, ignore_errors=True)
passed = sum(1 for _, ok in results if ok)
print(f"{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)

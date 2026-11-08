#!/usr/bin/env python3
"""Weekly token check. Plain script — no Claude. macOS, Linux, Windows via WSL (wake probe: macOS only).

Reads the credential registry (credentials.json; start from credentials.example.json) and
runs ONE cheap, read-only test per enabled credential:
  google_refresh  OAuth refresh-token grant against Google. The new access token is discarded,
                  nothing is written back. Remaining refresh-token life comes from the response
                  (`refresh_token_expires_in`, e.g. a 7-day "Testing" OAuth app) or, with
                  expiry_from_file, from the stored issue time.
  cmd             CLI exit code (e.g. `gh auth status`); optional jwt_exp reads only the `exp`
                  claim of a stored JWT for the early warning.
  http_bearer     read-only GET with the stored token → status code only.
  claude_mcp      status line of ONE `claude mcp list` run from the workspace (✔ Connected /
                  ! Needs authentication / ✘ Failed to connect).
  manual          no automated check; listed as ❓ with the `test` text.
Secrets are read in-process only to make the call; they are never printed, logged or written.
Every detail string goes through scrub() before it is shown anywhere.

No auto-refresh: nothing is written back. Google refresh tokens on Production OAuth clients
stay alive through use, so the weekly grant doubles as a keep-alive; short-lived tokens that
need an interactive login are reported with their `relogin` command.

Output: ONE message via notify.sh (Telegram, or the notify log when Telegram is not
configured) — ❌ dead / ⚠️ expiring before the next weekly run / ❓ unknown, each with the
exact re-login command, then the ✅ list. Run records via `runrecord.py write`
(task weekly-token-check), one per scope; a scope's record holds only its own credentials
(scope firewall).

Schedule (sleep-aware on macOS, like health.py): the timer fires hourly at :00 (install with
install-tokencheck-launchd.sh on macOS, install-linux.sh on Linux, install-windows.ps1 on
Windows; on Linux/WSL every run counts as awake). The check runs ONCE per ISO week, at the first FULLY-awake
run at/after Monday 08:00 (`run.at` in the registry; a Monday spent with the lid closed is
caught up on the next full wake that week). DarkWake or no network → exits and retries next
hour. A failed send is retried on the next hourly runs (3 tries per week).

Usage:
  tokencheck.py                    # scheduled run (timer): no-op unless this week's run is due
  tokencheck.py --force            # run now even if done this week / before Monday 08:00
  tokencheck.py --dry-run          # run all checks, print table + message; no send/state/records
  tokencheck.py --only a,b         # only these credential ids (implies --force)
  --now ISO                        # pin "now" (tests)

Env overrides (tests): TOKEN_REGISTRY, TOKEN_STATE_FILE, TOKEN_LOG, TOKEN_CLAUDE_BIN,
TOKEN_WORKSPACE, plus health.py's HEALTH_PMSET_BIN, HEALTH_NETWORK and runrecord's
SCHED_RUNS_DIR, SCHED_DEFAULT_SCOPE, NOTIFY_SH, NOTIFY_DRY_RUN. Stdlib only, Python 3.9.
"""
import argparse, base64, concurrent.futures, datetime as dt, json, os, re, shutil, subprocess, sys, tempfile
import urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # no __pycache__ in a synced vault
sys.path.insert(0, HERE)
import health  # noqa: E402  (fully_awake_now, network_up, send)

TASK_ID = "weekly-token-check"
OK, DEAD, EXPIRING, UNKNOWN = "OK", "DEAD", "EXPIRING", "UNKNOWN"
ICON = {OK: "✅", DEAD: "❌", EXPIRING: "⚠️", UNKNOWN: "❓"}
MAX_TRIES = 3
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def env(name, default):
    return os.environ.get(name) or default


WORKSPACE = lambda: env("TOKEN_WORKSPACE", os.path.dirname(os.path.dirname(HERE)))
REGISTRY = lambda: env("TOKEN_REGISTRY", os.path.join(HERE, "credentials.json"))
STATE_FILE = lambda: env("TOKEN_STATE_FILE", os.path.join(HERE, "state", "tokencheck.json"))
LOG = lambda: env("TOKEN_LOG", os.path.join(HERE, "logs", "tokencheck.log"))
EXTRA_PATH = ["/opt/homebrew/bin", "/usr/local/bin", os.path.expanduser("~/.local/bin"), os.path.expanduser("~/.claude/bin")]


def xp(p):
    return os.path.expanduser(p)


# ───────────────────────── secret hygiene ─────────────────────────
SECRETISH = [
    re.compile(r"bot\d+:[A-Za-z0-9_-]+"),                      # Telegram bot token
    re.compile(r"\b(gh[opsur]_|github_pat_)[A-Za-z0-9_]+"),    # GitHub
    re.compile(r"\bya29\.[A-Za-z0-9._-]+"),                    # Google access token
    re.compile(r"\b1//[A-Za-z0-9._-]+"),                       # Google refresh token
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"\b(secret_|ntn_|pat)[A-Za-z0-9._-]{16,}"),    # Notion / Airtable
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"),  # JWT
    re.compile(r"[A-Za-z0-9_\-]{32,}"),                        # anything long and token-shaped
]


def scrub(s, limit=160):
    s = str(s or "")
    for rx in SECRETISH:
        s = rx.sub("***", s)
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def load_json(p):
    with open(xp(p), encoding="utf-8") as f:
        return json.load(f)


def dig(d, path):
    for k in path:
        d = d[k] if isinstance(d, dict) else d[int(k)]
    return d


def read_env_var(path, var):
    with open(xp(path), encoding="utf-8") as f:
        for line in f:
            if line.startswith(var + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def load_token(spec):
    """→ token or None. Never logged."""
    try:
        if spec.get("env_file"):
            return read_env_var(spec["env_file"], spec["var"])
        return dig(load_json(spec["file"]), spec.get("path") or [spec["key"]])
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


# ───────────────────────── checks ─────────────────────────
def res(c, status, detail="", expires=None):
    return {"id": c["id"], "name": c.get("name", c["id"]), "scope": c.get("scope") or health.DEF(), "status": status,
            "detail": scrub(detail), "expires": expires.isoformat(timespec="minutes") if expires else None,
            "relogin": c.get("relogin", "")}


def http(req, timeout):
    """→ (status, parsed-json-or-None). Network errors raise URLError/OSError."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, body = r.status, r.read(65536)
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read(65536) if e.fp else b""
    try:
        return code, json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return code, None


def google_secrets(chk):
    """→ (client_id, client_secret, refresh_token, token_uri, creds_dict). Raises on missing files/keys."""
    creds, keys = load_json(chk["creds"]), load_json(chk["keys"])
    # Token-file layouts: flat = {"refresh_token": …} (most OAuth helpers; "gmail" is an alias),
    # gdrive3 = [{"token": {"refresh_token": …}}], drivemcp = {"accounts": {<name>: {"refreshToken": …}}}
    fmt = chk.get("format", "flat")
    if fmt in ("flat", "gmail"):
        rt = creds["refresh_token"]
    elif fmt == "gdrive3":
        rt = creds[0]["token"]["refresh_token"]
    elif fmt == "drivemcp":
        rt = creds["accounts"][creds.get("defaultAccount") or "default"]["refreshToken"]
    else:
        raise KeyError(f"unknown format {fmt}")
    k = keys.get("installed") or keys.get("web") or keys
    return k["client_id"], k["client_secret"], rt, k.get("token_uri") or GOOGLE_TOKEN_URI, creds


def file_expiry(creds, tz):
    """Refresh-token expiry from the stored issue time: (expiry_date - expires_in) + refresh_token_expires_in."""
    try:
        rtei = int(creds.get("refresh_token_expires_in") or 0)
        exp_ms = int(creds.get("expiry_date") or 0)
    except (TypeError, ValueError, AttributeError):
        return None
    if not rtei or not exp_ms:
        return None
    issued = exp_ms / 1000 - int(creds.get("expires_in") or 3599)
    return dt.datetime.fromtimestamp(issued + rtei, tz)


def check_google_refresh(c, ctx):
    chk = c["check"]
    try:
        cid, csec, rt, uri, creds = google_secrets(chk)
    except OSError:
        return res(c, DEAD, "credentials file missing — needs a fresh login")
    except (ValueError, KeyError, IndexError, TypeError):
        return res(c, DEAD, "credentials file unreadable / no refresh token — needs a fresh login")
    data = urllib.parse.urlencode({"client_id": cid, "client_secret": csec, "refresh_token": rt,
                                   "grant_type": "refresh_token"}).encode()
    del cid, csec, rt
    try:
        code, body = http(urllib.request.Request(uri, data=data, method="POST",
                                                 headers={"Content-Type": "application/x-www-form-urlencoded"}), ctx["timeout"])
    except (urllib.error.URLError, OSError) as e:
        return res(c, UNKNOWN, f"Google token endpoint unreachable ({e.__class__.__name__})")
    finally:
        del data
    body = body if isinstance(body, dict) else {}
    if code == 200 and body.get("access_token"):
        rtei = body.get("refresh_token_expires_in")
        body.clear()
        exp = None
        if isinstance(rtei, (int, float)) and rtei > 0:
            exp = ctx["now"] + dt.timedelta(seconds=int(rtei))
        elif chk.get("expiry_from_file"):
            exp = file_expiry(creds, ctx["tz"])
        return res(c, OK, "refresh OK", exp)
    err = str(body.get("error") or "")
    body.clear()
    if err in ("invalid_grant", "unauthorized_client", "invalid_client", "deleted_client", "access_denied"):
        exp = file_expiry(creds, ctx["tz"]) if chk.get("expiry_from_file") else None
        when = f"; expired {exp:%Y-%m-%d}" if exp and exp < ctx["now"] else ""
        return res(c, DEAD, f"refresh rejected ({err}){when}")
    return res(c, UNKNOWN, f"refresh returned HTTP {code}" + (f" ({err})" if err else ""))


def jwt_exp(spec, tz):
    tok = load_token(spec)
    try:
        payload = tok.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return dt.datetime.fromtimestamp(int(claims["exp"]), tz)
    except (AttributeError, IndexError, ValueError, KeyError, TypeError):
        return None
    finally:
        del tok


def run_env():
    e = dict(os.environ)
    e["PATH"] = ":".join([e.get("PATH", "/usr/bin:/bin")] + EXTRA_PATH)
    return e


def which(name):
    return shutil.which(name, path=run_env()["PATH"])


def check_cmd(c, ctx):
    chk = c["check"]
    argv = list(chk["argv"])
    exe = which(argv[0])
    if not exe:
        return res(c, UNKNOWN, f"`{argv[0]}` CLI not found")
    try:
        r = subprocess.run([exe] + argv[1:], capture_output=True, text=True, timeout=ctx["timeout"] * 3,
                           env=run_env(), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return res(c, UNKNOWN, f"`{' '.join(argv)}` timed out")
    except OSError as e:
        return res(c, UNKNOWN, f"`{argv[0]}` failed to start ({e.__class__.__name__})")
    exp = jwt_exp(chk["jwt_exp"], ctx["tz"]) if chk.get("jwt_exp") else None
    if r.returncode == 0:
        return res(c, OK, f"`{' '.join(argv)}` OK", exp)
    out = next((l for l in (r.stdout + "\n" + r.stderr).splitlines() if l.strip()), "")
    when = f"; token expired {exp:%Y-%m-%d}" if exp and exp < ctx["now"] else ""
    return res(c, DEAD, f"`{' '.join(argv)}` exit {r.returncode}: {out}{when}")


def check_http_bearer(c, ctx):
    chk = c["check"]
    tok = load_token(chk["token"])
    if not tok:
        src = chk["token"].get("env_file") or chk["token"].get("file")
        return res(c, DEAD, f"token not found in {src}")
    url = chk["url"]
    headers = dict(chk.get("headers") or {})
    if "{token}" in url:
        url = url.replace("{token}", tok)
    else:
        headers["Authorization"] = "Bearer " + tok
    del tok
    try:
        code, body = http(urllib.request.Request(url, headers=headers, method="GET"), ctx["timeout"])
    except (urllib.error.URLError, OSError) as e:
        return res(c, UNKNOWN, f"{urllib.parse.urlsplit(chk['url']).hostname} unreachable ({e.__class__.__name__})")
    finally:
        del url, headers
    if 200 <= code < 300:
        return res(c, OK, f"HTTP {code}")
    if code in (401, 403):
        return res(c, DEAD, f"HTTP {code} — token rejected")
    return res(c, UNKNOWN, f"HTTP {code}")


# `claude mcp list` line: "<name>: <target> - <status>". Names may contain ':' (plugin:x:y) but
# never ': ' — so the name ends at the first ': '; the status is after the last ' - '.
MCP_LINE = re.compile(r"^(?P<name>[^\n]+?): (?P<target>.*) - (?P<status>[✔✘!\-] .*)$")


def parse_mcp_list(text):
    out = {}
    for line in text.splitlines():
        m = MCP_LINE.match(line.strip())
        if m:
            out[m.group("name").strip()] = m.group("status").strip()
    return out


def claude_mcp_list(timeout):
    """→ ({server: status}, error-or-None). One call, from the workspace (project-scoped servers)."""
    exe = env("TOKEN_CLAUDE_BIN", "") or which("claude")
    if not exe:
        return {}, "claude CLI not found"
    try:
        r = subprocess.run([exe, "mcp", "list"], capture_output=True, text=True, timeout=timeout,
                           cwd=WORKSPACE(), env=run_env(), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {}, f"`claude mcp list` timed out after {timeout}s"
    except OSError as e:
        return {}, f"`claude mcp list` failed to start ({e.__class__.__name__})"
    parsed = parse_mcp_list(r.stdout)
    if not parsed:
        return {}, f"`claude mcp list` exit {r.returncode}, no server lines"
    return parsed, None


def check_claude_mcp(c, ctx):
    listing, err = ctx["mcp"]()
    if err:
        return res(c, UNKNOWN, err)
    st = listing.get(c["check"]["server"])
    if st is None:
        return res(c, DEAD, f"`{c['check']['server']}` not registered (absent from `claude mcp list`)")
    if st.startswith("✔"):
        return res(c, OK, "connected")
    if "Needs authentication" in st:
        return res(c, DEAD, "needs authentication")
    if st.startswith("✘"):
        return res(c, DEAD, st.lstrip("✘ ").strip())
    return res(c, UNKNOWN, st)


def check_manual(c, ctx):
    return res(c, UNKNOWN, "no automated check — " + (c.get("test") or "check by hand"))


CHECKERS = {"google_refresh": check_google_refresh, "cmd": check_cmd, "http_bearer": check_http_bearer,
            "claude_mcp": check_claude_mcp, "manual": check_manual}


def run_checks(creds, now, next_run, timeout=20, mcp_timeout=240):
    """Run every check (threaded). OK + expiry before next_run → EXPIRING."""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)
    mcp_future = [None]

    def mcp():
        if mcp_future[0] is None:
            mcp_future[0] = pool.submit(claude_mcp_list, mcp_timeout)
        return mcp_future[0].result()

    if any(c["check"]["kind"] == "claude_mcp" for c in creds):
        mcp_future[0] = pool.submit(claude_mcp_list, mcp_timeout)  # start the slow one first
    ctx = {"now": now, "tz": now.tzinfo, "timeout": timeout, "mcp": mcp}

    def one(c):
        fn = CHECKERS.get(c["check"].get("kind"))
        if not fn:
            return res(c, UNKNOWN, f"unknown check kind {c['check'].get('kind')!r}")
        try:
            return fn(c, ctx)
        except Exception as e:  # one broken check never kills the report
            return res(c, UNKNOWN, f"check crashed: {e.__class__.__name__}")

    try:
        results = list(pool.map(one, creds))
    finally:
        pool.shutdown(wait=True)
    for r in results:
        if r["status"] == OK and r["expires"] and dt.datetime.fromisoformat(r["expires"]) < next_run:
            r["status"] = EXPIRING
    return results


# ───────────────────────── schedule ─────────────────────────
def week_slot(now, at="08:00"):
    """This ISO week's Monday at `at`."""
    h, m = (int(x) for x in at.split(":"))
    monday = (now - dt.timedelta(days=now.weekday())).date()
    return dt.datetime.combine(monday, dt.time(h, m), now.tzinfo)


def short(iso_s, now):
    d = dt.datetime.fromisoformat(iso_s)
    return d.strftime("%a %m-%d %H:%M") if d >= now - dt.timedelta(days=6) else d.strftime("%Y-%m-%d")


# ───────────────────────── message ─────────────────────────
def compose(results, now, scope=None):
    rs = [r for r in results if scope is None or r["scope"] == scope]
    dead = [r for r in rs if r["status"] == DEAD]
    exp = [r for r in rs if r["status"] == EXPIRING]
    unk = [r for r in rs if r["status"] == UNKNOWN]
    ok = [r for r in rs if r["status"] == OK]
    head = "🔑" if (dead or exp or unk) else "✅"
    parts = [f"{len(ok)}/{len(rs)} ok"] + ([f"{len(dead)} dead"] if dead else []) \
        + ([f"{len(exp)} expiring"] if exp else []) + ([f"{len(unk)} unknown"] if unk else [])
    lines = [f"{head} Token check — {now:%Y-%m-%d %a}" + (f" [{scope}]" if scope else "") + " · " + " · ".join(parts)]
    for r in dead:
        lines.append(f"❌ {r['id']} — {r['detail']}")
        if r["relogin"]:
            lines.append(f"   ↳ {r['relogin']}")
    for r in exp:
        lines.append(f"⚠️ {r['id']} — expires {short(r['expires'], now)} (before the next weekly check)")
        if r["relogin"]:
            lines.append(f"   ↳ {r['relogin']}")
    for r in unk:
        lines.append(f"❓ {r['id']} — {r['detail']}")
    if ok:
        def tag(r):
            return f"{r['id']} (→{dt.datetime.fromisoformat(r['expires']):%m-%d})" if r["expires"] else r["id"]
        lines.append("✅ " + ", ".join(tag(r) for r in ok))
    return "\n".join(lines)


def scope_status(results, scope):
    rs = [r for r in results if r["scope"] == scope]
    if any(r["status"] == DEAD for r in rs):
        return "failed"
    if any(r["status"] in (EXPIRING, UNKNOWN) for r in rs):
        return "partial"
    return "success"


def write_record(scope, status, telegram, body, started):
    fd, tmp = tempfile.mkstemp(prefix="tokencheck-msg.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "runrecord.py"), "write", "--task", TASK_ID,
                            "--status", status, "--telegram", telegram, "--scope", scope, "--agent", "token-check",
                            "--message-file", tmp, "--started", started.isoformat()], capture_output=True, text=True, timeout=60,
                           env={k: v for k, v in os.environ.items() if k not in ("SCHED_TICK_ID", "SCHED_TICK_STARTED")})
        return r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else f"(run record failed: {scrub(r.stderr, 200)})"
    finally:
        os.unlink(tmp)


# ───────────────────────── state / log ─────────────────────────
def load_state():
    try:
        d = json.load(open(STATE_FILE(), encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    p = STATE_FILE()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".tokencheck.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


def log(line, now):
    p = LOG()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{now.strftime('%Y-%m-%d %H:%M')} tokencheck: {line}\n")
    except OSError:
        pass


def table(results, now):
    w = max((len(r["id"]) for r in results), default=4)
    out = []
    for r in results:
        exp = f" · expires {short(r['expires'], now)}" if r["expires"] else ""
        out.append(f"{ICON[r['status']]} {r['id']:<{w}} [{r['scope']}] {r['status']:<8} {r['detail']}{exp}")
    return "\n".join(out)


# ───────────────────────── main ─────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="Weekly token check (macOS, Linux, WSL)")
    ap.add_argument("--dry-run", action="store_true", help="run checks, print table + message; no send, state or records")
    ap.add_argument("--force", action="store_true", help="run now even if done this week / before Monday 08:00")
    ap.add_argument("--assume-awake", action="store_true", help="skip the full-wake check")
    ap.add_argument("--only", help="comma-separated credential ids (implies --force)")
    ap.add_argument("--now", help="ISO datetime (tests)")
    a = ap.parse_args(argv)
    force = a.force or a.dry_run or bool(a.only)

    now = dt.datetime.fromisoformat(a.now) if a.now else dt.datetime.now().astimezone().replace(microsecond=0)
    if now.tzinfo is None:
        now = now.astimezone()
    try:
        reg = json.load(open(REGISTRY(), encoding="utf-8"))
    except (OSError, ValueError) as e:
        msg = f"❌ {TASK_ID} — {now:%Y-%m-%d}\nCredential registry unreadable: {e.__class__.__name__}\n   fix: copy agents/scheduler/credentials.example.json to credentials.json and check it is valid JSON"
        if a.dry_run:
            print(msg)
            return 1
        health.send(msg)
        log(f"registry unreadable: {e}", now)
        return 1
    run = reg.get("run", {})
    slot = week_slot(now, run.get("at", "08:00"))
    next_run = slot + dt.timedelta(days=7)
    state = load_state()
    week = slot.date().isoformat()
    done = state.get("week") == week and state.get("done")
    if not force and (now < slot or done):
        return 0  # silent no-op (hourly trigger): no log line, so the health check's "missed" stays honest

    awake, why = (True, "assumed") if a.assume_awake else health.fully_awake_now()
    if not awake:
        log(f"deferred: not fully awake ({why})", now)
        if a.dry_run:
            print(f"deferred: not fully awake ({why})")
        return 0
    if not health.network_up():
        log("deferred: network down — retry next hour", now)
        if a.dry_run:
            print("deferred: network down")
        return 0

    creds = [c for c in reg.get("credentials", []) if c.get("enabled", True)]
    if a.only:
        want = {x.strip() for x in a.only.split(",") if x.strip()}
        creds = [c for c in creds if c["id"] in want]
    results = run_checks(creds, now, next_run, int(run.get("http_timeout_s", 20)), int(run.get("claude_mcp_timeout_s", 240)))
    msg = compose(results, now)

    print("--- results ---\n" + table(results, now))
    if a.dry_run:
        print("--- message ---\n" + msg)
        return 0

    tg = health.send(msg)
    prev_tries = state.get("tries", 0) if state.get("week") == week else 0
    tries = prev_tries + 1
    recs = []
    for sc in sorted({r["scope"] for r in results}):
        body = compose(results, now, scope=sc)
        if tg == "logged":
            body += "\n\n(Telegram not configured — message written to the notify log.)"
        elif tg != "sent":
            body += f"\n\n(Telegram send failed — try {tries}/{MAX_TRIES}; retried next hour.)"
        recs.append(write_record(sc, scope_status(results, sc), tg, body, now))
    if not a.only:  # a partial manual re-check never closes the week
        state = {"week": week, "done": tg in health.DELIVERED or tries >= MAX_TRIES, "tries": tries, "telegram": tg,
                 "last_run": now.isoformat(), "results": {r["id"]: {"status": r["status"], "expires": r["expires"]} for r in results}}
        save_state(state)
    counts = {s: sum(1 for r in results if r["status"] == s) for s in (OK, DEAD, EXPIRING, UNKNOWN)}
    log(f"{counts[OK]} ok, {counts[DEAD]} dead, {counts[EXPIRING]} expiring, {counts[UNKNOWN]} unknown; telegram {tg}; "
        f"dead: {', '.join(r['id'] for r in results if r['status'] == DEAD) or '-'}; records {', '.join(recs)}", now)
    print("--- message ---\n" + msg + f"\n--- telegram: {tg} · records: {', '.join(recs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

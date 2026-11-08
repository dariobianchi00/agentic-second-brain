#!/usr/bin/env python3
"""Scheduler run records + outcome notification.

Every automated run leaves ONE run record:
  agents/scheduler/runs/<scope>/YYYY-MM/<YYYY-MM-DD>_<HHMM>_<task-id>.md
frontmatter (task, scope, agent, status, started, finished, outputs, telegram) and
body = the exact message sent (or why none was sent).

Subcommands
  report   send the outcome to the principal via notify.sh, then write the run record.
           The standard LAST STEP of every scheduled task (see prompt.md).
             runrecord.py report --task ID --status success|partial|failed|deferred \
               [--output PATH]... [--message-file F | -] [--no-link]
           The message is read from --message-file, or stdin. A final line
           "→ <run record path>" is appended unless the message already has a "→ " line
           (or --no-link). Failure alerts are deduplicated: one per task per slot.
           Exit 0 = record written and message sent/logged/suppressed · 1 = record written, send failed.
           telegram: logged = Telegram is not configured, notify.sh wrote the message to its log.
  write    write a record only (no Telegram): --task --status --telegram sent|logged|failed|suppressed|none
           [--output PATH]... [--message-file F | -]
  postrun  called by tick.sh after the harness exits: for each task the gate named,
           detect "Last run not updated" (= failed attempt), count attempts per slot in
           state/attempts.json, write a failed run record, and send ONE ❌ alert when the
           attempt cap is reached. A run that updated Last run but left no run record gets a
           ⚠️ record + message so nothing finishes silently.
             runrecord.py postrun --due "a b" --started ISO --harness-rc N [--harness-log F]

Common: --agent / --scope override the register. Scope = the folder the agent lives in:
agents/<scope>/<agent>/ (multi-domain layout) → <scope>; agents/<agent>/ (single-domain) →
"general". An unknown agent goes to the `firewalled-scope:` named in agents/CONVENTIONS.md
(the safer side of the scope firewall), else "general". SCHED_DEFAULT_SCOPE overrides "general".
--started defaults to $SCHED_TICK_STARTED (exported by tick.sh), else now.
Env overrides (tests): SCHED_REGISTER, SCHED_RUNS_DIR, SCHED_STATE_FILE, SCHED_LOGS_DIR,
SCHED_MAX_ATTEMPTS, NOTIFY_SH; NOTIFY_DRY_RUN is passed through to notify.sh.
Stdlib only, Python 3.9-compatible (launchd uses /usr/bin/python3).
"""
import argparse, datetime, fcntl, json, os, re, subprocess, sys, tempfile
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True  # no __pycache__ in a synced vault
import gate  # noqa: E402

STATUSES = ("success", "partial", "failed", "deferred")
TELEGRAM = ("sent", "logged", "failed", "suppressed", "none")
DELIVERED = ("sent", "logged")  # logged = no Telegram configured; the notify log holds the message
SKIP_DIRS = {"scheduler", "reference", "tools", "templates", "playbooks"}


def env_path(name, default):
    return os.environ.get(name) or default


REGISTER = lambda: env_path("SCHED_REGISTER", os.path.join(WORKSPACE, "agents", "scheduled-tasks.md"))
RUNS_DIR = lambda: env_path("SCHED_RUNS_DIR", os.path.join(HERE, "runs"))
STATE_FILE = lambda: env_path("SCHED_STATE_FILE", gate.DEFAULT_STATE)
LOGS_DIR = lambda: env_path("SCHED_LOGS_DIR", os.path.join(HERE, "logs"))
NOTIFY = lambda: env_path("NOTIFY_SH", os.path.join(HERE, "notify.sh"))


def now_local():
    return datetime.datetime.now().astimezone().replace(microsecond=0)


def parse_iso(s):
    if not s:
        return None
    d = datetime.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    return d if d.tzinfo else d.astimezone()


def iso(d):
    return d.astimezone().isoformat(timespec="seconds")


def rel(path):
    p = os.path.abspath(path)
    return os.path.relpath(p, WORKSPACE) if p.startswith(WORKSPACE + os.sep) else p


def scrub(s):
    return re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot***", s)


# ---------- register ----------
def register_tasks():
    try:
        with open(REGISTER(), encoding="utf-8") as f:
            return dict(gate.parse_tasks(f.read()))
    except OSError:
        return {}


def default_scope():
    return os.environ.get("SCHED_DEFAULT_SCOPE") or "general"


def agents_dir():
    """The folder that holds the register (agents/)."""
    return os.path.dirname(os.path.abspath(REGISTER()))


def firewalled_scope(base):
    """`firewalled-scope:` from agents/CONVENTIONS.md frontmatter, or None."""
    try:
        text = open(os.path.join(base, "CONVENTIONS.md"), encoding="utf-8").read(8000)
    except OSError:
        return None
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    v = re.search(r"^firewalled-scope:\s*([^\s#]+)", m.group(1), re.M) if m else None
    return v.group(1).strip("'\"") if v and v.group(1).strip("'\"").lower() != "none" else None


def scope_for(agent):
    """Scope = the agents/<scope>/ folder holding the agent; single-domain agents → default."""
    a = (agent or "").strip().lower()
    base = agents_dir()
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        entries = []
    if a:
        for d in entries:
            if d.startswith((".", "_")) or d.lower() in SKIP_DIRS or not os.path.isdir(os.path.join(base, d)):
                continue
            if d.lower() == a:
                return default_scope()  # single-domain: agents/<agent>/
            try:
                if any(x.lower() == a and os.path.isdir(os.path.join(base, d, x)) for x in os.listdir(os.path.join(base, d))):
                    return d  # multi-domain: agents/<scope>/<agent>/
            except OSError:
                continue
    return firewalled_scope(base) or default_scope()  # unknown agent: the safer side of the firewall


def resolve(task, agent=None, scope=None):
    block = register_tasks().get(task)
    if not agent:
        agent = gate.field(block, "Agent") if block else ""
    agent = agent or "unknown"
    return agent, (scope or scope_for(agent)), block


def slot_for(task, block, when):
    """Dedup key: the task's cron slot, or the calendar day for unregistered jobs."""
    if block:
        s = gate.task_slot(block, when)
        if s is not None:
            return gate.slot_key(s)
    return when.strftime("%Y-%m-%d")


# ---------- state (attempts.json) ----------
@contextmanager
def locked_state():
    path = STATE_FILE()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        state = gate.load_state(path)
        yield state
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".attempts.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)


# ---------- records ----------
def reserve_record(task, scope, started):
    d = os.path.join(RUNS_DIR(), scope, started.strftime("%Y-%m"))
    os.makedirs(d, exist_ok=True)
    base = f"{started.strftime('%Y-%m-%d_%H%M')}_{task}"
    n = 1
    while True:
        p = os.path.join(d, base + ("" if n == 1 else f"_{n}") + ".md")
        try:
            os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return p
        except FileExistsError:
            n += 1


def write_record(path, task, scope, agent, status, started, finished, outputs, telegram, body):
    q = json.dumps  # JSON strings are valid YAML scalars (paths with spaces, colons)
    lines = ["---", f"task: {task}", f"scope: {scope}", f"agent: {q(agent)}", f"status: {status}",
             f"started: {iso(started)}", f"finished: {iso(finished)}"]
    if outputs:
        lines.append("outputs:")
        lines += [f"  - {q(o)}" for o in outputs]
    else:
        lines.append("outputs: []")
    lines.append(f"telegram: {telegram}")
    if os.environ.get("SCHED_TICK_ID"):  # which tick wrote it (postrun's "did the task report?" check)
        lines.append(f"tick: {os.environ['SCHED_TICK_ID']}")
    lines += ["---", ""]
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".rr.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + body.rstrip("\n") + "\n")
    os.replace(tmp, path)


def fresh_records(task, scope, since):
    """Run records for `task` written during this tick: same `tick:` id when tick.sh set
    SCHED_TICK_ID, else (manual runs) written at/after `since`."""
    tick_id = os.environ.get("SCHED_TICK_ID")
    out, cutoff = [], since.timestamp() - 1
    months = {since.strftime("%Y-%m"), now_local().strftime("%Y-%m")}
    pat = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}_" + re.escape(task) + r"(_\d+)?\.md$")
    for m in months:
        d = os.path.join(RUNS_DIR(), scope, m)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if pat.match(name) and os.path.getmtime(p) >= cutoff:
                try:
                    txt = open(p, encoding="utf-8").read()
                except OSError:
                    continue
                if tick_id and not re.search(r"^tick: " + re.escape(tick_id) + r"\s*$", txt, re.M):
                    continue
                st = re.search(r"^status:\s*(\S+)", txt, re.M)
                out.append((p, st.group(1) if st else ""))
    return out


def send(message):
    """→ 'sent' | 'logged' | 'failed'. notify.sh prints nothing secret; its stdout/err go to ours (stderr).
    notify.sh exit 4 = Telegram not configured, message written to the notify log."""
    try:
        r = subprocess.run(["/bin/bash", NOTIFY(), "-"], input=message, text=True,
                           stdout=sys.stderr, stderr=sys.stderr, timeout=60)
        return {0: "sent", 4: "logged"}.get(r.returncode, "failed")
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"runrecord: notify error: {e}", file=sys.stderr)
        return "failed"


def read_message(arg):
    if arg and arg != "-":
        with open(arg, encoding="utf-8") as f:
            return f.read()
    return sys.stdin.read()


# ---------- subcommands ----------
def cmd_write(a):
    agent, scope, _ = resolve(a.task, a.agent, a.scope)
    started = parse_iso(a.started or os.environ.get("SCHED_TICK_STARTED")) or now_local()
    body = read_message(a.message_file) if (a.message_file or not sys.stdin.isatty()) else ""
    p = reserve_record(a.task, scope, started)
    write_record(p, a.task, scope, agent, a.status, started, now_local(), a.output, a.telegram, body)
    print(rel(p))
    return 0


def cmd_report(a):
    agent, scope, block = resolve(a.task, a.agent, a.scope)
    started = parse_iso(a.started or os.environ.get("SCHED_TICK_STARTED")) or now_local()
    msg = read_message(a.message_file).strip("\n")
    if not msg.strip():
        print("runrecord: empty message", file=sys.stderr)
        return 2
    p = reserve_record(a.task, scope, started)
    if not a.no_link and not re.search(r"^→ ", msg, re.M):
        msg += f"\n→ {rel(p)}"
    telegram = None
    if a.status == "failed":  # dedupe: one failure alert per task per slot
        key = slot_for(a.task, block, started)
        with locked_state() as state:
            e = state.get(a.task)
            if isinstance(e, dict) and e.get("slot") == key and e.get("alerted"):
                telegram = "suppressed"
            else:
                telegram = send(msg)
                if telegram in DELIVERED:
                    e = e if isinstance(e, dict) and e.get("slot") == key else {"slot": key, "attempts": 0}
                    e["alerted"] = True
                    state[a.task] = e
    else:
        telegram = send(msg)
    body = msg if telegram != "suppressed" else msg + "\n\n(Telegram suppressed: a failure alert for this slot was already sent.)"
    write_record(p, a.task, scope, agent, a.status, started, now_local(), a.output, telegram, body)
    print(f"{rel(p)}\ntelegram: {telegram}")
    return 1 if telegram == "failed" else 0


def last_output_line(path):
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [l.strip() for l in f.read().splitlines() if l.strip()]
    except OSError:
        return ""
    if not lines:
        return ""
    s = scrub(lines[-1])
    return s if len(s) <= 200 else s[:197] + "…"


def append_log(rows, started):
    if not rows:
        return
    d = LOGS_DIR()
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, started.strftime("%Y-%m") + ".md")
    out = [f"\n## {now_local().strftime('%Y-%m-%d %H:%M')} — tick post-check (tick.sh)\n",
           "| Task | Status | Detail |", "|------|--------|--------|"]
    out += [f"| {t} | {s} | {d_.replace('|', '/')} |" for t, s, d_ in rows]
    with open(p, "a", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def cmd_postrun(a):
    started = parse_iso(a.started) or now_local()
    cap = gate.max_attempts()
    tasks = register_tasks()
    rc = a.harness_rc
    last_line = last_output_line(a.harness_log)
    log_rows, results = [], []
    with locked_state() as state:
        for tid in a.due.split():
            block = tasks.get(tid)
            if not block:
                results.append(f"{tid}: not in register, skipped")
                continue
            slot = gate.task_slot(block, started)
            if slot is None:
                continue
            key = gate.slot_key(slot)
            agent = gate.field(block, "Agent") or "unknown"
            scope = scope_for(agent)
            last = gate.parse_last(gate.field(block, "Last run"), started.tzinfo)
            fresh = fresh_records(tid, scope, started)
            date = slot.strftime("%Y-%m-%d")

            if last is not None and last.astimezone(started.tzinfo) >= slot:
                state.pop(tid, None)
                if fresh:
                    results.append(f"{tid}: ok")
                    continue
                logp = rel(os.path.join(LOGS_DIR(), started.strftime("%Y-%m") + ".md"))
                msg = (f"⚠️ {tid} — {date}\nRan and updated Last run, but sent no outcome report.\n"
                       f"Check the scheduler log for what it did.\n→ {logp}")
                p = reserve_record(tid, scope, started)
                tg = send(msg)
                write_record(p, tid, scope, agent, "partial", started, now_local(), [], tg, msg)
                log_rows.append((tid, "partial", f"ran, no run record; ⚠️ sent by tick ({tg}) → {rel(p)}"))
                results.append(f"{tid}: partial (no report), telegram {tg}")
                continue

            # Last run not updated for this slot.
            if any(s in ("success", "partial") for _, s in fresh):
                e = state.get(tid) if isinstance(state.get(tid), dict) and state[tid].get("slot") == key else {"slot": key, "attempts": 0}
                e["done"] = True
                state[tid] = e
                log_rows.append((tid, "done", "reported success/partial but did not update Last run; held until next slot"))
                results.append(f"{tid}: done (reported, Last run not updated)")
                continue

            e = state.get(tid)
            if not (isinstance(e, dict) and e.get("slot") == key):
                e = {"slot": key, "attempts": 0}
            e["attempts"] = int(e.get("attempts", 0)) + 1
            e["last_attempt"] = iso(started)
            e["last_rc"] = rc
            n = e["attempts"]
            capped = n >= cap
            send_alert = capped and not e.get("alerted")
            why = f"Last run not updated (harness exit {rc})."
            if send_alert or not fresh:
                p = reserve_record(tid, scope, started)
                if send_alert:
                    msg = (f"❌ {tid} — {date}\n"
                           f"Failed {n}/{cap} attempts for the {slot.strftime('%H:%M')} slot — no more retries until the next slot.\n"
                           f"{why}\n" + (f"Last output: {last_line}\n" if last_line else "") + f"→ {rel(p)}")
                    tg = send(msg)
                    if tg in DELIVERED:
                        e["alerted"] = True
                    body = msg
                else:
                    tg = "none"
                    body = (f"(No Telegram — attempt {n}/{cap} for the {key} slot; one alert is sent when the cap is reached"
                            + (", and one was already sent for this slot" if e.get("alerted") else "") + f".)\n{why}\n"
                            + (f"Last output: {last_line}\n" if last_line else ""))
                write_record(p, tid, scope, agent, "failed", started, now_local(), [], tg, body)
            else:
                tg, p = "none (task reported its own failure)", fresh[0][0]
            state[tid] = e
            detail = f"attempt {n}/{cap}; {why}" + (" Retry cap reached — held until next slot." if capped else " Retry next tick.")
            detail += f" telegram: {tg}. → {rel(p)}"
            log_rows.append((tid, "failed", detail))
            results.append(f"{tid}: failed attempt {n}/{cap}, telegram {tg}")
    append_log(log_rows, started)
    for r in results:
        print("postrun: " + r)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("report", "write"):
        s = sub.add_parser(name)
        s.add_argument("--task", required=True)
        s.add_argument("--status", required=True, choices=STATUSES)
        s.add_argument("--output", action="append", default=[], help="deliverable path (repeatable)")
        s.add_argument("--message-file", help="message text file, or - for stdin (default stdin)")
        s.add_argument("--agent")
        s.add_argument("--scope", help="run-record folder (default: from the agent's folder)")
        s.add_argument("--started")
        if name == "report":
            s.add_argument("--no-link", action="store_true")
        else:
            s.add_argument("--telegram", required=True, choices=TELEGRAM)
    s = sub.add_parser("postrun")
    s.add_argument("--due", required=True)
    s.add_argument("--started", required=True)
    s.add_argument("--harness-rc", type=int, default=0)
    s.add_argument("--harness-log")
    a = ap.parse_args(argv)
    return {"report": cmd_report, "write": cmd_write, "postrun": cmd_postrun}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

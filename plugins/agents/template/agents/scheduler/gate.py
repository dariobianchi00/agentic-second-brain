"""Cheap scheduler gate (no Claude). Prints the ids of enabled tasks due now, space-separated.

Usage: gate.py <register> [<ISO now>] [--state <attempts.json>]
  exit 2 = register missing.
A task is due once per scheduled slot: the most recent slot <= now within a 7-day
look-back, unless `Last run` is at/after that slot.

Retry cap: tick.sh records failed attempts per task per slot in
state/attempts.json (override: --state or $SCHED_STATE_FILE). A task whose
current slot has reached SCHED_MAX_ATTEMPTS (default 3) failed attempts, or is
marked done (ran and reported but did not write Last run), is not due again
until its next slot. A missing or unreadable state file = no caps (fail open).
Importable: runrecord.py uses parse_tasks / task_slot / load_state.

`Only if:` precondition (optional task field, checked here, no Claude):
  `open-handoff <Agent>` = due only while a HANDOFFS.md under `_commons/` (next to
  the register: `_commons/HANDOFFS.md` or `_commons/<scope>/HANDOFFS.md`) has an
  `## Open` entry `→ <Agent>` with `[STATUS: open…]` whose title is not already in
  that agent's `memory/scheduled/inbox.md` (a drafted RETURN). The agent folder is
  `<agent>/` or `<scope>/<agent>/` next to the register (case-insensitive).
  So a pickup runs only when there is work, within one slot of a new handoff.
  Unknown condition or no readable HANDOFFS = not due (fail closed).

`Created:` (date first, note allowed): a slot on a day before it does not count,
so a new task waits for its first real slot instead of catching up one that
predates it (e.g. a weekday task created on Sunday would otherwise run for Friday's slot).
"""
import datetime, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE = os.path.join(HERE, "state", "attempts.json")


def max_attempts():
    try:
        return max(1, int(os.environ.get("SCHED_MAX_ATTEMPTS", "3")))
    except ValueError:
        return 3


def field(block, name):
    m = re.search(r"^- \*\*" + re.escape(name) + r":\*\*\s*(.+?)\s*$", block, re.M)
    return m.group(1).strip() if m else ""


def parse_tasks(text):
    """[(task_id, block)] in register order."""
    return [(b.split("\n", 1)[0].strip(), b) for b in re.split(r"^### ", text, flags=re.M)[1:]]


def match(expr, value, lo, hi):
    if expr == "*":
        return True
    for part in expr.split(","):
        step = 1
        if "/" in part:
            part, step = part.split("/", 1); step = int(step)
        if part == "*":
            rng = range(lo, hi + 1)
        elif "-" in part:
            a, b = part.split("-", 1); rng = range(int(a), int(b) + 1)
        else:
            rng = range(int(part), int(part) + 1)
        if value in rng and (value - rng.start) % step == 0:
            return True
    return False


def parse_last(s, tz):
    s = s.strip()
    if not s or s.lower() in ("never", "-", "—"):
        return None
    s = s.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M%z", "%Y-%m-%d"):
        try:
            d = datetime.datetime.strptime(s, fmt)
            return d if d.tzinfo else d.replace(tzinfo=tz)
        except ValueError:
            pass
    return None


def task_slot(block, now):
    """Most recent scheduled slot <= now, looking back up to 7 days (today included),
    so a weekly/monthly slot missed while the laptop was closed is still caught up.
    None if no valid schedule or no slot in the window."""
    m = re.search(r"`([^`]+)`", field(block, "Schedule"))
    if not m:
        return None
    parts = m.group(1).split()
    if len(parts) != 5:
        return None
    M, H, dom, mon, dow = parts
    for back in range(7):
        day = now - datetime.timedelta(days=back)
        cron_dow = (day.weekday() + 1) % 7  # cron: 0=Sun
        if not (match(dom, day.day, 1, 31) and match(mon, day.month, 1, 12) and match(dow, cron_dow, 0, 6)):
            continue
        slots = [(h, mi) for h in range(24) if match(H, h, 0, 23)
                 for mi in range(60) if match(M, mi, 0, 59)
                 if back > 0 or (h, mi) <= (now.hour, now.minute)]
        if slots:
            h, mi = slots[-1]
            return day.replace(hour=h, minute=mi, second=0, microsecond=0)
    return None


def slot_key(slot):
    return slot.isoformat(timespec="minutes")


def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def held(entry, slot, cap):
    """True if the state entry holds this slot back (retry cap reached, or done)."""
    if not isinstance(entry, dict) or entry.get("slot") != slot_key(slot):
        return False
    try:
        attempts = int(entry.get("attempts", 0))
    except (TypeError, ValueError):
        attempts = 0
    return attempts >= cap or bool(entry.get("done"))


def enabled(block):
    """`Enabled:` is true when its first word is `true` (a trailing note is allowed,
    e.g. `true (approved 2026-01-05)`)."""
    v = field(block, "Enabled").lower().split()
    return bool(v) and v[0].strip("*`.,;") == "true"


def before_created(block, slot):
    """True if `slot` falls on a day before the task's `Created:` date. No or bad date = False."""
    m = re.match(r"\d{4}-\d{2}-\d{2}", field(block, "Created"))
    return bool(m) and slot.strftime("%Y-%m-%d") < m.group(0)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _ci_child(parent, name):
    """Child folder of `parent` whose name matches `name` case-insensitively, or None."""
    try:
        for x in sorted(os.listdir(parent)):
            if x.lower() == name.lower() and os.path.isdir(os.path.join(parent, x)):
                return os.path.join(parent, x)
    except OSError:
        pass
    return None


def agent_dir(base, agent):
    """`<base>/<agent>/` (single-domain) or `<base>/<scope>/<agent>/` (multi-domain)."""
    d = _ci_child(base, agent)
    if d:
        return d
    try:
        scopes = sorted(x for x in os.listdir(base) if not x.startswith((".", "_")))
    except OSError:
        return None
    for sc in scopes:
        d = _ci_child(os.path.join(base, sc), agent) if os.path.isdir(os.path.join(base, sc)) else None
        if d:
            return d
    return None


def handoff_files(base):
    """Every readable HANDOFFS.md under `<base>/_commons/` (flat or one folder per scope)."""
    root = os.path.join(base, "_commons")
    out = [os.path.join(root, "HANDOFFS.md")]
    try:
        out += [os.path.join(root, d, "HANDOFFS.md") for d in sorted(os.listdir(root))]
    except OSError:
        pass
    return [p for p in out if os.path.isfile(p)]


def pending_handoffs(base, agent):
    """Titles of open handoffs to `agent` with no drafted RETURN in its inbox; None = unreadable."""
    texts = [t for t in (_read(p) for p in handoff_files(base)) if t is not None]
    if not texts:
        return None
    ad = agent_dir(base, agent)
    inbox = (_read(os.path.join(ad, "memory", "scheduled", "inbox.md")) if ad else None) or ""
    out = []
    for text in texts:
        m = re.search(r"^## Open\s*$(.*?)(?=^## Closed|\Z)", text, re.M | re.S)
        section = m.group(1) if m else ""
        for line in section.splitlines():
            if not line.startswith("## "):
                continue
            st = re.search(r"\[STATUS:\s*([^\]]*)\]\s*$", line)
            parts = re.sub(r"\s*\[STATUS:[^\]]*\]\s*$", "", line[3:]).split(" — ")
            if not st or len(parts) < 4 or "→" not in parts[1]:
                continue
            to = parts[1].split("→", 1)[1].strip()
            title = " — ".join(parts[3:]).strip()
            if to.lower() == agent.lower() and st.group(1).strip().lower().startswith("open") and title not in inbox:
                out.append(title)
    return out


def only_if(cond, base):
    """Evaluate a task's `Only if:` precondition. Unknown = False (fail closed)."""
    c = cond.strip().strip("`").split()
    if len(c) == 2 and c[0] == "open-handoff" and base:
        p = pending_handoffs(base, c[1])
        return bool(p)
    print(f"gate: unknown Only if: {cond!r}", file=sys.stderr)
    return False


def due_tasks(text, now, state=None, cap=None, base=None):
    """[(task_id, slot, block)] for every enabled task due now.
    base = the register's directory (for `Only if:` preconditions)."""
    state = state or {}
    cap = cap or max_attempts()
    due = []
    for tid, block in parse_tasks(text):
        if not enabled(block):
            continue
        slot = task_slot(block, now)
        if slot is None or before_created(block, slot):
            continue
        # due once per scheduled slot: skip if it already ran at or after this slot
        # (was: any DoW field => once per ISO week, so `1-5` only fired on Mondays)
        last = parse_last(field(block, "Last run"), now.tzinfo)
        if last is not None and last.astimezone(now.tzinfo) >= slot:
            continue
        if held(state.get(tid), slot, cap):  # retry cap / done
            continue
        cond = field(block, "Only if")
        if cond and not only_if(cond, base):  # run only when there is work
            continue
        due.append((tid, slot, block))
    return due


def main(argv):
    args, state_path = [], os.environ.get("SCHED_STATE_FILE") or DEFAULT_STATE
    i = 0
    while i < len(argv):
        if argv[i] == "--state" and i + 1 < len(argv):
            state_path = argv[i + 1]; i += 2; continue
        args.append(argv[i]); i += 1
    try:
        text = open(args[0], encoding="utf-8").read()
    except FileNotFoundError:
        sys.exit(2)
    now = datetime.datetime.now().astimezone()
    if len(args) > 1:  # test hook: gate.py <register> <ISO now>
        now = datetime.datetime.fromisoformat(args[1])
    base = os.path.dirname(os.path.abspath(args[0]))
    print(" ".join(t for t, _, _ in due_tasks(text, now, load_state(state_path), base=base)))


if __name__ == "__main__":
    main(sys.argv[1:])

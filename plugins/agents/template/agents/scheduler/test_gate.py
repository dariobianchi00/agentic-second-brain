"""Regression tests for gate.py. Run: python3 -I agents/scheduler/test_gate.py"""
import json, os, subprocess, sys, tempfile

GATE = os.environ.get("GATE_PY") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "gate.py")

def due(schedule, last, now, state=None, env=None):
    """state: dict written to a temp attempts.json (None = no state file)."""
    reg = f"# reg\n\n### t\n- **Schedule:** `{schedule}`\n- **Enabled:** true\n- **Last run:** {last}\n"
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(reg)
    st = os.path.join(tempfile.mkdtemp(), "attempts.json")
    if state is not None:
        with open(st, "w") as s:
            json.dump(state, s)
    run_env = dict(os.environ, **(env or {}))
    run_env.pop("SCHED_STATE_FILE", None)
    out = subprocess.run([sys.executable, GATE, f.name, now, "--state", st],
                         capture_output=True, text=True, env=run_env).stdout
    os.unlink(f.name)
    return out.strip() == "t"

# 2026-10-12 = Monday, 10-13 Tue, 10-17 Sat, 10-18 Sun, 11-01 Sun
CASES = [
    # weekdays 1-5: the bug — must fire Tue-Fri, not only Mon
    ("0 9 * * 1-5", "2026-10-12T09:09:00+08:00", "2026-10-13T09:07:00+08:00", True),
    ("0 9 * * 1-5", "2026-10-12T09:09:00+08:00", "2026-10-16T10:07:00+08:00", True),
    ("0 9 * * 1-5", "2026-10-13T09:07:00+08:00", "2026-10-13T15:07:00+08:00", False),  # once per day
    ("0 9 * * 1-5", "2026-10-13T09:07:00+08:00", "2026-10-14T08:07:00+08:00", False),  # before slot
    ("0 9 * * 1-5", "2026-10-16T09:07:00+08:00", "2026-10-17T09:07:00+08:00", False),  # Saturday
    # single weekday
    ("0 8 * * 1", "2026-10-05T08:07:00+08:00", "2026-10-12T08:07:00+08:00", True),
    ("0 8 * * 1", "2026-10-12T08:07:00+08:00", "2026-10-13T08:07:00+08:00", False),
    # daily
    ("0 7 * * *", "2026-10-15T07:07:00+08:00", "2026-10-16T07:07:00+08:00", True),
    ("0 7 * * *", "2026-10-16T08:21:36+08:00", "2026-10-16T12:07:00+08:00", False),
    # weekend list
    ("0 10 * * 0,6", "2026-10-17T10:07:00+08:00", "2026-10-18T10:07:00+08:00", True),
    # monthly
    ("0 9 1 * *", "never", "2026-11-01T09:07:00+08:00", True),
    ("0 9 1 * *", "2026-11-01T09:07:00+08:00", "2026-11-01T18:07:00+08:00", False),
    ("0 9 1 * *", "never", "2026-11-02T09:07:00+08:00", True),  # 7-day look-back catches up 11-01
    # never run, before / after slot
    ("0 9 * * 1-5", "never", "2026-10-13T08:07:00+08:00", True),  # never-run catches up Mon 10-12 slot
    ("0 9 * * 1-5", "never", "2026-10-13T09:07:00+08:00", True),
    # two slots a day: each fires once
    ("0 9,14 * * *", "2026-10-13T09:07:00+08:00", "2026-10-13T14:07:00+08:00", True),
    ("0 9,14 * * *", "2026-10-13T14:07:00+08:00", "2026-10-13T16:07:00+08:00", False),
    # look-back: missed slots within 7 days (today included) are caught up
    ("0 8 * * 1", "2026-10-05T08:07:00+08:00", "2026-10-13T10:07:00+08:00", True),   # Mon missed, Tue
    ("0 8 * * 1", "2026-10-05T08:07:00+08:00", "2026-10-14T07:07:00+08:00", True),   # Mon missed, Wed
    ("0 8 * * 1", "2026-10-13T10:07:00+08:00", "2026-10-14T07:07:00+08:00", False),  # already caught up
    ("0 9 1 * *", "2026-10-01T09:07:00+08:00", "2026-11-07T09:07:00+08:00", True),   # 6 days after
    ("0 9 1 * *", "2026-10-01T09:07:00+08:00", "2026-11-08T09:07:00+08:00", False),  # 7 days after: out of window
    ("0 7 * * *", "2026-10-15T07:07:00+08:00", "2026-10-17T06:07:00+08:00", True),   # yesterday missed, before today's slot
    ("0 7 * * *", "2026-10-17T06:07:00+08:00", "2026-10-17T06:37:00+08:00", False),  # caught up, no refire
    ("0 7 * * *", "2026-10-17T06:07:00+08:00", "2026-10-17T07:07:00+08:00", True),   # today's slot is a distinct slot
    ("0 9 * * 1-5", "2026-10-15T09:07:00+08:00", "2026-10-17T11:07:00+08:00", True),  # Sat, Fri missed
    ("0 9 * * 1-5", "2026-10-16T12:07:00+08:00", "2026-10-18T11:07:00+08:00", False), # Sun, Fri done
]

# retry cap: (schedule, last, now, state, env, want). Slot keys are ISO minutes.
SLOT = "2026-10-17T07:00+08:00"
CAP_CASES = [
    ("0 7 * * *", "2026-10-16T07:07:00+08:00", "2026-10-17T07:37:00+08:00", {"t": {"slot": SLOT, "attempts": 3}}, None, False),  # cap hit
    ("0 7 * * *", "2026-10-16T07:07:00+08:00", "2026-10-17T07:37:00+08:00", {"t": {"slot": SLOT, "attempts": 5}}, None, False),  # over cap
    ("0 7 * * *", "2026-10-16T07:07:00+08:00", "2026-10-17T07:37:00+08:00", {"t": {"slot": SLOT, "attempts": 2}}, None, True),   # under cap
    ("0 7 * * *", "2026-10-16T07:07:00+08:00", "2026-10-18T07:07:00+08:00", {"t": {"slot": SLOT, "attempts": 3}}, None, True),   # next slot: fresh
    ("0 7 * * *", "2026-10-16T07:07:00+08:00", "2026-10-17T07:37:00+08:00", {"t": {"slot": SLOT, "attempts": 0, "done": True}}, None, False),  # done
    ("0 7 * * *", "2026-10-16T07:07:00+08:00", "2026-10-17T07:37:00+08:00", {"other": {"slot": SLOT, "attempts": 9}}, None, True),  # other task
    ("0 7 * * *", "2026-10-16T07:07:00+08:00", "2026-10-17T07:37:00+08:00", {"t": {"slot": SLOT, "attempts": 3}}, {"SCHED_MAX_ATTEMPTS": "5"}, True),  # cap override
    ("0 7 * * *", "2026-10-16T07:07:00+08:00", "2026-10-17T07:37:00+08:00", "corrupt", None, True),  # bad state fails open
    ("0 7 * * 1", "2026-10-05T08:07:00+08:00", "2026-10-14T07:07:00+08:00", {"t": {"slot": "2026-10-12T07:00+08:00", "attempts": 3}}, None, False),  # caught-up weekly slot capped
    ("0 7 * * *", "2026-10-17T07:09:00+08:00", "2026-10-17T07:37:00+08:00", {"t": {"slot": SLOT, "attempts": 1}}, None, False),  # Last run wins
]

fails = 0
for sched, last, now, want in CASES:
    got = due(sched, last, now)
    if got != want:
        fails += 1
        print(f"FAIL  {sched!r:16} last={last} now={now}: want {want}, got {got}")
for sched, last, now, state, env, want in CAP_CASES:
    got = due(sched, last, now, state, env)
    if got != want:
        fails += 1
        print(f"FAIL  cap {sched!r:16} now={now} state={state} env={env}: want {want}, got {got}")
# `Only if: open-handoff <Agent>` — a temp workspace with HANDOFFS.md + inbox
def due_only_if(handoffs, inbox, cond="`open-handoff Writer`", flat=False):
    """flat=False: multi-domain (`_commons/work/`, `work/writer/`); flat=True: single-domain."""
    base = tempfile.mkdtemp()
    commons = os.path.join(base, "_commons") if flat else os.path.join(base, "_commons", "work")
    agent = os.path.join(base, "writer") if flat else os.path.join(base, "work", "writer")
    os.makedirs(commons)
    os.makedirs(os.path.join(agent, "memory", "scheduled"))
    if handoffs is not None:
        open(os.path.join(commons, "HANDOFFS.md"), "w").write(handoffs)
    open(os.path.join(agent, "memory", "scheduled", "inbox.md"), "w").write(inbox)
    reg = os.path.join(base, "scheduled-tasks.md")
    open(reg, "w").write(f"# reg\n\n### t\n- **Schedule:** `0 9-19 * * 1-5`\n- **Only if:** {cond}\n- **Enabled:** true\n- **Last run:** never\n")
    env = dict(os.environ); env.pop("SCHED_STATE_FILE", None)
    out = subprocess.run([sys.executable, GATE, reg, "2026-10-13T10:07:00+08:00", "--state", os.path.join(base, "a.json")],
                         capture_output=True, text=True, env=env).stdout
    return out.strip() == "t"

H_OPEN = "# H\n\n## Open\n\n## 2026-10-23 — Planner → Writer — HANDOFF — Playbook v1   [STATUS: open]\nbody\n\n## Closed (fortnight)\n"
ONLY_IF_CASES = [
    (H_OPEN, "", "`open-handoff Writer`", True),                                   # open handoff, nothing drafted
    (H_OPEN, "- UNPROCESSED — draft RETURN — Playbook v1", "`open-handoff Writer`", False),  # RETURN already drafted
    (H_OPEN.replace("[STATUS: open]", "[STATUS: closed 2026-10-24 by Planner]"), "", "`open-handoff Writer`", False),
    (H_OPEN.replace("→ Writer", "→ Builder"), "", "`open-handoff Writer`", False),  # addressed to someone else
    ("# H\n\n## Open\n\n## Closed\n\n## 2026-10-01 — Planner → Writer — HANDOFF — Old   [STATUS: open]\n", "", "`open-handoff Writer`", False),  # under Closed
    (H_OPEN.replace("[STATUS: open]", "[STATUS: open — Writer to start Mon]"), "", "`open-handoff Writer`", True),  # text after open
    (None, "", "`open-handoff Writer`", False),                                    # no HANDOFFS.md = fail closed
    (H_OPEN, "", "`something-else`", False),                                       # unknown condition = fail closed
]
for flat in (False, True):  # multi-domain and single-domain layouts
    for h, inbox, cond, want in ONLY_IF_CASES:
        got = due_only_if(h, inbox, cond, flat)
        if got != want:
            fails += 1
            print(f"FAIL  only-if flat={flat} cond={cond} inbox={inbox[:20]!r}: want {want}, got {got}")
import importlib.util
sys.dont_write_bytecode = True
_s = importlib.util.spec_from_file_location("g", GATE); _g = importlib.util.module_from_spec(_s); _s.loader.exec_module(_g)
for val, want in [("true", True), ("true (approved 2026-11-01)", True), ("True", True), ("false", False), ("false (staged)", False), ("", False), ("truely", False)]:
    if _g.enabled(f"- **Enabled:** {val}\n") != want:
        fails += 1; print(f"FAIL  enabled({val!r}) want {want}")
# `Created:` — a slot on a day before it does not count (2026-11-01 Sun; Fri slot 10-30)
CREATED_CASES = [
    ("0 9-19 * * 1-5", "2026-11-01 (new pickup)", "2026-11-01T16:11:00+08:00", False),  # Sunday: only Friday's slot exists
    ("0 9-19 * * 1-5", "2026-11-01 (new pickup)", "2026-11-02T09:07:00+08:00", True),   # first real slot
    ("30 7 * * 1", "2026-11-01", "2026-11-01T16:11:00+08:00", False),                       # weekly: last Monday's slot
    ("0 9 * * *", "2026-11-01", "2026-11-01T16:11:00+08:00", True),                         # same-day slot still counts
    ("0 9-19 * * 1-5", "", "2026-11-01T16:11:00+08:00", True),                              # no date = old behaviour
    ("0 9-19 * * 1-5", "soon", "2026-11-01T16:11:00+08:00", True),                          # bad date = old behaviour
]
for sched, created, now, want in CREATED_CASES:
    nowd = _g.datetime.datetime.fromisoformat(now)
    text = f"### t\n- **Schedule:** `{sched}`\n- **Enabled:** true\n- **Last run:** never\n- **Created:** {created}\n"
    got = bool(_g.due_tasks(text, nowd, {}))
    if got != want:
        fails += 1; print(f"FAIL  created={created!r} {sched} now={now}: want {want}, got {got}")
total = len(CASES) + len(CAP_CASES) + 2 * len(ONLY_IF_CASES) + 7 + len(CREATED_CASES)
print(f"{total - fails}/{total} passed")
sys.exit(1 if fails else 0)

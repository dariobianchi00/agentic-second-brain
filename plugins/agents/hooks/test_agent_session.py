"""Tests for hooks/agent-session.sh (W2.21 inbox notice, W5.1a session span).

Run: python3 hooks/test_agent_session.py
Everything runs on temp fixtures: a fake workspace, a fake transcript, a temp state dir.
"""
import json, os, subprocess, tempfile, unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent-session.sh")

CONV = """---
layout: multi-domain
firewalled-scope: Personal
work-mode: on
work-mode-flag: Instructions/.work_mode
---
# conventions
"""


def cmd_line(args, ts="2026-10-19T01:00:00.000Z"):
    content = ("<command-message>agents:start</command-message>\n"
               "<command-name>/agents:start</command-name>\n"
               f"<command-args>{args}</command-args>")
    return json.dumps({"type": "user", "message": {"role": "user", "content": content},
                       "timestamp": ts}, separators=(",", ":")) + "\n"


class Hook(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp()
        self.state = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.ws, "Agents"))
        self.write("Agents/CONVENTIONS.md", CONV)
        for a in ("Work/alex", "Personal/Sam"):
            self.write(f"Agents/{a}/context.md", "# ctx\n")
        self.tp = os.path.join(self.ws, "t.jsonl")
        self.write("t.jsonl", '{"type":"user","timestamp":"2026-10-19T01:00:00Z"}\n')

    def write(self, rel, text, mode="w"):
        p = os.path.join(self.ws, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, mode) as f:
            f.write(text)

    def inbox(self, agent, text):
        self.write(f"Agents/{agent}/memory/scheduled/inbox.md", text)

    def run_hook(self, prompt="hello", session="s1", today="2026-10-23", tp=True, cwd=None, raw=None):
        payload = raw if raw is not None else json.dumps({
            "session_id": session, "cwd": cwd or self.ws, "prompt": prompt,
            "transcript_path": self.tp if tp else ""})
        env = dict(os.environ, AGENTS_STATE_DIR=self.state, AGENTS_TODAY=today)
        r = subprocess.run(["sh", HOOK], input=payload, capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    # --- workspace / no-op ---------------------------------------------------
    def test_noop_outside_workspace(self):
        out = self.run_hook(cwd=tempfile.mkdtemp())
        self.assertEqual(out, "")
        self.assertEqual(os.listdir(self.state), [])

    def test_bad_input_never_fails(self):
        self.assertEqual(self.run_hook(raw="not json at all"), "")
        self.assertEqual(self.run_hook(raw=""), "")

    def test_non_agent_session_silent(self):
        self.inbox("Work/alex", "## UNPROCESSED — 2026-10-22 slot · alex-watch\n")
        self.assertEqual(self.run_hook(), "")

    # --- agent detection -------------------------------------------------------
    def test_start_prompt_seeds_silently_then_new_entry_notifies_once(self):
        self.inbox("Work/alex", "# inbox\n\n## UNPROCESSED — 2026-10-22 20:00 slot · alex-replies-watch · 1 new reply\n")
        self.assertEqual(self.run_hook("/agents:start alex"), "")      # startup drains itself
        self.assertEqual(self.run_hook("next"), "")                     # already seeded
        self.write("Agents/Work/alex/memory/scheduled/inbox.md",
                   "## UNPROCESSED — 2026-10-23 09:00 slot · alex-freecredit-replies-watch · 2 new replies\n", "a")
        out = self.run_hook("next")
        self.assertIn("[inbox] alex: 1 new — 2026-10-23 09:00 slot · alex-freecredit-replies-watch · 2 new replies", out)
        self.assertNotIn("lapsed", out)
        self.assertEqual(self.run_hook("again"), "")                    # no repeat every prompt

    def test_command_name_form_in_prompt(self):
        self.inbox("Work/alex", "## UNPROCESSED — a · b\n")
        p = "<command-name>/agents:start</command-name>\n<command-args>Alex</command-args>"
        self.assertEqual(self.run_hook(p), "")
        self.write("Agents/Work/alex/memory/scheduled/inbox.md", "## UNPROCESSED — c · d\n", "a")
        self.assertIn("[inbox] alex: 1 new — c · d", self.run_hook("x"))

    def test_already_open_session_found_in_transcript(self):
        # session opened before the hook existed: only the transcript knows the agent
        self.write("t.jsonl", cmd_line("alex"), "a")
        self.inbox("Work/alex", "## UNPROCESSED — 2026-10-20 09:04 · alex-replies-watch · 2 customer replies\n")
        out = self.run_hook("what's new?")
        self.assertIn("[inbox] alex: 1 new", out)
        self.assertIn("2 customer replies", out)

    def test_transcript_mentions_do_not_count(self):
        # CLAUDE.md text quoting `/agents:start <name>` is not a command message
        self.write("t.jsonl", json.dumps({"type": "user", "message": {"content": "run `/agents:start alex` <command-args>alex</command-args>"}}) + "\n", "a")
        self.inbox("Work/alex", "## UNPROCESSED — x · y\n")
        self.assertEqual(self.run_hook("hi"), "")

    def test_peer_session_never_notified(self):
        self.inbox("Work/alex", "## UNPROCESSED — x · y\n")
        self.run_hook("/agents:start alex peer peer/req.md")
        self.write("Agents/Work/alex/memory/scheduled/inbox.md", "## UNPROCESSED — z · w\n", "a")
        self.assertEqual(self.run_hook("x"), "")

    # --- firewall ---------------------------------------------------------------
    def test_mv_session_never_sees_personal_inbox(self):
        self.inbox("Personal/Sam", "- **UNPROCESSED** — 2026-10-23 · sam-tech-news — digest\n")
        self.inbox("Work/alex", "")
        self.run_hook("/agents:start alex")
        self.write("Agents/Personal/Sam/memory/scheduled/inbox.md", "- **UNPROCESSED** — 2026-10-24 · sam-secret\n", "a")
        out = self.run_hook("x")
        self.assertEqual(out, "")
        self.assertNotIn("sam", out.lower())

    def test_personal_agent_silent_in_work_mode(self):
        self.inbox("Personal/Sam", "")
        self.run_hook("/agents:start sam")
        self.write("Agents/Personal/Sam/memory/scheduled/inbox.md", "- **UNPROCESSED** — 2026-10-23 · sam-tech-news\n", "a")
        self.write("Instructions/.work_mode", "on\n")
        self.assertEqual(self.run_hook("x"), "")
        os.remove(os.path.join(self.ws, "Instructions/.work_mode"))
        self.assertIn("[inbox] Sam: 1 new — 2026-10-23 · sam-tech-news", self.run_hook("x"))

    # --- parsing ----------------------------------------------------------------
    def test_entry_parsing(self):
        self.run_hook("/agents:start alex")
        self.inbox("Work/alex", "\n".join([
            "# Alex — inbox",
            "Ticks append `UNPROCESSED` entries; entries flip UNPROCESSED → PROCESSED.",
            "- flip UNPROCESSED -> PROCESSED when drained",
            "```",
            "## UNPROCESSED — template example",
            "```",
            "## PROCESSED — 2026-10-19 · old",
            "## 2026-10-22 — riley-daily-scan — UNPROCESSED",
            "## UNPROCESSED — 2026-10-19 08:50 — alex-weekly-refresh (tick)",
            "- **UNPROCESSED** — 2026-10-22 09:0x · sam-tech-news (tick) — digest written (`Knowledge/x.md`)",
            "## UNPROCESSED — four",
            "   - **UNPROCESSED** nested bullet is not an entry",
        ]) + "\n")
        out = self.run_hook("x")
        self.assertIn("[inbox] alex: 4 new — 2026-10-22 — riley-daily-scan | 2026-10-19 08:50 — alex-weekly-refresh | 2026-10-22 09:0x · sam-tech-news — digest written (Knowledge/x.md) | +1 more", out)
        self.assertNotIn("template example", out)
        self.assertNotIn("old", out)

    def test_long_entry_is_cut(self):
        self.run_hook("/agents:start alex")
        self.inbox("Work/alex", "## UNPROCESSED — " + "word " * 60 + "\n")
        out = self.run_hook("x")
        self.assertIn(" …", out)
        self.assertLess(len(out), 260)

    # --- session span (W5.1a) ---------------------------------------------------
    def test_span_on_close_after_midnight(self):
        self.run_hook("/agents:start alex", today="2026-10-19")
        out = self.run_hook("/agents:close", today="2026-10-23")
        self.assertIn("spans: 2026-10-19 → 2026-10-23", out)

    def test_span_on_start_name_close(self):
        self.run_hook("/agents:start alex", today="2026-10-20")
        out = self.run_hook("/agents:start alex close", today="2026-10-21")
        self.assertIn("spans: 2026-10-20 → 2026-10-21", out)

    def test_no_span_same_day(self):
        self.run_hook("/agents:start alex", today="2026-10-23")
        self.assertEqual(self.run_hook("/agents:wrap", today="2026-10-23"), "")

    def test_span_from_transcript_start_date(self):
        self.write("t.jsonl", cmd_line("alex", ts="2026-10-19T03:00:00.000Z"), "a")
        out = self.run_hook("<command-name>/agents:close</command-name>", today="2026-10-23")
        self.assertIn("spans: 2026-10-19 → 2026-10-23", out)

    def test_switching_agent_resets_start(self):
        self.run_hook("/agents:start alex", today="2026-10-19")
        self.write("Agents/Work/riley/context.md", "# ctx\n")
        self.run_hook("/agents:start riley", today="2026-10-22")
        out = self.run_hook("/agents:close", today="2026-10-23")
        self.assertIn("spans: 2026-10-22 → 2026-10-23", out)
        self.assertIn("riley:", out)

    def test_span_line_matches_health_checker_regex(self):
        import re
        self.run_hook("/agents:start alex", today="2026-10-19")
        out = self.run_hook("/agents:close", today="2026-10-23")
        line = re.search(r"`(spans: [^`]+)`", out).group(1)
        m = re.search(r"^spans:\s*(\d{4}-\d{2}-\d{2})\s*(?:→|->|to)\s*(\d{4}-\d{2}-\d{2})", line, re.M)
        self.assertEqual(m.groups(), ("2026-10-19", "2026-10-23"))


SB_DOCTOR = os.environ.get("SB_DOCTOR_PY") or ""


@unittest.skipUnless(os.path.isfile(SB_DOCTOR), "vault sb_doctor.py not found")
class HealthCheckerFixture(unittest.TestCase):
    """A session memory written the way session-end step 4 says is covered by the
    vault checker (temp COPY of sb_doctor.py, temp agent dir; the vault is untouched)."""

    def test_spans_file_covers_every_day(self):
        import datetime as dt, importlib.util, shutil, sys
        from pathlib import Path
        tmp = tempfile.mkdtemp()
        shutil.copy(SB_DOCTOR, os.path.join(tmp, "sb_doctor_copy.py"))
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location("sb_doctor_copy", os.path.join(tmp, "sb_doctor_copy.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        agent = Path(tmp) / "Agents" / "Work" / "alex"
        (agent / "memory" / "sessions").mkdir(parents=True)
        (agent / "memory" / "sessions" / "2026-10-23-replies.md").write_text(
            "---\ndate: 2026-10-23\ntype: session\nspans: 2026-10-19 → 2026-10-23\n"
            "session_id: abc\nresume: claude --resume abc\n---\n\n# Replies\n")
        covered = mod._session_dates({"name": "alex", "scope": "Work", "dir": agent})
        for d in range(19, 24):
            self.assertIn(dt.date(2026, 10, d), covered)


if __name__ == "__main__":
    unittest.main(verbosity=1)

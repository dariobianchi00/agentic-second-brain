---
name: close
description: End the current agent session, save its state, and hand back the clear for a clean start. It is /agents:wrap, then tells you to type /clear. Run it from inside an active agent session; no name needed. Use /agents:wrap instead if you want to keep the conversation open after saving.
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(date), Bash(git add:*), Bash(git commit:*), Bash(git push:*), Bash(git status), Bash(git log:*), Bash(echo:*), Bash(ls)
argument-hint: (none — closes the session you are in)
---

# /agents:close — End the session and clear context

`/agents:close` is `/agents:wrap` followed by `/clear`: it saves the session's state, then tells you to type `/clear` so the next session starts fresh. Because the Session End Protocol persists everything to disk (tracker, memory, commit) and `/clear` keeps the conversation resumable, nothing is lost by clearing.

## Procedure

> **`vcs: none` workspaces** (frontmatter of `agents/CONVENTIONS.md`): there is no repository to commit to. Session End step 7 is the CHANGELOG entry `[<Name>] <summary>` (master § Session End Protocol); no `git add`, `git commit` or `git push` runs, and "committed" in the steps below reads "logged".

1. **Wrap the session first.** Do everything `/agents:wrap` does: read `${CLAUDE_PLUGIN_ROOT}/skills/wrap/SKILL.md` (if the variable is empty, glob `~/.claude/plugins/cache/*/agents/*/skills/wrap/SKILL.md` and take the highest version; in copied mode `.claude/skills/agents/skills/wrap/SKILL.md`) and follow it exactly — identify the active agent and run the full eight-step Session End Protocol.
   - If `/agents:wrap` finds no active agent, stop as it says. Do **not** clear the context.
2. **Confirm the wrap fully succeeded** before clearing: the action tracker is updated, the session memory file exists in `memory/sessions/` (Read it back — never assume), it has a `date:` line, and if the session ran over more than one day (a `[session span]` line, a `[gap notice]` of a day or more, or dates in the conversation earlier than today) it has a `spans: <first day> → <today>` line at the start of a line; and the commit (Session End Protocol step 7) reported success. If the session memory is missing or lacks the needed `spans:` line, write or fix it now, then re-check. If any step failed, stop and report it — do **not** clear the context, so the unsaved work stays visible.
3. **Hand back the clear.** Say one line: `Session wrapped and logged. Type /clear to start the next session fresh.` — and stop. A model cannot run `/clear`; the user types it.

It takes no arguments.

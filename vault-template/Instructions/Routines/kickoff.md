# Kickoff — agent session-open brief

Fires on the first agent session of the day, or on `kickoff` / `good morning`.

1. **Date** — today's date and weekday.
2. **Scheduled inbox** — new entries in the agent's `memory/scheduled/inbox.md` (unattended runs since last session).
3. **Actions** — overdue and due-this-week items from the agent's `actions.md` and the root `ACTION_ITEMS.md` (in scope only).
4. **Handoffs** — open entries addressed to this agent in `agents/_commons/<scope>/HANDOFFS.md`.
5. **Priorities** — the agent declares today's top 3; the user agrees, redirects or overrides.

Keep it under 20 lines. One emoji per line from a fixed legend: 🔴 overdue · 🟡 due soon · 📥 inbox · 🤝 handoff · 🎯 priority.

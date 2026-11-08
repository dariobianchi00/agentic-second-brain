# Agentic Second Brain

Most AI assistants wait for you to tell them what to do. Mine don't: they open every session with a view on my priorities, remember what we decided last week, and tell me when the conversation drifts.

This is the setup I run my work and my life on, every day, in [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Same system, with my data taken out.

Built by Dario Bianchi.

## What's inside

| # | Part | What it does |
|---|---|---|
| 1 | **`agents` plugin** (`plugins/agents`) | Named agents that drive the agenda. Each one opens the session with priorities, keeps an action tracker, remembers across sessions, and acts within the autonomy levels you set (L1 tell me → L4 act). Scopes keep work and personal apart: personal is firewalled from work agents. Agents hand work to each other through a shared handoffs file. |
| 2 | **`brain` plugin** (`plugins/brain`) | 16 skills, invoked as `/brain:<skill>`: meeting transcripts and batch sync, writing in your own voice, data analysis, market research, decks, product feedback, CV tailoring, job sweeps, tech news, and more. |
| 3 | **Scheduler** (inside the `agents` plugin template) | **macOS only (launchd).** Runs agents on a schedule, without you. A cheap gate decides what is due before any model call, so idle ticks cost nothing. Every run writes a record and can message you on Telegram. A daily health check flags anything that missed, failed or went stale. |
| 4 | **Starter vault** (`vault-template/`) | Folder structure, a `CLAUDE.md` with the operating rules, agent conventions, and one example agent (Atlas, a chief of staff) to copy and adapt. |

## Install

Inside Claude Code:

```
/plugin marketplace add dariobianchi00/agentic-second-brain
/plugin install agents@agentic-second-brain
/plugin install brain@agentic-second-brain
```

Then restart Claude Code. Plugins load only on a full restart.

## Quick start

1. Copy `vault-template/` to where your notes will live, and open Claude Code there.
2. Fill in `CLAUDE.md`: who you are, your priorities.
3. Run `/agents:start atlas`. Atlas reads its files, declares the priorities and asks what to work on.
4. Create your own agents with `/agents:new`.
5. **macOS only:** set up the scheduler from `agents/scheduler/README.md` to run agents unattended.

## Requirements

1. Claude Code.
2. Python 3 (scheduler, hooks).
3. **macOS** for the scheduler (launchd). Agents and skills work on any OS that runs Claude Code.
4. Optional: Herdr to run several agents side by side (peer requests, the "needs you" marker in the sidebar); Telegram for run reports; email, calendar and Google Drive MCP servers for the skills that read them.

## How I use it

The agents are not task runners. Each one owns a lane, sets the agenda at the start of the session, challenges my framing, and calls out drift. I steer. Overnight the scheduler does the routine work (inbox triage, meeting sync, picking up handoffs) and leaves the results in each agent's inbox for the next session.

Design notes for the agent framework: [`plugins/agents/PHILOSOPHY.md`](plugins/agents/PHILOSOPHY.md).

## Credits

The `agents` plugin is a branch of [Norman Noble's agent-framework](https://github.com/normannoble/agent-framework) (MIT). The autonomy model, the session mechanics and the memory design are his. The scope firewall, commons, scheduler toolkit and hooks are what I added. See [`plugins/agents/CHANGELOG.md`](plugins/agents/CHANGELOG.md).

## License

MIT. See [LICENSE](LICENSE).

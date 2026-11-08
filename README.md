# Agentic Second Brain

A second brain for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that runs itself: scoped agents with memory and autonomy levels, a pack of skills for the work a senior operator does every week, and a scheduler that runs agents unattended and reports back.

Built by Dario Bianchi. I run my own work and life on this setup every day. This repo is the same system with my data taken out.

## What's inside

| # | Part | What it does |
|---|---|---|
| 1 | **`agents` plugin** (`plugins/agents`) | Named agents that drive the agenda: they open each session with priorities, keep an action tracker, remember across sessions, and act within autonomy levels you set (L1 tell me → L4 act). Scopes keep work and personal apart: personal is firewalled from work agents. Agents hand work to each other through a shared handoffs file. |
| 2 | **`brain` plugin** (`plugins/brain`) | 18 skills, invoked as `/brain:<skill>`: meeting transcripts and batch sync, writing in your own voice, data analysis, market research, PRDs, decks, product feedback, CV tailoring, job sweeps, tech news, and more. |
| 3 | **Scheduler** (inside the `agents` plugin template) | **macOS only (launchd).** Runs agents on a schedule without you. A cheap gate decides what is due without calling the model, so idle ticks cost nothing. Every run writes a record and can message you on Telegram; a daily health check flags anything that missed, failed or went stale. |
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
3. Run `/agents:start atlas`. Atlas reads its files, declares priorities and asks what to work on.
4. Create your own agents with `/agents:new`.
5. **macOS only:** set up the scheduler from `agents/scheduler/README.md` to run agents unattended.

## Requirements

1. Claude Code.
2. Python 3 (scheduler, hooks).
3. **macOS** for the scheduler (launchd). Agents and skills work on any OS Claude Code runs on.
4. Optional: Herdr to run several agents side by side (peer requests, the "needs you" sidebar marker); Telegram for run reports; email, calendar and Google Drive MCP servers for the skills that read them.

## How it is meant to be used

The agents are not task runners. Each one owns a lane, sets the agenda at session start, challenges your framing, and tells you when the conversation drifts. You steer. The scheduler handles the routine work overnight (inbox triage, meeting sync, picking up handoffs) and leaves the results in each agent's inbox for the next session.

Design notes for the agent framework: [`plugins/agents/PHILOSOPHY.md`](plugins/agents/PHILOSOPHY.md).

## Credits

The `agents` plugin is a branch of [Norman Noble's agent-framework](https://github.com/normannoble/agent-framework) (MIT). The autonomy model, session mechanics and memory design are his; the scope firewall, commons, scheduler toolkit and hooks are additions in this branch. See [`plugins/agents/CHANGELOG.md`](plugins/agents/CHANGELOG.md).

## License

MIT. See [LICENSE](LICENSE).

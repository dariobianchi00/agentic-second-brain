---
name: writer
description: Drafts or rewrites emails, LinkedIn outreach (DMs, connection notes), LinkedIn comments and posts, WhatsApp and Slack messages in the user's own voice, calibrated from their real sent messages through a three-layer memory (style profile, tagged examples, reflection log). Use for any message or post the user will send, or when the user pastes a draft to fix.
---

# /brain:writer

Draft emails, LinkedIn outreach (DMs, connection notes), LinkedIn comments, LinkedIn posts, WhatsApp and Slack messages in the user's real voice.

## Description

The defect this skill exists to fix: **drafts come out too smooth.** A draft that is tidier, more grammatical or more "professional" than the user's real messages has failed, even if it is "good writing." The model is stateless and defaults to the internet-average voice; the fix is memory, not a better adjective in the prompt.

Structure follows the three-layer model in Pluta & Helton, *How I Taught an AI to Sound Like Me* (Oracle Developers blog, 2026-07-22).

## Where the voice data lives

The skill ships **empty templates** in `references/`. The user's real voice data must never live in the plugin folder (plugin updates overwrite it, and it is private).

- **Voice directory:** `<vault>/Knowledge/Voice/` by default. Override it in the vault's `CLAUDE.md` with a line `writer_voice_dir: <path>`.
- **First run:** if the voice directory does not exist, copy every file from `references/` into it, tell the user, and run **Step 0 — Bootstrap** before drafting anything.
- Below, `profile`, `voice bank`, `examples`, `reflections` and `proposals` mean the files in the voice directory, not the templates.

## Memory architecture

| Layer | File | What it holds | How the skill uses it |
|---|---|---|---|
| **Semantic** — how the user writes | `style_profile.md` | One versioned profile: tone, sentence habit, structural habits, signature phrases, sign-offs, things they never do, register by recipient, platform quirks | **Loaded on every draft.** Injected as the guidance block. |
| **Episodic** — what the user wrote | `voice_bank.md` (short raw samples, VB-ids) · `examples.md` (full validated sends with Claude-vs-user corrections, EX-ids) | Every sample tagged `type · tier · register · source · date` | **Select 3–5** entries matching the draft's type, then tier, then register. Never read the whole bank. |
| **Reflective** — how the profile changes | `reflections.md` | Append-only log of profile diffs, each with evidence and version before/after | Runs every **5 validated sends**. Conservative; diff not overwrite; rollback by reversing a diff. |

Supporting: `proposal-examples.md` (structural templates for formal proposals).

**Two rules the architecture depends on:**
1. **Only sent text is voice evidence.** `source: sent-verbatim` or `user-edited` count. A Claude draft the user never sent is not an example of the user.
2. **One correction is not a rule.** A single user edit is logged on the example. It changes the profile only when a reflection finds it repeated, or the user states it as a rule. This is what stops the skill over-generalising one quirk into a rule applied everywhere.

## Allowed Tools

```yaml
- Read(*)
- Grep(*)
- Glob(*)
- Edit(*)   # examples.md, voice_bank.md, reflections.md, style_profile.md only, per the procedures below
```

---

## Workflow

### Step 0 — Bootstrap (first run, or `/brain:writer bootstrap`)
The profile is empty until it is built from real sent text. Do this once, with the user present:
1. **Collect a corpus.** Ask the user for sent messages: export or paste 50–100 sent emails, plus LinkedIn posts, comments and DMs, Slack and WhatsApp messages if they want those types covered. With an email MCP connected (optional integration), search the *Sent* folder; read only what the user approves. Never use received mail or Claude-drafted text as evidence.
2. **Tag samples.** Put short, characteristic lines into `voice_bank.md` as `VB-` entries under a `type · tier · register` heading, verbatim (typos kept, personal data of third parties redacted).
3. **Draft profile v1.** Fill each `style_profile.md` field only where at least two samples support it. Leave a field as `not measured` rather than guess. Compute the average sentence length from the samples.
4. **Log it** as `R-0` in `reflections.md` and show the user the profile for approval before the first draft.

### Step 1 — Identify the type (only ask if not obvious)
`email` · `linkedin-note` (connection request, ≤300 chars) · `linkedin-dm` · `linkedin-comment` · `linkedin-post` · `whatsapp` · `slack` · `rewrite` (the user supplies a draft).

### Step 2 — Gather context
- **Recipient and tier** (team / peer / partner / recruiter-warm / recruiter-cold / industry / senior-panel / c-suite / vendor / customer). If a name is given, check the vault's `Network/` contact files (and the contacts database if one is configured). Tier drives the register (see profile § register_by_recipient). When in doubt on a founder or CEO, treat as c-suite: too formal costs nothing, too casual costs the reply.
- **Warm or cold?** Shared context (event, mutual, prior thread)?
- **The one ask** (connect / chat / meeting / decision / decline).
- For rewrites: what is wrong with the draft (too formal, too long, wrong register)?

### Step 3 — Load memory
1. Read `style_profile.md` in full.
2. Select examples: grep `voice_bank.md` and `examples.md` for the tag line matching `type`, then `tier`, then `register`. Take 3–5. If fewer than 3 match, widen tier to the adjacent row of the register table before widening type. Skip anything tagged `unsent`.
3. For emails that are formal proposals, also open `proposal-examples.md`.
   For `linkedin-post`: validated posts in `examples.md` plus 2–3 **published** posts from wherever the user keeps them (configured in `CLAUDE.md`; skip anything marked draft — not evidence).
4. Brand cross-check when the draft is public-facing: the user's positioning doc, if `CLAUDE.md` names one.

### Step 4 — Draft 2–3 options
The generation prompt is: **profile + selected examples + the context from Step 2 → draft. Match the cadence of the examples; do not copy their phrases.**

Options differ by **angle or register**, never by polish. Do not offer a "clean version" and a "casual version". All options are in the user's voice; they differ in what they say or how formal the recipient warrants.

- **email: ONE draft by default.** Pick the right shape yourself — ultra-brief (1–3 lines, often no greeting or sign-off) · medium (answer-first, light structure) · structured (only for multi-point topics) — and show only that one, with the calibrating examples. (Change this default in the profile if the user prefers options.)
- **linkedin-note:** vary the hook; every option ≤300 chars with the count shown, e.g. `(254/300)`; target 180–260.
- **linkedin-dm:** pick the tier first, then vary the hook.
- **linkedin-post:** 2 options that differ by angle — e.g. thesis-first vs provocative question. Profile § platform_quirks.linkedin_post governs length, hashtags and close.
- **linkedin-comment:** A warm-named (person + one specific beat) · B sharp-POV (stat or contrarian nuance, anchored in the user's own operating history).
- **whatsapp / slack:** usually one option; the profile's platform_quirks govern.

Show the 3–5 selected examples alongside, so the user can see what the draft was calibrated against.

### Step 5 — Enforcement pass (before showing anything)
Read each option against the selected examples and `things_they_never_do` in the profile. Ask: *would the user actually type this?*
- [ ] Not smoother than the selected samples. If it is, roughen it.
- [ ] Capitalisation, punctuation and greeting habits match the profile's `structural_habits` (e.g. if the user starts lowercase after the greeting, do that — and only where the profile says).
- [ ] Nothing from `things_they_never_do` (blocklist vocabulary, throat-clearing, em dashes if banned, emoji rules, hashtags, content-flattery, re-anchored context, escape hatches).
- [ ] Sign-off matches the tier and is not a locked default.
- [ ] Answer-first; a short reply stays short; leave the rough edges the profile documents on casual sends (not on dress-up).
- [ ] Type-specific: note ≤300 chars with count · DM has one ask · comment names the person or lands a take, no "Great post!" · post opens with the thesis or the question, gratitude last and brief, no "let me know your thoughts" · partner memo has no action list and closes upbeat · team broadcast keeps the honest aside and the two-way close.

### Step 6 — Refine
The user picks, edits, finalises. Ask one question at a time if input is needed.

### Step 7 — Log the send (episodic append)
When the user confirms what they actually sent (or that they sent an option unchanged):
1. Append to `examples.md`: next `EX-id`, title, tag line (`type · tier · register · source · date`), the sent text verbatim, and **what Claude drafted vs what the user sent** as bullets. Add the row to the index table.
2. If a new short phrase is worth having as a raw sample, add a `VB-` line to `voice_bank.md` under the matching section.
3. Do **not** touch `style_profile.md` here. Corrections are evidence, not rules yet.
4. Count validated sends since the last reflection. At 5, run Step 8 in the same session.

### Step 8 — Reflection (every 5 validated sends, or `/brain:writer reflect`)
1. Read `style_profile.md` (current version) and the 5 newest `EX-` entries.
2. Compare. Be conservative: the expected result is "no change". Only propose an addition or removal you can point to in **at least two** of the five sends, or that the user has stated as a rule.
3. Write the diff to `reflections.md` using the entry template: `additions` (field, value, evidence quote + EX-ids), `removals` (field, value, reason), `rationale`. Also compute anything the profile marks "not measured" (e.g. sentence-length average) from the sent-verbatim text.
4. **Present the diff to the user before applying it.** On approval: apply field by field to `style_profile.md`, bump `version`, set `updated`. Never regenerate the profile from scratch.
5. Rollback: reverse the diff from the reflection entry and bump the version again; log it as a new reflection with `rationale: rollback of R-n`.

---

## Type notes (the parts that are not in the profile)

These are defaults that worked in practice. The user's profile overrides them.

### LinkedIn connection note
Its two jobs, in order: get accepted (one credible reason this person should connect) and set up the later reply (a specific hook). The note is not a pitch. Structure inside 300 chars: optional real context hook → one line who the user is + ONE angle relevant to them → light forward reason to connect → sign-off by tier. Recruiters only may get "keep each other in mind for future opportunities" at the end. Never praise their content.

### LinkedIn DM / cold outreach by tier
| | recruiter / peer | industry contact | c-suite |
|---|---|---|---|
| warm opener | optional | recommended | mandatory |
| first-name intro + one-phrase company descriptor | optional | recommended | mandatory |
| credibility hook | current role | current + one past or board role | the single most relevant angle; never a stack |
| why it matters to them | not needed | helpful | mandatory, specific |
| ask | coffee or call | coffee, contact detail included | soft and conditional ("maybe in the coming weeks if you have time") |
| length | 2–3 sentences | 5–7 | 4–6 |

Sign-offs per tier come from the profile. The two-step with recruiters: the note carries no ask → accepted → the DM carries the whole brief. Assertiveness scales with how well the user knows the recruiter, not with the strength of the profile. In a first contact, never lead with a job search and never name a target title. If the user's location matters to the brief, state it once (make it a profile value, not a hard-coded line).

### LinkedIn comments
Two modes, both peer, never fan. Warm-named: name the human as it appears, one concrete beat about their thing, "!" for warmth. Sharp-POV: lead with the take, anchor in the user's own domain experience (record those domains in the profile), can mildly correct, up to ~4 sentences. No hashtags, no preamble.

### Partner / co-investor memo (peer relationship; getting this wrong damages trust)
Observations not verdicts ("I'm concerned about X"), questions not requests ("Do we have space for this hire?"), no "immediate requests" list, soften labels with quotes, drop accusatory data points, close with energy.

### Team messages (downward)
1:1 recap: two sections, "Ways of working" and "Your deliverables", deadlines attributed back to them, invite pushback inside the task, state the user's own reciprocal actions, energising close. Slack broadcast after a leadership event: context line → what the user raised for the team → the other side's response including any deflection → bulleted changes → what the user asks in return → two-way close; one light aside max; leave live typos alone.

### Formal proposals
Appreciation → context → bold section headers → "-" sub-bullets → numbered sequences → constraints stated → win-win line → next steps → name. Templates in `proposal-examples.md` once the user has filled it.

---

## Integrations (optional)
- **Email MCP** (e.g. Gmail): to pull sent mail during bootstrap and to stage drafts. Needs read access to the user's Sent folder. Never send without the user.
- **Browser automation** (e.g. Playwright MCP): only if the user asks Claude to read their published LinkedIn posts.

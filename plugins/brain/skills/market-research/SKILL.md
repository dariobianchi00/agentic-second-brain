---
name: market-research
description: Rigorous market research — market sizing (TAM/SAM/SOM), competitor landscape, and customer/demand signals — with a confirmed brief, cited and triangulated figures, confidence ratings, and an independent verification pass before delivery. Use whenever the user asks for market research, market size, competitive analysis, demand validation, or "how big is the market for X". Not for full commercial business cases or analysis of internal product/sales data (use /brain:analyze).
---

# Market Research

Produce decision-grade market research for product, pricing, investment and board decisions. Accuracy beats speed. Never present a number you cannot trace to a source.

Typical contexts: product and pricing decisions, board and advisory work, investment screens, and new-product validation. Adapt depth to the decision being made. For a full commercial business case (unit economics, P&L, go/no-go), use a dedicated business-case tool; this skill supplies its market inputs.

## Non-negotiable rules

1. **Every number is cited.** Source name, URL, publication date, and the exact figure as stated. No citation → it does not appear in the report.
2. **Load-bearing figures need 2+ independent sources.** A figure is load-bearing if the conclusion changes when it moves ±30%. Prefer primary sources: annual reports, SEC/regulator filings, central banks, national statistics offices, World Bank, IMF, GSMA, company investor materials.
3. **Second-hand figures** (e.g. a blog quoting paywalled Statista) may be used but are tagged `SECONDARY-UNVERIFIED`, rated Low confidence, never used alone as a load-bearing figure, and logged as an access gap (see Step 6).
4. **Freshness.** Data older than 24 months is tagged `STALE` with a reason it is still used. Always state the data year, not just the publication year.
5. **Currency.** Report in USD with local currency alongside. State the FX rate, source and date used. Never mix nominal years without saying so.
6. **Separate facts, estimates and assumptions.** Every assumption gets an ID (A1, A2…) and is listed in the assumptions log.
7. **No invented precision.** Round to the precision the sources support. Ranges beat false point estimates.
8. **Disagreeing sources are reported, not averaged away.** Show the spread and explain which you trust and why.

## Confidence scale (apply to every key figure and every conclusion)

- **High** — 2+ independent sources, at least one primary, agree within ±15%, data ≤24 months old.
- **Medium** — one primary source, or 2+ reputable secondary sources agreeing; or minor staleness.
- **Low** — single secondary source, second-hand, stale, or heavy assumption chain.

## Tools & escalation ladder

Use the lowest tier that gets a verifiable answer. Escalate only when a lower tier fails (blocked, JS-rendered, incomplete, or only second-hand). Record the tier used for every source in `sources.csv` (`retrieval_method` column).

**Approval rule: WebSearch and WebFetch are the only tools used without asking.** Anything else — running code to call an API, downloading and parsing files, Playwright, connectors — requires the user's approval *during* the research, at the moment the need arises. Approvals last for the current session only; a new session asks again.

**How to ask (pause the research and ask in one short message):**
> Need to go beyond WebFetch. **Tool:** <tier/tool> · **Where:** <site/API> · **Why:** <what WebFetch couldn't get> · **Data:** <figure needed> · **Impact:** <load-bearing? how confidence changes> · Approve for this session? (yes / no / yes for this site only)

Batch pending requests into one question where possible. While waiting, continue Tier 1 work on other parts. If declined, log it as an access gap and continue with what Tier 1 gives, flagging affected figures.

| Tier | Tool | Use for | Approval |
|---|---|---|---|
| 1 | **WebSearch + WebFetch** | Discovery, news, articles, static pages, simple PDFs WebFetch can read | None — default |
| 2 | **Open data APIs via code** (curl / Python): World Bank, IMF, UN data, OECD, SEC EDGAR, FRED, central-bank and statistics-office APIs, Google Trends (pytrends) | Load-bearing macro, population, financial and filing data straight from the primary source | Ask — once per session |
| 3 | **File download + extraction** (pdfplumber / pandas): annual reports, regulator PDFs, investor decks, Excel/CSV downloads | Exact figures from primary documents WebFetch can't parse properly | Ask — once per session |
| 4 | **Playwright (headless browser)** | JS-rendered pricing pages, app-store pages, interactive statistics portals, filtered/paginated tables | Ask — once per session, naming the sites |
| 5 | **Authenticated sources / MCP connectors** (a site the user signs into; Amplitude, PostHog, Metabase) | Gated or internal data | Ask — **every time** |
| 6 | **Parallel subagents** | Fan-out: one agent per competitor or country. Subagents follow the same approval rule — WebSearch/WebFetch only unless the user has already approved a tier this session | None for the fan-out itself |

**Paid data:** don't assume access to paid data subscriptions (Statista, Crunchbase, PitchBook, Sensor Tower etc.) — ask, or check the vault's `CLAUDE.md` for what the user has. When one would materially improve a load-bearing figure, list it under access gaps with what it would unlock and indicative cost if publicly listed.

**Playwright:** use the Playwright MCP if it is already installed. Never register a new MCP server or install packages yourself; if Playwright is unavailable, log it as an access gap and tell the user.

**Hard limits for all tiers:**
- Never enter passwords, bypass CAPTCHAs, paywalls or bot detection. If a site requires login, the user signs in themselves; Claude only reads.
- Respect robots.txt and site terms; rate-limit (≥2s between page loads on the same domain); no bulk scraping of personal data.
- Never use any tool beyond WebSearch/WebFetch without the user's explicit yes in this session; never use an MCP connector or authenticated source without a yes for that specific request.
- If a tier is blocked, log it as an access gap — don't silently fall back to a weaker source for a load-bearing figure.

## Workflow

### Step 1 — Research brief (ALWAYS stop here for approval)

Write `brief.md` from `templates/brief.md` and show it to the user. Include:
- The decision this research supports, and the core question(s)
- Research type(s): sizing / competitors / demand signals
- Geography, segment, customer definition, timeframe, currency
- Hypotheses to test (including ones that could kill the idea)
- Planned sources and method
- **Tools plan:** which tiers beyond WebFetch are likely to be needed and for what. This is a forecast only — approving the brief does not approve any tool; each is still asked for during research when the need arises.
- **Access check:** list paid databases, gated reports or connectors (MCP servers) likely to hold the answer that are not available now (e.g. Statista, Crunchbase, PitchBook, Sensor Tower/data.ai, Euromonitor, GSMA Intelligence, CB Insights). For each: what it would add, and whether it is worth enabling or subscribing.
- Open questions for the user

Do not start research until the user approves or amends the brief. If any MCP connector or tool could answer part of the question, ask before using it.

### Step 2 — Collect

- Set up the output folder: **ask the user where to save it** (propose a default: the folder of the product or topic the research is about) and use `<that folder>/YYYY-MM-DD-<slug>/`. Never create a new top-level folder without the user's yes.
- Follow the tools ladder. For each load-bearing figure, try to reach the primary source via Tier 2–3 before accepting a Tier 1 article.
- Search broad, then narrow. Run separate searches per competitor, per country, per metric. Fetch full pages for any figure you will use; never cite from a search snippet.
- Log every source in `sources.csv` (template in `templates/sources.csv`) as you go, not at the end.
- When sources conflict, search specifically to resolve the conflict rather than picking the convenient one.

### Step 3 — Analyse

**Market sizing (always both methods):**
- *Top-down:* total market from industry/primary data → narrowed by geography, segment, channel, price point. Show each filter with its source or assumption ID.
- *Bottom-up:* addressable customers × adoption/conversion × price × purchase frequency. Every input sourced or assumption-tagged.
- *Reconcile:* if the two differ by >30%, explain why and state which you trust more.
- Define TAM, SAM, SOM explicitly for this case. SOM must reflect realistic share given competitors, channels and capacity — justify it.
- Build the model in `sizing.csv` so every number is reproducible. Run the arithmetic in code; do not compute in prose.
- Give base / low / high scenarios.

**Competitor landscape:**
- Identify direct, indirect and substitute competitors. Include local players, not only global brands.
- For each: positioning, target customer, pricing (with date checked), business model, scale signals (revenue, users, funding, headcount, app downloads — each cited), strengths, weaknesses.
- Capture in `competitors.csv`. Mark any field you could not verify as `unknown`, never guess.
- End with white space / differentiation opportunities.

**Customer & demand signals:**
- Search trends, app store rankings and reviews, community discussions, survey data, pricing pages, job postings, funding flows.
- Distinguish stated interest from revealed behaviour (paying, downloading, searching). Weight revealed behaviour higher.
- Quote customer language sparingly and paraphrase; note sample size and bias of each signal.

### Step 4 — Draft report

Write `report.md` from `templates/report.md`. Answer first: the executive summary must give the answer to the decision question, key numbers with confidence, and the top risks — in under 250 words.

### Step 5 — Independent verification (mandatory)

Spawn a separate subagent that has not seen your reasoning. Pass it only `report.md`, `sources.csv`, `sizing.csv`, `competitors.csv`, and the instructions in `verifier-prompt.md`.

The verifier re-fetches sources and checks every load-bearing figure and conclusion. It writes `verification.md`.

Then:
- Fix every FAIL. Re-run the verifier on changed items. Maximum 2 loops.
- Anything unresolved after 2 loops is disclosed in the report's "Known limitations" section and downgraded to Low confidence.
- Never deliver a report with an undisclosed FAIL.

### Step 6 — Deliver

1. **On screen:** a short highlights block —
   - Answer to the decision question (1–2 lines)
   - 3–5 key numbers with confidence ratings
   - Top 3 risks / unknowns
   - Verification result (e.g. "28/30 figures verified, 2 downgraded to Low")
   - **Access gaps:** sources that would materially improve accuracy, what each would unlock, and a direct question: "Do you want to subscribe to / enable any of these so I can re-run with better data?"
2. **Files:** `report.md`, `sources.csv`, `sizing.csv`, `competitors.csv`, `verification.md`, `brief.md` in the dated folder.
3. **Ask:** "Do you also want this as PDF, Google Doc, or HTML?" Produce only what the user picks. PDF and Google Doc go through the user's document-conversion skill if one is installed (e.g. `/brain:gdocs`), so formatting stays consistent.

## Quality checklist (run before Step 5)

- [ ] Brief approved by user
- [ ] Every number in the report appears in sources.csv
- [ ] Load-bearing figures have 2+ independent sources or are flagged
- [ ] SECONDARY-UNVERIFIED and STALE tags applied
- [ ] Top-down and bottom-up both done and reconciled
- [ ] Assumptions log complete; each assumption has a rationale
- [ ] USD + local currency with FX rate and date
- [ ] Scenarios (low/base/high) given
- [ ] Competitor fields marked `unknown` where not verified
- [ ] Known limitations and access gaps listed
- [ ] Arithmetic run in code, not by hand
- [ ] Every table has a `#` column and every list is numbered

## Anti-patterns to avoid

- Citing a "market will reach $X bn by 2030" press release as fact without finding the original report and its methodology.
- Using a global TAM for a country-level decision.
- Mixing users, MAUs, downloads and paying customers.
- Confusing GMV/transaction volume with revenue.
- Treating a single analyst firm's forecast as consensus.
- Filling unknown competitor data with plausible guesses.

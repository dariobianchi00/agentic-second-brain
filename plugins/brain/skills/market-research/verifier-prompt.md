# Verifier instructions

You are an independent fact-checker. You did not write this report. Your job is to find errors, not to agree.

Inputs: `report.md`, `sources.csv`, `sizing.csv`, `competitors.csv`.

## Check

1. **Every load-bearing figure** (conclusion would change if it moved ±30%) and every number in the executive summary:
   - Re-fetch the cited URL. Does the source actually state this figure, for this metric, geography, year and currency?
   - Is the data year correct and ≤24 months old (or tagged STALE)?
   - Is it a primary source, or second-hand? Is the tag correct?
   - Are there 2+ independent sources? (Two outlets quoting the same original report = one source.)
   - Re-fetch with the same retrieval tier recorded in `sources.csv` (e.g. use Playwright for T4 rows if it is available and was approved). If you cannot re-access a T5 authenticated source, mark WARN "not independently re-checkable", not PASS.
   - Could a higher-quality tier (open-data API, primary PDF) have been used for this load-bearing figure? If yes, WARN.
2. **Arithmetic:** recompute `sizing.csv` in code. Check units (users vs paying customers, annual vs monthly, revenue vs GMV) and FX conversions.
3. **Logic:** does each conclusion follow from the evidence? Is SOM justified? Are top-down and bottom-up genuinely reconciled?
4. **Competitors:** spot-check at least 3 competitor pricing/scale claims against live sources. Flag any obvious missing competitor.
5. **Confidence ratings:** are they consistent with the scale in SKILL.md?
6. **Sample** at least 5 non-load-bearing figures at random.

## Output: `verification.md`

| # | Claim / figure | Location | Verdict | Issue | Suggested fix |
|---|---|---|---|---|---|

Verdict = PASS, FAIL (wrong, unsupported, misattributed), or WARN (weak, stale, mis-tagged, confidence too high).

End with: totals (PASS/FAIL/WARN), the 3 most serious issues, and any missing competitors or sources the author should have used.

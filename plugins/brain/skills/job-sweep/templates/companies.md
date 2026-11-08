# /brain:job-sweep — target companies

> **Template.** Copy to your sweeps folder and replace the example rows (Acme Corp and Globex are fictional). Fill careers URLs on the first run and re-check them in the browser: most portals need JavaScript, so a plain fetch reports them as empty. Use brackets to note how to read a portal, or what it showed on the last check.
> Promotion rule: a Tier 2 company that posts a matching role in two runs moves to Tier 1.

Last updated: YYYY-MM-DD

## Config

```yaml
region: "<Country or City>"            # LinkedIn location= value and geography screen
employing_entity_rule: "employed by an entity in <region>"   # or "any"
seniority_floor: "Director"
titles:
  - "Chief Product Officer"
  - "VP Product OR Head of Product"
  - "Director of Product OR Product Director"
  - "Chief Digital Officer"
  - "General Manager digital"
sectors:                               # optionally map to target_map rows (TM1…TMn)
  - "<sector A>"
  - "<sector B>"
window_days: 7                         # 30 on the first run
attended_until: YYYY-MM-DD
```

## Tier 1 — careers page checked every run

| Company | Sector | Careers URL |
|---|---|---|
| Acme Corp | Fintech | https://careers.acme.example/jobs (filter by location, leave keyword blank) |
| Globex | Telco | https://globex.example/careers (no public listing; LinkedIn only) |

## Tier 2 — LinkedIn search only

- **<sector A>:** Company, Company
- **<sector B>:** Company, Company

## Excluded
- **<Company>** — reason (e.g. on hold, conflict of interest).
- **Roles employed outside `region`** — if they break `employing_entity_rule`.
- **Your current employer and its affiliates.**

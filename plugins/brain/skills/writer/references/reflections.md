# Reflections — how the style profile changes (reflective memory)

> **Template.** Append-only log. Your first entry is `R-0`, written when `/brain:writer bootstrap` builds profile v1 from your corpus.

One entry per reflection run. A reflection is triggered every **5 validated sends** logged in `examples.md` (or on demand: `/brain:writer reflect`). Procedure in `SKILL.md` § Reflection.

Rules that make this safe:
- **Conservative by default.** Most reflections should return "no change". A voice is stable; one odd week is not a new voice.
- **Evidence or nothing.** Every addition or removal quotes the sent text that justifies it and names the example IDs. A change with no quote is rejected.
- **Diff, never overwrite.** The profile is edited field by field; it is never regenerated from scratch.
- **Version and rollback.** Each entry records `profile_version_before → after` and the full diff. To unlearn a bad update, reverse the diff and bump the version again; never silently edit the profile.
- **One correction ≠ a rule.** A single user edit goes into the example's "what Claude got wrong" notes. It reaches the profile only when a reflection finds it repeated (2+ examples) or the user states it as a rule.
- **Scope changes are entries too.** When the user states a rule outright ("posts are in scope now"), log it as an entry with `change:` / `evidence:` / `watch:` instead of a reflection window.

Entry template:
```
## R-<n> — <YYYY-MM-DD> — profile v<before> → v<after> (status: proposed | approved YYYY-MM-DD | partly approved)
window: EX-<id>, EX-<id>, ... (the 5 sends reviewed)
additions:
  - field: <profile field> | value: <text> | evidence: "<quote>" (EX-<id>)
removals:
  - field: <profile field> | value: <text> | reason: <why, with evidence>
not proposed (single occurrence — watch):
  - <pattern> | evidence: "<quote>" (EX-<id>)
rationale: <one paragraph>
```

---

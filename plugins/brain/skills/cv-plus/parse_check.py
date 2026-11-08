#!/usr/bin/env python3
"""
parse_check.py — read a rendered CV PDF back the way an ATS parser reads it.

Ships with /cv-plus Step 7b. A render is not a readable CV until the text layer
is checked: parsers read the text stream linearly, and a PDF that looks right
can still extract as scrambled or corrupted text.

Checks (each prints PASS / WARN / FAIL):
  1. Extraction     — the text layer exists and is not empty.
  2. Section order  — expected headings all present, in the right order.
  3. Hyphen breaks  — no word corrupted by a hyphenated line break
                      (e.g. "Digital-Bank" extracting as "DigitalBank").
  4. Role lines     — COMPANY / dates extract on one line per role, not split.
  5. Contact block  — appears once (channels A and B) or is flagged as repeating.
  6. Page count     — 2-page cap.

Exit code is always 0: this reports, it does not gate the render.
Usage: parse_check.py <file.pdf> [--expect-repeating-header] [--allow-camel=Word1,Word2]

Add your own CamelCase company/product names with --allow-camel or the
CV_ALLOW_CAMEL env var (comma-separated) so they are not reported as fused words.
"""
import os
import re
import subprocess
import sys

SECTIONS = [
    "Core Competencies",
    "Professional Experience",
    "Board & Advisory",
    "Earlier Career",
    "Education",
]

# CamelCase that is genuinely part of a name and must not be reported as a fused word.
KNOWN_CAMEL = {
    "LinkedIn", "WhatsApp", "YouTube", "GitHub", "OpenAI", "PayPal", "JavaScript",
    "TypeScript", "PowerPoint", "SuccessFactors", "FinTech", "EdTech", "HealthTech",
    "InsurTech", "PropTech", "DevOps", "MLOps", "SaaS",
}

KNOWN_HYPHENATED = re.compile(
    r"(AI-native|builder-led|multi-market|self-care|go-to-market|e-commerce|"
    r"cross-market|first-ever|product-led|full-time|on-site|two-page)", re.I)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def main():
    if len(sys.argv) < 2:
        print("usage: parse_check.py <file.pdf> [--expect-repeating-header]")
        return 0
    pdf = sys.argv[1]
    expect_repeating = "--expect-repeating-header" in sys.argv
    extra = os.environ.get("CV_ALLOW_CAMEL", "")
    for a in sys.argv[2:]:
        if a.startswith("--allow-camel="):
            extra += "," + a.split("=", 1)[1]
    KNOWN_CAMEL.update(w.strip() for w in extra.split(",") if w.strip())

    raw = run(["pdftotext", pdf, "-"])
    lines = [l.rstrip() for l in raw.splitlines()]
    nonblank = [l for l in lines if l.strip()]
    findings = []

    def ok(msg):
        findings.append(("PASS", msg))

    def warn(msg):
        findings.append(("WARN", msg))

    def fail(msg):
        findings.append(("FAIL", msg))

    # 1. extraction
    if len(nonblank) < 20:
        fail(f"text layer nearly empty ({len(nonblank)} lines) — the PDF may be image-only")
        report(findings)
        return 0
    ok(f"text layer extracted ({len(nonblank)} lines)")

    # 2. section order
    found = [(s, raw.find(s)) for s in SECTIONS if raw.find(s) != -1]
    missing = [s for s in SECTIONS if raw.find(s) == -1]
    positions = [p for _, p in found]
    if missing:
        warn("headings not found in the text layer: " + ", ".join(missing)
             + "  (fine if the CV genuinely omits them)")
    if positions != sorted(positions):
        fail("section headings extract OUT OF ORDER — the parser will mis-assign content")
    else:
        ok(f"section order intact ({len(found)} headings, linear)")

    # 3. hyphenated line breaks
    #    pdftotext joins a line ending in '-' with the next line, producing a fused word.
    broken = []
    for a, b in zip(lines, lines[1:]):
        if a.endswith("-") and b[:1].isalpha():
            tail = re.search(r"([A-Za-z]+)-$", a)
            head = re.match(r"([A-Za-z]+)", b)
            if tail and head:
                broken.append(f"{tail.group(1)}-{head.group(1)} -> {tail.group(1)}{head.group(1)}")
    # also catch words already fused in the stream that look like CamelCase joins
    fused = re.findall(r"\b([A-Za-z][a-z]{2,}[A-Z][a-z]{2,})\b", raw)
    fused = [f for f in fused if not KNOWN_HYPHENATED.search(f) and f not in KNOWN_CAMEL]
    if broken:
        fail("hyphenated line break corrupts a word: " + "; ".join(broken[:4])
             + "  -> rewrite without the hyphen")
    elif fused:
        warn("possible fused words in the text layer: " + ", ".join(sorted(set(fused))[:5]))
    else:
        ok("no hyphen-break corruption")

    # 4. role lines: COMPANY — Location <tab/space> dates on one line
    #    The flex layout emits company and dates as adjacent lines in the text stream.
    #    That is parseable. What is NOT parseable is dates landing before the company,
    #    or more than two lines away from it.
    DATE_RE = re.compile(r"(19|20)\d{2}\s*(–|-|to)\s*([A-Za-z]+\s+)?((19|20)\d{2}|Present|now)", re.I)
    idx = {l: i for i, l in enumerate(nonblank)}
    role_idx = [i for i, l in enumerate(nonblank) if re.search(r"^[A-Z][A-Z &.']{2,}.*—", l)]
    detached = []
    for i in role_idx:
        window = nonblank[i:i + 3]
        if not any(DATE_RE.search(w) for w in window):
            detached.append(nonblank[i][:40])
    if not role_idx:
        warn("no role header lines detected — check the COMPANY — Location format")
    elif detached:
        fail("role header separated from its dates: " + "; ".join(detached)
             + "  -> the parser may mis-date the role")
    else:
        ok(f"each role header carries its dates within the text stream ({len(role_idx)} roles)")

    # 5. contact block repetition
    email_hits = raw.count("@")
    if expect_repeating:
        ok(f"contact block repeats by design ({email_hits} occurrences, channel C)")
    elif email_hits > 1:
        warn(f"contact details appear {email_hits} times — a repeating header lands mid-document "
             f"and confuses section detection. Render with --header=first-page for channels A and B.")
    else:
        ok("contact block appears once")

    # 6. page count
    info = run(["pdfinfo", pdf])
    m = re.search(r"^Pages:\s+(\d+)", info, re.M)
    if m:
        pages = int(m.group(1))
        (ok if pages <= 2 else fail)(f"{pages} page(s)" + ("" if pages <= 2 else " — over the 2-page cap"))

    report(findings)
    return 0


def report(findings):
    icons = {"PASS": "  ✓", "WARN": "  ⚠", "FAIL": "  ✗"}
    print("  -- parse check (how an ATS reads this file) --")
    for level, msg in findings:
        print(f"{icons[level]} {msg}")
    bad = [f for f in findings if f[0] == "FAIL"]
    if bad:
        print(f"  ✗ {len(bad)} parse defect(s) — fix before sending.")


if __name__ == "__main__":
    sys.exit(main())

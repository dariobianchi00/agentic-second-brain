#!/usr/bin/env python3
"""
Render the Customer Feedback dashboard (product-feedback skill).

Source of truth = the master markdown file. The COUNTER and SENTIMENT INDEX are
derived purely from the per-product "Ledger" tables — never from the prose — so
they can't drift. This script:

  1. parses every "## <Product>" section and its "### 📒 Ledger" table,
  2. recomputes each product's feedback count and -10..+10 sentiment index
     (used internally to pick a qualitative band — never displayed),
  3. rewrites the AUTO lines in the MD (count/sentiment + Last updated),
  4. regenerates a branded HTML dashboard next to the MD.

Usage:
    python3 render_feedback.py /path/to/Customer_Feedback.md \
        [--theme /path/to/theme.css] [--back-link Status.html] [--back-label "Back to status"]

The theme CSS (optional; also FEEDBACK_THEME_CSS env var) must define the --ds-*
variables used below. Without one, a neutral built-in theme is used.
"""

import argparse
import os
import sys
import re
import html
import datetime
from pathlib import Path

# ---- brand: values live in the theme CSS, not here ----
# The theme is inlined into the page so the HTML ships as one self-contained file.
NAVY = "var(--ds-secondary)"         # headings, rules
ACCENT = "var(--ds-primary)"         # fills, bars, borders
LINK = "var(--ds-primary-strong)"    # small coloured text (AA-safe)
MUTED = "var(--ds-ink-muted)"
LINE = "var(--ds-border)"

# Neutral fallback theme — used when no theme CSS is configured.
DEFAULT_THEME = """
:root {
  --ds-font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  --ds-primary: #3b6fb6;
  --ds-primary-strong: #285a9e;
  --ds-secondary: #1e3550;
  --ds-ink: #1f2933;
  --ds-ink-muted: #616e7c;
  --ds-bg: #ffffff;
  --ds-surface: #f5f7fa;
  --ds-border: #e4e7eb;
  --ds-success: #2f855a;
  --ds-warning: #b7791f;
  --ds-danger: #c53030;
}
"""


def load_theme(theme_arg):
    """Return theme CSS: --theme, then FEEDBACK_THEME_CSS, else the built-in neutral theme."""
    path = theme_arg or os.environ.get("FEEDBACK_THEME_CSS")
    if path:
        p = Path(path).expanduser()
        if not p.is_file():
            print(f"error: theme CSS not found at {p}", file=sys.stderr)
            sys.exit(1)
        return p.read_text(encoding="utf-8")
    return DEFAULT_THEME

OVERALL_HEADING = "Overall"  # the "## 📊 Overall" section, excluded from products


def label_for(index: float) -> str:
    """Map a -10..+10 sentiment index to a qualitative label."""
    if index >= 6:
        return "Strongly positive"
    if index >= 2:
        return "Mostly positive"
    if index > -2:
        return "Mixed"
    if index > -6:
        return "Mostly negative"
    return "Strongly negative"


def color_for(index: float) -> str:
    if index >= 2:
        return "var(--ds-success)"
    if index > -2:
        return "var(--ds-warning)"
    return "var(--ds-danger)"


def parse_ledger_ratings(section_text: str):
    """Return list of integer ratings from a section's Ledger table.

    A ledger row looks like: | 3 | 2026-06-22 | +1 | new user | summary |
    We grab the 3rd pipe-cell (the Rating) and parse signed ints. The header
    row (Rating == 'Rating') and the separator (|----|) are skipped naturally
    because they don't parse as ints.
    """
    ratings = []
    in_ledger = False
    for line in section_text.splitlines():
        if line.lstrip().startswith("### ") and "Ledger" in line:
            in_ledger = True
            continue
        if in_ledger and line.lstrip().startswith("### "):
            break  # next subsection ends the ledger
        if not in_ledger:
            continue
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue
        m = re.fullmatch(r"[+-]?\d+", cells[2])
        if m:
            ratings.append(int(cells[2]))
    return ratings


def split_sections(text: str):
    """Split the MD into (heading_line, body_text) chunks at each '## ' heading.

    Returns (preamble, [(heading_title, full_block_text), ...]) where
    full_block_text includes the heading line and everything until the next
    '## ' heading.
    """
    lines = text.splitlines(keepends=True)
    sections = []
    preamble = []
    current_title = None
    current = []
    in_comment = False  # are we inside a <!-- ... --> block at line start?
    for line in lines:
        at_line_start_in_comment = in_comment
        # advance comment state across this line (handles inline <!-- AUTO -->
        # which opens and closes on one line, and multi-line block comments)
        idx = 0
        while True:
            if not in_comment:
                o = line.find("<!--", idx)
                if o == -1:
                    break
                in_comment = True
                idx = o + 4
            else:
                c = line.find("-->", idx)
                if c == -1:
                    break
                in_comment = False
                idx = c + 3
        # a heading inside a comment (e.g. the template's example block) is not real
        m = None if at_line_start_in_comment else re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            if current_title is None:
                preamble = current
            else:
                sections.append((current_title, "".join(current)))
            current_title = m.group(1)
            current = [line]
        else:
            current.append(line)
    if current_title is None:
        preamble = current
    else:
        sections.append((current_title, "".join(current)))
    return "".join(preamble), sections


def clean_title(raw: str) -> str:
    """Strip leading emoji/symbols from a heading for display + product checks."""
    # remove leading non-alphanumeric (emoji, spaces) but keep inner chars
    return re.sub(r"^[^A-Za-z0-9]+", "", raw).strip()


def update_auto_lines(block: str, count: int, index: float) -> str:
    """Rewrite the AUTO count/sentiment lines inside a section block.

    Sentiment is shown as a QUALITATIVE BAND only — never a number. The -2..+2
    ratings still drive the band internally (via `index`), but a precise score
    on a small, self-selected sample reads as a verdict, so we never surface it.
    """
    lbl = label_for(index) if count else "No data yet"

    def repl_count(m):
        return f"{m.group(1)}{count}{m.group(3)}"

    # Overall uses "Feedback logged:", products use "Feedback:"
    block = re.sub(
        r"(- \*\*Feedback logged:\*\*\s*)(\S+)(.*)$",
        repl_count, block, count=1, flags=re.MULTILINE)
    block = re.sub(
        r"(- \*\*Feedback:\*\*\s*)(\S+)(.*)$",
        repl_count, block, count=1, flags=re.MULTILINE)

    # Sentiment line — band only. New files use "- **Sentiment:**" everywhere;
    # also normalize the legacy "- **Sentiment index:**" key to band-only form.
    block = re.sub(
        r"- \*\*Sentiment(?: index)?:\*\*\s*.*$",
        f"- **Sentiment:** {lbl} <!-- AUTO -->",
        block, count=1, flags=re.MULTILINE)
    return block


# ---------- simple inline markdown -> html ----------
def md_inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"_(.+?)_", r"<em>\1</em>", s)
    return s


def extract_bullets(block: str, heading_keyword: str):
    """Return list of bullet strings under a '### ...keyword...' subsection."""
    bullets = []
    capture = False
    for line in block.splitlines():
        st = line.strip()
        if st.startswith("### "):
            capture = heading_keyword.lower() in st.lower()
            continue
        if capture and st.startswith("- "):
            bullets.append(st[2:].strip())
    return bullets


def extract_grouped(block: str, heading_keyword: str):
    """Return [(category|None, [bullets]), ...] under a '### ...keyword...' subsection.

    Bullets under a '#### Category' header are grouped by that category; bullets
    before any '#### ' land in a leading (None, [...]) group. A section with no
    '#### ' headers therefore yields a single (None, [all bullets]) group — the
    renderer treats that as a flat list (backward compatible with un-categorised
    products). '#### ' does NOT match the '### ' subsection test, so category
    headers never end the subsection.
    """
    groups = []
    capture = False
    cur_name = None
    cur = []

    def flush():
        nonlocal cur
        if cur:
            groups.append((cur_name, cur))
            cur = []

    for line in block.splitlines():
        st = line.strip()
        if st.startswith("### "):
            if capture:
                flush()
                cur_name = None
            capture = heading_keyword.lower() in st.lower()
            continue
        if not capture:
            continue
        if st.startswith("#### "):
            flush()
            cur_name = st[5:].strip()
        elif st.startswith("- "):
            cur.append(st[2:].strip())
    if capture:
        flush()
    return groups


def extract_bug_table(block: str):
    """Return [[severity, bug, ticket, status], ...] from a '### 🐛 Bugs' table.

    Parses a 4-column markdown table (Severity | Bug | Ticket | Status), skipping
    the header and the |---| separator. Returns [] if the Bugs subsection has no
    table (e.g. it's still a bullet list) so the renderer can fall back to bullets.
    """
    rows = []
    capture = False
    header_seen = False
    for line in block.splitlines():
        st = line.strip()
        if st.startswith("### "):
            capture = "bugs" in st.lower()
            header_seen = False
            continue
        if not capture or not st.startswith("|"):
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if len(cells) < 4:
            continue
        if not header_seen:            # first pipe row = header
            header_seen = True
            continue
        if set("".join(cells)) <= set("-: "):  # separator row
            continue
        rows.append(cells[:4])
    return rows


def _empty_ul():
    return '<ul><li class="empty">—</li></ul>'


def render_sub_body(bullets, quote=False, bugs=False):
    """Inner content for a flat-bullet section (Suggested / Verbatim / bug fallback)."""
    real = [b for b in bullets if b and b.lower() not in ("_none yet_", "none yet")]
    if not real:
        return _empty_ul()
    out = ['<ul>']
    for b in real:
        cls = "quote" if quote else ""
        if quote and b[:1] in ("😊", "😞"):
            tone, rest = b[0], b[1:].lstrip()
            txt = f'<span class="tone">{tone}</span>{md_inline(rest)}'
        else:
            txt = md_inline(b)
        if bugs and ("[high]" in b.lower()):
            txt = f'<span class="sev-high">{txt}</span>'
        out.append(f'<li class="{cls}">{txt}</li>')
    out.append('</ul>')
    return "".join(out)


def render_grouped_body(groups):
    """Inner content for Liked / Don't-like — optional '#### Category' sub-groups."""
    def keep(bl):
        return [b for b in bl if b and b.lower() not in ("_none yet_", "none yet")]
    has_cat = any(name for name, _ in groups)
    real = [b for _, bl in groups for b in keep(bl)]
    if not real:
        return _empty_ul()
    out = []
    if has_cat:
        for name, bullets in groups:
            bl = keep(bullets)
            if not bl:
                continue
            if name:
                out.append(f'<div class="cat">{md_inline(name)}</div>')
            out.append('<ul>')
            for b in bl:
                out.append(f'<li>{md_inline(b)}</li>')
            out.append('</ul>')
    else:
        out.append('<ul>')
        for b in real:
            out.append(f'<li>{md_inline(b)}</li>')
        out.append('</ul>')
    return "".join(out)


def render_bug_body(rows):
    """Inner content for the Bugs table."""
    sevmap = {"high": "sev-high", "med": "sev-med", "medium": "sev-med", "low": "sev-low"}
    if not rows:
        return _empty_ul()
    out = ['<table class="bugtable"><thead><tr>'
           '<th>Sev</th><th>Bug</th><th>Ticket</th><th>Status</th>'
           '</tr></thead><tbody>']
    for sev, bug, ticket, status in rows:
        sc = sevmap.get(sev.strip().lower(), "")
        out.append(
            f'<tr><td class="{sc}">{md_inline(sev)}</td>'
            f'<td>{md_inline(bug)}</td>'
            f'<td class="tk">{md_inline(ticket)}</td>'
            f'<td class="st">{md_inline(status)}</td></tr>')
    out.append('</tbody></table>')
    return "".join(out)


def sub_block(title, body):
    """Wrap a body in the compact .sub/.h card (used in the multi-product layout)."""
    return f'<div class="sub"><div class="h">{title}</div>{body}</div>'


def sections_for(d):
    """The 5 category sections (id, title, inner-html) for one product."""
    bugs_body = render_bug_body(d["bug_rows"]) if d["bug_rows"] else render_sub_body(d["bugs"], bugs=True)
    return [
        ("liked",     "👍 Liked — key areas",      render_grouped_body(d["liked_groups"])),
        ("dislike",   "👎 Don't like — key areas", render_grouped_body(d["disliked_groups"])),
        ("suggested", "💡 Suggested features",     render_sub_body(d["suggested"])),
        ("bugs",      "🐛 Bugs",                   bugs_body),
        ("verbatim",  "💬 Verbatim",               render_sub_body(d["quotes"], quote=True)),
    ]


def summary_head(d):
    c = color_for(d["index"]) if d["count"] else ACCENT
    lbl = label_for(d["index"]) if d["count"] else "No data yet"
    return (f'<div class="prod-summary">'
            f'<span class="pname">{html.escape(d["display"])}</span>'
            f'<span class="pill" style="background:{c}">{lbl}</span>'
            f'<span class="pcount">{d["count"]} feedback</span></div>')


def render_html(title_block_data, overall_count, overall_index, updated, theme_css,
                page_title="Customer Feedback", back_link=None, back_label=None):
    m = re.search(r"--ds-secondary:\s*#([0-9a-fA-F]{3,8})", theme_css)
    fav = m.group(1) if m else "1e3550"
    letter = html.escape((page_title.strip()[:1] or "F").upper())
    title_h = html.escape(page_title)
    back_html = (f'  <a class="backlink" href="{html.escape(back_link)}">&larr; '
                 f'{html.escape(back_label or "Back")}</a>\n') if back_link else ""
    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title_h}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='%23{fav}'/><text x='50' y='75' font-family='Arial,Helvetica,sans-serif' font-size='80' font-weight='700' fill='%23ffffff' text-anchor='middle'>{letter}</text></svg>">
<style>
{theme_css}
</style>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: var(--ds-font-body); color:var(--ds-ink); background:var(--ds-bg); line-height:1.55;
         padding:0 56px 48px 56px; max-width:1180px; margin:0 auto; }}
  header {{ border-bottom:2px solid {NAVY}; padding:40px 0 18px 0; }}
  h1 {{ font-size:28pt; color:{NAVY}; font-weight:700; letter-spacing:-0.5px; }}
  .subtitle {{ font-size:12pt; color:{MUTED}; margin-top:6px; }}
  .backlink {{ display:inline-block; margin-top:10px; font-size:10.5pt; font-weight:700; color:{LINK}; text-decoration:none; }}
  .backlink:hover {{ text-decoration:underline; }}
  .caveat {{ background:color-mix(in srgb, var(--ds-warning) 10%, var(--ds-bg)); border-left:4px solid var(--ds-warning); color:var(--ds-ink);
            padding:14px 18px; margin:22px 0; font-size:10.5pt; }}
  .scorecards {{ display:flex; gap:18px; flex-wrap:wrap; margin:24px 0 8px 0; }}
  .scorecard {{ flex:1 1 220px; background:var(--ds-surface); border-left:3px solid {ACCENT};
               padding:20px 22px; }}
  .scorecard .num {{ font-size:34pt; font-weight:700; color:{NAVY}; line-height:1; }}
  .scorecard .band {{ font-size:21pt; font-weight:700; line-height:1.1; }}
  .scorecard .lbl {{ font-size:9pt; text-transform:uppercase; letter-spacing:1px;
                    color:{MUTED}; font-weight:700; margin-bottom:8px; }}
  .scorecard .sub {{ font-size:10.5pt; color:var(--ds-ink); margin-top:6px; }}
  h2 {{ font-size:18pt; color:{NAVY}; margin-top:40px; margin-bottom:14px; font-weight:700; }}
  h2 .accent {{ display:inline-block; width:8px; height:22px; background:{ACCENT};
               margin-right:12px; vertical-align:middle; }}
  .product {{ padding:22px 26px; background:var(--ds-surface); border-left:3px solid {ACCENT}; margin-bottom:22px; }}
  .product-head {{ display:flex; align-items:baseline; gap:16px; flex-wrap:wrap; margin-bottom:8px; }}
  .product-head .pname {{ font-size:15pt; font-weight:700; color:{NAVY}; }}
  .pill {{ display:inline-block; font-size:9pt; font-weight:700; padding:3px 10px;
          border-radius:3px; color:#fff; }}
  .pcount {{ font-size:10pt; color:{MUTED}; font-weight:600; }}
  .sub {{ margin-top:14px; }}
  .sub .h {{ font-size:9pt; text-transform:uppercase; letter-spacing:1px; font-weight:700;
            color:{NAVY}; margin-bottom:6px; }}
  ul {{ list-style:none; padding:0; margin:0; }}
  li {{ font-size:10.5pt; padding:5px 0; border-bottom:1px solid {LINE}; }}
  li:last-child {{ border-bottom:none; }}
  .quote {{ font-style:italic; }}
  .tone {{ font-size:18pt; font-style:normal; vertical-align:-2px; margin-right:6px; }}
  .empty {{ color:{MUTED}; font-style:italic; }}
  .sev-high {{ color:var(--ds-danger); font-weight:700; }}
  .sev-med {{ color:var(--ds-warning); font-weight:700; }}
  .sev-low {{ color:{MUTED}; font-weight:700; }}
  .cat {{ font-size:9pt; text-transform:uppercase; letter-spacing:.5px; font-weight:700;
         color:{MUTED}; margin:12px 0 2px 0; }}
  .cat:first-of-type {{ margin-top:2px; }}
  .bugtable {{ width:100%; border-collapse:collapse; font-size:10pt; margin-top:4px; }}
  .bugtable th {{ text-align:left; font-size:8pt; text-transform:uppercase; letter-spacing:.5px;
                 color:{MUTED}; background:none; border-bottom:2px solid {LINE}; padding:5px 10px 5px 0; }}
  .bugtable td {{ border-bottom:1px solid {LINE}; padding:7px 10px 7px 0; vertical-align:top; }}
  .bugtable tr:last-child td {{ border-bottom:none; }}
  .bugtable td.sev-high, .bugtable td.sev-med, .bugtable td.sev-low {{ white-space:nowrap; }}
  .bugtable td.tk {{ white-space:nowrap; color:{LINK}; font-weight:600; }}
  .bugtable td.st {{ white-space:nowrap; }}
  .prod-summary {{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; margin:22px 0 4px; }}
  .prod-summary .pname {{ font-size:16pt; font-weight:700; color:{NAVY}; }}
  nav.fnav {{ position:sticky; top:0; background:var(--ds-bg); border-bottom:1px solid {LINE};
             padding:11px 0; margin:10px 0 4px; z-index:10; }}
  nav.fnav a {{ font-size:10.5pt; font-weight:700; color:{LINK}; text-decoration:none;
               margin-right:22px; padding-bottom:2px; border-bottom:2px solid transparent; white-space:nowrap; }}
  nav.fnav a:hover {{ border-bottom-color:{LINK}; }}
  section.fbsec {{ padding:24px 0 10px; border-bottom:1px solid {LINE}; scroll-margin-top:58px; }}
  section.fbsec:last-of-type {{ border-bottom:none; }}
  section.fbsec > h2 {{ font-size:15pt; color:{NAVY}; font-weight:700; margin-bottom:12px;
                       display:flex; align-items:center; }}
  footer {{ margin-top:40px; padding-top:16px; border-top:1px solid {LINE};
           font-size:9.5pt; color:{MUTED}; }}
</style>
</head>
<body>
<header>
  <h1>{title_h}</h1>
  <div class="subtitle">Qualitative voice-of-customer across the portfolio · Updated {updated}</div>
{back_html}</header>

<div class="caveat">⚠️ <strong>Qualitative.</strong> This is directional signal from a small, self-selected sample — read it as themes, not metrics. Sentiment is shown as a band ("Mostly positive"), never a score: it reflects which way the people who spoke up leaned, not what share of users are happy.</div>
""")

    # Single product → break the page into
    # top-level sections (Liked / Don't-like / Suggested / Bugs / Verbatim) with
    # a sticky nav. Multiple products → fall back to per-product cards.
    if len(title_block_data) == 1:
        d = title_block_data[0]
        parts.append(summary_head(d))
        secs = sections_for(d)
        parts.append('<nav class="fnav">' +
                     "".join(f'<a href="#{sid}">{title}</a>' for sid, title, _ in secs) +
                     '</nav>')
        for sid, title, body in secs:
            parts.append(f'<section id="{sid}" class="fbsec"><h2>{title}</h2>{body}</section>')
    else:
        parts.append('<h2><span class="accent"></span>By product</h2>')
        for d in title_block_data:
            c = color_for(d["index"]) if d["count"] else ACCENT
            parts.append(f'<div class="product" style="border-left-color:{c}">')
            parts.append(summary_head(d))
            for _sid, title, body in sections_for(d):
                parts.append(sub_block(title, body))
            parts.append('</div>')

    parts.append(f'<footer>Source of truth: Customer_Feedback.md · Rendered by the product-feedback skill · {updated}</footer>')
    parts.append('</body></html>')
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description="Render the Customer Feedback dashboard.")
    ap.add_argument("md", help="path to Customer_Feedback.md")
    ap.add_argument("--theme", help="theme CSS defining --ds-* variables (optional)")
    ap.add_argument("--back-link", help="href for a back link in the page header (optional)")
    ap.add_argument("--back-label", help="text for the back link (optional)")
    args = ap.parse_args()
    md_path = Path(args.md)
    if not md_path.exists():
        print(f"error: {md_path} not found", file=sys.stderr)
        sys.exit(1)

    theme_css = load_theme(args.theme)
    text = md_path.read_text(encoding="utf-8")
    tm = re.search(r"^#\s+(.+?)\s*$", text, flags=re.MULTILINE)
    page_title = tm.group(1) if tm else "Customer Feedback"
    today = datetime.date.today().isoformat()

    preamble, sections = split_sections(text)

    all_ratings = []
    product_data = []
    new_blocks = []  # rebuilt section blocks (heading included)

    for title, block in sections:
        ct = clean_title(title)
        is_overall = ct.lower().startswith(OVERALL_HEADING.lower())
        ratings = parse_ledger_ratings(block)
        count = len(ratings)
        index = round((sum(ratings) / count) * 5, 1) if count else 0.0

        if not is_overall:
            all_ratings.extend(ratings)
            product_data.append({
                "display": ct,
                "count": count,
                "index": index,
                "liked_groups": extract_grouped(block, "Liked"),
                "disliked_groups": extract_grouped(block, "Don't"),
                "suggested": extract_bullets(block, "Suggested"),
                "bug_rows": extract_bug_table(block),
                "bugs": extract_bullets(block, "Bugs"),
                "quotes": extract_bullets(block, "Verbatim"),
            })
            block = update_auto_lines(block, count, index)
        new_blocks.append((title, block, is_overall))

    overall_count = len(all_ratings)
    overall_index = round((sum(all_ratings) / overall_count) * 5, 1) if overall_count else 0.0

    # rebuild MD: stamp date in preamble, update overall block
    preamble = re.sub(
        r"(\*\*Last updated:\*\*).*",
        lambda m: f"{m.group(1)} {today} <!-- AUTO -->",
        preamble, count=1)

    out = [preamble]
    for title, block, is_overall in new_blocks:
        if is_overall:
            block = update_auto_lines(block, overall_count, overall_index)
        out.append(block)
    md_path.write_text("".join(out), encoding="utf-8")

    # render HTML
    html_path = md_path.with_suffix(".html")
    html_path.write_text(
        render_html(product_data, overall_count, overall_index, today, theme_css,
                    page_title, args.back_link, args.back_label),
        encoding="utf-8")

    # report (band only — never surface the numeric index)
    print(f"Updated {md_path.name} (per product — never rolled up):")
    for d in product_data:
        print(f"  - {d['display']}: {d['count']} feedback — "
              f"{label_for(d['index']) if d['count'] else 'no data'}")
    print(f"Rendered {html_path.name}")


if __name__ == "__main__":
    main()

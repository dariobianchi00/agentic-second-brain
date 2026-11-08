#!/usr/bin/env bash
# cv-plus PDF renderer — HTML -> A4 PDF using template.html.
# Delegates to cdp_pdf.py (Chrome DevTools Protocol) because Chrome's CLI --print-to-pdf
# ignores CSS @page size and defaults to US Letter; CDP lets us force A4 + a repeating header.
# Usage: render.sh [--header=repeat|first-page] <input.html> <output.pdf>
#   --header=repeat      (default) name/contact block on every page. Channel C.
#   --header=first-page  no repeating print header; put the contact block in the HTML body.
#                        Parse-safe for channels A (portal) and B (agency ATS).

set -euo pipefail

HEADER_FLAG=""
if [[ "${1:-}" == --header=* ]]; then HEADER_FLAG="$1"; shift; fi
IN="${1:?usage: render.sh [--header=repeat|first-page] <input.html> <output.pdf>}"
OUT="${2:?usage: render.sh [--header=repeat|first-page] <input.html> <output.pdf>}"
DIR="$(cd "$(dirname "$0")" && pwd)"

python3 "$DIR/cdp_pdf.py" ${HEADER_FLAG:+$HEADER_FLAG} "$IN" "$OUT"

# Page-count guard (2-page cap) if pdfinfo is available.
if command -v pdfinfo >/dev/null 2>&1; then
  PAGES="$(pdfinfo "$OUT" 2>/dev/null | awk '/^Pages:/{print $2}')"
  SIZE="$(pdfinfo "$OUT" 2>/dev/null | awk '/^Page size:/{print $3" x "$5}')"
  echo "  -> ${PAGES} pages, ${SIZE} pts"
  if [ "${PAGES:-0}" -gt 2 ]; then
    echo "WARNING: ${PAGES} pages — exceeds the 2-page cap. Trim content and re-render." >&2
  fi
fi

# Parse check (Step 7b) — reads the PDF back the way an ATS parser would.
if command -v pdftotext >/dev/null 2>&1; then
  python3 "$DIR/parse_check.py" "$OUT" || true
else
  echo "  note: pdftotext not found — parse check skipped (brew install poppler)" >&2
fi

---
name: gdocs
description: Converts vault markdown files to Google Docs (private by default, uploaded with the gdrive CLI) or to a styled PDF (pandoc + headless Chrome, optional design-system theme). Fires on "/brain:gdocs <file>", "/brain:gdocs pdf <file>", "make this a Google Doc", "export this to PDF".
---

# /brain:gdocs

Convert markdown files to Google Docs or PDF.

## User-invocable

## Description

Converts vault markdown files to either Google Docs (private by default) or styled PDF. Supports two subcommands based on the argument or context.

## Requirements and configuration

- **pandoc** (`brew install pandoc`), **python-docx** (`pip install python-docx`) — both modes.
- **gdrive CLI** v3 (https://github.com/glotlabs/gdrive) — Google Docs mode. Add each Google account once with `gdrive account add`.
- **Google Chrome** — PDF mode. The path below is the macOS default; on Linux use `google-chrome` / `chromium`.
- Accounts and default folders live in a `## Google Docs export` block in the vault's `CLAUDE.md`:

  ```markdown
  ## Google Docs export
  - Default account: work@example.com
  - Accounts:
    - work@example.com → default folder ID <drive-folder-id> ("Vault Exports")
    - personal@example.com → default folder ID <drive-folder-id>
  - Themes (PDF, optional): <work area>/** → Instructions/Design_System/<entity>/theme.css (+ logo <entity>/assets/<logo>.svg)
  ```

  Missing block → ask which account and folder to use (one question at a time, with a recommendation), then offer to write the block. Never guess an account.

## Allowed Tools

```yaml
- Read(*)
- Glob(*)
- Bash(*)
```

## Workflow

### Step 1: Determine Mode & File

Parse the user's command:
- `/brain:gdocs <filepath> [<filepath> ...]` → Google Docs conversion (default: the configured default account and its default folder)
- `--account <email>` → upload to specified account (overrides default)
- `--folder <name-or-id>` → upload to specified destination folder (overrides default)
- `--share` → also make it viewable by **anyone with the link**. Only when the user explicitly asks to share ("share it", "make a link I can send"). Never for HR/people, personal, legal or financial docs without asking first. Default = private (owner only).
- `/brain:gdocs pdf <filepath>` → PDF conversion (folder/account flags ignored)
- `/brain:gdocs` (no args) → Ask what they want to convert. Check recent conversation for files worked on.

Multiple filepaths are supported in one invocation — process each file through the full workflow sequentially and return all links.

**Available accounts:** the ones listed in the `## Google Docs export` config block.

**File resolution:** If the path is relative, resolve it from the vault root (`<vault>`, the working directory). Verify the file exists before proceeding.

**Folder resolution** (only if `--folder` provided; otherwise use account default):
- If the value matches `^[A-Za-z0-9_-]{25,}$` (looks like a Google Drive ID), use it directly.
- Otherwise treat as a folder name and look up:
  ```bash
  gdrive files list --query "name = '<name>' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
  ```
  - **0 results** → error: "No folder named '<name>' found in this account. Specify by ID or check the name."
  - **1 result** → use that folder ID.
  - **>1 results** → error: list the candidates with their parent paths and ask the user to disambiguate (specify by ID or by `<parent>/<name>`).
- The resolved folder must be in the account that's about to be uploaded to (account switch happens first; then lookup runs on that account).

**CRITICAL — never invent or guess flags.** If the user mentions a destination ("save to the board folder", "in my product folder") in conversation but didn't pass `--folder`, either (a) ask before running, or (b) pass `--folder "<their phrase>"` explicitly and let folder resolution succeed or error. Do NOT silently fall back to default.

---

### Mode A: Google Docs Conversion

1. **Convert MD → DOCX via pandoc:**
   ```bash
   TMP="${TMPDIR:-/tmp}"
   pandoc "<full-path-to-md>" -o "$TMP/<basename>.docx"
   ```

2. **Apply Arial font + all-black text + table borders + remove bookmarks via python-docx:**
   ```python
   import os
   from docx import Document
   from docx.oxml.ns import qn
   from docx.oxml import OxmlElement
   from docx.shared import RGBColor

   doc = Document(f"{os.environ.get('TMPDIR', '/tmp')}/<basename>.docx")

   def set_arial_black(run):
       rPr = run._element.get_or_add_rPr()
       rFonts = OxmlElement('w:rFonts')
       rFonts.set(qn('w:ascii'), 'Arial')
       rFonts.set(qn('w:hAnsi'), 'Arial')
       rFonts.set(qn('w:cs'), 'Arial')
       existing = rPr.find(qn('w:rFonts'))
       if existing is not None:
           rPr.remove(existing)
       rPr.insert(0, rFonts)
       run.font.name = 'Arial'
       run.font.color.rgb = RGBColor(0, 0, 0)

   def add_table_borders(table):
       tbl = table._tbl
       tblPr = tbl.tblPr
       if tblPr is None:
           tblPr = OxmlElement('w:tblPr')
           tbl.insert(0, tblPr)
       for existing in tblPr.findall(qn('w:tblBorders')):
           tblPr.remove(existing)
       tblBorders = OxmlElement('w:tblBorders')
       for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
           border = OxmlElement(f'w:{border_name}')
           border.set(qn('w:val'), 'single')
           border.set(qn('w:sz'), '4')
           border.set(qn('w:space'), '0')
           border.set(qn('w:color'), '000000')
           tblBorders.append(border)
       tblPr.append(tblBorders)

   def remove_bookmarks(doc):
       body = doc.element.body
       for bookmark in body.iter(qn('w:bookmarkStart')):
           bookmark.getparent().remove(bookmark)
       for bookmark in body.iter(qn('w:bookmarkEnd')):
           bookmark.getparent().remove(bookmark)

   for para in doc.paragraphs:
       for run in para.runs:
           set_arial_black(run)

   for table in doc.tables:
       add_table_borders(table)
       for row in table.rows:
           for cell in row.cells:
               for para in cell.paragraphs:
                   for run in para.runs:
                       set_arial_black(run)

   remove_bookmarks(doc)

   doc.save(f"{os.environ.get('TMPDIR', '/tmp')}/<basename>.docx")
   ```

3. **Resolve destination folder** (after account switch — folder lookup runs on the active account):
   ```bash
   gdrive account switch "<account>"
   ```
   - If user passed `--folder <value>`: apply folder-resolution rules from Step 1.
   - If no `--folder` flag: use the account default below.

   **Account → default folder ID:** from the `## Google Docs export` config block. No default folder configured → upload to the Drive root and say so.

4. **Upload to Google Drive:**
   ```bash
   FILE_ID=$(gdrive files upload --print-only-id --mime application/vnd.google-apps.document --parent "<RESOLVED_FOLDER_ID>" "$TMP/<basename>.docx")
   # Only with --share (the user asked to share):
   # gdrive permissions share --role reader --type anyone "$FILE_ID"
   echo "https://docs.google.com/document/d/${FILE_ID}/edit"
   rm "$TMP/<basename>.docx"
   ```

5. **Return the Google Docs link AND the resolved destination folder name.** Format: `<filename>: <link> (in folder: <folder name>)`. The folder name must be stated explicitly in the success message so the user can verify destination matches their instruction.

6. **If `gdrive` auth fails**, tell the user: "gdrive needs Google OAuth — it will open a browser window for authentication."

**Output:** A Google Docs link — **private (owner only)** unless `--share` was used; say which in the response — **with the destination folder name confirmed in the response**. Arial font, all-black text, solid black borders on all tables, all bookmarks removed.

---

### Mode B: PDF Conversion

1. **Read the source markdown file.**

2. **Pick the entity theme** (optional vault design system, e.g. `Instructions/Design_System/<entity>/theme.css`) from the source path using the `Themes` mapping in the config block, unless the user names an entity:
   - path matches a configured mapping → that `theme.css`
   - user names an entity that has a theme folder → that folder's `theme.css`
   - anything else (personal notes, knowledge, no entity, no design system) → **Neutral fallback CSS** below
   State the chosen theme in the result line.

3. **Convert MD → styled HTML** via pandoc:
   ```bash
   pandoc "<source.md>" -o "<source.html>" --standalone --metadata title="" -c /dev/null
   ```
   Then inject, just before `</head>`: a `<style>` block with the **full contents of the entity `theme.css`** (read it; never hand-type its colours/fonts), followed by a `<style>` block with the document CSS below.

   **Logo (required for every entity theme):** insert right after `<body>` an `<img class="ds-logo" style="margin-bottom:8mm" src="data:image/...;base64,...">` with the logo the config maps to that entity (from `Instructions/Design_System/<entity>/assets/`), base64-inlined. Product sub-folders may map to their own product logo. Neutral fallback: no logo. The theme is expected to carry the print rules (A4 page with 16mm margins, light colours forced, colour fills kept, no stranded headings, repeating table headers, no split tables/callouts); if yours doesn't, add them to the theme rather than here.

   **Document CSS (entity theme — inject after `theme.css`):**
   ```css
   body { max-width: 100%; margin: 0; padding: 0; }
   h1, h2, h3 { margin-top: 1.2em; }
   h1 { border-bottom: 2px solid var(--ds-primary); padding-bottom: 6px; }
   code { background: var(--ds-surface-alt); padding: 2px 5px; border-radius: var(--ds-radius-sm); }
   pre { background: var(--ds-surface-alt); padding: 12px; border-radius: var(--ds-radius-md); overflow-x: auto; }
   blockquote { border-left: 3px solid var(--ds-primary); padding-left: 12px; color: var(--ds-ink-muted); margin-left: 0; }
   ```

   **Neutral fallback CSS (no entity only — inject this instead of the two blocks above):**
   ```css
   @page { margin: 0; }
   @media print { @page { margin: 0; } }
   body {
     font-family: Arial, sans-serif;
     font-size: 11pt;
     line-height: 1.5;
     padding: 50px 60px;
     max-width: 100%;
     color: #333;
   }
   h1, h2, h3 { color: #000; margin-top: 1.2em; }
   h1 { font-size: 22pt; border-bottom: 2px solid #000; padding-bottom: 6px; }
   h2 { font-size: 16pt; }
   h3 { font-size: 13pt; }
   table { border-collapse: collapse; width: 100%; margin: 1em 0; }
   th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; font-size: 10pt; }
   th { background: #f5f5f5; font-weight: 600; }
   code { background: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-size: 10pt; }
   pre { background: #f4f4f4; padding: 12px; border-radius: 4px; overflow-x: auto; }
   blockquote { border-left: 3px solid #999; padding-left: 12px; color: #666; }
   a { color: #0066cc; }
   ```

4. **Render HTML → PDF** via Chrome headless (`--virtual-time-budget` lets the theme's web fonts load before printing). Path shown is macOS; on Linux call `google-chrome` or `chromium`:
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     --headless=new --disable-gpu --no-sandbox \
     --print-to-pdf="<output>.pdf" \
     --no-pdf-header-footer --print-to-pdf-no-header \
     --virtual-time-budget=5000 \
     "file://<html-path>"
   ```

5. **Delete the intermediate HTML file.**

6. **Return the PDF path** and the theme used. PDF is saved next to the source MD file (same name, `.pdf` extension).

---

## Error Handling

| Error | Response |
|-------|----------|
| File not found | "File not found: `<path>`. Check the path and try again." |
| Folder name not found | "No folder named '<name>' found in account <account>. Pass a folder ID instead, or check the name." |
| Folder name ambiguous (>1 match) | List each candidate with parent path: "Multiple folders named '<name>' — ID `<id1>` in `<parent1>`, ID `<id2>` in `<parent2>`. Re-run with `--folder <id>`." |
| pandoc not installed | "pandoc is required. Install with: `brew install pandoc`" |
| Chrome not found | "Google Chrome is required for PDF rendering. Expected at `/Applications/Google Chrome.app` (macOS) or `google-chrome` / `chromium` on PATH." |
| python-docx missing | "python-docx is required. Install with: `pip install python-docx`" |
| No account configured | Ask which account to use; offer to add the `## Google Docs export` block. |
| gdrive auth error | "gdrive needs authentication. It will open a browser for Google OAuth." |
| gdrive not installed | "gdrive CLI is required. Install from https://github.com/glotlabs/gdrive" |

## Notes

- PDF output has no Chrome headers/footers (URL, date) thanks to `--no-pdf-header-footer` (older Chrome: `--print-to-pdf-no-header`). Entity PDFs take their margins from `theme.css` (e.g. `@page { size: A4; margin: 16mm 16mm 18mm }`); the Neutral fallback keeps `@page { margin: 0 }` + body padding (50px 60px).
- Google Docs mode stays Arial + all-black by design — Docs import strips custom CSS, so the design system applies to the PDF path only.
- Google Docs uploads auto-convert from docx format via gdrive.

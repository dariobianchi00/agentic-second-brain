---
name: deck
description: Generates Marp-compatible markdown slide decks with consistent styling — brand theme pulled from the vault's design system (or a neutral dark/light fallback), emoji headers, the 6x6 content rule, two-column image layouts, and a per-slide image review. Fires on /brain:deck or "make a deck / slides about X".
user-invocable: true
allowed-tools:
  - Read(*)
  - Write(*)
  - Edit(*)
  - Glob(*)
  - Grep(*)
  - WebSearch(*)
  - WebFetch(*)
  - Bash(*)
---

# /brain:deck

Generate Marp-compatible markdown presentations with consistent styling and structure.

## Description

Creates professional slide decks as Marp markdown files. Styling comes from the vault design system if it has one (`Instructions/Design_System/<entity>/theme.css` — one folder per company, product or venture the user presents for) with dark/light modes, emoji-rich headers, and the 6x6 content rule. Neutral (no entity) decks use the generic fallback theme below. Output files work directly with the VS Code Marp extension for preview and PDF/PPTX export.

> **Design system (optional):** to brand decks, add `Instructions/Design_System/<entity>/` with a `theme.css` that defines the `--ds-*` CSS variables used below (`--ds-bg`, `--ds-ink`, `--ds-ink-muted`, `--ds-primary`, `--ds-primary-strong`, `--ds-primary-soft`, `--ds-font-body`, `--ds-font-display`, `--ds-gradient-hero`, `--ds-hero-ink`; a `[data-theme="dark"]` block for dark values), an `assets/` folder with on-light and on-dark logos, and an optional `BRAND.md` for usage rules. Without it, every deck is Neutral.

## Workflow

### Step 1: Gather Parameters (one at a time)

1. **Topic/title** — if provided as argument (e.g., `/brain:deck "Q3 Product Strategy"`), use it. Otherwise ask.
2. **Entity** — "Which entity is this for?" List the folders under `Instructions/Design_System/` and recommend one by context (default: the user's main employer/company), plus **Neutral** (personal/speaking, no entity). Entity → that entity's theme + its logo on every slide; Neutral → generic fallback theme, no logo. If the design system has a `README.md` mapping work to entities, follow it. If there is no design system, skip this question — the deck is Neutral.
3. **Theme** — "Dark or light background?" (default light; keynote-style talks = dark)
4. **Content source** — "Do you have a source document I should base this on, or should I build from scratch?" If source doc provided → Read it first and extract structure.
5. **Audience** — "Who is the audience?" (one line, e.g., "CEO and exec team")

### Step 2: Generate Draft

1. Determine slide count based on content complexity.
2. Confirm with the user: "I'm thinking X slides — good?"
3. Generate the full Marp markdown file following the Technical Spec and Content Rules below.

### Step 3: Per-Slide Image Review

For each content slide (not title or thank-you), ask the user one at a time:
- "Slide X: [header]. Do you want an image?"
  - **No image** (default) — move on
  - **I'll provide one** — the user gives a file path or pastes an image. Save it to the `images/` subfolder next to the deck file with a descriptive name (e.g., `overall_refund_rate.png`). **Important:** screenshots from macOS often contain non-breaking spaces in filenames — use glob matching (`*keyword*`) when renaming, not literal filenames.
  - **Fetch a stock image** — search Unsplash via WebSearch for a relevant image, download to `images/` subfolder, reference locally
  - **Generate with AI** — describe what image would work; note that Marp can't render AI-generated images inline without saving the file locally first

### Step 4: Write File

1. Ask the user where to save (default: same folder as source doc, or `Inbox/` if built from scratch).
2. Create an `images/` subfolder next to the deck file for all image assets.
3. Write the `.md` file.
4. Confirm: "File written to [path]. Open it in VS Code with Marp extension to preview. Make sure 'Enable HTML' is checked in Marp settings."

---

## Marp Technical Spec

### Frontmatter (always included)

```yaml
---
marp: true
paginate: true
size: 16:9
style: |
  [THEME CSS HERE — Entity Theme CSS below; Neutral decks use the Dark/Light fallback]
  [TWO-COLUMN LAYOUT CSS — always included]
  [LOGO CSS HERE — if an entity is chosen]
  [PAGE NUMBER CSS — if a logo is used, to separate from logo]
---
```

### Entity Theme CSS (default — any deck for an entity)

Source of truth: `Instructions/Design_System/<entity>/theme.css` (relative to the vault root). **Read it and copy values from it — never hand-type brand hex codes or fonts.** Into the `style:` block, in this order:

1. The `@import url("https://fonts.googleapis.com/…")` line at the top of `theme.css` (must be first).
2. Light deck → the `:root { … }` variable block. Dark deck → the `:root { … }` block, then the `[data-theme="dark"] { … }` block's variables pasted as a second `:root { … }` (Marp has no `data-theme` attribute, so the dark values override directly).
3. These rules (targeting `section`, not `body`):

```css
section { background: var(--ds-bg); color: var(--ds-ink); font-family: var(--ds-font-body); font-size: 28px; padding: 40px 60px; line-height: 1.4; }
h1 { font-family: var(--ds-font-display); font-size: 44px; color: var(--ds-ink); border-bottom: 2px solid var(--ds-primary); padding-bottom: 12px; margin-bottom: 16px; }
h2 { font-family: var(--ds-font-display); font-size: 34px; color: var(--ds-ink); }
li { font-size: 26px; }
table { font-size: 22px; }
strong { color: var(--ds-primary-strong); }
blockquote { border-left: 4px solid var(--ds-primary); background: var(--ds-primary-soft); padding: 10px 16px; font-size: 24px; }
section.brand { background: var(--ds-gradient-hero); color: var(--ds-hero-ink); }
section.brand h1, section.brand h2 { color: var(--ds-hero-ink); border-bottom-color: var(--ds-hero-ink); }
```

`<!-- _class: brand -->` gives a brand divider slide (keynote style). Small coloured text uses `--ds-primary-strong` (passes WCAG AA); fills and big headings use `--ds-primary`. If the theme defines per-product accent variables (e.g. `--ds-product-<name>`), use them as accents only.

**Dark decks: never use markdown tables** — the Marp theme forces light cells and it cannot be fixed. Use structured bullets (`- **Name** — Detail — **Deadline**`) instead.

### Neutral Fallback — Dark Theme CSS (no entity only)

```css
section { background: #1a1a2e; color: #eaeaea; font-size: 28px; padding: 40px 60px; line-height: 1.4; }
h1 { font-size: 44px; color: #ffffff; border-bottom: 2px solid #4fc3f7; padding-bottom: 12px; margin-bottom: 16px; }
h2 { font-size: 34px; color: #ffffff; }
li { font-size: 26px; }
table { font-size: 22px; }
strong { color: #4fc3f7; }
blockquote { border-left: 4px solid #4fc3f7; background: #2a2a4e; padding: 10px 16px; font-size: 24px; }
```

### Neutral Fallback — Light Theme CSS (no entity only)

```css
section { background: #ffffff; color: #333333; font-size: 28px; padding: 40px 60px; line-height: 1.4; }
h1 { font-size: 44px; color: #1a1a2e; border-bottom: 2px solid #0066cc; padding-bottom: 12px; margin-bottom: 16px; }
h2 { font-size: 34px; color: #1a1a2e; }
li { font-size: 26px; }
table { font-size: 22px; }
strong { color: #0066cc; }
blockquote { border-left: 4px solid #e94560; background: #fff5f5; padding: 10px 16px; font-size: 24px; }
```

### Two-Column Layout CSS (always included)

Used for slides that have text + image side by side, with a full-width title on top.

```css
.columns { display: flex; gap: 32px; align-items: flex-start; margin-top: 16px; }
.col-left { flex: 1; }
.col-right { flex: 1; display: flex; align-items: center; justify-content: center; }
.col-right img { max-width: 100%; max-height: 380px; }
```

### Entity Logo (top-right on every slide — only if an entity is chosen)

Logos live in `Instructions/Design_System/<entity>/assets/` — copy the right one into the deck's `images/` subfolder. Use the on-light file for light decks, the white/on-dark file for dark decks (e.g. `acme-logo-color.svg` / `acme-logo-white.svg`). Check `<entity>/BRAND.md`, if present, for logo usage.

```css
section::after {
  background-image: url('./images/<logo-file>');
  background-size: contain;
  background-repeat: no-repeat;
  background-position: right center;
  position: absolute;
  top: 16px;
  right: 24px;
  width: 154px;
  height: 24px;
  padding: 0;
  font-size: 0;
  color: transparent;
}
```

> **Note:** Marp uses `section::after` for page numbers by default. The CSS above repurposes `::after` for the logo and hides the page number text (`font-size: 0; color: transparent`). Page numbers are moved to `::before` — see below.

### Page Numbers (when a logo is used)

Since `::after` is taken by the logo, page numbers must use `::before`:

```css
section::before {
  position: absolute;
  bottom: 20px;
  right: 30px;
  font-size: 16px;
  color: var(--ds-ink-muted);  /* Neutral decks: #999 */
}
```

### Image Placement — Two-Column Layout (preferred for slides with charts/images)

**Do NOT use `![bg right]` for slides with images.** Marp's `bg right` splits the entire slide including the title. Instead, use the HTML two-column layout so the H1 title spans full width on top:

```markdown
# 📊 Slide Title Goes Here Full Width

<div class="columns">
<div class="col-left">

- Bullet point one
- Bullet point two
- Bullet point three

</div>
<div class="col-right">
<img src="./images/chart_name.png" />
</div>
</div>
```

**Important:** Leave blank lines before and after the markdown content inside `<div class="col-left">` so Marp processes the markdown correctly.

### Image Placement — Full-Width (for slides without text/image split)

When an image should be the main focus without side-by-side text:

```markdown
![w:900 center](./images/image_name.png)
```

### Title Slide Structure

```markdown
<!-- _class: lead -->

# [Emoji] [Title]
## [Subtitle]

*[One-liner tagline]*
```

### Thank You Slide (always last)

```markdown
---

<!-- _class: lead -->

# <!-- fit --> **Thank You**
```

### Slide Separator

Use `---` between slides (standard Marp separator).

---

## Slide Content Rules

1. **Header**: One key insight per slide. Max 2 lines. Always starts with an emoji.

2. **Body format — choose the best fit per slide:**
   - **6x6 bullets** — when listing distinct items, features, steps, comparisons. Max 6 bullets, max 6 words per bullet. Use sub-bullets sparingly. Best for: action lists, feature overviews, checklists, priorities.
   - **Short paragraph** (2-3 sentences) — when conveying a narrative point, strategic argument, or "why" that reads better as flowing text. Best for: vision statements, problem descriptions, context-setting, key takeaways.
   - **Hybrid** — bold one-liner statement followed by 3-4 supporting bullets. Best for: slides that make a claim and then back it up.
   - Choose the format that fits best based on content. Apply automatically.

3. **Emojis**: Every header gets a relevant emoji. Key bullets can get emojis too.

4. **Tables**: Use when comparing 3+ items. Keep to 4-5 columns max. Font size 22px. **Light decks only** — on dark decks use structured bullets (see Entity Theme CSS).

5. **No walls of text**: If a paragraph exceeds 3 sentences, break it into bullets or split across slides.

6. **Slides with images/charts**: Always use the two-column HTML layout (`<div class="columns">`) so the title spans full width. Never use `![bg right]`.

---

## Quality Checklist

Before delivering the final file, verify:

- [ ] Frontmatter includes `marp: true`, `paginate: true`, `size: 16:9`
- [ ] Theme CSS copied from `Instructions/Design_System/<entity>/theme.css` (font `@import` first, dark values if dark) — no hand-typed brand hex; Neutral fallback only when no entity
- [ ] Two-column layout CSS included
- [ ] Entity logo CSS included only if an entity is chosen (top-right, `::after`, logo copied from `<entity>/assets/`)
- [ ] Page number CSS uses `::before` if a logo is present
- [ ] Dark deck has no markdown tables
- [ ] Every slide header has an emoji
- [ ] No slide exceeds 6 bullets or has bullets longer than ~6 words
- [ ] Tables use font-size 22px
- [ ] Image slides use HTML two-column layout (not `![bg right]`)
- [ ] All images saved locally in `images/` subfolder (no external URLs)
- [ ] Last slide is Thank You with `<!-- fit -->` formatting
- [ ] Slide separators (`---`) are correct
- [ ] File extension is `.md`
- [ ] "Enable HTML" reminder given to user

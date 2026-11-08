#!/usr/bin/env python3
"""
Tech News — RSS Fetcher (Stage 1 of the tech-news skill)

Fetches the configured RSS feeds + Google News queries for one region and
writes the raw articles to a staging markdown file. No AI, no API costs.
Can run on a schedule (e.g. a macOS LaunchAgent at 07:00) or on demand.

Usage:
    python3 fetch.py --vault <vault root> [--config <path to config.json>]

Config defaults to <vault>/Knowledge/Tech_News/config.json — copy
config.example.json from this skill and edit it. Requires:
    pip install feedparser requests python-dateutil
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import feedparser
    import requests
    from dateutil import parser as dateparser
except ImportError as e:  # pragma: no cover
    sys.exit(f"missing dependency ({e.name}) — run: pip install feedparser requests python-dateutil")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

CONFIG = {}          # loaded in main()
OUTPUT_FILE = None   # <vault>/<output_dir>/_staged_raw.md


def fetch_feed(name, url):
    """Fetch a single RSS feed, return list of article dicts."""
    articles = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries:
            pub_date = None
            if hasattr(entry, "published"):
                try:
                    pub_date = dateparser.parse(entry.published)
                except (ValueError, TypeError):
                    pass
            elif hasattr(entry, "updated"):
                try:
                    pub_date = dateparser.parse(entry.updated)
                except (ValueError, TypeError):
                    pass

            # Get snippet from summary or content
            snippet = ""
            if hasattr(entry, "summary"):
                snippet = entry.summary
            elif hasattr(entry, "content") and entry.content:
                snippet = entry.content[0].get("value", "")

            # Strip HTML tags (basic)
            import re
            snippet = re.sub(r"<[^>]+>", "", snippet).strip()
            snippet = snippet[:300] if snippet else ""

            articles.append({
                "title": getattr(entry, "title", "Untitled"),
                "source": name,
                "date": pub_date,
                "url": getattr(entry, "link", ""),
                "snippet": snippet,
            })
    except Exception as e:
        print(f"[WARN] Failed to fetch {name} ({url}): {e}", file=sys.stderr)
    return articles


def fetch_google_news(query):
    """Fetch Google News RSS for a search query, localised per config."""
    g = CONFIG.get("google_news", {})
    loc = f"&hl={g.get('hl', 'en-US')}&gl={g.get('gl', 'US')}&ceid={g.get('ceid', 'US:en')}"
    url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}{loc}"
    return fetch_feed(f"Google News ({query})", url)


def _slugify_title(title):
    """Convert article title to a URL slug."""
    import re
    slug = title.lower().strip()
    slug = re.sub(r"[''']s\b", "s", slug)  # possessives
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    # Remove common trailing words that TIA often drops
    slug = re.sub(r"-(report|update|sources?|exclusive|analysis)$", "", slug)
    return slug


def _url_slug_words(url):
    """Extract keyword set from a URL slug."""
    import re
    from urllib.parse import urlparse
    path = urlparse(url).path.strip("/").split("/")[-1] if url else ""
    if not path:
        return set()
    return set(re.sub(r"[^a-z0-9 ]", " ", path.replace("-", " ").lower()).split())


def _title_words(title):
    """Extract keyword set from a title."""
    import re
    return set(re.sub(r"[^a-z0-9 ]", " ", title.lower()).split())


_STOP_WORDS = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
               "is", "are", "was", "were", "be", "been", "with", "from", "by", "as",
               "its", "it", "s", "that", "this", "has", "have", "had", "not", "but",
               "new", "after", "into", "over", "how", "why", "what", "who", "when"}


def check_url_title_match(article):
    """Check if URL slug roughly matches the article title.

    Some RSS feeds (notably Tech in Asia) return wrong URLs for articles.
    This flags mismatches so Claude can find the correct link.
    Returns True if URL looks valid, False if suspect.
    """
    url = article.get("url", "")
    title = article.get("title", "")
    if not url or not title:
        return True

    slug_words = _url_slug_words(url) - _STOP_WORDS
    title_kw = _title_words(title) - _STOP_WORDS

    if not slug_words or not title_kw:
        return True

    overlap = slug_words & title_kw
    overlap_ratio = len(overlap) / min(len(slug_words), len(title_kw))

    return len(overlap) >= 2 or overlap_ratio >= 0.3


def _decode_google_news(url):
    """Decode a Google News 'rss/articles/<id>' link to the publisher URL (added 2026-09-25).
    Newer ids (AU_yqL…) don't redirect; Google's own page carries a signature + timestamp that
    its batchexecute endpoint exchanges for the real URL. Returns URL or None."""
    import re, json
    from urllib.parse import urlparse, quote
    try:
        gid = urlparse(url).path.rstrip("/").split("/")[-1]
        r = requests.get(f"https://news.google.com/rss/articles/{gid}", headers=HEADERS, timeout=10)
        sig = re.search(r'data-n-a-sg="([^"]+)"', r.text)
        ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
        if not (sig and ts):
            return None
        inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
                 f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{gid}",{ts.group(1)},"{sig.group(1)}"]')
        body = "f.req=" + quote(json.dumps([[["Fbv4je", inner, None, "generic"]]]))
        r2 = requests.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                           headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                           data=body, timeout=10)
        data = json.loads(r2.text.split("\n\n")[1])[:-2]
        decoded = json.loads(data[0][2])[1]
        return decoded if decoded and "news.google.com" not in decoded else None
    except Exception:
        return None


def _try_resolve_url(article):
    """Attempt to fix a suspect URL. Returns corrected URL or None."""
    from urllib.parse import urlparse
    url = article.get("url", "")
    title = article.get("title", "")
    source = article.get("source", "")

    # --- Strategy 1: Google News redirect resolution ---
    if "news.google.com" in url:
        decoded = _decode_google_news(url)
        if decoded:
            return decoded
        try:
            resp = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
            if resp.url and "news.google.com" not in resp.url:
                return resp.url
            # Some Google News URLs need a GET to resolve
            resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
            if resp.url and "news.google.com" not in resp.url:
                return resp.url
        except Exception:
            pass
        return None

    # --- Strategy 2: Tech in Asia title-slug construction ---
    if "techinasia.com" in url:
        slug = _slugify_title(title)
        if not slug:
            return None
        candidate = f"https://www.techinasia.com/{slug}"
        try:
            resp = requests.head(candidate, headers=HEADERS, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                return candidate
            # Try shorter slug (first 8 words)
            short_slug = "-".join(slug.split("-")[:8])
            if short_slug != slug:
                candidate2 = f"https://www.techinasia.com/{short_slug}"
                resp2 = requests.head(candidate2, headers=HEADERS, timeout=10, allow_redirects=True)
                if resp2.status_code == 200:
                    return candidate2
        except Exception:
            pass
        return None

    return None


def resolve_suspect_urls(articles):
    """Try to fix suspect URLs. Modifies articles in-place."""
    resolved = 0
    still_suspect = 0
    suspects = [a for a in articles if not check_url_title_match(a)]
    # Parallel (6 workers) — Google News decoding is ~0.5s/link (2026-09-25)
    with ThreadPoolExecutor(max_workers=6) as ex:
        fixes = list(ex.map(_try_resolve_url, suspects))
    for a, fixed_url in zip(suspects, fixes):
        if fixed_url:
            a["url"] = fixed_url
            a["_url_resolved"] = True
            resolved += 1
        else:
            still_suspect += 1
    print(f"[URL] Resolved {resolved} suspect URLs, {still_suspect} still suspect")
    return articles


def deduplicate(articles):
    """Basic dedup by normalized title prefix."""
    seen = set()
    unique = []
    for a in articles:
        # Normalize: lowercase, strip punctuation, take first 50 chars
        import re
        norm = re.sub(r"[^a-z0-9 ]", "", a["title"].lower())[:50].strip()
        if norm and norm not in seen:
            seen.add(norm)
            unique.append(a)
    return unique


def filter_recent(articles, hours=None):
    """Keep only articles from the last N hours."""
    hours = hours or CONFIG.get("cutoff_hours", 48)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    recent = []
    for a in articles:
        if a["date"] is None:
            # Include undated articles (better to have extras than miss)
            recent.append(a)
        else:
            # Make timezone-aware if needed
            d = a["date"]
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            if d >= cutoff:
                recent.append(a)
    return recent


def write_staging_file(articles):
    """Write structured markdown staging file."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%Y-%m-%d %H:%M")
    region = CONFIG.get("region_short") or CONFIG.get("region_name", "")

    lines = [
        f"# {region} Tech News — Raw Feed ({date_str})".replace("#  ", "# "),
        f"Generated: {time_str}",
        "",
        f"## Articles ({len(articles)} items)",
        "",
    ]

    suspect_count = 0
    for i, a in enumerate(articles, 1):
        date_display = a["date"].strftime("%Y-%m-%d") if a["date"] else "Unknown"
        url_ok = check_url_title_match(a)
        was_resolved = a.get("_url_resolved", False)
        lines.append(f"### {i}. {a['title']}")
        lines.append(f"- **Source:** {a['source']}")
        lines.append(f"- **Date:** {date_display}")
        lines.append(f"- **URL:** {a['url']}")
        if was_resolved:
            lines.append("- **✅ URL_RESOLVED** — Original URL was suspect; auto-corrected via title-slug lookup.")
        elif not url_ok:
            lines.append("- **⚠️ URL_SUSPECT** — URL slug does not match headline. Find correct link before publishing.")
            suspect_count += 1
        if a["snippet"]:
            lines.append(f"- **Snippet:** {a['snippet']}")
        lines.append("")

    if suspect_count:
        lines.insert(4, f"**⚠️ {suspect_count} articles have suspect URLs — verify before publishing.**\n")

    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Wrote {len(articles)} articles to {OUTPUT_FILE}")


def main():
    global CONFIG, OUTPUT_FILE
    ap = argparse.ArgumentParser(description="Fetch regional tech news into a staging file.")
    ap.add_argument("--vault", required=True, help="vault root")
    ap.add_argument("--config", help="config.json (default: <vault>/Knowledge/Tech_News/config.json)")
    args = ap.parse_args()
    vault = Path(args.vault).expanduser().resolve()
    cfg_path = Path(args.config).expanduser() if args.config else vault / "Knowledge" / "Tech_News" / "config.json"
    if not cfg_path.is_file():
        sys.exit(f"config not found: {cfg_path} — copy config.example.json from the tech-news skill")
    CONFIG = json.loads(cfg_path.read_text(encoding="utf-8"))
    OUTPUT_FILE = vault / CONFIG.get("output_dir", "Knowledge/Tech_News") / "_staged_raw.md"

    all_articles = []

    # Fetch all feeds in parallel
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        for name, url in CONFIG.get("rss_feeds", {}).items():
            futures[executor.submit(fetch_feed, name, url)] = name
        for query in CONFIG.get("google_news_queries", []):
            futures[executor.submit(fetch_google_news, query)] = f"Google: {query}"

        for future in as_completed(futures):
            source = futures[future]
            try:
                results = future.result()
                print(f"[OK] {source}: {len(results)} articles")
                all_articles.extend(results)
            except Exception as e:
                print(f"[ERR] {source}: {e}", file=sys.stderr)

    print(f"\nTotal raw: {len(all_articles)}")

    recent = filter_recent(all_articles)
    print(f"After time filter: {len(recent)}")

    unique = deduplicate(recent)
    print(f"After dedup: {len(unique)}")

    # Sort by date (newest first), undated at the end
    unique.sort(key=lambda a: a["date"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    resolve_suspect_urls(unique)
    write_staging_file(unique)


if __name__ == "__main__":
    main()

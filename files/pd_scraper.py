#!/usr/bin/env python3
"""
Family Procedure Rules – Practice Directions Scraper
Fetches all active (non-expired, non-revoked) Practice Directions from
https://www.justice.gov.uk/courts/procedure-rules/family/rules_pd_menu
and saves each as a structured markdown file with YAML frontmatter.

Output: ./pd_output/PD_<ref>.md
        ./pd_output/_scrape_log.txt

Usage:
    python pd_scraper.py
"""

import os
import re
import time
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ── Configuration ──────────────────────────────────────────────────────────────

INDEX_URL = "https://www.justice.gov.uk/courts/procedure-rules/family/rules_pd_menu"
OUTPUT_DIR = "./pd_output"
DELAY_SECONDS = 2

HEADERS = {
    "User-Agent": "ATJ-KnowledgeBase-Builder/1.0 (research; contact: atj@veeya.co.uk)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Setup ──────────────────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(OUTPUT_DIR, "_scrape_log.txt")),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

session = requests.Session()
session.headers.update(HEADERS)

# ── Index parsing ──────────────────────────────────────────────────────────────

def parse_index() -> list[dict]:
    """
    Parse the PD index page and return a list of active PD entries.
    Each entry: {title, url, status, ref}
    Skips anything without an <a> link or whose text contains Expired/REVOKED.
    """
    log.info(f"Fetching index: {INDEX_URL}")
    resp = session.get(INDEX_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    article = soup.find("article", id="main-page-content") or soup.find("main")
    if not article:
        raise RuntimeError("Could not find main content on index page")

    entries = []
    seen_urls = set()

    for td in article.find_all("td"):
        link = td.find("a", class_="link")

        # No link → expired / revoked plain text cell
        if not link:
            cell_text = td.get_text(" ", strip=True)
            if cell_text and cell_text != "\xa0":
                log.debug(f"  SKIP (no link): {cell_text[:80]}")
            continue

        href = link.get("href", "").strip()
        title = link.get_text(" ", strip=True)

        # Skip links that point back to the index page itself (exact path match or query param)
        parsed_href = urlparse(href)
        if parsed_href.path.rstrip("/") == urlparse(INDEX_URL).path.rstrip("/"):
            log.info(f"  SKIP (self-link): {title[:60]}")
            continue

        # Skip non-PD links (Parts, etc.) — only keep Practice Directions
        if not title.lower().startswith("practice direction"):
            log.debug(f"  SKIP (not a PD): {title[:60]}")
            continue

        # Skip off-domain links
        parsed = urlparse(href)
        if parsed.netloc and "justice.gov.uk" not in parsed.netloc:
            log.info(f"  SKIP (off-domain): {href}")
            continue

        # Deduplicate
        if href in seen_urls:
            continue
        seen_urls.add(href)

        # Extract status annotation: text in the <td> after the </a>
        full_cell_text = td.get_text(" ", strip=True)
        link_text = title
        annotation = full_cell_text[len(link_text):].strip().strip("()")

        # Normalise status
        status = normalise_status(annotation)

        ref = extract_ref(title)
        entries.append({"title": title, "url": href, "status": status, "ref": ref})

    log.info(f"Index parsed: {len(entries)} active Practice Directions found")
    return entries


def normalise_status(annotation: str) -> str:
    """Convert raw annotation text to a clean status string."""
    if not annotation:
        return "Active"
    a = annotation.lower()
    if "expired" in a:
        return f"Expired: {annotation}"
    if "revoked" in a:
        return f"Revoked"
    if "comes into force" in a:
        return f"In force: {annotation}"
    if "applicable to" in a or "applicable from" in a:
        return f"Applicable: {annotation}"
    if "commenced" in a or "pilot commenced" in a:
        return f"Pilot: {annotation}"
    return annotation.capitalize() if annotation else "Active"


def extract_ref(title: str) -> str:
    """
    Extract a short reference key for use in the filename.
    'Practice Direction 12B – ...' → '12B'
    'Practice Direction – Notes to ...' → 'Notes'
    'Practice Direction 3AA – ...' → '3AA'
    """
    # Try to match a number+letter ref like 12B, 3AA, 36ZH, etc.
    m = re.search(r"Practice Direction\s+(\d+[A-Z]*)", title, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Fallback: use a slug from the title
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", title)
    slug = re.sub(r"^Practice_Direction_?", "", slug, flags=re.IGNORECASE)
    return slug[:30].strip("_") or "Unknown"


# ── Page fetching & conversion ─────────────────────────────────────────────────

def fetch_pd(url: str) -> Optional[str]:
    """Fetch a PD page and return its HTML."""
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200:
            log.info(f"  ✓ fetched ({len(resp.text):,} chars)")
            return resp.text
        log.warning(f"  ✗ HTTP {resp.status_code}: {url}")
        return None
    except Exception as e:
        log.error(f"  ✗ error fetching {url}: {e}")
        return None


def html_to_markdown(html: str, entry: dict) -> str:
    """
    Convert a justice.gov.uk PD page to clean markdown with YAML frontmatter.
    Extracts from article#main-page-content, strips site chrome.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Target the article content element
    article = (
        soup.find("article", id="main-page-content")
        or soup.find("main")
        or soup.find("div", class_=re.compile(r"content"))
    )
    if not article:
        article = soup.find("body") or soup

    # Remove noise: nav, sidebars, cookie banners, print widgets, related links
    for tag in article.select(
        "nav, .nav, .navigation, header, footer, "
        ".sidebar, aside, "
        ".breadcrumbs, .breadcrumb, "
        ".print-page, .print-options, .print-link, "
        ".related-links, .related-content, "
        ".cookie-banner, #ccfw-page-banner, "
        "script, style, noscript, "
        ".page-tools, .social-links, "
        ".alert, .notice, .warning-box"
    ):
        tag.decompose()

    scrape_date = datetime.utcnow().strftime("%Y-%m-%d")

    # Build YAML frontmatter
    lines = [
        "---",
        f"source: Family Procedure Rules – Practice Directions",
        f"ref: PD {entry['ref']}",
        f"title: {entry['title']}",
        f"url: {entry['url']}",
        f"status: {entry['status']}",
        f"scraped: {scrape_date}",
        f"licence: Open Government Licence v3.0",
        "---",
        "",
        f"# {entry['title']}",
        "",
    ]

    def process(el) -> list[str]:
        out = []
        for child in el.children:
            if child.name is None:
                text = (child.string or "").strip()
                if text:
                    out.append(text)
            elif child.name == "h1":
                # Already emitted as YAML title / doc H1 — skip duplicate
                pass
            elif child.name == "h2":
                text = child.get_text(" ", strip=True)
                if text:
                    out.append(f"\n## {text}\n")
            elif child.name == "h3":
                text = child.get_text(" ", strip=True)
                if text:
                    out.append(f"\n### {text}\n")
            elif child.name in ("h4", "h5", "h6"):
                text = child.get_text(" ", strip=True)
                if text:
                    out.append(f"\n#### {text}\n")
            elif child.name == "p":
                text = child.get_text(" ", strip=True)
                if text:
                    out.append(f"\n{text}\n")
            elif child.name in ("ul", "ol"):
                for li in child.find_all("li", recursive=False):
                    text = li.get_text(" ", strip=True)
                    if text:
                        out.append(f"- {text}")
                out.append("")
            elif child.name == "li":
                text = child.get_text(" ", strip=True)
                if text:
                    out.append(f"- {text}")
            elif child.name == "table":
                rows = child.find_all("tr")
                if rows:
                    # Emit as markdown table
                    header_cells = rows[0].find_all(["th", "td"])
                    headers = [c.get_text(" ", strip=True) for c in header_cells]
                    if any(headers):
                        out.append("| " + " | ".join(headers) + " |")
                        out.append("| " + " | ".join(["---"] * len(headers)) + " |")
                    for row in rows[1:]:
                        cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
                        if any(cells):
                            out.append("| " + " | ".join(cells) + " |")
                    out.append("")
            elif child.name in ("div", "section", "article", "blockquote"):
                out.extend(process(child))
            elif child.name in ("strong", "b", "em", "i"):
                text = child.get_text(" ", strip=True)
                if text:
                    out.append(text)
            elif child.name == "a":
                text = child.get_text(" ", strip=True)
                if text:
                    out.append(text)
            elif child.name == "br":
                out.append("")
            elif child.name in ("span",):
                out.extend(process(child))
        return out

    content_parts = process(article)
    content = "\n".join(content_parts)
    content = re.sub(r"\n{4,}", "\n\n\n", content).strip()

    lines.append(content)
    return "\n".join(lines) + "\n"


def save_markdown(content: str, filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    log.info(f"    → saved: {filename} ({len(content):,} chars)")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("FPR Practice Directions Scraper — starting")
    log.info(f"Output directory: {os.path.abspath(OUTPUT_DIR)}")
    log.info("=" * 60)

    entries = parse_index()

    success, failed = 0, []

    for entry in entries:
        log.info(f"[PD {entry['ref']}] {entry['title'][:70]}")
        html = fetch_pd(entry["url"])
        if not html:
            failed.append(entry["ref"])
            time.sleep(DELAY_SECONDS)
            continue

        md = html_to_markdown(html, entry)
        filename = f"PD_{entry['ref']}.md"
        save_markdown(md, filename)
        success += 1
        time.sleep(DELAY_SECONDS)

    log.info("=" * 60)
    log.info(f"Complete. {success} files saved, {len(failed)} failed.")
    if failed:
        log.warning(f"Failed refs: {', '.join(failed)}")
    log.info(f"Files in: {os.path.abspath(OUTPUT_DIR)}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()

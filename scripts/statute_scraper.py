#!/usr/bin/env python3
"""
Statute Section Scraper
Fetches specific sections from three Acts on legislation.gov.uk
(revised/current versions) and saves each as a structured markdown
file with YAML frontmatter.

Usage:
    cd scripts && python3 statute_scraper.py

Output:
    ../raw/legislation/children_act_1989/s{N}.md
    ../raw/legislation/matrimonial_causes_act_1973/s{N}.md
    ../raw/legislation/family_law_act_1996/s{N}.md
    ../raw/legislation/_scrape_log.txt
"""

import os
import re
import time
import logging
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ── Configuration ──────────────────────────────────────────────────────────────

DELAY_SECONDS = 2
LOG_PATH = "../raw/legislation/_scrape_log.txt"

ACTS = [
    {
        "name": "Children Act 1989",
        "citation": "Children Act 1989 (c. 41)",
        "base_url": "https://www.legislation.gov.uk/ukpga/1989/41/section/",
        "output_dir": "../raw/legislation/children_act_1989",
        "sections": ["1", "2", "3", "4", "7", "8", "11", "16A", "31", "37", "91", "97"],
    },
    {
        "name": "Matrimonial Causes Act 1973",
        "citation": "Matrimonial Causes Act 1973 (c. 18)",
        "base_url": "https://www.legislation.gov.uk/ukpga/1973/18/section/",
        "output_dir": "../raw/legislation/matrimonial_causes_act_1973",
        "sections": ["1", "21", "22", "23", "24", "24A", "25", "25A", "37"],
    },
    {
        "name": "Family Law Act 1996",
        "citation": "Family Law Act 1996 (c. 27)",
        "base_url": "https://www.legislation.gov.uk/ukpga/1996/27/section/",
        "output_dir": "../raw/legislation/family_law_act_1996",
        "sections": ["30", "31", "32", "33", "42", "43", "44", "63"],
    },
]

# ── Logging ────────────────────────────────────────────────────────────────────

os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── HTTP session ───────────────────────────────────────────────────────────────

session = requests.Session()
session.headers.update({
    "User-Agent": "ATJ-KnowledgeBase-Builder/1.0 (research; contact: atj@veeya.co.uk)",
    "Accept": "text/html,application/xhtml+xml",
})

# ── Fetch ──────────────────────────────────────────────────────────────────────

def fetch_section(base_url: str, section: str) -> Optional[str]:
    url = f"{base_url}{section}/data.xht?view=snippet&wrap=true"
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200:
            log.info(f"    ✓ fetched ({len(resp.text):,} chars)")
            return resp.text
        log.warning(f"    ✗ HTTP {resp.status_code}: {url}")
        return None
    except Exception as e:
        log.error(f"    ✗ error: {e}")
        return None

# ── HTML → Markdown ────────────────────────────────────────────────────────────

def extract_section_title(soup: BeautifulSoup) -> str:
    """Pull the section title from the h3 LegP1Container heading."""
    h3 = soup.find("h3", class_=re.compile(r"LegP1Container"))
    if not h3:
        return ""
    title_span = h3.find("span", class_=re.compile(r"LegP1GroupTitle"))
    if title_span:
        return title_span.get_text(" ", strip=True).rstrip(".")
    # Fallback: full h3 text with leading number stripped
    text = h3.get_text(" ", strip=True)
    return re.sub(r"^\d+[A-Za-z]*\s*", "", text).rstrip(".")


def get_valid_date(soup: BeautifulSoup) -> str:
    """Read DC.Date.Valid meta tag — the 'valid from' date for this version."""
    meta = soup.find("meta", attrs={"name": "DC.Date.Valid"})
    return meta["content"] if meta else ""


def html_to_markdown(html: str, act: dict, section: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # ── Strip noise ─────────────────────────────────────────────────────────
    # LegExtentRestriction: "E+W" territorial markers
    # LegAnchorID: invisible anchor <a> elements
    # LegClearPart: decorative spacer divs between Parts
    # LegChangeDelimiter: amendment bracket characters [ ]
    # LegAnnotations / LegCommentary*: footnotes and amendment history
    for tag in soup.select(
        ".LegExtentRestriction, .LegAnchorID, .LegClearPart, "
        ".LegChangeDelimiter, .LegAnnotations, .LegAnnotationsGroupHeading, "
        ".LegCommentaryItem, .LegCommentaryPara, .LegCommentaryText, "
        ".LegCommentaryType, .LegCommentaryLink, "
        "script, style"
    ):
        tag.decompose()

    section_title = extract_section_title(soup)
    valid_date = get_valid_date(soup)
    scrape_date = datetime.utcnow().strftime("%Y-%m-%d")

    section_url = f"{act['base_url']}{section}"
    full_title = f"Section {section} — {section_title}" if section_title else f"Section {section}"
    version = f"Latest available (Revised)"
    if valid_date:
        version += f" — valid from {valid_date}"

    lines = [
        "---",
        f"source: {act['citation']}",
        f"act: {act['name']}",
        f'section: "{section}"',
        f"title: {full_title}",
        f"url: {section_url}",
        f"version: {version}",
        f"scraped: {scrape_date}",
        "licence: Open Government Licence v3.0",
        "---",
        "",
        f"# {full_title}",
        "",
    ]

    content = render_content(soup)
    lines.append(content)
    return "\n".join(lines) + "\n"


def render_content(soup: BeautifulSoup) -> str:
    """
    Walk the legislation HTML and produce clean markdown.

    Paragraph depth classes:
      LegP2 → subsection   (1), (2)  →  **bold** inline
      LegP3 → paragraph    (a), (b)  →  - list item
      LegP4 → sub-para     (i), (ii) →  indented - list item
      LegP5 → sub-sub-para           →  double-indented - list item

    Continuation text (no LHS number) is emitted as a plain paragraph.
    """
    doc = (
        soup.find("div", class_="DocContainer")
        or soup.find("div", class_="LegSnippet")
        or soup.find("body")
        or soup
    )

    lines = []

    def lhs(el: BeautifulSoup) -> str:
        span = el.find(class_=re.compile(r"Leg(?:LHS|P\dNo)"))
        return span.get_text(strip=True) if span else ""

    def rhs(el: BeautifulSoup) -> str:
        span = el.find(class_=re.compile(r"Leg(?:RHS|P\dText|Text$)"))
        if span:
            return span.get_text(" ", strip=True)
        full = el.get_text(" ", strip=True)
        num = lhs(el)
        return full[len(num):].strip() if num else full.strip()

    def class_str(el: BeautifulSoup) -> str:
        return " ".join(el.get("class") or [])

    def walk(parent):
        for el in parent.children:
            if not getattr(el, "name", None):
                continue
            cs = class_str(el)

            if el.name == "h2":
                text = el.get_text(" ", strip=True)
                if text:
                    lines.append(f"\n## {text}\n")

            elif el.name == "h3":
                text = el.get_text(" ", strip=True)
                if text:
                    lines.append(f"\n### {text}\n")

            elif el.name == "h4":
                text = el.get_text(" ", strip=True)
                if text:
                    lines.append(f"\n#### {text}\n")

            elif el.name == "p":
                num = lhs(el)
                text = rhs(el)

                if "LegP5" in cs:
                    prefix = f"    - **{num}**" if num else "    -"
                elif "LegP4" in cs:
                    prefix = f"  - **{num}**" if num else "  -"
                elif "LegP3" in cs:
                    prefix = f"- **{num}**" if num else "-"
                elif "LegP2" in cs:
                    prefix = f"\n**{num}**" if num else "\n"
                else:
                    # Continuation text or plain paragraph
                    if text:
                        lines.append(f"\n{text}\n")
                    continue

                if text:
                    lines.append(f"{prefix} {text}")
                elif num:
                    lines.append(prefix)

            elif el.name in ("div", "section", "article"):
                walk(el)

    walk(doc)

    content = "\n".join(lines)
    return re.sub(r"\n{4,}", "\n\n\n", content).strip()

# ── Save ───────────────────────────────────────────────────────────────────────

def save_markdown(content: str, output_dir: str, section: str):
    os.makedirs(output_dir, exist_ok=True)
    filename = f"s{section}.md"
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    log.info(f"    → saved: {filename} ({len(content):,} chars)")

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("Statute Section Scraper — starting")
    total_sections = sum(len(a["sections"]) for a in ACTS)
    log.info(f"Acts: {len(ACTS)}  |  Sections: {total_sections}")
    log.info("=" * 60)

    success, failed = 0, []

    for act in ACTS:
        log.info(f"\n{act['name']}  ({len(act['sections'])} sections)")
        os.makedirs(act["output_dir"], exist_ok=True)

        for section in act["sections"]:
            log.info(f"  s{section}")
            html = fetch_section(act["base_url"], section)
            if not html:
                failed.append(f"{act['name']} s{section}")
                time.sleep(DELAY_SECONDS)
                continue

            md = html_to_markdown(html, act, section)
            save_markdown(md, act["output_dir"], section)
            success += 1
            time.sleep(DELAY_SECONDS)

    log.info("\n" + "=" * 60)
    log.info(f"Complete. {success}/{total_sections} sections saved, {len(failed)} failed.")
    if failed:
        log.warning(f"Failed: {', '.join(failed)}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
ATJ Knowledge Base — Category 6 Scraper
Supporting context: CAFCASS, Family Mediation Council, GOV.UK legal aid.

RAG design: each logical section (H2 boundary) saved as its own markdown file.
Frontmatter carries parent document, section title, URL, and provenance.

Run from repo root:
    python scripts/supporting_context_scraper.py

Output: raw/supporting_context/
"""

import logging
import os
import re
import sys
import time
from datetime import date
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUTPUT_DIR = "raw/supporting_context"
LOG_FILE = os.path.join(OUTPUT_DIR, "_scrape_log.txt")
DELAY_SECONDS = 2
TODAY = date.today().isoformat()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ATJ-KB-Scraper/1.0; "
        "+https://github.com/veeyastudio-wq/atj-knowledge-base)"
    )
}

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

# Each entry: (slug, label, url, organisation, licence)
SOURCES = [
    # --- CAFCASS ---
    (
        "cafcass_private_law_overview",
        "My family is involved in private law proceedings: Cafcass",
        "https://www.cafcass.gov.uk/parent-carer-or-family-member/my-family-involved-private-law-proceedings",
        "cafcass",
        "Open Government Licence v3.0",
    ),
    (
        "cafcass_court_process",
        "The court process and what to expect in private law: Cafcass",
        "https://www.cafcass.gov.uk/parent-carer-or-family-member/my-family-involved-private-law-proceedings/court-process-and-what-expect-private-law",
        "cafcass",
        "Open Government Licence v3.0",
    ),
    (
        "cafcass_what_happens_private_law",
        "What happens in private law proceedings: Cafcass",
        "https://www.cafcass.gov.uk/parent-carer-or-family-member/my-family-involved-private-law-proceedings/court-process-and-what-expect/what-happens-private-law-proceedings",
        "cafcass",
        "Open Government Licence v3.0",
    ),
    (
        "cafcass_safeguarding_letter",
        "The safeguarding letter: Cafcass",
        "https://www.cafcass.gov.uk/parent-carer-or-family-member/my-family-involved-private-law-proceedings/court-process-and-what-expect/family-court-adviser-gives-safeguarding-advice-court-safeguarding-letter",
        "cafcass",
        "Open Government Licence v3.0",
    ),
    (
        "cafcass_section7_reports",
        "Section 7 reports: Cafcass",
        "https://www.cafcass.gov.uk/parent-carer-or-family-member/applications-child-arrangements-order/court-process-and-what-expect/court-asks-fca-write-report-if-your-case-goes-beyond-first-hearing-section-7-reports",
        "cafcass",
        "Open Government Licence v3.0",
    ),
    (
        "cafcass_resources_parents",
        "Information and resources for parents: Cafcass",
        "https://www.cafcass.gov.uk/parent-carer-or-family-member/information-and-resources-parents",
        "cafcass",
        "Open Government Licence v3.0",
    ),
    # --- Family Mediation Council ---
    (
        "fmc_what_is_mediation",
        "What is family mediation: Family Mediation Council",
        "https://www.familymediationcouncil.org.uk/family-mediation/",
        "fmc",
        "© Family Mediation Council",
    ),
    (
        "fmc_miam",
        "Mediation Information and Assessment Meeting (MIAM): Family Mediation Council",
        "https://www.familymediationcouncil.org.uk/family-mediation/assessment-meeting-miam/",
        "fmc",
        "© Family Mediation Council",
    ),
    (
        "fmc_why_choose_mediation",
        "Why choose family mediation: Family Mediation Council",
        "https://www.familymediationcouncil.org.uk/family-mediation/choose-family-mediation/",
        "fmc",
        "© Family Mediation Council",
    ),
    # --- GOV.UK legal aid ---
    (
        "govuk_legal_aid_overview",
        "Legal aid overview: GOV.UK",
        "https://www.gov.uk/legal-aid",
        "govuk",
        "Open Government Licence v3.0",
    ),
    (
        "govuk_legal_aid_what_youll_get",
        "Legal aid — what you'll get: GOV.UK",
        "https://www.gov.uk/legal-aid/what-youll-get",
        "govuk",
        "Open Government Licence v3.0",
    ),
    (
        "govuk_legal_aid_means_testing",
        "Civil legal aid means testing: GOV.UK",
        "https://www.gov.uk/guidance/civil-legal-aid-means-testing",
        "govuk",
        "Open Government Licence v3.0",
    ),
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    logger = logging.getLogger("supporting_context_scraper")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


log = _setup_logging()

# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

_YAML_SPECIAL = re.compile(r'[:#\[\]{},&*?|<>=!%@`]')


def _yaml_str(value: str) -> str:
    if _YAML_SPECIAL.search(value):
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _frontmatter(fields: dict) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if v is None:
            lines.append(f"{k}:")
        elif isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {_yaml_str(str(item))}")
        else:
            lines.append(f"{k}: {_yaml_str(str(v))}")
    lines.append("---\n")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    text = re.sub(r"^_+|_+$", "", text)
    return text[:80]

# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

def _extract_sections(soup: BeautifulSoup, org: str) -> List[Tuple[str, str]]:
    """
    Extract H2-bounded sections from a page.
    Works for GOV.UK, CAFCASS, and FMC — all use standard semantic HTML.
    Falls back gracefully when H2s are absent (shallow pages become one section).
    """
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"(content|main|body)", re.I))
        or soup.body
    )
    if not main:
        return []

    # Strip nav, header, footer, aside, and script/style noise
    for tag in main.find_all(["nav", "header", "footer", "aside", "script", "style"]):
        tag.decompose()

    sections: List[Tuple[str, str]] = []
    current_heading = "Overview"
    current_blocks: List[str] = []

    def _flush() -> None:
        body = "\n\n".join(current_blocks).strip()
        if body:
            sections.append((current_heading, body))

    for el in main.descendants:
        if not isinstance(el, Tag):
            continue
        if el.name == "h1" and not sections and not current_blocks:
            # Use H1 as the Overview heading if we haven't started yet
            current_heading = el.get_text(separator=" ", strip=True)
        elif el.name == "h2":
            _flush()
            current_heading = el.get_text(separator=" ", strip=True)
            current_blocks = []
        elif el.name == "h3":
            current_blocks.append(f"### {el.get_text(separator=' ', strip=True)}")
        elif el.name == "h4":
            current_blocks.append(f"#### {el.get_text(separator=' ', strip=True)}")
        elif el.name == "p":
            text = el.get_text(separator=" ", strip=True)
            if text:
                current_blocks.append(text)
        elif el.name in ("ul", "ol"):
            # Only process top-level list items to avoid double-counting nested lists
            items = []
            for li in el.find_all("li", recursive=False):
                items.append(f"- {li.get_text(separator=' ', strip=True)}")
            if items:
                current_blocks.append("\n".join(items))

    _flush()
    return sections

# ---------------------------------------------------------------------------
# Scrape one source
# ---------------------------------------------------------------------------

def scrape_source(
    session: requests.Session,
    slug: str,
    label: str,
    url: str,
    org: str,
    licence: str,
) -> int:
    log.info(f"Fetching: {url}")
    try:
        resp = session.get(url, timeout=30, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Failed to fetch {url}: {e}")
        return 0

    time.sleep(DELAY_SECONDS)

    soup = BeautifulSoup(resp.text, "html.parser")
    sections = _extract_sections(soup, org)

    if not sections:
        log.warning(f"No sections extracted from {url} — page structure may have changed")
        return 0

    saved = 0
    for idx, (heading, body) in enumerate(sections):
        section_slug = _slugify(heading)
        filename = f"{slug}__{idx:03d}__{section_slug}.md"
        filepath = os.path.join(OUTPUT_DIR, filename)

        fm = _frontmatter({
            "source": label,
            "section": heading,
            "parent_document": label,
            "parent_slug": slug,
            "section_index": idx,
            "organisation": org,
            "url": url,
            "scrape_date": TODAY,
            "licence": licence,
            "content_type": "supporting_context",
            "jurisdiction": "England and Wales",
        })

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(fm)
            f.write(f"# {heading}\n\n")
            f.write(body)
            f.write("\n")

        log.info(f"  Saved: {filename}")
        saved += 1

    return saved

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session = _make_session()
    total = 0

    log.info("=== Category 6 scraper starting ===")
    log.info(f"Output: {OUTPUT_DIR}/")

    for slug, label, url, org, licence in SOURCES:
        count = scrape_source(session, slug, label, url, org, licence)
        log.info(f"{slug}: {count} section files saved")
        total += count

    log.info(f"=== Done. {total} files saved to {OUTPUT_DIR}/ ===")


if __name__ == "__main__":
    main()

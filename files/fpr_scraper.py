#!/usr/bin/env python3
"""
FPR 2010 Scraper
Fetches each Part of the Family Procedure Rules 2010 (revised/current version)
from legislation.gov.uk and saves as structured markdown files for RAG ingestion.

Source: https://www.legislation.gov.uk/uksi/2010/2955
Licence: Open Government Licence v3.0

Usage:
    python fpr_scraper.py

Output:
    ./fpr_output/FPR_Part_1.md
    ./fpr_output/FPR_Part_2.md
    ... etc
    ./fpr_output/FPR_Glossary.md
    ./fpr_output/_scrape_log.txt
"""

import os
import time
import logging
import requests
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup

# ── Configuration ──────────────────────────────────────────────────────────────

BASE_URL = "https://www.legislation.gov.uk/uksi/2010/2955"
OUTPUT_DIR = "./fpr_output"
DELAY_SECONDS = 2  # polite delay between requests

# All Parts of the FPR 2010 as they appear in the revised version.
# Format: (part_id, human_readable_title)
# part_id maps to the URL segment: /uksi/2010/2955/part/{part_id}
PARTS = [
    ("1",   "Overriding Objective"),
    ("2",   "Application and Interpretation of the Rules"),
    ("3",   "Non-court Dispute Resolution"),
    ("3A",  "Vulnerable Persons: Participation in Proceedings and Giving Evidence"),
    ("4",   "General Case Management Powers"),
    ("5",   "Forms, Start of Proceedings and Communication with the Court"),
    ("6",   "Service"),
    ("7",   "Procedure for Applications in Matrimonial and Civil Partnership Proceedings"),
    ("8",   "Procedure for Miscellaneous Applications"),
    ("9",   "Applications for a Financial Remedy"),
    ("10",  "Applications under Part 4 of the Family Law Act 1996"),
    ("11",  "Applications under Part 4A of the Family Law Act 1996 or Part 1 of Schedule 2 to the Female Genital Mutilation Act 2003"),
    ("12",  "Children Proceedings except Parental Order Proceedings and Proceedings for Applications in Adoption, Placement and Related Proceedings"),
    ("13",  "Proceedings under Section 54 of the Human Fertilisation and Embryology Act 2008"),
    ("14",  "Procedure for Applications in Adoption, Placement and Related Proceedings"),
    ("15",  "Representation of Protected Parties"),
    ("16",  "Representation of Children and Reports in Proceedings Involving Children"),
    ("17",  "Statements of Truth"),
    ("18",  "Procedure for Other Applications in Proceedings"),
    ("19",  "Alternative Procedure for Applications"),
    ("20",  "Interim Remedies and Security for Costs"),
    ("21",  "Miscellaneous Rules about Disclosure and Inspection of Documents"),
    ("22",  "Evidence"),
    ("23",  "Miscellaneous Rules about Evidence"),
    ("24",  "Witnesses, Depositions Generally and Taking of Evidence in Member States of the European Union"),
    ("25",  "Experts and Assessors"),
    ("26",  "Change of Solicitor"),
    ("27",  "Hearings and Directions Appointments"),
    ("28",  "Costs"),
    ("29",  "Miscellaneous"),
    ("30",  "Appeals"),
    ("31",  "Registration of Orders under the Council Regulation, the Civil Partnership (Jurisdiction and Recognition of Judgments) Regulations 2005 and under the Hague Convention 1996"),
    ("32",  "Registration and Enforcement of Orders"),
    ("33",  "Enforcement"),
    ("34",  "Reciprocal Enforcement of Maintenance Orders"),
    ("35",  "Mediation Directive"),
    ("36",  "Transitional Arrangements and Pilot Schemes"),
]

# The glossary is at a different URL
GLOSSARY_URL = f"{BASE_URL}/schedule/Glossary"

# ── Setup ──────────────────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(OUTPUT_DIR, "_scrape_log.txt")),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

session = requests.Session()
session.headers.update({
    "User-Agent": "ATJ-KnowledgeBase-Builder/1.0 (research; contact: atj@veeya.co.uk)",
    "Accept": "text/html,application/xhtml+xml",
})

# ── Core functions ─────────────────────────────────────────────────────────────

def fetch_part_html(part_id: str) -> Optional[str]:
    """Fetch the full HTML of a Part using the data.xht snippet endpoint."""
    url = f"{BASE_URL}/part/{part_id}/data.xht?view=snippet&wrap=true"
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200:
            log.info(f"✓ Part {part_id} — fetched ({len(resp.text)} chars)")
            return resp.text
        else:
            log.warning(f"✗ Part {part_id} — HTTP {resp.status_code}")
            return None
    except Exception as e:
        log.error(f"✗ Part {part_id} — error: {e}")
        return None


def fetch_glossary_html() -> Optional[str]:
    """Fetch the Glossary. It lives at part/GLOSSARY (uppercase), not as a schedule."""
    url = f"{BASE_URL}/part/GLOSSARY/data.xht?view=snippet&wrap=true"
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200:
            log.info(f"✓ Glossary — fetched ({len(resp.text)} chars)")
            return resp.text
        log.warning(f"✗ Glossary — HTTP {resp.status_code}")
        return None
    except Exception as e:
        log.error(f"✗ Glossary — error: {e}")
        return None


def html_to_markdown(html: str, part_id: str, title: str) -> str:
    """
    Parse the legislation HTML and convert to clean markdown.
    Preserves rule numbering, headings, and structure.
    Strips navigation chrome, footnotes, and metadata noise.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove known noise elements — do NOT remove .LegClearFix broadly
    # as it also wraps .LegTableContainer (e.g. the Glossary table)
    for tag in soup.select(
        "nav, .navigation, .breadcrumbs, .print-options, "
        ".timeline, .changes, script, style, "
        ".LegClearPart, .interface, .viewLegContents, "
        ".LegExtentRestriction, footer, header"
    ):
        tag.decompose()

    lines = []
    scrape_date = datetime.utcnow().strftime("%Y-%m-%d")

    # Metadata header
    lines.append(f"---")
    lines.append(f"source: The Family Procedure Rules 2010 (SI 2010/2955)")
    lines.append(f"part: {part_id}")
    lines.append(f"title: Part {part_id} — {title}")
    lines.append(f"url: https://www.legislation.gov.uk/uksi/2010/2955/part/{part_id}")
    lines.append(f"version: Latest available (Revised)")
    lines.append(f"scraped: {scrape_date}")
    lines.append(f"licence: Open Government Licence v3.0")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"# Part {part_id} — {title}")
    lines.append(f"")

    def process_element(el):
        """Recursively extract text from an element, preserving structure."""
        result = []
        for child in el.children:
            if child.name is None:
                # Text node
                text = child.string or ""
                text = text.strip()
                if text:
                    result.append(text)
            elif child.name in ["h1", "h2"]:
                text = child.get_text(separator=" ", strip=True)
                if text:
                    result.append(f"\n## {text}\n")
            elif child.name in ["h3", "h4"]:
                text = child.get_text(separator=" ", strip=True)
                if text:
                    result.append(f"\n### {text}\n")
            elif child.name in ["h5", "h6"]:
                text = child.get_text(separator=" ", strip=True)
                if text:
                    result.append(f"\n#### {text}\n")
            elif child.name == "p":
                text = child.get_text(separator=" ", strip=True)
                if text:
                    result.append(f"\n{text}\n")
            elif child.name in ["ul", "ol"]:
                for li in child.find_all("li", recursive=False):
                    text = li.get_text(separator=" ", strip=True)
                    if text:
                        result.append(f"- {text}")
                result.append("")
            elif child.name == "li":
                text = child.get_text(separator=" ", strip=True)
                if text:
                    result.append(f"- {text}")
            elif child.name in ["div", "section", "article", "span"]:
                result.extend(process_element(child))
            elif child.name in ["strong", "b", "em", "i", "a"]:
                text = child.get_text(separator=" ", strip=True)
                if text:
                    result.append(text)
            elif child.name == "br":
                result.append("")
            elif child.name == "table":
                # Flatten tables to readable text
                for row in child.find_all("tr"):
                    cells = [td.get_text(separator=" ", strip=True) for td in row.find_all(["td", "th"])]
                    if any(cells):
                        result.append(" | ".join(cells))
                result.append("")
        return result

    body = soup.find("body") or soup
    content_parts = process_element(body)
    content = "\n".join(content_parts)

    # Clean up excessive blank lines
    import re
    content = re.sub(r"\n{4,}", "\n\n\n", content)
    content = content.strip()

    lines.append(content)
    return "\n".join(lines)


def save_markdown(content: str, filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    log.info(f"  → saved: {filename} ({len(content)} chars)")


# ── Main scrape loop ────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("FPR 2010 Scraper — starting")
    log.info(f"Output directory: {os.path.abspath(OUTPUT_DIR)}")
    log.info(f"Parts to fetch: {len(PARTS)} + Glossary")
    log.info("=" * 60)

    success = 0
    failed = []

    for part_id, title in PARTS:
        html = fetch_part_html(part_id)
        if html:
            md = html_to_markdown(html, part_id, title)
            filename = f"FPR_Part_{part_id.replace('/', '_')}.md"
            save_markdown(md, filename)
            success += 1
        else:
            failed.append(f"Part {part_id}")
        time.sleep(DELAY_SECONDS)

    # Glossary
    log.info("Fetching Glossary...")
    glossary_html = fetch_glossary_html()
    if glossary_html:
        md = html_to_markdown(glossary_html, "GLOSSARY", "Glossary")
        save_markdown(md, "FPR_Glossary.md")
        success += 1
    else:
        failed.append("Glossary")

    # Summary
    log.info("=" * 60)
    log.info(f"Complete. {success} files saved, {len(failed)} failed.")
    if failed:
        log.warning(f"Failed: {', '.join(failed)}")
    log.info(f"Files are in: {os.path.abspath(OUTPUT_DIR)}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()

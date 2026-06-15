#!/usr/bin/env python3
"""
Standalone scraper for FL401 — Application for a non-molestation order or
an occupation order.

Downloads the PDF from the direct GOV.UK assets URL, extracts text and form
fields, and saves raw/court_forms/FL401.md with YAML frontmatter matching the
existing court_forms_scraper.py pattern.

Usage:
    cd <repo-root>
    python3 scripts/scrape_fl401.py
"""

import os
import re
import sys
import tempfile
from datetime import datetime

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# ── Config ────────────────────────────────────────────────────────────────────

FORM_ID      = "FL401"
TRACK        = "cross_cutting"
LANDING_URL  = "https://www.gov.uk/government/publications/apply-for-a-non-molestation-or-occupation-order-fl401"
PDF_URL      = "https://assets.publishing.service.gov.uk/media/64ba40ae2059dc00125d2745/FL401_ER.pdf"
VERSION_DATE = "2025-06-16"   # GOV.UK last updated date confirmed by user
OUTPUT_PATH  = "raw/court_forms/FL401.md"

session = requests.Session()
session.headers.update({
    "User-Agent": "ATJ-KnowledgeBase-Builder/1.0 (research; contact: atj@veeya.co.uk)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_landing_meta() -> dict:
    """Fetch title and description from the GOV.UK landing page."""
    print(f"Fetching landing page: {LANDING_URL}")
    resp = session.get(LANDING_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else f"Form {FORM_ID}"

    lead = soup.select_one("p.gem-c-lead-paragraph")
    description = lead.get_text(strip=True) if lead else ""

    print(f"  title: {title[:80]}")
    return {"title": title, "description": description}


def download_pdf() -> str:
    """Download PDF to a temp file and return its path."""
    print(f"Downloading PDF: {PDF_URL}")
    resp = session.get(PDF_URL, timeout=60, stream=True)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    for chunk in resp.iter_content(chunk_size=65536):
        tmp.write(chunk)
    tmp.close()
    size_kb = os.path.getsize(tmp.name) // 1024
    print(f"  Downloaded {size_kb:,} KB → {tmp.name}")
    return tmp.name


def extract_text(pdf_path: str) -> str:
    if not HAS_PDFPLUMBER:
        return ""
    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                lines.append(page_text.strip())
    text = "\n\n".join(lines)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    print(f"  Extracted {len(text):,} chars of text")
    return text.strip()


def extract_fields(pdf_path: str) -> list:
    if not HAS_PYPDF:
        return []
    reader = PdfReader(pdf_path)
    fields = reader.get_fields()
    result = sorted(fields.keys()) if fields else []
    print(f"  Found {len(result)} AcroForm fields")
    return result


def _yaml_str(value: str) -> str:
    if not value:
        return '""'
    needs_quotes = any(c in value for c in ':#{}[]|>&!\'",')
    if needs_quotes:
        return '"' + value.replace('"', '\\"') + '"'
    return value


def build_markdown(meta: dict, body_text: str, fields: list) -> str:
    scrape_date = datetime.utcnow().strftime("%Y-%m-%d")

    yaml_lines = [
        "---",
        f"form_id: {FORM_ID}",
        f"title: {_yaml_str(meta['title'])}",
        f"description: {_yaml_str(meta['description'])}",
        f"track: {TRACK}",
        f"landing_url: {LANDING_URL}",
        f"pdf_url: {PDF_URL}",
        f"version_date: {VERSION_DATE}",
        f"scrape_date: {scrape_date}",
        'licence: "Open Government Licence v3.0"',
    ]
    if fields:
        yaml_lines.append("form_fields:")
        for f in fields:
            yaml_lines.append(f'  - "{f.replace(chr(34), chr(92)+chr(34))}"')
    else:
        yaml_lines.append("form_fields: []")
    yaml_lines.append("---")

    parts = ["\n".join(yaml_lines), ""]
    parts.append(f"# {meta['title']}")
    parts.append("")
    if meta["description"]:
        parts.append(meta["description"])
        parts.append("")
    if body_text:
        parts.append("## Form Content")
        parts.append("")
        parts.append(body_text)
        parts.append("")
    else:
        parts.append("*No text could be extracted from the PDF.*")
        parts.append("")

    return "\n".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not HAS_PDFPLUMBER:
        print("ERROR: pdfplumber is required. Run: pip3 install pdfplumber")
        sys.exit(1)
    if not HAS_PYPDF:
        print("ERROR: pypdf is required. Run: pip3 install pypdf")
        sys.exit(1)

    os.makedirs("raw/court_forms", exist_ok=True)

    meta = fetch_landing_meta()
    pdf_path = download_pdf()

    try:
        body_text = extract_text(pdf_path)
        fields = extract_fields(pdf_path)
    finally:
        try:
            os.unlink(pdf_path)
        except OSError:
            pass

    md = build_markdown(meta, body_text, fields)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        fh.write(md)

    print(f"\nSaved: {OUTPUT_PATH} ({len(md):,} chars)")
    print(f"  form_id:      {FORM_ID}")
    print(f"  version_date: {VERSION_DATE}")
    print(f"  text chars:   {len(body_text):,}")
    print(f"  form fields:  {len(fields)}")


if __name__ == "__main__":
    main()

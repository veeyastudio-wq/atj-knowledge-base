#!/usr/bin/env python3
"""
HMCTS Court Forms Scraper
Fetches 21 family-law court forms from GOV.UK publication pages,
downloads the primary PDF, extracts body text (pdfplumber) and
form fields (pypdf), and saves structured markdown with YAML
frontmatter to raw/court_forms/{form_id}.md.

Usage:
    cd <repo-root>
    python3 scripts/court_forms_scraper.py

Output:
    raw/court_forms/{form_id}.md
    raw/court_forms/_scrape_log.txt
"""

import os
import re
import sys
import time
import tempfile
import logging
from datetime import datetime
from typing import Optional, List

import requests
from bs4 import BeautifulSoup

# ── Optional PDF libs ───────────────────────────────────────────────────────────
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

# ── Configuration ───────────────────────────────────────────────────────────────

OUTPUT_DIR = "raw/court_forms"
LOG_PATH = "raw/court_forms/_scrape_log.txt"
DELAY_SECONDS = 2
BASE_URL = "https://www.gov.uk/government/publications/"

FORMS = [
    # ── Divorce / dissolution ───────────────────────────────────────────────
    {
        "form_id": "D8",
        "track": "divorce",
        "slug": "form-d8-application-for-a-divorce-dissolution-or-to-apply-for-a-judicial-separation-order",
    },
    {
        "form_id": "D10",
        "track": "divorce",
        "slug": "respond-to-a-divorce-dissolution-or-judicial-separation-application-form-d10",
    },
    {
        "form_id": "D84",
        "track": "divorce",
        "slug": "form-d84-apply-for-a-conditional-order-or-judicial-separation-order",
    },
    {
        "form_id": "D36",
        "track": "divorce",
        "slug": "form-d36-apply-to-make-a-conditional-order-final",
    },
    {
        "form_id": "D11",
        "track": "divorce",
        "slug": "form-d11-application-notice",
    },
    # ── Financial remedy ────────────────────────────────────────────────────
    {
        "form_id": "Form_A",
        "track": "financial_remedy",
        # Renamed on GOV.UK; original slug give-financial-details-... is 404
        "slug": "give-notice-of-your-intention-to-proceed-with-an-application-for-a-financial-order-form-a",
    },
    # Form_E: removed from GOV.UK (replaced by MyHMCTS online service) — skip
    {
        "form_id": "Form_E1",
        "track": "financial_remedy",
        "slug": "give-a-financial-statement-divorce-form-e1",
    },
    # Form_G: removed from GOV.UK (replaced by MyHMCTS online service) — skip
    {
        "form_id": "Form_H",
        "track": "financial_remedy",
        # Renamed on GOV.UK; original slug estimate-of-costs-financial-remedy-form-h is 404
        "slug": "estimate-of-costs-for-a-financial-remedy-hearing-form-h",
    },
    {
        "form_id": "Form_H1",
        "track": "financial_remedy",
        "slug": "give-a-statement-of-costs-for-a-financial-remedy-divorce-form-h1",
    },
    # ── Children Act ────────────────────────────────────────────────────────
    {
        "form_id": "C100",
        "track": "children",
        "slug": "form-c100-application-under-the-children-act-1989-for-a-child-arrangements-prohibited-steps-specific-issue-section-8-order-or-to-vary-or-discharge",
    },
    {
        "form_id": "C1",
        "track": "children",
        "slug": "form-c1-application-for-an-order",
    },
    {
        "form_id": "C1A",
        "track": "children",
        "slug": "form-c1a-allegations-of-harm-and-domestic-violence-supplemental-information-form",
    },
    {
        "form_id": "C2",
        "track": "children",
        "slug": "form-c2-application-for-permission-to-start-proceedings-for-an-order-or-directions-in-existing-proceedings-to-be-joined-as-or-cease-to-be-a-part",
    },
    {
        "form_id": "C7",
        "track": "children",
        "slug": "form-c7-acknowledgment",
    },
    {
        "form_id": "C8",
        "track": "children",
        "slug": "form-c8-confidential-contact-details-family-procedure-rules-2010-rule-291",
    },
    # ── Cross-cutting ───────────────────────────────────────────────────────
    {
        "form_id": "FM1",
        "track": "cross_cutting",
        "slug": "give-information-for-a-family-mediation-assessment-form-fm1",
    },
    {
        "form_id": "FP2",
        "track": "cross_cutting",
        "slug": "form-fp2-application-notice-part-18-of-the-family-procedure-rules-2010",
    },
    {
        "form_id": "FP6",
        "track": "cross_cutting",
        "slug": "form-fp6-certificate-of-service",
    },
    {
        "form_id": "D89",
        "track": "cross_cutting",
        "slug": "form-d89-request-personal-service-of-papers-by-a-court-bailiff",
    },
]

# ── Logging ─────────────────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── HTTP session ─────────────────────────────────────────────────────────────────

session = requests.Session()
session.headers.update({
    "User-Agent": "ATJ-KnowledgeBase-Builder/1.0 (research; contact: atj@veeya.co.uk)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

# ── Landing page parsing ─────────────────────────────────────────────────────────

def fetch_landing(slug: str) -> Optional[str]:
    url = BASE_URL + slug
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200:
            log.info(f"  ✓ landing page fetched ({len(resp.text):,} chars)")
            return resp.text
        log.warning(f"  ✗ HTTP {resp.status_code}: {url}")
        return None
    except Exception as e:
        log.error(f"  ✗ error fetching landing: {e}")
        return None


def parse_landing(html: str, slug: str) -> dict:
    """Extract title, description, version_date, and primary PDF URL."""
    soup = BeautifulSoup(html, "html.parser")

    # Title from H1
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # Description from lead paragraph
    lead = soup.select_one("p.gem-c-lead-paragraph")
    description = lead.get_text(strip=True) if lead else ""

    # Version date: the first <time datetime="..."> tag (= "last updated")
    first_time = soup.find("time", attrs={"datetime": True})
    version_date = ""
    if first_time:
        dt_str = first_time.get("datetime", "")
        # Parse ISO datetime and keep just the date part
        try:
            version_date = dt_str[:10]  # "2026-04-29T11:15:10Z" → "2026-04-29"
        except Exception:
            version_date = dt_str

    # Primary PDF URL
    pdf_url = find_primary_pdf(soup)

    return {
        "title": title,
        "description": description,
        "version_date": version_date,
        "pdf_url": pdf_url,
        "landing_url": BASE_URL + slug,
    }


def find_primary_pdf(soup: BeautifulSoup) -> str:
    """
    Return the URL of the primary English PDF from the page.
    Skips: Welsh/Cymraeg variants, large-print versions.
    Takes the first qualifying unique PDF link.
    """
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" not in href.lower():
            continue
        if "assets.publishing" not in href:
            continue
        if href in seen:
            continue
        seen.add(href)

        # Skip Welsh variants (filename markers)
        fn = href.lower()
        if any(marker in fn for marker in ["cymraeg", "welsh", "_cy_", "_cy.", "cymru"]):
            continue

        # Skip large-print versions (link text)
        link_text = a.get_text(strip=True).lower()
        if "large print" in link_text or "large-print" in link_text:
            continue

        return href

    return ""

# ── PDF download ─────────────────────────────────────────────────────────────────

def download_pdf(url: str) -> Optional[str]:
    """Download a PDF to a temp file and return its path, or None on failure."""
    if not url:
        return None
    try:
        resp = session.get(url, timeout=60, stream=True)
        if resp.status_code != 200:
            log.warning(f"  ✗ PDF download HTTP {resp.status_code}: {url}")
            return None
        suffix = ".pdf"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        for chunk in resp.iter_content(chunk_size=65536):
            tmp.write(chunk)
        tmp.close()
        size_kb = os.path.getsize(tmp.name) // 1024
        log.info(f"  ✓ PDF downloaded ({size_kb:,} KB)")
        return tmp.name
    except Exception as e:
        log.error(f"  ✗ PDF download error: {e}")
        return None

# ── PDF text extraction ──────────────────────────────────────────────────────────

def extract_text(pdf_path: str) -> str:
    """Extract plain text from PDF using pdfplumber."""
    if not HAS_PDFPLUMBER or not pdf_path:
        return ""
    try:
        lines = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    lines.append(page_text.strip())
        text = "\n\n".join(lines)
        # Collapse excessive whitespace
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        return text.strip()
    except Exception as e:
        log.warning(f"  ✗ pdfplumber extraction error: {e}")
        return ""


def extract_fields(pdf_path: str) -> List[str]:
    """Extract AcroForm field names from PDF using pypdf."""
    if not HAS_PYPDF or not pdf_path:
        return []
    try:
        reader = PdfReader(pdf_path)
        fields = reader.get_fields()
        if not fields:
            return []
        # Field names may be hierarchical (e.g. "form1[0].address[0].city[0]")
        # Keep them as-is for faithfulness
        return sorted(fields.keys())
    except Exception as e:
        log.warning(f"  ✗ pypdf field extraction error: {e}")
        return []

# ── Markdown generation ──────────────────────────────────────────────────────────

def _yaml_str(value: str) -> str:
    """Wrap a string in YAML double-quotes if it contains special chars."""
    if not value:
        return '""'
    needs_quotes = any(c in value for c in ':#{}[]|>&!\'",')
    if needs_quotes:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def build_markdown(form: dict, meta: dict, body_text: str, fields: List[str]) -> str:
    scrape_date = datetime.utcnow().strftime("%Y-%m-%d")

    # YAML frontmatter
    yaml_lines = [
        "---",
        f"form_id: {form['form_id']}",
        f"title: {_yaml_str(meta['title'])}",
        f"description: {_yaml_str(meta['description'])}",
        f"track: {form['track']}",
        f"landing_url: {meta['landing_url']}",
        f"pdf_url: {meta['pdf_url']}",
        f"version_date: {_yaml_str(meta['version_date'])}",
        f"scrape_date: {scrape_date}",
        'licence: "Open Government Licence v3.0"',
    ]
    if fields:
        yaml_lines.append("form_fields:")
        for f in fields:
            safe = f.replace('"', '\\"')
            yaml_lines.append(f'  - "{safe}"')
    else:
        yaml_lines.append("form_fields: []")
    yaml_lines.append("---")

    parts = ["\n".join(yaml_lines), ""]

    # Document header
    parts.append(f"# {meta['title']}" if meta['title'] else f"# Form {form['form_id']}")
    parts.append("")

    if meta['description']:
        parts.append(meta['description'])
        parts.append("")

    # Extracted body text
    if body_text:
        parts.append("## Form Content")
        parts.append("")
        parts.append(body_text)
        parts.append("")
    else:
        parts.append("*No text could be extracted from the PDF.*")
        parts.append("")

    return "\n".join(parts)

# ── Main ─────────────────────────────────────────────────────────────────────────

def process_form(form: dict) -> bool:
    log.info(f"\n[{form['form_id']}]  slug: {form['slug'][:60]}")

    # 1. Fetch landing page
    html = fetch_landing(form["slug"])
    if not html:
        return False

    # 2. Parse metadata
    meta = parse_landing(html, form["slug"])
    log.info(f"  title: {meta['title'][:70]}")
    log.info(f"  pdf:   {meta['pdf_url'][-70:] if meta['pdf_url'] else '(none found)'}")

    # 3. Download PDF
    time.sleep(DELAY_SECONDS)
    pdf_path = download_pdf(meta["pdf_url"])

    # 4. Extract text and fields
    body_text = extract_text(pdf_path) if pdf_path else ""
    fields = extract_fields(pdf_path) if pdf_path else []
    if body_text:
        log.info(f"  text: {len(body_text):,} chars extracted")
    if fields:
        log.info(f"  fields: {len(fields)} AcroForm fields")

    # 5. Clean up temp file
    if pdf_path and os.path.exists(pdf_path):
        try:
            os.unlink(pdf_path)
        except OSError:
            pass

    # 6. Build and save markdown
    md = build_markdown(form, meta, body_text, fields)
    out_path = os.path.join(OUTPUT_DIR, f"{form['form_id']}.md")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    log.info(f"  → saved: {form['form_id']}.md ({len(md):,} chars)")
    return True


def main():
    log.info("=" * 60)
    log.info("HMCTS Court Forms Scraper — starting")
    log.info(f"pdfplumber: {'available' if HAS_PDFPLUMBER else 'NOT installed'}")
    log.info(f"pypdf:      {'available' if HAS_PYPDF else 'NOT installed'}")
    log.info(f"Forms to scrape: {len(FORMS)}")
    log.info("=" * 60)

    if not HAS_PDFPLUMBER:
        log.error("pdfplumber is required. Run: pip3 install pdfplumber")
        sys.exit(1)
    if not HAS_PYPDF:
        log.error("pypdf is required. Run: pip3 install pypdf")
        sys.exit(1)

    success, failed = 0, []

    for form in FORMS:
        ok = process_form(form)
        if ok:
            success += 1
        else:
            failed.append(form["form_id"])
        time.sleep(DELAY_SECONDS)

    log.info("\n" + "=" * 60)
    log.info(f"Complete. {success}/{len(FORMS)} forms saved, {len(failed)} failed.")
    if failed:
        log.warning(f"Failed: {', '.join(failed)}")
    log.info(f"Note: Form_E and Form_G are excluded — these have been replaced")
    log.info(f"      by the MyHMCTS online service and are no longer available")
    log.info(f"      as downloadable PDFs on GOV.UK.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
ATJ Knowledge Base — Category 3 Scraper
GOV.UK procedural guidance, judiciary PDF guides, Advicenow guides.

RAG design: each logical section (H2 boundary) saved as its own markdown file.
Frontmatter carries parent document, section title, URL, and provenance.

Run from repo root:
    python scripts/guidance_scraper.py

Output: raw/guidance/
"""

import logging
import os
import re
import sys
import tempfile
import time
from datetime import date
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUTPUT_DIR = "raw/guidance"
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

HTML_SOURCES = [
    (
        "govuk_divorce",
        "Get a divorce: GOV.UK guide",
        "https://www.gov.uk/divorce",
        "govuk",
    ),
    (
        "govuk_financial_remedy",
        "Money and property when you separate or divorce: GOV.UK guide",
        "https://www.gov.uk/money-property-when-relationship-ends",
        "govuk",
    ),
    (
        "govuk_child_arrangements",
        "Looking after children if you divorce or separate: GOV.UK guide",
        "https://www.gov.uk/looking-after-children-divorce",
        "govuk",
    ),
    (
        "advicenow_financial_order",
        "How to apply for a financial order without a lawyer: Advicenow",
        "https://www.advicenow.org.uk/guides/how-apply-financial-order-without-lawyer",
        "advicenow",
    ),
    (
        "advicenow_divorce",
        "How to get a divorce without a lawyer: Advicenow",
        "https://www.advicenow.org.uk/get-help/family-and-children/divorce-and-separation/get-divorce-without-lawyer",
        "advicenow",
    ),
]

PDF_SOURCES = [
    (
        "court_bundles_guide_2026",
        "Guide for Litigants in Person: Preparing Court Bundles (March 2026)",
        "https://www.judiciary.uk/wp-content/uploads/2026/03/020326-Preparing-Court-Bundles-for-Family-Proceedings-Guide-for-Litigants-in-Person.pdf",
        "https://www.judiciary.uk/publications/family-court-practice-directions/",
    ),
    (
        "financial_remedies_guide_2026",
        "Financial Remedies Guide 2026",
        "https://www.judiciary.uk/wp-content/uploads/2026/03/FRC-Guide-Final-Clean.pdf",
        "https://www.judiciary.uk/publications/financial-remedies-court/",
    ),
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    logger = logging.getLogger("guidance_scraper")
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
# HTML section extraction
# ---------------------------------------------------------------------------

def _extract_govuk_sections(soup: BeautifulSoup, source_url: str) -> List[Tuple[str, str]]:
    main = soup.find("main") or soup.find("article") or soup.body
    if not main:
        return []

    sections = []
    current_heading = "Overview"
    current_blocks: List[str] = []

    def _flush():
        body = "\n\n".join(current_blocks).strip()
        if body:
            sections.append((current_heading, body))

    for el in main.descendants:
        if not isinstance(el, Tag):
            continue
        if el.name == "h2":
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
            items = []
            for li in el.find_all("li", recursive=False):
                items.append(f"- {li.get_text(separator=' ', strip=True)}")
            if items:
                current_blocks.append("\n".join(items))

    _flush()
    return sections


def _extract_advicenow_sections(soup: BeautifulSoup, source_url: str) -> List[Tuple[str, str]]:
    main = (
        soup.find("article")
        or soup.find("div", class_=re.compile(r"(content|main|guide)", re.I))
        or soup.body
    )
    if not main:
        return []

    sections = []
    current_heading = "Overview"
    current_blocks: List[str] = []

    def _flush():
        body = "\n\n".join(current_blocks).strip()
        if body:
            sections.append((current_heading, body))

    for el in main.descendants:
        if not isinstance(el, Tag):
            continue
        if el.name == "h2":
            _flush()
            current_heading = el.get_text(separator=" ", strip=True)
            current_blocks = []
        elif el.name == "h3":
            current_blocks.append(f"### {el.get_text(separator=' ', strip=True)}")
        elif el.name == "p":
            text = el.get_text(separator=" ", strip=True)
            if text:
                current_blocks.append(text)
        elif el.name in ("ul", "ol"):
            items = []
            for li in el.find_all("li", recursive=False):
                items.append(f"- {li.get_text(separator=' ', strip=True)}")
            if items:
                current_blocks.append("\n".join(items))

    _flush()
    return sections

# ---------------------------------------------------------------------------
# HTML scraping
# ---------------------------------------------------------------------------

def scrape_html_source(
    session: requests.Session,
    slug: str,
    label: str,
    url: str,
    site_type: str,
) -> int:
    log.info(f"Fetching HTML: {url}")
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Failed to fetch {url}: {e}")
        return 0

    time.sleep(DELAY_SECONDS)

    soup = BeautifulSoup(resp.text, "html.parser")

    if site_type == "govuk":
        sections = _extract_govuk_sections(soup, url)
    elif site_type == "advicenow":
        sections = _extract_advicenow_sections(soup, url)
    else:
        sections = _extract_govuk_sections(soup, url)

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
            "url": url,
            "scrape_date": TODAY,
            "licence": "Open Government Licence v3.0",
            "content_type": "guidance",
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
# PDF scraping
# ---------------------------------------------------------------------------

def _extract_pdf_sections(pdf_path: str) -> List[Tuple[str, str]]:
    raw_text = ""

    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
                raw_text = "\n\n".join(pages)
        except Exception as e:
            log.warning(f"pdfplumber failed: {e} — trying pypdf")

    if not raw_text and HAS_PYPDF:
        try:
            reader = pypdf.PdfReader(pdf_path)
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            raw_text = "\n\n".join(pages)
        except Exception as e:
            log.error(f"pypdf also failed: {e}")
            return []

    if not raw_text:
        return []

    lines = raw_text.split("\n")
    sections: List[Tuple[str, str]] = []
    current_heading = "Introduction"
    current_lines: List[str] = []

    heading_re = re.compile(
        r"^(?:\d+[\.\s]+)?[A-Z][A-Za-z0-9 \-:,()]{3,70}$"
    )

    def _is_heading(line: str) -> bool:
        line = line.strip()
        if not line or len(line) > 80:
            return False
        if line.endswith((".", ",", ";", ":", ")", "?")):
            return False
        return bool(heading_re.match(line))

    def _flush():
        body = "\n".join(current_lines).strip()
        if body:
            sections.append((current_heading, body))

    for line in lines:
        stripped = line.strip()
        if _is_heading(stripped) and stripped != current_heading:
            _flush()
            current_heading = stripped
            current_lines = []
        else:
            current_lines.append(line)

    _flush()
    return sections


def scrape_pdf_source(
    session: requests.Session,
    slug: str,
    label: str,
    primary_url: str,
    fallback_page: str,
) -> int:
    def _try_download(url: str) -> Optional[str]:
        log.info(f"Downloading PDF: {url}")
        try:
            resp = session.get(url, timeout=60, stream=True)
            resp.raise_for_status()
            time.sleep(DELAY_SECONDS)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
            tmp.flush()
            tmp.close()
            return tmp.name
        except requests.RequestException as e:
            log.warning(f"Could not fetch {url}: {e}")
            return None

    tmp_path = _try_download(primary_url)

    if not tmp_path:
        log.info(f"Primary URL failed — searching fallback page: {fallback_page}")
        try:
            resp = session.get(fallback_page, timeout=30)
            resp.raise_for_status()
            time.sleep(DELAY_SECONDS)
            soup = BeautifulSoup(resp.text, "html.parser")
            pdf_links = [
                a["href"] for a in soup.find_all("a", href=True)
                if a["href"].endswith(".pdf") and slug.split("_")[0] in a["href"].lower()
            ]
            if pdf_links:
                resolved = pdf_links[0]
                if resolved.startswith("/"):
                    resolved = "https://www.judiciary.uk" + resolved
                tmp_path = _try_download(resolved)
            else:
                log.error(f"No PDF found on fallback page {fallback_page}")
        except requests.RequestException as e:
            log.error(f"Fallback page also failed: {e}")

    if not tmp_path:
        log.error(f"Skipping {slug} — could not retrieve PDF from any source")
        return 0

    try:
        sections = _extract_pdf_sections(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not sections:
        log.warning(f"No sections extracted from PDF for {slug}")
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
            "url": primary_url,
            "scrape_date": TODAY,
            "licence": "Open Government Licence v3.0",
            "content_type": "guidance",
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
    if not HAS_PDFPLUMBER and not HAS_PYPDF:
        log.error("Neither pdfplumber nor pypdf is installed. Run: pip install pdfplumber pypdf")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session = _make_session()
    total = 0

    log.info("=== Category 3 scraper starting ===")

    for slug, label, url, site_type in HTML_SOURCES:
        count = scrape_html_source(session, slug, label, url, site_type)
        log.info(f"{slug}: {count} section files saved")
        total += count

    for slug, label, primary_url, fallback_page in PDF_SOURCES:
        count = scrape_pdf_source(session, slug, label, primary_url, fallback_page)
        log.info(f"{slug}: {count} section files saved")
        total += count

    log.info(f"=== Done. {total} files saved to {OUTPUT_DIR}/ ===")


if __name__ == "__main__":
    main()

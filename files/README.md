# FPR 2010 Scraper

Fetches all Parts of the Family Procedure Rules 2010 (revised/current version)
from legislation.gov.uk and saves each as a structured markdown file for RAG ingestion.

## What it produces

One markdown file per Part (e.g. `FPR_Part_1.md`, `FPR_Part_9.md`)
plus `FPR_Glossary.md` — saved to `./fpr_output/`.

Each file has a YAML frontmatter header with:
- source, part number, title, canonical URL
- version (Latest available / Revised)
- scrape date
- licence

## Requirements

Python 3.10+

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python3 fpr_scraper.py
```

The scraper pauses 2 seconds between requests to be polite to legislation.gov.uk.
Full run will take approximately 90 seconds.

Output is written to `./fpr_output/`.
A scrape log is saved to `./fpr_output/_scrape_log.txt`.

## Re-running

The FPR is updated multiple times per year. Re-run the scraper periodically to
pick up amendments. Check `_scrape_log.txt` for any Parts that failed to fetch.

## Licence

All content fetched from legislation.gov.uk is © Crown copyright and
available under the Open Government Licence v3.0.
https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3

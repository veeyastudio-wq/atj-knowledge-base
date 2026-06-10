# ATJ Knowledge Base

Source documents for the Access to Justice RAG knowledge base. All raw content is scraped from official sources, structured as markdown with YAML frontmatter, and organised for chunking and embedding.

## Repository structure

```
atj-knowledge-base/
├── raw/                          # Layer 1: official source documents
│   ├── legislation/
│   │   └── fpr_2010/             # Family Procedure Rules 2010 (38 files)
│   ├── practice_directions/      # FPR Practice Directions (114 files)
│   ├── court_forms/              # Court forms — to be populated
│   ├── guidance/                 # Judiciary/HMCTS guidance — to be populated
│   └── case_law/                 # Key case law — to be populated
├── processed/                    # Layer 2: enriched/chunked content — to be populated
├── scripts/                      # Scraper scripts
│   ├── fpr_scraper.py            # Fetches all Parts of FPR 2010 from legislation.gov.uk
│   ├── pd_scraper.py             # Fetches all active Practice Directions from justice.gov.uk
│   └── requirements.txt
└── atj_knowledge_base_sources.md # Source map and discovery notes
```

## Current coverage

| Folder | Source | Files | Last scraped |
|---|---|---|---|
| `raw/legislation/fpr_2010/` | legislation.gov.uk | 38 | 2026-06-10 |
| `raw/practice_directions/` | justice.gov.uk | 114 | 2026-06-10 |

## File format

Every file in `raw/` has a YAML frontmatter block followed by markdown content:

```yaml
---
source: ...
title: ...
url: ...
status: ...
scraped: YYYY-MM-DD
licence: Open Government Licence v3.0
---
```

## Running the scrapers

```bash
cd scripts
pip install -r requirements.txt

python3 fpr_scraper.py   # outputs to ../raw/legislation/fpr_2010/
python3 pd_scraper.py    # outputs to ../raw/practice_directions/
```

Both scrapers pause 2 seconds between requests. The FPR scraper takes ~90 seconds for a full run; the PD scraper takes ~4 minutes.

Re-run periodically to pick up amendments — the FPR and Practice Directions are updated multiple times per year.

## Licence

All content fetched from legislation.gov.uk and justice.gov.uk is © Crown copyright, available under the Open Government Licence v3.0.
https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3

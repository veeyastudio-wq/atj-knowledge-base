# ATJ Knowledge Base — Technical Environment Inventory

*Generated 2026-06-15. All entries verified by reading files or running commands.*

---

## Machine and OS

| Field | Value |
|---|---|
| OS | macOS 15.1.1 (Sequoia) |
| Kernel | Darwin 24.1.0 |
| Architecture | arm64 (Apple Silicon) |
| Build | 24B91 |

---

## Python environment

| Field | Value |
|---|---|
| Version | Python 3.9.6 |
| Executable | `/usr/bin/python3` |
| Prefix | `/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9` |
| Virtualenv | None — packages installed to the macOS Command Line Tools system Python |
| Install method | `pip3 install` globally |

**Installed packages (all relevant to this project, from `pip3 list`):**

| Package | Installed version | Role |
|---|---|---|
| anthropic | 0.109.1 | Claude API client (triage, golden set generation) |
| beautifulsoup4 | 4.14.3 | HTML parsing in scrapers |
| langchain-core | 0.3.86 | Dependency of langchain-text-splitters |
| langchain-text-splitters | 0.3.11 | RecursiveCharacterTextSplitter used in chunk_kb.py |
| numpy | 2.0.2 | Numerical operations |
| openai | 2.41.1 | Embeddings via text-embedding-3-small |
| pdfplumber | 0.11.8 | PDF text extraction in scrapers |
| pgvector | 0.4.2 | pgvector Python client |
| psycopg2-binary | 2.9.12 | PostgreSQL adapter |
| pypdf | 6.13.1 | PDF form field extraction in scrapers |
| pypdfium2 | 5.9.0 | PDF rendering (pdfplumber dependency) |
| python-docx | 1.2.0 | .docx parsing in standard_orders_scraper.py |
| python-dotenv | 1.2.1 | `.env` file loading |
| requests | 2.32.5 | HTTP in all scrapers |
| requests-toolbelt | 1.0.0 | requests utility (dependency) |
| tiktoken | 0.13.0 | Token counting for chunking (cl100k_base) |

All dependencies for all scripts — scrapers, chunking, embedding, retrieval, triage, and evaluation — are listed in `scripts/requirements.txt`. Install with `pip3 install -r scripts/requirements.txt` from the repo root.

---

## Repository

| Field | Value |
|---|---|
| Name | atj-knowledge-base |
| Remote | `git@github.com:veeyastudio-wq/atj-knowledge-base.git` |
| Branch | `main` |
| Git user | Vilam |

---

## Directory structure

```
atj-knowledge-base/
├── .env                        # API keys — gitignored, never committed
├── .gitignore                  # Excludes .DS_Store and .env
├── .github/
│   └── workflows/
│       └── kb_update.yml       # GitHub Actions monthly update pipeline
├── README.md                   # Project overview
├── atj_knowledge_base_sources.md  # Source list and scraping provenance notes
├── data/
│   ├── delta_report.json       # Output of detect_changes.py — changed/new/deleted files
│   ├── file_registry.json      # SHA-256 hashes of all raw/*.md files; updated after eval gate
│   └── triage_report.json      # Output of triage_changes.py — SAFE/HOLD per file
├── docs/
│   ├── environment.md          # This file
│   └── layer2_entry_format_spec.md  # Canonical spec for all Layer 2 entry types
├── eval/
│   ├── README.md               # How to run evaluation
│   ├── golden_set.json         # 69 hand-curated query→expected_chunk pairs
│   ├── golden_set_summary.txt  # Summary from generate_golden_set.py run
│   ├── retrieval_report.txt    # Human-readable pass/fail from evaluate_retrieval.py
│   └── retrieval_results.json  # Full per-query results from evaluate_retrieval.py
├── processed/                  # Chunked JSON files output by chunk_kb.py
│   ├── court_forms/
│   ├── guidance/
│   ├── layer2/
│   ├── legislation/
│   ├── practice_directions/
│   ├── standard_orders/
│   └── supporting_context/
├── raw/                        # Source markdown files — the knowledge base corpus
│   ├── case_law/               # Case law source files
│   ├── court_forms/            # Scraped court forms (PDF text + form fields)
│   ├── guidance/               # GOV.UK guidance, judiciary guides, Advicenow
│   ├── layer2/                 # Handwritten Layer 2 explanatory entries
│   │   ├── _discovery_gaps.md
│   │   ├── case_law_summaries/
│   │   ├── document_explanations/
│   │   ├── legal_principles/
│   │   ├── process_explanations/
│   │   └── terminology/
│   ├── legislation/            # Scraped statute sections and FPR parts
│   │   ├── children_act_1989/
│   │   ├── family_law_act_1996/
│   │   ├── fpr_2010/
│   │   └── matrimonial_causes_act_1973/
│   ├── practice_directions/    # Scraped FPR Practice Directions
│   ├── standard_orders/        # Standard Family Orders Vol 1 & 2 (.docx → .md)
│   └── supporting_context/     # CAFCASS, FMC, GOV.UK legal aid pages
└── scripts/                    # All Python scripts (see Scripts section)
    └── requirements.txt        # Scraper dependencies only
```

---

## Scripts

All scripts live in `scripts/` and are run from the repo root with `python3 scripts/<name>.py` unless noted.

| Script | Description |
|---|---|
| `chunk_kb.py` | Reads all `raw/**/*.md` files, applies RecursiveCharacterTextSplitter (512 tokens, 50 overlap, cl100k_base), and writes chunk JSON files to `processed/`; exposes `chunk_file()` as an importable function |
| `court_forms_scraper.py` | Scrapes 21 family law court forms from GOV.UK publication pages, downloads each primary PDF, extracts body text (pdfplumber) and AcroForm fields (pypdf), saves to `raw/court_forms/` |
| `detect_changes.py` | Computes SHA-256 hashes of all `raw/*.md` files, compares against `data/file_registry.json`, outputs `data/delta_report.json` listing changed/new/deleted files |
| `embed_kb.py` | Reads chunk JSON files from `processed/`, calls OpenAI text-embedding-3-small to generate 1536-dimension vectors, loads into pgvector via psycopg2; exposes `embed_chunks()` as an importable function |
| `evaluate_retrieval.py` | Runs all 69 golden set queries through hybrid retrieval, checks whether the expected chunk appears in top-10 results, outputs context recall score and pass/fail report to `eval/` |
| `fpr_scraper.py` | Scrapes all parts of the Family Procedure Rules 2010 (revised) from legislation.gov.uk, saves one file per part to `raw/legislation/fpr_2010/` |
| `generate_golden_set.py` | Samples chunks from pgvector, calls Claude to generate realistic unrepresented-litigant questions for each chunk, outputs `eval/golden_set.json` and `eval/golden_set_summary.txt` |
| `guidance_scraper.py` | Scrapes GOV.UK procedural guidance, judiciary PDF guides, and Advicenow guides; splits at H2 boundaries into individual section files; saves to `raw/guidance/` |
| `pd_scraper.py` | Scrapes all active (non-expired, non-revoked) FPR Practice Directions from justice.gov.uk, saves one file per PD to `raw/practice_directions/` |
| `retrieve.py` | Hybrid retrieval combining dense (HNSW cosine, top 50 candidates) and sparse (BM25 via GIN full-text, top 20 candidates) signals using RRF (k=60), returning top 10 results per layer; usable standalone or importable |
| `scrape_fl401.py` | Standalone one-off scraper for the FL401 form PDF from GOV.UK; saves to `raw/court_forms/FL401.md` using the same frontmatter pattern as `court_forms_scraper.py` |
| `setup_db.py` | Creates the pgvector extension and `chunks` table in PostgreSQL; run once on a fresh database |
| `standard_orders_scraper.py` | Downloads Standard Family Orders Volume 1 (Financial) and Volume 2 (Children) ZIP archives from judiciary.uk, extracts and parses each .docx using python-docx, saves one .md per order to `raw/standard_orders/` |
| `statute_scraper.py` | Scrapes specific sections from the Children Act 1989, Matrimonial Causes Act 1973, and Family Law Act 1996 from legislation.gov.uk; saves to `raw/legislation/` |
| `supporting_context_scraper.py` | Scrapes CAFCASS, Family Mediation Council, and GOV.UK legal aid pages; splits at H2 boundaries; saves to `raw/supporting_context/` |
| `triage_changes.py` | Reads `data/delta_report.json`, sends each changed/new file to the Claude API for legal materiality assessment, classifies each as SAFE (auto-promote) or HOLD (needs human review), outputs `data/triage_report.json` |
| `update_kb.py` | Orchestrates the full KB update pipeline: detect → triage → re-chunk/re-embed SAFE files → remove deleted from pgvector → eval gate (must pass 75%) → update `data/file_registry.json` |

---

## Dependencies

All dependencies are in `scripts/requirements.txt`. Install from repo root:

```bash
pip3 install -r scripts/requirements.txt
```

| Package | Min version | Role |
|---|---|---|
| requests | 2.31.0 | HTTP in all scrapers |
| beautifulsoup4 | 4.12.0 | HTML parsing in scrapers |
| pdfplumber | 0.10.0 | PDF text extraction |
| pypdf | 3.0.0 | PDF AcroForm field extraction |
| python-docx | 1.1.0 | .docx parsing (standard orders scraper) |
| langchain-text-splitters | 0.3.0 | RecursiveCharacterTextSplitter for chunking |
| tiktoken | 0.13.0 | Token counting (cl100k_base) |
| PyYAML | 6.0 | YAML frontmatter parsing in chunk_kb.py |
| openai | 2.41.0 | text-embedding-3-small embeddings |
| psycopg2-binary | 2.9.0 | PostgreSQL adapter |
| pgvector | 0.4.0 | pgvector Python client |
| numpy | 2.0.0 | Numerical operations |
| anthropic | 0.109.0 | Claude API (triage + golden set generation) |
| python-dotenv | 1.0.0 | `.env` file loading |

---

## Docker containers

| Field | Value |
|---|---|
| Container name | `atj-db` |
| Image | `pgvector/pgvector:pg16` |
| Status | Running |
| Port mapping | `0.0.0.0:5432->5432/tcp` |
| Database name | `atj` |
| DB user | `postgres` |
| DB password | `postgres` |
| Start command | `docker start atj-db` |
| First-time setup | `docker run -d --name atj-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=atj -p 5432:5432 pgvector/pgvector:pg16` then `python3 scripts/setup_db.py` |

**Retrieval configuration (in retrieve.py):**

| Parameter | Value |
|---|---|
| Embedding model | `text-embedding-3-small` |
| Vector dimensions | 1536 |
| Index type | HNSW (vector_cosine_ops) |
| Sparse index | GIN on `to_tsvector('english', text)` |
| RRF k | 60 |
| Top-K returned per layer | 10 |
| Dense candidates before fusion | 50 |
| Sparse candidates before fusion | 20 |

---

## Environment variables

Stored in `.env` at repo root. Loaded via `python-dotenv`. Gitignored — never committed.

| Key | Used by | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | `embed_kb.py`, `retrieve.py`, `generate_golden_set.py` | Authenticates calls to the OpenAI Embeddings API (text-embedding-3-small) |
| `ANTHROPIC_API_KEY` | `triage_changes.py`, `generate_golden_set.py` | Authenticates calls to the Claude API for materiality triage and golden set generation |

In GitHub Actions, both keys are stored as repository secrets (`secrets.OPENAI_API_KEY`, `secrets.ANTHROPIC_API_KEY`) and injected at runtime. They do not exist in any committed file.

---

## GitHub Actions

**Workflow: `kb_update.yml` — "KB monthly update"**

| Field | Value |
|---|---|
| Trigger | `schedule: cron '0 3 1 * *'` (1st of each month, 03:00 UTC) + `workflow_dispatch` |
| Runner | `ubuntu-latest` |
| Python version | 3.9 |
| Service container | `pgvector/pgvector:pg16` on port 5432 |

Steps:
1. Checkout repository (`actions/checkout@v4.2.2`)
2. Set up Python 3.9 (`actions/setup-python@v5.6.0`)
3. Install dependencies from `scripts/requirements.txt`
4. Run `python scripts/update_kb.py` with `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` injected from secrets
5. Commit updated `data/file_registry.json`, `data/triage_report.json`, `data/delta_report.json` back to `main` if changed

The pipeline will not update `file_registry.json` if the evaluation gate fails (context recall below 75%). A failed pipeline does not produce a commit.

**Note:** `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` is set at workflow level to maintain compatibility with Node.js 24 in the GitHub Actions runner environment.

---

## Working method

*To be completed manually by Vilam.*

<!-- Suggested headings:
- How Claude chat (claude.ai) is used vs Claude Code (this CLI)
- How new Layer 2 entries are written and reviewed before commit
- How the monthly update pipeline is monitored
- How HOLD triage decisions are reviewed and resolved
- How the golden set is maintained and expanded
-->

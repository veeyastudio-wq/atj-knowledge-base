"""
generate_golden_set.py

Samples chunks from the pgvector KB and uses Claude to generate realistic
user questions for each chunk. Outputs eval/golden_set.json as ground truth
for retrieval evaluation.

Usage:
    python scripts/generate_golden_set.py

Output:
    eval/golden_set.json
    eval/golden_set_summary.txt

Requires:
    ANTHROPIC_API_KEY and DATABASE_URL (or defaults) in .env at repo root
"""

import os
import json
import random
import time
import logging
from pathlib import Path
from datetime import datetime

import psycopg2
import anthropic
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "atj")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# How many chunks to sample per layer. Adjust to hit your target set size.
# layer1 samples * ~1 question each + layer2 samples * ~2 questions each ≈ total pairs
LAYER1_SAMPLE_SIZE = 35
LAYER2_SAMPLE_SIZE = 20

TARGET_PAIRS = 100          # aim high; the evaluator uses whatever is generated
MIN_CHUNK_TOKENS = 80       # skip very short chunks unlikely to answer anything

OUTPUT_DIR = Path("eval")
OUTPUT_FILE = OUTPUT_DIR / "golden_set.json"
SUMMARY_FILE = OUTPUT_DIR / "golden_set_summary.txt"

CLAUDE_MODEL = "claude-sonnet-4-6"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are helping evaluate a retrieval system for an AI product that supports
people going through the UK family court system without legal representation.

Your job is to generate realistic questions that a scared, non-legally-trained person
might type or say when using this product. Questions should:

- Sound like a real person asking for help, not a lawyer
- Be specific enough that this chunk would genuinely be the right answer
- Cover a range of tones: confused, anxious, practical, angry
- Avoid legal jargon in the question itself unless the person would naturally use it

Return ONLY a JSON array of question strings. No preamble, no explanation."""

def build_user_prompt(chunk: dict, n_questions: int) -> str:
    return f"""Here is a chunk of content from a UK family court knowledge base.

Chunk ID: {chunk['chunk_id']}
Layer: {chunk['layer']}
Source: {chunk['source_file']}
Content:
\"\"\"
{chunk['text']}
\"\"\"

Generate {n_questions} realistic question(s) that a litigant in person might ask,
where this chunk would be the correct or highly relevant answer.

Return as a JSON array of strings, e.g.:
["What does a without prejudice offer mean?", "Can I show the judge this letter?"]"""


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD
    )


def sample_chunks(conn, layer: str, n: int, min_tokens: int) -> list[dict]:
    """Return n randomly sampled chunks from the given layer."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT chunk_id, source_file, layer, chunk_index, token_count, text, metadata
            FROM chunks
            WHERE layer = %s
              AND token_count >= %s
            ORDER BY RANDOM()
            LIMIT %s
            """,
            (layer, min_tokens, n),
        )
        rows = cur.fetchall()
    cols = ["chunk_id", "source_file", "layer", "chunk_index", "token_count", "text", "metadata"]
    return [dict(zip(cols, row)) for row in rows]


# ---------------------------------------------------------------------------
# Claude helper
# ---------------------------------------------------------------------------

def generate_questions(client: anthropic.Anthropic, chunk: dict, n: int) -> list[str]:
    """Call Claude to generate n questions for this chunk. Returns list of strings."""
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_prompt(chunk, n)}],
            )
            raw = response.content[0].text.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            questions = json.loads(raw)
            if isinstance(questions, list):
                return [q for q in questions if isinstance(q, str) and q.strip()]
        except (json.JSONDecodeError, IndexError) as e:
            log.warning(f"Parse error on attempt {attempt + 1} for {chunk['chunk_id']}: {e}")
        except anthropic.RateLimitError:
            wait = 20 * (attempt + 1)
            log.warning(f"Rate limit — waiting {wait}s")
            time.sleep(wait)
        except Exception as e:
            log.error(f"Unexpected error for {chunk['chunk_id']}: {e}")
            break
    return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not ANTHROPIC_API_KEY:
        raise EnvironmentError("ANTHROPIC_API_KEY not found in .env")

    OUTPUT_DIR.mkdir(exist_ok=True)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    conn = get_connection()

    log.info("Sampling chunks from pgvector...")
    layer1_chunks = sample_chunks(conn, "layer1", LAYER1_SAMPLE_SIZE, MIN_CHUNK_TOKENS)
    layer2_chunks = sample_chunks(conn, "layer2", LAYER2_SAMPLE_SIZE, MIN_CHUNK_TOKENS)
    log.info(f"Sampled {len(layer1_chunks)} layer1 chunks, {len(layer2_chunks)} layer2 chunks")

    pairs = []
    total = len(layer1_chunks) + len(layer2_chunks)

    for i, chunk in enumerate(layer1_chunks + layer2_chunks):
        n_q = 1 if chunk["layer"] == "layer1" else 2
        log.info(f"[{i+1}/{total}] Generating {n_q}q for {chunk['chunk_id']}")
        questions = generate_questions(client, chunk, n_q)
        for q in questions:
            pairs.append({
                "query": q,
                "expected_chunk_id": chunk["chunk_id"],
                "layer": chunk["layer"],
                "source_file": chunk["source_file"],
                "chunk_text_preview": chunk["text"][:200],
            })
        # Polite pause to avoid rate limits
        time.sleep(0.5)

    conn.close()

    # Shuffle so layer1 and layer2 are interleaved in the output
    random.shuffle(pairs)

    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model": CLAUDE_MODEL,
        "total_pairs": len(pairs),
        "layer1_pairs": sum(1 for p in pairs if p["layer"] == "layer1"),
        "layer2_pairs": sum(1 for p in pairs if p["layer"] == "layer2"),
        "pairs": pairs,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    summary_lines = [
        f"Golden set generated: {datetime.utcnow().isoformat()}Z",
        f"Total pairs: {len(pairs)}",
        f"  layer1: {output['layer1_pairs']}",
        f"  layer2: {output['layer2_pairs']}",
        f"Output: {OUTPUT_FILE}",
    ]
    summary = "\n".join(summary_lines)
    with open(SUMMARY_FILE, "w") as f:
        f.write(summary)

    log.info("\n" + summary)
    log.info(f"Golden set written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

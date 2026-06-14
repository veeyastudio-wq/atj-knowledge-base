#!/usr/bin/env python3
"""
ATJ Knowledge Base — Embedding Script
Reads all chunk JSON files from processed/, generates embeddings via OpenAI,
and loads everything into the pgvector database.
"""

import os
import json
import time
import psycopg2
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

PROCESSED_DIR = Path("processed")
EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100  # chunks per API call — stays well within OpenAI limits

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "atj",
    "user": "postgres",
    "password": "postgres",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_chunks(processed_dir: Path) -> list[dict]:
    """Load all chunk JSON files from processed/."""
    chunks = []
    for path in sorted(processed_dir.rglob("*.json")):
        with open(path, encoding="utf-8") as f:
            chunks.append(json.load(f))
    return chunks


def get_embeddings(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API for a batch of texts."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def chunk_already_exists(cur, chunk_id: str) -> bool:
    """Check if a chunk is already in the database — supports safe re-runs."""
    cur.execute("SELECT 1 FROM chunks WHERE chunk_id = %s", (chunk_id,))
    return cur.fetchone() is not None


def insert_chunk(cur, chunk: dict, embedding: list[float]):
    """Insert a single chunk and its embedding into the database."""
    cur.execute("""
        INSERT INTO chunks (
            chunk_id, source_file, layer, chunk_index, total_chunks,
            token_count, text, metadata, embedding
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (chunk_id) DO NOTHING;
    """, (
        chunk["chunk_id"],
        chunk["source_file"],
        chunk["layer"],
        chunk["chunk_index"],
        chunk["total_chunks"],
        chunk["token_count"],
        chunk["text"],
        json.dumps(chunk["metadata"]),
        embedding,
    ))


# ── Core embedding logic ──────────────────────────────────────────────────────

def embed_and_load(chunks: list[dict], client: OpenAI, conn) -> dict:
    """Embed all chunks in batches and load into the database."""
    cur = conn.cursor()
    stats = {"inserted": 0, "skipped": 0, "batches": 0}

    # Filter out chunks already in the database
    to_embed = []
    for chunk in chunks:
        if chunk_already_exists(cur, chunk["chunk_id"]):
            stats["skipped"] += 1
        else:
            to_embed.append(chunk)

    if stats["skipped"] > 0:
        print(f"  Skipping {stats['skipped']} chunks already in database")

    print(f"  Embedding {len(to_embed)} chunks in batches of {BATCH_SIZE}...\n")

    for i in range(0, len(to_embed), BATCH_SIZE):
        batch = to_embed[i:i + BATCH_SIZE]
        texts = [c["text"] for c in batch]

        try:
            embeddings = get_embeddings(client, texts)
        except Exception as e:
            print(f"  ERROR on batch {stats['batches'] + 1}: {e}")
            time.sleep(5)
            continue

        for chunk, embedding in zip(batch, embeddings):
            insert_chunk(cur, chunk, embedding)
            stats["inserted"] += 1

        conn.commit()
        stats["batches"] += 1

        print(f"  Batch {stats['batches']}: {len(batch)} chunks embedded and loaded")

        # Polite pause between batches to stay within rate limits
        if i + BATCH_SIZE < len(to_embed):
            time.sleep(0.5)

    cur.close()
    return stats


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("ATJ Knowledge Base — Embedding Script")
    print(f"Model: {EMBEDDING_MODEL} | Batch size: {BATCH_SIZE}\n")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment. Check your .env file.")

    client = OpenAI(api_key=api_key)

    print(f"Loading chunks from {PROCESSED_DIR}/...")
    chunks = load_chunks(PROCESSED_DIR)
    print(f"  Found {len(chunks)} chunks\n")

    print("Connecting to database...")
    conn = psycopg2.connect(**DB_CONFIG)
    print("  Connected\n")

    stats = embed_and_load(chunks, client, conn)
    conn.close()

    print("\n── Summary ──────────────────────────────────────────")
    print(f"  Chunks embedded and inserted: {stats['inserted']}")
    print(f"  Chunks skipped (already exist): {stats['skipped']}")
    print(f"  API batches: {stats['batches']}")
    print("─────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()

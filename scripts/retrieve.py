"""
retrieve.py

Hybrid retrieval over the ATJ pgvector knowledge base.
Combines dense (cosine similarity via HNSW) and sparse (BM25 via GIN full-text)
signals using Reciprocal Rank Fusion (RRF).

Layer1 and Layer2 are retrieved separately so they never compete for the same slot.

Usage (standalone):
    python scripts/retrieve.py "What happens at a First Appointment hearing?"
    python scripts/retrieve.py "What happens at a First Appointment?" --layer layer2
    python scripts/retrieve.py "What is Form E?" --top-k 5

Importable:
    from scripts.retrieve import retrieve

Requires:
    OPENAI_API_KEY in .env at repo root
"""

import os
import sys
import json
import argparse
import logging
from typing import Optional

import psycopg2
import psycopg2.extras
from openai import OpenAI
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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# RRF constant — standard value; higher k reduces sensitivity to top ranks
RRF_K = 60

TOP_K = 10          # results returned per layer
DENSE_CANDIDATES = 20   # how many to fetch from each signal before fusion
SPARSE_CANDIDATES = 20

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_query(client: OpenAI, query: str) -> list[float]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
    )
    return response.data[0].embedding


# ---------------------------------------------------------------------------
# Dense retrieval (cosine similarity via HNSW index)
# ---------------------------------------------------------------------------

DENSE_SQL = """
SELECT
    chunk_id,
    source_file,
    layer,
    chunk_index,
    token_count,
    text,
    metadata,
    1 - (embedding <=> %s::vector) AS score
FROM chunks
WHERE layer = %s
ORDER BY embedding <=> %s::vector
LIMIT %s
"""

def dense_retrieve(cur, embedding: list[float], layer: str, n: int) -> list[dict]:
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    cur.execute(DENSE_SQL, (vec_str, layer, vec_str, n))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# Sparse retrieval (BM25-style via GIN full-text index)
# ---------------------------------------------------------------------------

SPARSE_SQL = """
SELECT
    chunk_id,
    source_file,
    layer,
    chunk_index,
    token_count,
    text,
    metadata,
    ts_rank_cd(
        to_tsvector('english', text),
        plainto_tsquery('english', %s)
    ) AS score
FROM chunks
WHERE layer = %s
  AND to_tsvector('english', text) @@ plainto_tsquery('english', %s)
ORDER BY score DESC
LIMIT %s
"""

def sparse_retrieve(cur, query: str, layer: str, n: int) -> list[dict]:
    cur.execute(SPARSE_SQL, (query, layer, query, n))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(
    dense_results: list[dict],
    sparse_results: list[dict],
    k: int = RRF_K,
) -> list[dict]:
    """
    Combine two ranked lists using RRF.
    Returns merged list sorted by descending RRF score.
    """
    scores: dict[str, float] = {}
    chunks: dict[str, dict] = {}

    for rank, chunk in enumerate(dense_results, start=1):
        cid = chunk["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        chunks[cid] = chunk

    for rank, chunk in enumerate(sparse_results, start=1):
        cid = chunk["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        if cid not in chunks:
            chunks[cid] = chunk

    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    result = []
    for cid, rrf_score in merged:
        entry = dict(chunks[cid])
        entry["rrf_score"] = round(rrf_score, 6)
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def retrieve(
    query: str,
    layer: Optional[str] = None,
    top_k: int = TOP_K,
    dense_n: int = DENSE_CANDIDATES,
    sparse_n: int = SPARSE_CANDIDATES,
) -> dict:
    """
    Run hybrid retrieval for a query.

    Args:
        query:   Plain English question from the user.
        layer:   'layer1', 'layer2', or None (returns both separately).
        top_k:   Number of results to return per layer.
        dense_n: Dense candidates before fusion.
        sparse_n: Sparse candidates before fusion.

    Returns:
        {
            "query": str,
            "layer1": [...],  # present if layer is None or 'layer1'
            "layer2": [...],  # present if layer is None or 'layer2'
        }
    """
    if not OPENAI_API_KEY:
        raise EnvironmentError("OPENAI_API_KEY not found in .env")

    oai = OpenAI(api_key=OPENAI_API_KEY)
    embedding = embed_query(oai, query)

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )

    layers_to_query = []
    if layer is None:
        layers_to_query = ["layer1", "layer2"]
    elif layer in ("layer1", "layer2"):
        layers_to_query = [layer]
    else:
        raise ValueError(f"layer must be 'layer1', 'layer2', or None — got {layer!r}")

    result = {"query": query}

    with conn.cursor() as cur:
        for lyr in layers_to_query:
            dense = dense_retrieve(cur, embedding, lyr, dense_n)
            sparse = sparse_retrieve(cur, query, lyr, sparse_n)
            fused = reciprocal_rank_fusion(dense, sparse)[:top_k]

            # Clean metadata for JSON serialisation
            for chunk in fused:
                if isinstance(chunk.get("metadata"), str):
                    try:
                        chunk["metadata"] = json.loads(chunk["metadata"])
                    except Exception:
                        pass

            result[lyr] = fused

    conn.close()
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _format_result(result: dict) -> str:
    lines = [f"\nQuery: {result['query']}\n{'='*60}"]
    for layer in ("layer1", "layer2"):
        if layer not in result:
            continue
        lines.append(f"\n--- {layer.upper()} ({len(result[layer])} results) ---")
        for i, chunk in enumerate(result[layer], 1):
            lines.append(
                f"\n[{i}] {chunk['chunk_id']}"
                f"\n    Source : {chunk['source_file']}"
                f"\n    Tokens : {chunk['token_count']}"
                f"\n    RRF    : {chunk['rrf_score']}"
                f"\n    Preview: {chunk['text'][:120].replace(chr(10), ' ')}..."
            )
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="ATJ hybrid retrieval")
    parser.add_argument("query", help="Plain English query")
    parser.add_argument(
        "--layer", choices=["layer1", "layer2"],
        default=None, help="Filter to a single layer (default: both)"
    )
    parser.add_argument(
        "--top-k", type=int, default=TOP_K,
        help=f"Results per layer (default: {TOP_K})"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON instead of formatted text"
    )
    args = parser.parse_args()

    result = retrieve(args.query, layer=args.layer, top_k=args.top_k)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(_format_result(result))

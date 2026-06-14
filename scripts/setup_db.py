#!/usr/bin/env python3
"""
ATJ Knowledge Base — Database Setup Script
Creates the pgvector extension and the chunks table in PostgreSQL.
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "atj",
    "user": "postgres",
    "password": "postgres",
}

def setup():
    print("ATJ — Database Setup")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    # Enable pgvector extension
    print("  Enabling pgvector extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Create chunks table
    print("  Creating chunks table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id              SERIAL PRIMARY KEY,
            chunk_id        TEXT NOT NULL UNIQUE,
            source_file     TEXT NOT NULL,
            layer           TEXT NOT NULL CHECK (layer IN ('layer1', 'layer2')),
            chunk_index     INTEGER NOT NULL,
            total_chunks    INTEGER NOT NULL,
            token_count     INTEGER NOT NULL,
            text            TEXT NOT NULL,
            metadata        JSONB,
            embedding       vector(1536),
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Indexes
    print("  Creating indexes...")

    # Index for fast layer filtering
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_layer
        ON chunks (layer);
    """)

    # Index for vector similarity search (HNSW — best for our scale)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding
        ON chunks USING hnsw (embedding vector_cosine_ops);
    """)

    # Index for full-text search (sparse/BM25 leg of hybrid retrieval)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_text_fts
        ON chunks USING gin (to_tsvector('english', text));
    """)

    cur.close()
    conn.close()

    print("\n── Setup complete ───────────────────────────────────")
    print("  Extension: pgvector")
    print("  Table: chunks")
    print("  Indexes: layer, embedding (HNSW cosine), text (GIN full-text)")
    print("─────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    setup()

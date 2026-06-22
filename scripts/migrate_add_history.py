#!/usr/bin/env python3
"""
scripts/migrate_add_history.py

Adds two new tables to the ATJ PostgreSQL database:

  conversation_history — durable per-user-session conversation turns,
    replacing the in-process _session_store dict in api.py for the case
    file panel and searchable history features.

  document_store — transcribed text extracted from uploaded documents and
    photos. The original image is never stored; only the text Claude
    produces from reading it is written here.

Safe to re-run: uses CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT
EXISTS throughout. Matches the connection pattern in setup_db.py exactly.

Run with:
    python3.12 scripts/migrate_add_history.py
"""

import traceback

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "atj",
    "user": "postgres",
    "password": "postgres",
}


def migrate():
    print("ATJ — History Migration")

    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    # ── conversation_history ──────────────────────────────────────────
    print("  Creating conversation_history table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversation_history (
            id          SERIAL PRIMARY KEY,
            user_id     TEXT        NOT NULL,
            session_id  TEXT        NOT NULL,
            role        TEXT        NOT NULL,
            content     TEXT        NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    print("  Creating index on conversation_history(user_id, session_id, created_at DESC)...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_conv_history_user_session
        ON conversation_history (user_id, session_id, created_at DESC);
    """)

    # ── document_store ────────────────────────────────────────────────
    print("  Creating document_store table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS document_store (
            id               SERIAL PRIMARY KEY,
            user_id          TEXT        NOT NULL,
            session_id       TEXT        NOT NULL,
            document_label   TEXT,
            transcribed_text TEXT        NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    print("  Creating index on document_store(user_id, created_at DESC)...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_store_user
        ON document_store (user_id, created_at DESC);
    """)

    # ── Verification ──────────────────────────────────────────────────
    print("\n  Verifying tables in public schema...")
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = [row[0] for row in cur.fetchall()]
    print(f"  Tables: {tables}")

    cur.close()
    conn.close()

    print("\n── Migration complete ────────────────────────────────────────")
    print("  Table : conversation_history")
    print("  Index : idx_conv_history_user_session")
    print("          (user_id, session_id, created_at DESC)")
    print("  Table : document_store")
    print("  Index : idx_document_store_user")
    print("          (user_id, created_at DESC)")
    print("─────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    try:
        migrate()
    except Exception:
        print("\n── Migration FAILED ──────────────────────────────────────────")
        traceback.print_exc()
        print("──────────────────────────────────────────────────────────────\n")
        raise SystemExit(1)

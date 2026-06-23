"""
scripts/case_file.py

Read-only access to the case file data stored in PostgreSQL.
Used by the case file panel to display conversation history and
uploaded documents. All writes stay in api.py.

Functions
---------
get_conversation_history(user_id, session_id=None, limit=100)
    Last `limit` turns for the user, in chronological order (ASC).

get_documents(user_id, limit=50)
    Last `limit` document_store rows for the user, newest first (DESC).
    transcribed_text is excluded — it is large and the panel only needs
    label and metadata. Use a separate get_document_text() call (not yet
    implemented) when the full text is needed.
"""

import psycopg2

_DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "atj",
    "user": "postgres",
    "password": "postgres",
}


def get_conversation_history(
    user_id: str,
    session_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return the last `limit` conversation turns for the user.

    If session_id is provided, scoped to that session.
    Rows are returned in chronological order (created_at ASC) so the UI
    can render them top-to-bottom without reversing.
    Each row: id, session_id, role, content, created_at (ISO string).
    """
    try:
        conn = psycopg2.connect(**_DB_CONFIG)
        cur = conn.cursor()

        if session_id is not None:
            cur.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM (
                    SELECT id, session_id, role, content, created_at
                    FROM conversation_history
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                ) sub
                ORDER BY created_at ASC
                """,
                (user_id, session_id, limit),
            )
        else:
            cur.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM (
                    SELECT id, session_id, role, content, created_at
                    FROM conversation_history
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                ) sub
                ORDER BY created_at ASC
                """,
                (user_id, limit),
            )

        rows = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "id":         row[0],
                "session_id": row[1],
                "role":       row[2],
                "content":    row[3],
                "created_at": row[4].isoformat(),
            }
            for row in rows
        ]

    except psycopg2.Error as exc:
        print(f"HISTORY READ ERROR: {exc}")
        return []


def get_documents(user_id: str, limit: int = 50) -> list[dict]:
    """Return the last `limit` uploaded documents for the user, newest first.

    transcribed_text is intentionally excluded — it can be large and
    the panel only needs the label and metadata for display.
    Each row: id, session_id, document_label, created_at (ISO string).
    """
    try:
        conn = psycopg2.connect(**_DB_CONFIG)
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, session_id, document_label, created_at
            FROM document_store
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )

        rows = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "id":             row[0],
                "session_id":     row[1],
                "document_label": row[2],
                "created_at":     row[3].isoformat(),
            }
            for row in rows
        ]

    except psycopg2.Error as exc:
        print(f"DOCUMENT READ ERROR: {exc}")
        return []


def search_conversation_history(user_id: str, query: str, limit: int = 50) -> list[dict]:
    """Search conversation_history rows matching query using PostgreSQL full-text search.

    Uses plainto_tsquery('english', ...) — handles stemming and stop words.
    Results are ordered newest first (created_at DESC).
    Each row: id, session_id, role, content, created_at (ISO string).
    """
    try:
        conn = psycopg2.connect(**_DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, session_id, role, content, created_at
            FROM conversation_history
            WHERE user_id = %s
              AND to_tsvector('english', content) @@ plainto_tsquery('english', %s)
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, query, limit),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "id":         row[0],
                "session_id": row[1],
                "role":       row[2],
                "content":    row[3],
                "created_at": row[4].isoformat(),
            }
            for row in rows
        ]
    except psycopg2.Error as exc:
        print(f"SEARCH ERROR: {exc}")
        return []


if __name__ == "__main__":
    print("── get_conversation_history('history_test_001') ─────────────────")
    turns = get_conversation_history("history_test_001")
    print(f"Row count: {len(turns)}")
    if turns:
        print("First row:", turns[0])

    print()
    print("── get_documents('doc_test_001') ────────────────────────────────")
    docs = get_documents("doc_test_001")
    print(f"Row count: {len(docs)}")
    if docs:
        print("First row:", docs[0])

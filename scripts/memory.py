"""
ATJ Memory Layer — scripts/memory.py

Provides per-user persistent memory backed by Neo4j via neo4j-agent-memory v0.5.
Local embeddings via sentence-transformers (BAAI/bge-small-en-v1.5, 384 dims).
No data leaves ATJ infrastructure during memory reads or writes.

Public API:
    initialise_memory()                                  — call once at startup
    write_memory(user_identifier, session_id, content)   — store a memory
    retrieve_memory(user_identifier, query)              — semantic search
    delete_user_memory(user_identifier)                  — GDPR Article 17 delete
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from neo4j_agent_memory import MemoryClient, MemorySettings
from neo4j_agent_memory.config.settings import (
    EmbeddingConfig,
    EnrichmentConfig,
    ExtractionConfig,
    GeocodingConfig,
    MemoryConfig,
    Neo4jConfig,
    ResolutionConfig,
    SchemaConfig,
    SearchConfig,
)
from neo4j_agent_memory.embeddings.sentence_transformers import SentenceTransformerEmbedder
from pydantic import SecretStr

load_dotenv()

_LOG_PATH = Path("logs/memory_ops.jsonl")
_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
_EMBED_DIMS = 384

_settings: MemorySettings | None = None
_embedder: SentenceTransformerEmbedder | None = None


# ── Logging ───────────────────────────────────────────────────────────────────

def _log_memory_op(
    *,
    user_identifier: str,
    operation: str,
    entity_count: int,
    latency_ms: float,
    success: bool,
    error: str | None = None,
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_identifier": user_identifier,
        "operation": operation,
        "entity_count": entity_count,
        "latency_ms": round(latency_ms, 2),
        "success": success,
        "error": error,
    }
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


# ── Internal guards ───────────────────────────────────────────────────────────

def _require_init() -> None:
    if _settings is None:
        raise RuntimeError("Call initialise_memory() before using memory functions.")


def _make_client() -> MemoryClient:
    return MemoryClient(_settings, embedder=_embedder)


# ── Public API ────────────────────────────────────────────────────────────────

def initialise_memory() -> None:
    """Initialise the neo4j-agent-memory client. Call once at startup."""
    global _settings, _embedder

    load_dotenv()

    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]

    _embedder = SentenceTransformerEmbedder(model_name=_EMBED_MODEL, device="cpu")

    _settings = MemorySettings(
        neo4j=Neo4jConfig(
            uri=uri,
            username=user,
            password=SecretStr(password),
        ),
        embedding=EmbeddingConfig(
            provider="openai",  # overridden by the custom embedder argument below
            dimensions=_EMBED_DIMS,
        ),
        extraction=ExtractionConfig(
            extractor_type="none",
            enable_spacy=False,
            enable_gliner=False,
            enable_llm_fallback=False,
        ),
        schema_config=SchemaConfig(),
        resolution=ResolutionConfig(),
        memory=MemoryConfig(multi_tenant=True),
        search=SearchConfig(),
        geocoding=GeocodingConfig(),
        enrichment=EnrichmentConfig(),
    )

    asyncio.run(_init_async())


async def _init_async() -> None:
    """Connect once to verify credentials and let the library set up Neo4j schema."""
    async with _make_client():
        pass


def write_memory(
    user_identifier: str,
    session_id: str,
    content: str,
    memory_enabled: bool = True,
) -> None:
    """Extract facts from content and write to the memory graph for this user."""
    _require_init()

    if not memory_enabled:
        return

    t0 = time.monotonic()
    error: str | None = None
    success = False
    count = 0
    try:
        asyncio.run(_write_async(user_identifier, session_id, content))
        count = 1
        success = True
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        _log_memory_op(
            user_identifier=user_identifier,
            operation="write",
            entity_count=count,
            latency_ms=(time.monotonic() - t0) * 1000,
            success=success,
            error=error,
        )


async def _write_async(user_identifier: str, session_id: str, content: str) -> None:
    async with _make_client() as client:
        await client.short_term.add_message(
            session_id=user_identifier,   # user_identifier scopes the session
            role="user",
            content=content,
            user_identifier=user_identifier,
            extract_entities=False,
            extract_relations=False,
            generate_embedding=True,
            metadata={"atj_session_id": session_id, "user_identifier": user_identifier},
        )


def retrieve_memory(user_identifier: str, query: str) -> list:
    """Retrieve relevant memory for this user given a query string."""
    _require_init()

    t0 = time.monotonic()
    error: str | None = None
    success = False
    results: list = []
    try:
        results = asyncio.run(_retrieve_async(user_identifier, query))
        success = True
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        _log_memory_op(
            user_identifier=user_identifier,
            operation="retrieve",
            entity_count=len(results),
            latency_ms=(time.monotonic() - t0) * 1000,
            success=success,
            error=error,
        )
    return results


async def _retrieve_async(user_identifier: str, query: str) -> list:
    async with _make_client() as client:
        messages = await client.short_term.search_messages(
            query,
            metadata_filters={"user_identifier": user_identifier},
            limit=10,
            threshold=0.3,
        )
        return [
            {
                "content": m.content,
                "role": str(m.role),
                "created_at": str(m.created_at),
                "user_identifier": user_identifier,
            }
            for m in messages
        ]


def delete_user_memory(user_identifier: str) -> None:
    """Delete all memory for this user. Logs the deletion. GDPR Article 17."""
    _require_init()

    t0 = time.monotonic()
    error: str | None = None
    success = False
    count = 0
    try:
        count = asyncio.run(_delete_async(user_identifier))
        success = True
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        _log_memory_op(
            user_identifier=user_identifier,
            operation="delete",
            entity_count=count,
            latency_ms=(time.monotonic() - t0) * 1000,
            success=success,
            error=error,
        )


async def _delete_async(user_identifier: str) -> int:
    # 1. Use the library's session delete (removes session node, messages, links)
    try:
        async with _make_client() as client:
            await client.short_term.clear_session(user_identifier)
    except Exception:
        pass  # session may not exist; proceed to raw Cypher sweep

    # 2. Raw Cypher cascade-delete any remaining nodes scoped to this user
    from neo4j import AsyncGraphDatabase  # neo4j driver installed as library dependency

    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    count = 0
    try:
        async with driver.session() as db_session:
            result = await db_session.run(
                """
                MATCH (n)
                WHERE n.user_identifier = $uid
                   OR n.session_id = $uid
                DETACH DELETE n
                """,
                uid=user_identifier,
            )
            summary = await result.consume()
            count = summary.counters.nodes_deleted
    finally:
        await driver.close()

    return count

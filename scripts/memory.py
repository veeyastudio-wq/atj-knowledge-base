"""
ATJ Memory Layer — scripts/memory.py

Extract-then-discard: no raw conversational content is ever written to Neo4j.
Each turn is passed through an Anthropic extraction step that returns a list of
structured case facts. Only those facts reach the graph. If nothing storable is
present in a turn, nothing is written — that is a valid and expected outcome.

Stored node types:
  (:User {identifier})                     — one node per user_identifier
  (:Preference {category, preference, ...}) — one node per extracted fact
  (:User)-[:HAS_PREFERENCE]->(:Preference)  — scoping edge

Fact categories (POLE+O extension for family court):
  case_stage | key_date | document_status | party_name |
  financial_figure | order_made | hearing_outcome

Public API:
    initialise_memory()
    write_memory(user_identifier, session_id, content, *, role, memory_enabled)
    retrieve_memory(user_identifier, query)
    delete_user_memory(user_identifier)
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic as _anthropic
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase
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
_EXTRACTION_MODEL = "claude-sonnet-4-6"

_FACT_CATEGORIES = frozenset([
    "case_stage",
    "key_date",
    "document_status",
    "party_name",
    "financial_figure",
    "order_made",
    "hearing_outcome",
])

_EXTRACTION_SYSTEM = """\
You are a structured data extractor for a family court case management system.

Extract ONLY these fact categories from the text you are given:
- case_stage: Current stage of the proceedings (e.g. "Financial Disclosure — Form E exchange", "FDA hearing pending")
- key_date: Specific dates mentioned (e.g. "FDA hearing on 15 July 2026", "Form E deadline: 20 June 2026")
- document_status: Status of any legal documents (e.g. "Form E not yet filed", "Form A issued by court")
- party_name: Names of parties, solicitors, or key individuals (e.g. "applicant: Sarah Johnson", "respondent represented by Harris and Co")
- financial_figure: Specific monetary values (e.g. "CETV for NHS pension: £180,000", "family home valued at £350,000")
- order_made: Any court orders mentioned (e.g. "non-molestation order granted", "pension sharing order applied for")
- hearing_outcome: Outcomes of hearings (e.g. "FDA adjourned to September 2026", "FDR resolved — consent order agreed")

Do NOT extract:
- Emotional expressions or feelings
- Speculative statements (anything with "might", "could", "wondering", "perhaps")
- Legal questions asked by the user
- General legal information or explanations
- Anything that could constitute legal advice

Output ONLY a JSON array. No markdown fences, no extra text. Each item must have:
  "type": one of the category names above
  "value": a concise, factual string — no full sentences, no verbatim quotation of the input

Return [] if there is nothing storable. That is a valid and expected output.\
"""

_settings: MemorySettings | None = None
_embedder: SentenceTransformerEmbedder | None = None
_anthropic_client: _anthropic.Anthropic | None = None


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


# ── Internal helpers ──────────────────────────────────────────────────────────

def _require_init() -> None:
    if _settings is None:
        raise RuntimeError("Call initialise_memory() before using memory functions.")


def _make_client() -> MemoryClient:
    return MemoryClient(_settings, embedder=_embedder)


def _extract_facts(content: str) -> list[dict]:
    """Call Anthropic API to extract structured case facts from a conversation turn.

    Returns a list of {type, value} dicts. Empty list if nothing storable is found.
    Raw content is never stored; only structured fact values reach Neo4j.
    """
    message = _anthropic_client.messages.create(
        model=_EXTRACTION_MODEL,
        max_tokens=512,
        system=_EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    raw = message.content[0].text.strip()
    # Strip markdown fences defensively, even though the prompt forbids them
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        facts = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(facts, list):
        return []
    return [
        f for f in facts
        if isinstance(f, dict)
        and "type" in f
        and "value" in f
        and f["type"] in _FACT_CATEGORIES
        and isinstance(f["value"], str)
        and f["value"].strip()
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def initialise_memory() -> None:
    """Initialise the memory layer. Call once at startup."""
    global _settings, _embedder, _anthropic_client

    load_dotenv()

    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]

    _anthropic_client = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    _embedder = SentenceTransformerEmbedder(model_name=_EMBED_MODEL, device="cpu")

    _settings = MemorySettings(
        neo4j=Neo4jConfig(
            uri=uri,
            username=user,
            password=SecretStr(password),
        ),
        embedding=EmbeddingConfig(
            provider="openai",  # overridden by the custom embedder argument
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
    async with _make_client():
        pass


def write_memory(
    user_identifier: str,
    session_id: str,
    content: str,
    *,
    role: str = "user",
    memory_enabled: bool = True,
) -> None:
    """Extract structured facts from content and write them to the memory graph.

    No raw content is stored. The Anthropic extraction step runs first; only
    the returned structured facts (type + value) reach Neo4j. If nothing
    storable is present in this turn, nothing is written — entity_count=0.

    role: accepted for API compatibility but not used in extraction.
    """
    _require_init()

    if not memory_enabled:
        return

    t0 = time.monotonic()
    error: str | None = None
    success = False
    count = 0
    try:
        facts = _extract_facts(content)
        if facts:
            asyncio.run(_write_async(user_identifier, session_id, facts))
        count = len(facts)
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


async def _write_async(user_identifier: str, session_id: str, facts: list[dict]) -> None:
    async with _make_client() as client:
        for fact in facts:
            await client.long_term.add_preference(
                category=fact["type"],
                preference=fact["value"],
                context=f"session:{session_id}",
                generate_embedding=True,
                metadata={
                    "atj_session_id": session_id,
                    "user_identifier": user_identifier,
                },
                user_identifier=user_identifier,
            )


def retrieve_memory(user_identifier: str, query: str) -> list:
    """Retrieve all stored case facts for this user.

    Returns a list of dicts with keys: content, role, created_at, user_identifier.
    content is formatted as "{category}: {value}" — structured fact, not raw text.
    query is accepted for API compatibility; retrieval is user-scoped via graph
    traversal (User→HAS_PREFERENCE→Preference), not vector search.
    """
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
        prefs = await client.long_term.get_preferences_for(
            user_identifier,
            active_only=True,
        )
        return [
            {
                "content": f"{p.category}: {p.preference}",
                "role": "fact",
                "created_at": str(p.created_at),
                "user_identifier": user_identifier,
            }
            for p in prefs
        ]


def delete_user_memory(user_identifier: str) -> None:
    """Delete all memory for this user. GDPR Article 17 — right to erasure."""
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
    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    count = 0
    try:
        async with driver.session() as session:
            # Collect IDs of all Preference nodes linked to this user
            result = await session.run(
                "MATCH (u:User {identifier: $uid})-[:HAS_PREFERENCE]->(p:Preference) "
                "RETURN p.id AS pref_id",
                uid=user_identifier,
            )
            records = await result.data()
            pref_ids = [r["pref_id"] for r in records]

            # Delete the User node; DETACH DELETE removes all HAS_PREFERENCE edges
            result = await session.run(
                "MATCH (u:User {identifier: $uid}) DETACH DELETE u",
                uid=user_identifier,
            )
            summary = await result.consume()
            count += summary.counters.nodes_deleted

            # Delete any Preference nodes that are now orphaned (no other user owns them)
            if pref_ids:
                result = await session.run(
                    """
                    UNWIND $ids AS id
                    MATCH (p:Preference {id: id})
                    WHERE NOT EXISTS { MATCH (:User)-[:HAS_PREFERENCE]->(p) }
                    DETACH DELETE p
                    """,
                    ids=pref_ids,
                )
                summary = await result.consume()
                count += summary.counters.nodes_deleted

            # Broad sweep: catch any remaining nodes carrying this identifier
            result = await session.run(
                """
                MATCH (n)
                WHERE n.user_identifier = $uid
                   OR n.identifier = $uid
                   OR n.session_id = $uid
                DETACH DELETE n
                """,
                uid=user_identifier,
            )
            summary = await result.consume()
            count += summary.counters.nodes_deleted
    finally:
        await driver.close()

    return count

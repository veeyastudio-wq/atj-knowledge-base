"""
ATJ Memory Layer — scripts/memory.py

Extract-then-discard: no raw conversational content is ever written to Neo4j.
Each turn is passed through an Anthropic extraction step that returns a list of
structured case facts. Only those facts reach the graph. If nothing storable is
present in a turn, nothing is written — that is a valid and expected outcome.

Graph schema — typed fact nodes extending POLE+O:

  Custom family-court domain types:
    (:ATJFact:CaseStage)       — case_stage       — Current stage of proceedings
    (:ATJFact:Deadline)        — key_date         — Specific dates and deadlines
    (:ATJFact:FinancialFigure) — financial_figure — Monetary values
    (:ATJFact:OrderType)       — order_made       — Court orders
    (:ATJFact:HearingType)     — hearing_outcome  — Hearing outcomes

  Base POLE+O types:
    (:ATJFact:Person)          — party_name       — Parties, solicitors, individuals
    (:ATJFact:Document)        — document_status  — Document states (Object > Document)

  User scoping:
    (:User {identifier})-[:HAS_ATJ_FACT]->(:ATJFact)

  All ATJFact nodes carry user_identifier as a direct property for sweep deletion.

  The neo4j-agent-memory library's add_entity() has no user_identifier parameter,
  making its entity API unsuitable for multi-tenant storage. Raw Cypher is used
  for writes and reads to maintain per-user isolation across all typed nodes.

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
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic as _anthropic
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

load_dotenv()

_LOG_PATH = Path("logs/memory_ops.jsonl")
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

# Maps extraction category → additional Neo4j label on the :ATJFact base node.
# Five custom family-court types (brief spec) + two POLE+O base types.
# Values are statically defined here; they are the only strings interpolated
# into Cypher label position — user input never reaches that position.
_CATEGORY_TO_LABEL: dict[str, str] = {
    "case_stage":        "CaseStage",        # custom ATJ
    "key_date":          "Deadline",         # custom ATJ
    "financial_figure":  "FinancialFigure",  # custom ATJ
    "order_made":        "OrderType",        # custom ATJ
    "hearing_outcome":   "HearingType",      # custom ATJ
    "party_name":        "Person",           # POLE+O
    "document_status":   "Document",         # POLE+O Object > Document
}

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

_neo4j_uri: str | None = None
_neo4j_auth: tuple | None = None
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
    if _neo4j_uri is None:
        raise RuntimeError("Call initialise_memory() before using memory functions.")


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
    global _neo4j_uri, _neo4j_auth, _anthropic_client

    load_dotenv()

    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]

    _neo4j_uri = uri
    _neo4j_auth = (user, password)
    _anthropic_client = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    asyncio.run(_init_async())


async def _init_async() -> None:
    """Create indexes for the ATJFact schema on first run."""
    driver = AsyncGraphDatabase.driver(_neo4j_uri, auth=_neo4j_auth)
    try:
        async with driver.session() as session:
            await session.run(
                "CREATE INDEX atj_fact_user IF NOT EXISTS "
                "FOR (n:ATJFact) ON (n.user_identifier)"
            )
            await session.run(
                "CREATE CONSTRAINT atj_fact_id IF NOT EXISTS "
                "FOR (n:ATJFact) REQUIRE n.id IS UNIQUE"
            )
    finally:
        await driver.close()


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
    driver = AsyncGraphDatabase.driver(_neo4j_uri, auth=_neo4j_auth)
    try:
        async with driver.session() as session:
            for fact in facts:
                # Label comes from a static dict keyed on validated category — not user input
                label = _CATEGORY_TO_LABEL.get(fact["type"], "ATJFact")
                query = (
                    f"MERGE (u:User {{identifier: $uid}}) "
                    f"CREATE (f:ATJFact:{label} {{"
                    f"  id: $id, category: $category, value: $value, "
                    f"  user_identifier: $uid, session_id: $sid, "
                    f"  created_at: datetime() "
                    f"}}) "
                    f"MERGE (u)-[:HAS_ATJ_FACT]->(f)"
                )
                await session.run(
                    query,
                    uid=user_identifier,
                    id=str(uuid.uuid4()),
                    category=fact["type"],
                    value=fact["value"],
                    sid=session_id,
                )
    finally:
        await driver.close()


def retrieve_memory(user_identifier: str, query: str) -> list:
    """Retrieve all stored case facts for this user.

    Returns a list of dicts with keys: content, role, created_at, user_identifier.
    content is formatted as "{category}: {value}" — structured fact, not raw text.
    query is accepted for API compatibility; retrieval is user-scoped via graph
    traversal (User→HAS_ATJ_FACT→ATJFact), not vector search.
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
    driver = AsyncGraphDatabase.driver(_neo4j_uri, auth=_neo4j_auth)
    try:
        async with driver.session() as session:
            result = await session.run(
                "MATCH (u:User {identifier: $uid})-[:HAS_ATJ_FACT]->(f:ATJFact) "
                "RETURN f.category AS category, f.value AS value, "
                "       toString(f.created_at) AS created_at "
                "ORDER BY f.created_at",
                uid=user_identifier,
            )
            records = await result.data()
            return [
                {
                    "content": f"{r['category']}: {r['value']}",
                    "role": "fact",
                    "created_at": r["created_at"],
                    "user_identifier": user_identifier,
                }
                for r in records
            ]
    finally:
        await driver.close()


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
    driver = AsyncGraphDatabase.driver(_neo4j_uri, auth=_neo4j_auth)
    count = 0
    try:
        async with driver.session() as session:
            # Delete typed ATJFact nodes via relationship traversal
            result = await session.run(
                "MATCH (u:User {identifier: $uid})-[:HAS_ATJ_FACT]->(f:ATJFact) "
                "DETACH DELETE f",
                uid=user_identifier,
            )
            summary = await result.consume()
            count += summary.counters.nodes_deleted

            # Legacy Preference nodes (prior schema — clean up if present)
            result = await session.run(
                "MATCH (u:User {identifier: $uid})-[:HAS_PREFERENCE]->(p:Preference) "
                "RETURN p.id AS pref_id",
                uid=user_identifier,
            )
            records = await result.data()
            pref_ids = [r["pref_id"] for r in records]

            # Delete the User node; DETACH DELETE removes all relationship edges
            result = await session.run(
                "MATCH (u:User {identifier: $uid}) DETACH DELETE u",
                uid=user_identifier,
            )
            summary = await result.consume()
            count += summary.counters.nodes_deleted

            # Delete any legacy Preference nodes now orphaned
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
                DETACH DELETE n
                """,
                uid=user_identifier,
            )
            summary = await result.consume()
            count += summary.counters.nodes_deleted
    finally:
        await driver.close()

    return count

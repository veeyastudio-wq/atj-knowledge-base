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

  CaseStage supersession and fact reconciliation:
    When a new case_stage fact is written, any existing active CaseStage node
    for that user (where invalid_at IS NULL) has invalid_at set to the current
    timestamp before the new node is created. This means retrieve_memory always
    returns at most one active CaseStage per user.

    All other fact types go through LLM-based reconciliation: if the new fact
    refers to the same real-world subject as an existing active fact of the same
    type, the existing fact is superseded (invalid_at set) and the new value
    replaces it. If genuinely distinct, it is added without affecting existing
    nodes. Reconciliation defaults to "new" on model uncertainty or parse
    failure — false merges (erasing a stored fact) are worse than false separates.

  Per-fact compliance audit:
    After Anthropic extraction and before Neo4j writes, each fact is checked
    individually by a second API call (Haiku) that judges the fact's category
    and value against the exclusion list. Facts that fail are logged as
    audit_reject and never written. Facts that pass proceed to Neo4j normally.

  The neo4j-agent-memory library's add_entity() has no user_identifier parameter,
  making its entity API unsuitable for multi-tenant storage. Raw Cypher is used
  for writes and reads to maintain per-user isolation across all typed nodes.

Public API:
    initialise_memory()
    write_memory(user_identifier, session_id, content, *, role, memory_enabled)
    retrieve_memory(user_identifier, query)
    delete_user_memory(user_identifier)

Semi-public (importable for testing):
    _compliance_check(category, value) -> (passes: bool, reason: str)
    _filter_by_compliance(user_identifier, facts) -> list[dict]
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
_COMPLIANCE_MODEL = "claude-haiku-4-5-20251001"

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

_COMPLIANCE_SYSTEM = """\
You are a compliance auditor for a family court case management system.

You will receive a single extracted fact: a category and a value. Determine
whether the value violates any of these prohibited content types:

1. Emotional expressions or feelings
2. Speculative statements (language implying uncertainty: might, could, perhaps, wondering, maybe)
3. Legal questions asked by the user (anything phrased as a question seeking legal guidance)
4. General legal information or explanations
5. Anything that could constitute legal advice (recommendations, should, must, you need to)

A passing fact is concise and purely factual — it records an objective case
detail (a date, a name, a court order, a stage of proceedings, a monetary value)
without any of the above violations.

Respond with a JSON object with exactly two keys:
  "passes": true if the fact is safe to store, false if it violates a prohibition
  "reason": one sentence — if passes=true write "OK"; if passes=false name the specific prohibition violated

No markdown fences. No extra text. JSON only.\
"""

_RECONCILIATION_SYSTEM = """\
You are a fact reconciliation assistant for a family court case management system.

You will receive a candidate fact value and a list of existing active facts of the same
category for this user, each with an id and value.

Decide whether the candidate is:
  "update" — it refers to the same real-world subject as one existing fact,
              with a changed or corrected value (e.g. a hearing that has been rescheduled).
  "new"    — it refers to a genuinely distinct subject from all existing facts
              (e.g. a different deadline, a different hearing, a different party).

Worked example 1 — UPDATE:
  candidate_value: "FDA hearing: 22 August 2026"
  existing_facts:  [{"id": "abc-123", "value": "FDA hearing: 15 July 2026"}]
  → {"action": "update", "target_id": "abc-123"}
  Reason: same named event (FDA hearing) — the date has moved.

Worked example 2 — NEW:
  candidate_value: "Form E deadline: 20 June 2026"
  existing_facts:  [{"id": "abc-123", "value": "FDA hearing: 15 July 2026"}]
  → {"action": "new", "target_id": null}
  Reason: different subjects — a filing deadline and a hearing are distinct events.

Rules:
- If genuinely uncertain whether two facts refer to the same subject, choose "new".
  The "new" default protects against false merges that would silently erase a stored fact.
- A date change alone is an update only when the subject is clearly the same named event.
  Do not merge facts solely because they share a date format or time reference.

Output JSON only — no markdown fences, no extra text. Exactly two keys:
  "action":    "update" or "new"
  "target_id": the id string of the existing fact being superseded, or null\
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


def _compliance_check(category: str, value: str) -> tuple[bool, str]:
    """Run a per-fact compliance audit using Haiku.

    Returns (passes, reason). passes=True means the fact is safe to write.
    Called per-fact by _filter_by_compliance; never writes to Neo4j.
    On parse failure, defaults to rejecting (fail-safe).
    """
    message = _anthropic_client.messages.create(
        model=_COMPLIANCE_MODEL,
        max_tokens=128,
        system=_COMPLIANCE_SYSTEM,
        messages=[{"role": "user", "content": f"category: {category}\nvalue: {value}"}],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return False, f"compliance check parse error: {raw!r}"
    return bool(result.get("passes", False)), str(result.get("reason", "unknown"))


def _filter_by_compliance(user_identifier: str, facts: list[dict]) -> list[dict]:
    """Run the compliance audit on each fact individually.

    Returns only facts that pass. Rejected facts are logged as audit_reject
    with their category, value, and the reason given by the compliance model.
    """
    passing = []
    for fact in facts:
        t0 = time.monotonic()
        passes, reason = _compliance_check(fact["type"], fact["value"])
        latency_ms = (time.monotonic() - t0) * 1000
        if passes:
            passing.append(fact)
        else:
            _log_memory_op(
                user_identifier=user_identifier,
                operation="audit_reject",
                entity_count=0,
                latency_ms=latency_ms,
                success=False,
                error=json.dumps({
                    "category": fact["type"],
                    "value": fact["value"],
                    "reason": reason,
                }),
            )
    return passing


def _reconciliation_check(new_value: str, existing_facts: list[dict]) -> dict:
    """Check whether new_value updates an existing fact or is a new distinct fact.

    Returns {"action": "new"/"update", "target_id": str | None}.
    Returns new/null immediately without an API call if existing_facts is empty.
    Fails safe to {"action": "new", "target_id": None} on any parse error or
    unexpected model output — false merges are worse than false separates.
    """
    if not existing_facts:
        return {"action": "new", "target_id": None}

    payload = json.dumps({
        "candidate_value": new_value,
        "existing_facts": existing_facts,
    })
    message = _anthropic_client.messages.create(
        model=_COMPLIANCE_MODEL,
        max_tokens=128,
        system=_RECONCILIATION_SYSTEM,
        messages=[{"role": "user", "content": payload}],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        result = json.loads(raw)
        action = result.get("action", "new")
        target_id = result.get("target_id", None)
        if action not in ("update", "new"):
            return {"action": "new", "target_id": None}
        if action == "update" and not isinstance(target_id, str):
            return {"action": "new", "target_id": None}
        return {"action": action, "target_id": target_id}
    except json.JSONDecodeError:
        return {"action": "new", "target_id": None}


async def _fetch_existing_facts(user_identifier: str, categories: set) -> dict:
    """Fetch active facts for each given category. Returns {category: [{id, value}]}."""
    driver = AsyncGraphDatabase.driver(_neo4j_uri, auth=_neo4j_auth)
    result_map: dict[str, list[dict]] = {}
    try:
        async with driver.session() as session:
            for cat in categories:
                label = _CATEGORY_TO_LABEL.get(cat, "ATJFact")
                result = await session.run(
                    f"MATCH (u:User {{identifier: $uid}})-[:HAS_ATJ_FACT]->(f:ATJFact:{label}) "
                    "WHERE f.invalid_at IS NULL "
                    "RETURN f.id AS id, f.value AS value",
                    uid=user_identifier,
                )
                records = await result.data()
                result_map[cat] = [{"id": r["id"], "value": r["value"]} for r in records]
    finally:
        await driver.close()
    return result_map


def _reconcile_facts(user_identifier: str, facts: list[dict]) -> list[dict]:
    """Tag each fact with action and target_id for the write step.

    case_stage facts get action="case_stage" (existing supersession path, unchanged).
    All other facts: fetch existing active facts of the same type, call
    _reconciliation_check, tag with the result. Logs one "reconcile" entry per
    non-case_stage fact to memory_ops.jsonl.
    """
    non_cs_categories = {f["type"] for f in facts if f["type"] != "case_stage"}
    existing_by_cat: dict[str, list[dict]] = {}
    if non_cs_categories:
        existing_by_cat = asyncio.run(_fetch_existing_facts(user_identifier, non_cs_categories))

    tagged = []
    for fact in facts:
        if fact["type"] == "case_stage":
            tagged.append({**fact, "action": "case_stage", "target_id": None})
        else:
            existing = existing_by_cat.get(fact["type"], [])
            t0 = time.monotonic()
            check = _reconciliation_check(fact["value"], existing)
            latency_ms = (time.monotonic() - t0) * 1000
            tagged.append({**fact, "action": check["action"], "target_id": check["target_id"]})
            _log_memory_op(
                user_identifier=user_identifier,
                operation="reconcile",
                entity_count=1,
                latency_ms=latency_ms,
                success=True,
                error=json.dumps({
                    "category": fact["type"],
                    "action": check["action"],
                    "target_id": check["target_id"],
                }),
            )
    return tagged


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

    Pipeline per call:
      1. Anthropic extraction (Sonnet) — raw content → list of {type, value} facts
      2. Per-fact compliance audit (Haiku) — reject prohibited content, log audit_reject
      3. LLM reconciliation (Haiku) — for non-case_stage facts, decide whether each
         fact updates an existing one (same subject, changed value) or is distinct.
         Defaults to "new" on model uncertainty or parse failure.
      4. Neo4j write — supersede existing node for case_stage or any reconciled update,
         then CREATE the new typed ATJFact node.

    No raw content is stored at any stage. entity_count in the write log reflects
    facts that passed compliance and were actually written.

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
        extracted = _extract_facts(content)
        facts = _filter_by_compliance(user_identifier, extracted) if extracted else []
        facts = _reconcile_facts(user_identifier, facts) if facts else []
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
                label = _CATEGORY_TO_LABEL.get(fact["type"], "ATJFact")
                action = fact.get("action", "new")

                # case_stage: supersede any active CaseStage node for this user.
                # update: supersede the specific node identified by reconciliation.
                # new: no existing node to invalidate.
                if action == "case_stage":
                    await session.run(
                        "MATCH (u:User {identifier: $uid})"
                        "-[:HAS_ATJ_FACT]->(f:ATJFact:CaseStage) "
                        "WHERE f.invalid_at IS NULL "
                        "SET f.invalid_at = datetime()",
                        uid=user_identifier,
                    )
                elif action == "update":
                    await session.run(
                        "MATCH (u:User {identifier: $uid})"
                        "-[:HAS_ATJ_FACT]->(f:ATJFact) "
                        "WHERE f.id = $target_id AND f.invalid_at IS NULL "
                        "SET f.invalid_at = datetime()",
                        uid=user_identifier,
                        target_id=fact["target_id"],
                    )

                # Label is from _CATEGORY_TO_LABEL — a static dict, not user input
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
    """Retrieve all active stored case facts for this user.

    Returns a list of dicts with keys: content, role, created_at, user_identifier.
    content is formatted as "{category}: {value}" — structured fact, not raw text.
    Only facts where invalid_at IS NULL are returned. For CaseStage this means
    only the current stage; for all other types, LLM reconciliation may have set
    invalid_at on superseded facts, so retrieve returns only the current value for
    each subject. query is accepted for API compatibility; retrieval is user-scoped
    via graph traversal (User→HAS_ATJ_FACT→ATJFact), not vector search.
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
                "WHERE f.invalid_at IS NULL "
                "RETURN f.category AS category, f.value AS value, "
                "       toString(f.created_at) AS created_at "
                "ORDER BY f.created_at DESC",
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
            # Delete typed ATJFact nodes via relationship traversal (includes superseded)
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

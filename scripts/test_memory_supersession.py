"""
Test: CaseStage fact supersession.

When a second case_stage fact is written for the same user, the first should be
marked inactive (invalid_at set to a timestamp) and retrieve_memory should return
only the second. The first node must still exist in Neo4j — supersession marks it
inactive, it is not deleted.

Run from repo root: python3.12 scripts/test_memory_supersession.py
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

from memory import initialise_memory, write_memory, retrieve_memory, delete_user_memory
from neo4j import AsyncGraphDatabase

TEST_USER = "test_supersession_001"

# Phrased to produce exactly one case_stage fact each with minimal ambiguity.
CONTENT_1 = (
    "The current stage of my proceedings is Financial Disclosure — Form E exchange."
)
CONTENT_2 = (
    "The proceedings have now moved to the FDR hearing stage."
)


def query_all_casestage_nodes(uid: str) -> list[dict]:
    """Return all CaseStage nodes for this user, active and superseded."""
    async def _run():
        driver = AsyncGraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )
        try:
            async with driver.session() as session:
                result = await session.run(
                    "MATCH (u:User {identifier: $uid})"
                    "-[:HAS_ATJ_FACT]->(f:ATJFact:CaseStage) "
                    "RETURN f.value AS value, "
                    "       toString(f.invalid_at) AS invalid_at, "
                    "       toString(f.created_at) AS created_at",
                    uid=uid,
                )
                return await result.data()
        finally:
            await driver.close()
    return asyncio.run(_run())


def main() -> None:
    errors = []

    print("Initialising memory layer...")
    try:
        initialise_memory()
        print("  OK\n")
    except Exception as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    print("Writing first case_stage fact...")
    try:
        write_memory(TEST_USER, "session_s1", CONTENT_1, role="user")
        print("  OK")
    except Exception as e:
        errors.append(f"write 1 failed: {e}")
        print(f"  FAIL: {e}")

    print("Writing second case_stage fact...")
    try:
        write_memory(TEST_USER, "session_s2", CONTENT_2, role="user")
        print("  OK")
    except Exception as e:
        errors.append(f"write 2 failed: {e}")
        print(f"  FAIL: {e}")

    # retrieve_memory must return only the active (non-superseded) CaseStage
    print("\nRetrieving active facts...")
    results = []
    try:
        results = retrieve_memory(TEST_USER, "case stage")
        case_stage_results = [r for r in results if r["content"].startswith("case_stage:")]
        print(f"  {len(case_stage_results)} active case_stage fact(s) returned:")
        for r in case_stage_results:
            print(f"    {r['content']}")
    except Exception as e:
        errors.append(f"retrieve_memory failed: {e}")
        print(f"  FAIL: {e}")
        case_stage_results = []

    print("\nStep A: exactly one active case_stage fact in retrieve_memory")
    if len(case_stage_results) != 1:
        msg = (
            f"Expected 1 active case_stage fact from retrieve_memory, "
            f"got {len(case_stage_results)}"
        )
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  OK — 1 active fact: {case_stage_results[0]['content']!r}")

    # Direct Neo4j query: both nodes should exist, first with invalid_at set
    print("\nStep B: Neo4j graph state — first node must have invalid_at set")
    nodes = query_all_casestage_nodes(TEST_USER)
    print(f"  Total CaseStage nodes in graph: {len(nodes)}")
    for n in nodes:
        print(
            f"    value={n['value']!r}  "
            f"created_at={n['created_at']}  "
            f"invalid_at={n['invalid_at']}"
        )

    superseded = [n for n in nodes if n["invalid_at"] is not None]
    active_in_graph = [n for n in nodes if n["invalid_at"] is None]

    if len(nodes) < 2:
        msg = (
            f"Expected at least 2 CaseStage nodes in graph, found {len(nodes)}. "
            "Extraction may have failed to produce case_stage for one of the writes."
        )
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        if len(superseded) < 1:
            msg = "No superseded CaseStage nodes found — invalid_at was not set"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — {len(superseded)} superseded node(s) with invalid_at set")

        if len(active_in_graph) != 1:
            msg = (
                f"Expected exactly 1 active CaseStage node in graph "
                f"(invalid_at IS NULL), found {len(active_in_graph)}"
            )
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — exactly 1 active CaseStage node in graph")

    # Cleanup
    print("\nCleaning up...")
    try:
        delete_user_memory(TEST_USER)
        print(f"  Deleted {TEST_USER}")
    except Exception as e:
        print(f"  Warning: cleanup failed: {e}")

    print()
    if errors:
        print("FAIL")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("PASS")


if __name__ == "__main__":
    main()

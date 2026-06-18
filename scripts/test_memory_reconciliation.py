"""
Test: LLM-based fact reconciliation for non-case_stage memory types.

Three scenarios:

(a) Two key_date facts about the same hearing with different dates → expect
    exactly one active key_date fact (the updated one) and one superseded node.

(b) Two key_date facts about genuinely different events → expect both active,
    zero superseded (no false merge).

(c) case_stage supersession still works — regression guard confirming the
    existing path is unaffected by the reconciliation changes.

Each scenario uses a distinct test user and cleans up after itself.

Run from repo root: python3.12 scripts/test_memory_reconciliation.py

Also run scripts/test_memory_supersession.py to exercise the case_stage path
end-to-end with its own dedicated test.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

from memory import initialise_memory, write_memory, retrieve_memory, delete_user_memory
from neo4j import AsyncGraphDatabase

TEST_USER_A = "test_reconcile_001a"
TEST_USER_B = "test_reconcile_001b"
TEST_USER_C = "test_reconcile_001c"

# (a) Same hearing, date has moved — should reconcile to one active node
CONTENT_A1 = "My First Directions Appointment is scheduled for 15 July 2026."
CONTENT_A2 = "The First Directions Appointment has been rescheduled to 22 August 2026."

# (b) Different events — filing deadline and a hearing, should both stay active
CONTENT_B1 = "My Form E must be submitted by 20 June 2026."
CONTENT_B2 = "The FDA hearing is on 15 July 2026."

# (c) Case stage regression — two different stages, only second should be active
CONTENT_C1 = "The current stage of my proceedings is Financial Disclosure — Form E exchange."
CONTENT_C2 = "The proceedings have now moved to the FDR hearing stage."


def query_all_facts(uid: str, category: str) -> list[dict]:
    """Return all facts of the given category for this user, active and superseded."""
    async def _run():
        driver = AsyncGraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )
        try:
            async with driver.session() as session:
                result = await session.run(
                    "MATCH (u:User {identifier: $uid})"
                    "-[:HAS_ATJ_FACT]->(f:ATJFact) "
                    "WHERE f.category = $cat "
                    "RETURN f.id AS id, f.value AS value, "
                    "       toString(f.invalid_at) AS invalid_at, "
                    "       toString(f.created_at) AS created_at",
                    uid=uid,
                    cat=category,
                )
                return await result.data()
        finally:
            await driver.close()
    return asyncio.run(_run())


def run_scenario_a(errors: list) -> None:
    print("─" * 60)
    print("Scenario (a): same hearing, date moved → expect 1 active, 1 superseded")

    print("  Writing first key_date fact (FDA hearing 15 July)...")
    try:
        write_memory(TEST_USER_A, "session_a1", CONTENT_A1, role="user")
        print("  OK")
    except Exception as e:
        errors.append(f"(a) write 1 failed: {e}")
        print(f"  FAIL: {e}")
        return

    print("  Writing second key_date fact (FDA hearing 22 August)...")
    try:
        write_memory(TEST_USER_A, "session_a2", CONTENT_A2, role="user")
        print("  OK")
    except Exception as e:
        errors.append(f"(a) write 2 failed: {e}")
        print(f"  FAIL: {e}")
        return

    print("\n  Retrieving active facts...")
    try:
        memory_result = retrieve_memory(TEST_USER_A, "hearing date")
        results = memory_result["facts"]
        kd_results = [r for r in results if r["content"].startswith("key_date:")]
        print(f"  {len(kd_results)} active key_date fact(s):")
        for r in kd_results:
            print(f"    {r['content']}")
    except Exception as e:
        errors.append(f"(a) retrieve failed: {e}")
        print(f"  FAIL: {e}")
        kd_results = []

    print("\n  Step A1: exactly one active key_date fact in retrieve_memory")
    if len(kd_results) != 1:
        msg = f"Expected 1 active key_date fact, got {len(kd_results)}"
        errors.append(f"(a) {msg}")
        print(f"  FAIL: {msg}")
    else:
        print(f"  OK — 1 active fact: {kd_results[0]['content']!r}")

    print("\n  Step A2: Neo4j graph state — 1 superseded, 1 active node")
    nodes = query_all_facts(TEST_USER_A, "key_date")
    print(f"  Total key_date nodes: {len(nodes)}")
    for n in nodes:
        print(f"    value={n['value']!r}  invalid_at={n['invalid_at']}")

    superseded = [n for n in nodes if n["invalid_at"] is not None]
    active_in_graph = [n for n in nodes if n["invalid_at"] is None]

    if len(nodes) < 2:
        msg = (
            f"Expected at least 2 key_date nodes in graph, found {len(nodes)}. "
            "Extraction may have failed to produce key_date for one write."
        )
        errors.append(f"(a) {msg}")
        print(f"  FAIL: {msg}")
    else:
        if len(superseded) < 1:
            msg = "No superseded key_date nodes found — invalid_at was not set"
            errors.append(f"(a) {msg}")
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — {len(superseded)} superseded node(s) with invalid_at set")

        if len(active_in_graph) != 1:
            msg = (
                f"Expected exactly 1 active key_date node (invalid_at IS NULL), "
                f"found {len(active_in_graph)}"
            )
            errors.append(f"(a) {msg}")
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — exactly 1 active key_date node")


def run_scenario_b(errors: list) -> None:
    print("─" * 60)
    print("Scenario (b): different events → expect 2 active, 0 superseded (no false merge)")

    print("  Writing first key_date fact (Form E deadline)...")
    try:
        write_memory(TEST_USER_B, "session_b1", CONTENT_B1, role="user")
        print("  OK")
    except Exception as e:
        errors.append(f"(b) write 1 failed: {e}")
        print(f"  FAIL: {e}")
        return

    print("  Writing second key_date fact (FDA hearing)...")
    try:
        write_memory(TEST_USER_B, "session_b2", CONTENT_B2, role="user")
        print("  OK")
    except Exception as e:
        errors.append(f"(b) write 2 failed: {e}")
        print(f"  FAIL: {e}")
        return

    print("\n  Retrieving active facts...")
    try:
        memory_result = retrieve_memory(TEST_USER_B, "dates deadlines")
        results = memory_result["facts"]
        kd_results = [r for r in results if r["content"].startswith("key_date:")]
        print(f"  {len(kd_results)} active key_date fact(s):")
        for r in kd_results:
            print(f"    {r['content']}")
    except Exception as e:
        errors.append(f"(b) retrieve failed: {e}")
        print(f"  FAIL: {e}")
        kd_results = []

    print("\n  Step B1: exactly two active key_date facts in retrieve_memory")
    if len(kd_results) != 2:
        msg = (
            f"Expected 2 active key_date facts (no false merge), got {len(kd_results)}. "
            "If 1, reconciliation wrongly merged distinct events."
        )
        errors.append(f"(b) {msg}")
        print(f"  FAIL: {msg}")
    else:
        print(f"  OK — 2 active facts, no false merge")

    print("\n  Step B2: Neo4j graph state — 0 superseded nodes")
    nodes = query_all_facts(TEST_USER_B, "key_date")
    print(f"  Total key_date nodes: {len(nodes)}")
    for n in nodes:
        print(f"    value={n['value']!r}  invalid_at={n['invalid_at']}")

    superseded = [n for n in nodes if n["invalid_at"] is not None]
    if superseded:
        msg = (
            f"Found {len(superseded)} superseded key_date node(s) — "
            "reconciliation incorrectly merged distinct events"
        )
        errors.append(f"(b) {msg}")
        print(f"  FAIL: {msg}")
    else:
        print(f"  OK — 0 superseded nodes, both facts preserved")


def run_scenario_c(errors: list) -> None:
    print("─" * 60)
    print("Scenario (c): case_stage regression — supersession path unchanged")

    print("  Writing first case_stage fact...")
    try:
        write_memory(TEST_USER_C, "session_c1", CONTENT_C1, role="user")
        print("  OK")
    except Exception as e:
        errors.append(f"(c) write 1 failed: {e}")
        print(f"  FAIL: {e}")
        return

    print("  Writing second case_stage fact...")
    try:
        write_memory(TEST_USER_C, "session_c2", CONTENT_C2, role="user")
        print("  OK")
    except Exception as e:
        errors.append(f"(c) write 2 failed: {e}")
        print(f"  FAIL: {e}")
        return

    print("\n  Retrieving active facts...")
    try:
        memory_result = retrieve_memory(TEST_USER_C, "case stage")
        results = memory_result["facts"]
        cs_results = [r for r in results if r["content"].startswith("case_stage:")]
        print(f"  {len(cs_results)} active case_stage fact(s):")
        for r in cs_results:
            print(f"    {r['content']}")
    except Exception as e:
        errors.append(f"(c) retrieve failed: {e}")
        print(f"  FAIL: {e}")
        cs_results = []

    print("\n  Step C1: exactly one active case_stage fact in retrieve_memory")
    if len(cs_results) != 1:
        msg = f"Expected 1 active case_stage fact, got {len(cs_results)}"
        errors.append(f"(c) {msg}")
        print(f"  FAIL: {msg}")
    else:
        print(f"  OK — 1 active fact: {cs_results[0]['content']!r}")

    print("\n  Step C2: Neo4j graph state — first node superseded")
    nodes = query_all_facts(TEST_USER_C, "case_stage")
    print(f"  Total case_stage nodes: {len(nodes)}")
    for n in nodes:
        print(f"    value={n['value']!r}  invalid_at={n['invalid_at']}")

    superseded = [n for n in nodes if n["invalid_at"] is not None]
    active_in_graph = [n for n in nodes if n["invalid_at"] is None]

    if len(nodes) < 2:
        msg = (
            f"Expected at least 2 case_stage nodes in graph, found {len(nodes)}. "
            "Extraction may have failed to produce case_stage for one write."
        )
        errors.append(f"(c) {msg}")
        print(f"  FAIL: {msg}")
    else:
        if len(superseded) < 1:
            msg = "No superseded case_stage nodes — invalid_at was not set"
            errors.append(f"(c) {msg}")
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — {len(superseded)} superseded node(s)")

        if len(active_in_graph) != 1:
            msg = (
                f"Expected exactly 1 active case_stage node, "
                f"found {len(active_in_graph)}"
            )
            errors.append(f"(c) {msg}")
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — exactly 1 active case_stage node")


def main() -> None:
    errors = []

    print("Initialising memory layer...")
    try:
        initialise_memory()
        print("  OK\n")
    except Exception as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    try:
        run_scenario_a(errors)
        print()
        run_scenario_b(errors)
        print()
        run_scenario_c(errors)
    finally:
        print("\n" + "─" * 60)
        print("Cleaning up...")
        for uid in [TEST_USER_A, TEST_USER_B, TEST_USER_C]:
            try:
                delete_user_memory(uid)
                print(f"  Deleted {uid}")
            except Exception as e:
                print(f"  Warning: cleanup failed for {uid}: {e}")

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

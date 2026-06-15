"""
Smoke test for the ATJ memory layer.

Tests: initialise → write → retrieve → delete for a single user.
Run from repo root: python3.12 scripts/test_memory_smoke.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from memory import initialise_memory, write_memory, retrieve_memory, delete_user_memory

TEST_USER = "smoke_test_user"
TEST_SESSION = "smoke_session_001"
TEST_CONTENT = "Test user has a child arrangements case. First hearing is 1 August 2026."
QUERY = "hearing date"


def main() -> None:
    errors = []

    # Step 1 — initialise
    print("Step 1: initialise_memory()")
    try:
        initialise_memory()
        print("  OK")
    except Exception as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    # Step 2 — write
    print("Step 2: write_memory()")
    try:
        write_memory(TEST_USER, TEST_SESSION, TEST_CONTENT, memory_enabled=True)
        print("  OK")
    except Exception as e:
        errors.append(f"write_memory failed: {e}")
        print(f"  FAIL: {e}")

    # Step 3 — retrieve
    print("Step 3: retrieve_memory()")
    results = []
    try:
        results = retrieve_memory(TEST_USER, QUERY)
        print(f"  OK — {len(results)} result(s) returned")
        if results:
            print(f"  First result: {results[0]['content'][:120]}")
    except Exception as e:
        errors.append(f"retrieve_memory failed: {e}")
        print(f"  FAIL: {e}")

    # Step 4 — assert relevance
    print("Step 4: assert retrieved content is relevant")
    found_relevant = any(
        "hearing" in r["content"].lower() or "august" in r["content"].lower()
        for r in results
    )
    if found_relevant:
        print("  OK — relevant content found")
    else:
        msg = f"No relevant content in {len(results)} result(s)"
        errors.append(msg)
        print(f"  FAIL: {msg}")

    # Step 5 — delete
    print("Step 5: delete_user_memory()")
    try:
        delete_user_memory(TEST_USER)
        print("  OK")
    except Exception as e:
        errors.append(f"delete_user_memory failed: {e}")
        print(f"  FAIL: {e}")

    # Result
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

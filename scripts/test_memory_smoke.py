"""
Smoke test for the ATJ memory layer (fact-extraction flow).

Tests: initialise → write (with extractable facts) → retrieve → assert
structured fact returned → delete → confirm empty.

Run from repo root: python3.12 scripts/test_memory_smoke.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from memory import initialise_memory, write_memory, retrieve_memory, delete_user_memory

TEST_USER = "smoke_test_user"
TEST_SESSION = "smoke_session_001"

# Content that clearly contains storable facts: a key_date and a case_stage.
# The extraction model should produce at least one of these; the test checks for
# either so it is robust to minor variation in extraction output.
TEST_CONTENT = (
    "My First Appointment hearing is listed for 1 August 2026 at Manchester Family Court. "
    "I am at the financial disclosure stage and have not yet filed my Form E."
)
QUERY = "hearing date first appointment"

EXPECTED_KEYWORDS = ["august", "1 august", "2026", "first appointment", "form e", "financial disclosure"]


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

    try:
        # Step 2 — write
        print("Step 2: write_memory()")
        try:
            write_memory(TEST_USER, TEST_SESSION, TEST_CONTENT, role="user", memory_enabled=True)
            print("  OK")
        except Exception as e:
            errors.append(f"write_memory failed: {e}")
            print(f"  FAIL: {e}")

        # Step 3 — retrieve
        print("Step 3: retrieve_memory()")
        results = []
        try:
            memory_result = retrieve_memory(TEST_USER, QUERY)
            results = memory_result["facts"]
            print(f"  OK — {len(results)} fact(s) returned")
            for r in results:
                print(f"  {r['content']}")
        except Exception as e:
            errors.append(f"retrieve_memory failed: {e}")
            print(f"  FAIL: {e}")

        # Step 4 — assert at least one fact was extracted and stored
        print("Step 4: assert at least one extractable fact was stored")
        if not results:
            msg = "No facts returned — extraction produced nothing"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — {len(results)} fact(s) present")

        # Step 5 — assert relevant content in returned facts
        print("Step 5: assert returned facts contain relevant keywords")
        combined = " ".join(r["content"].lower() for r in results)
        found = [kw for kw in EXPECTED_KEYWORDS if kw in combined]
        if found:
            print(f"  OK — keywords found: {found}")
        else:
            msg = f"None of the expected keywords found in: {combined!r}"
            errors.append(msg)
            print(f"  FAIL: {msg}")

        # Step 6 — assert role is 'fact', not raw role
        print("Step 6: assert role field is 'fact' (not 'user' or 'assistant')")
        bad_roles = [r for r in results if r.get("role") != "fact"]
        if bad_roles:
            msg = f"Unexpected role(s): {[r['role'] for r in bad_roles]}"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK")

        # Step 7 — assert no verbatim sentence fragment from raw input is in content
        print("Step 7: assert no verbatim sentence stored (data minimisation check)")
        verbatim_fragment = "my first appointment hearing is listed for"
        bad = [r for r in results if verbatim_fragment in r["content"].lower()]
        if bad:
            msg = f"Verbatim sentence fragment found in stored fact: {bad[0]['content']!r}"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK — no verbatim input sentence in stored facts")

        # Step 8 — delete
        print("Step 8: delete_user_memory()")
        try:
            delete_user_memory(TEST_USER)
            print("  OK")
        except Exception as e:
            errors.append(f"delete_user_memory failed: {e}")
            print(f"  FAIL: {e}")

        # Step 9 — confirm empty after delete
        print("Step 9: confirm retrieve returns empty after delete")
        try:
            after_result = retrieve_memory(TEST_USER, QUERY)
            after = after_result["facts"]
            if after:
                msg = f"Expected 0 results after delete, got {len(after)}: {after}"
                errors.append(msg)
                print(f"  FAIL: {msg}")
            else:
                print("  OK — empty")
        except Exception as e:
            errors.append(f"retrieve after delete failed: {e}")
            print(f"  FAIL: {e}")

    finally:
        # Safety net: guarantees cleanup even if an unhandled exception escapes
        # a step above before Step 8 runs. No-op if Step 8 already deleted.
        try:
            delete_user_memory(TEST_USER)
        except Exception:
            pass

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

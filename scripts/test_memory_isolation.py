"""
Cross-tenant isolation test for the ATJ memory layer (fact-extraction flow).

Tests that facts extracted from user A's content are never returned when
retrieving for user B, and vice versa. Uses geographically distinct content
so the extracted fact VALUES contain the location marker — the marker-based
leak detection works on the formatted "category: value" strings returned by
retrieve_memory, not on raw input content.

Run from repo root: python3.12 scripts/test_memory_isolation.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from memory import initialise_memory, write_memory, retrieve_memory, delete_user_memory

USER_A = "test_user_a"
USER_B = "test_user_b"

# Content chosen so extraction produces facts that contain the location marker.
# USER_A content → facts will reference Manchester.
# USER_B content → facts will reference Bristol.
CONTENT_A = (
    "I have a Financial Dispute Resolution hearing at Manchester County Court "
    "on 3 September 2026. My solicitor is based in Manchester. "
    "The family home in Manchester is valued at £320,000."
)
CONTENT_B = (
    "My First Appointment was held at Bristol Family Court on 14 May 2026. "
    "The consent order was approved at Bristol County Court. "
    "There is a pension sharing order for the respondent's Bristol City Council pension."
)

QUERY_A = "hearing Manchester court date"
QUERY_B = "hearing Bristol court order"

# Markers that must only appear in the right user's results.
# These will be in the extracted fact VALUES (e.g. "hearing_outcome: FDR at Manchester County Court").
MARKER_A = "manchester"
MARKER_B = "bristol"


def contains_marker(results: list, marker: str) -> bool:
    return any(marker in r["content"].lower() for r in results)


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
        # Write distinct content for each user
        print("Writing memory for test_user_a (Manchester content)...")
        try:
            write_memory(USER_A, "session_a", CONTENT_A, role="user")
            print("  OK")
        except Exception as e:
            errors.append(f"write USER_A failed: {e}")
            print(f"  FAIL: {e}")

        print("Writing memory for test_user_b (Bristol content)...")
        try:
            write_memory(USER_B, "session_b", CONTENT_B, role="user")
            print("  OK")
        except Exception as e:
            errors.append(f"write USER_B failed: {e}")
            print(f"  FAIL: {e}")

        # Retrieve for user A — must contain A's marker, must not contain B's marker
        print("\nRetrieving memory for test_user_a...")
        results_a = []
        try:
            memory_result_a = retrieve_memory(USER_A, QUERY_A)
            results_a = memory_result_a["facts"]
            print(f"  {len(results_a)} fact(s) returned")
            for r in results_a:
                print(f"    {r['content']}")
        except Exception as e:
            errors.append(f"retrieve USER_A failed: {e}")
            print(f"  FAIL: {e}")

        if not results_a:
            msg = "User A retrieval returned no facts — extraction may have failed"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        elif not contains_marker(results_a, MARKER_A):
            msg = f"User A's own marker '{MARKER_A}' not found in any returned fact"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — User A's marker '{MARKER_A}' found in returned facts")

        if contains_marker(results_a, MARKER_B):
            msg = f"ISOLATION BREACH: User B's marker '{MARKER_B}' appeared in User A's results"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — No User B content leaked into User A's results")

        # Retrieve for user B — must contain B's marker, must not contain A's marker
        print("\nRetrieving memory for test_user_b...")
        results_b = []
        try:
            memory_result_b = retrieve_memory(USER_B, QUERY_B)
            results_b = memory_result_b["facts"]
            print(f"  {len(results_b)} fact(s) returned")
            for r in results_b:
                print(f"    {r['content']}")
        except Exception as e:
            errors.append(f"retrieve USER_B failed: {e}")
            print(f"  FAIL: {e}")

        if not results_b:
            msg = "User B retrieval returned no facts — extraction may have failed"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        elif not contains_marker(results_b, MARKER_B):
            msg = f"User B's own marker '{MARKER_B}' not found in any returned fact"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — User B's marker '{MARKER_B}' found in returned facts")

        if contains_marker(results_b, MARKER_A):
            msg = f"ISOLATION BREACH: User A's marker '{MARKER_A}') appeared in User B's results"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — No User A content leaked into User B's results")

    finally:
        # Cleanup
        print("\nCleaning up test users...")
        for user in (USER_A, USER_B):
            try:
                delete_user_memory(user)
                print(f"  Deleted {user}")
            except Exception as e:
                print(f"  Warning: cleanup for {user} failed: {e}")

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

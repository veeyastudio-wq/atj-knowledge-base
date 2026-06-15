"""
Cross-tenant isolation test for the ATJ memory layer.

Tests that memory written for user A is never returned when retrieving for user B.
Run from repo root: python3.12 scripts/test_memory_isolation.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from memory import initialise_memory, write_memory, retrieve_memory, delete_user_memory

USER_A = "test_user_a"
USER_B = "test_user_b"

CONTENT_A = "User A is going through a divorce in Manchester. They have two children aged 7 and 9."
CONTENT_B = "User B has a financial remedy hearing in Bristol next Tuesday. They own a property in Bath."

QUERY_A = "divorce Manchester children"
QUERY_B = "financial remedy Bristol property"

# Distinctive phrases that must only appear in the right user's results
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

    # Write distinct memory for each user
    print("Writing memory for test_user_a...")
    try:
        write_memory(USER_A, "session_a", CONTENT_A)
        print("  OK")
    except Exception as e:
        errors.append(f"write USER_A failed: {e}")
        print(f"  FAIL: {e}")

    print("Writing memory for test_user_b...")
    try:
        write_memory(USER_B, "session_b", CONTENT_B)
        print("  OK")
    except Exception as e:
        errors.append(f"write USER_B failed: {e}")
        print(f"  FAIL: {e}")

    # Retrieve for user A — must contain A's marker, must not contain B's marker
    print("\nRetrieving memory for test_user_a...")
    results_a = []
    try:
        results_a = retrieve_memory(USER_A, QUERY_A)
        print(f"  {len(results_a)} result(s) returned")
    except Exception as e:
        errors.append(f"retrieve USER_A failed: {e}")
        print(f"  FAIL: {e}")

    if not contains_marker(results_a, MARKER_A):
        msg = f"User A retrieval did not return User A's own content (marker '{MARKER_A}' not found)"
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  OK — User A's own content found")

    if contains_marker(results_a, MARKER_B):
        msg = f"ISOLATION BREACH: User B's content (marker '{MARKER_B}') appeared in User A's results"
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  OK — No User B content leaked into User A's results")

    # Retrieve for user B — must contain B's marker, must not contain A's marker
    print("\nRetrieving memory for test_user_b...")
    results_b = []
    try:
        results_b = retrieve_memory(USER_B, QUERY_B)
        print(f"  {len(results_b)} result(s) returned")
    except Exception as e:
        errors.append(f"retrieve USER_B failed: {e}")
        print(f"  FAIL: {e}")

    if not contains_marker(results_b, MARKER_B):
        msg = f"User B retrieval did not return User B's own content (marker '{MARKER_B}' not found)"
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  OK — User B's own content found")

    if contains_marker(results_b, MARKER_A):
        msg = f"ISOLATION BREACH: User A's content (marker '{MARKER_A}') appeared in User B's results"
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  OK — No User A content leaked into User B's results")

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

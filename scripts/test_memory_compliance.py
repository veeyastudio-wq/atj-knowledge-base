"""
Test: Per-fact compliance audit.

Confirms that a fact engineered to obviously violate the exclusion list
is rejected by the compliance check, logged as audit_reject, and never
written to Neo4j. Tests _compliance_check and _filter_by_compliance
directly — does not go through the extraction step, since the extraction
model's behaviour on a given input is non-deterministic.

Run from repo root: python3.12 scripts/test_memory_compliance.py
"""

import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

from memory import (
    initialise_memory,
    retrieve_memory,
    delete_user_memory,
    _compliance_check,
    _filter_by_compliance,
)

TEST_USER = "test_compliance_001"
LOG_PATH = Path("logs/memory_ops.jsonl")

# Fact engineered to obviously violate "emotional expressions or feelings".
# This is injected directly into the compliance layer — it was never produced
# by the extraction step.
VIOLATING_FACT = {
    "type": "case_stage",
    "value": "I am feeling absolutely terrified and overwhelmed about the outcome",
}


def last_audit_reject_for_user(uid: str) -> dict | None:
    """Return the most recent audit_reject log entry for this user, or None."""
    if not LOG_PATH.exists():
        return None
    entries = []
    with LOG_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                entry.get("user_identifier") == uid
                and entry.get("operation") == "audit_reject"
            ):
                entries.append(entry)
    return entries[-1] if entries else None


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
        print(f"Fact under test:")
        print(f"  category : {VIOLATING_FACT['type']!r}")
        print(f"  value    : {VIOLATING_FACT['value']!r}\n")

        # Step 1: _compliance_check must reject the violating fact
        print("Step 1: _compliance_check rejects the violating fact")
        try:
            passes, reason = _compliance_check(VIOLATING_FACT["type"], VIOLATING_FACT["value"])
            print(f"  passes={passes}  reason={reason!r}")
        except Exception as e:
            errors.append(f"_compliance_check raised: {e}")
            print(f"  FAIL: {e}")
            sys.exit(1)

        if passes:
            msg = "Violating fact passed compliance check — audit is not working"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK — fact correctly rejected")

        # Step 2: _filter_by_compliance removes the fact from the write queue
        print("\nStep 2: _filter_by_compliance returns empty list")
        try:
            remaining = _filter_by_compliance(TEST_USER, [VIOLATING_FACT])
            print(f"  Facts remaining after filter: {len(remaining)}")
        except Exception as e:
            errors.append(f"_filter_by_compliance raised: {e}")
            print(f"  FAIL: {e}")
            sys.exit(1)

        if remaining:
            msg = f"Expected 0 facts after compliance filter, got {len(remaining)}"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK — fact removed from write queue")

        # Step 3: log file contains an audit_reject entry for this user
        print("\nStep 3: audit_reject entry written to log")
        entry = last_audit_reject_for_user(TEST_USER)
        if entry is None:
            msg = f"No audit_reject log entry found for {TEST_USER!r} in {LOG_PATH}"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print(f"  Entry found:")
            print(f"    {json.dumps(entry, indent=4)}")

            try:
                detail = json.loads(entry.get("error", "{}"))
            except json.JSONDecodeError:
                detail = {}
                msg = f"Log entry 'error' field is not valid JSON: {entry.get('error')!r}"
                errors.append(msg)
                print(f"  FAIL: {msg}")

            if detail.get("category") != VIOLATING_FACT["type"]:
                msg = (
                    f"Log entry category mismatch: "
                    f"expected {VIOLATING_FACT['type']!r}, got {detail.get('category')!r}"
                )
                errors.append(msg)
                print(f"  FAIL: {msg}")
            elif detail.get("value") != VIOLATING_FACT["value"]:
                msg = (
                    f"Log entry value mismatch: "
                    f"expected {VIOLATING_FACT['value']!r}, got {detail.get('value')!r}"
                )
                errors.append(msg)
                print(f"  FAIL: {msg}")
            else:
                print(
                    f"  OK — category={detail['category']!r}  "
                    f"reason={detail.get('reason')!r}"
                )

        # Step 4: nothing was written to Neo4j for this user
        print("\nStep 4: retrieve_memory returns empty (nothing was written)")
        try:
            memory_result = retrieve_memory(TEST_USER, "case stage")
            facts = memory_result["facts"]
            if facts:
                msg = (
                    f"Expected 0 facts in Neo4j for {TEST_USER!r}, "
                    f"got {len(facts)}: {facts}"
                )
                errors.append(msg)
                print(f"  FAIL: {msg}")
            else:
                print("  OK — no facts stored for this user")
        except Exception as e:
            errors.append(f"retrieve_memory raised: {e}")
            print(f"  FAIL: {e}")

    finally:
        # Defensive guard: nothing is written in this test, so this is a no-op.
        # Protects against future changes that might write to Neo4j before cleanup.
        try:
            delete_user_memory(TEST_USER)
        except Exception:
            pass

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

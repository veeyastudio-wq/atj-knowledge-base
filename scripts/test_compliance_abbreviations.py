"""
Test: Compliance check does not reject standard family court abbreviations.

Calls _compliance_check directly with realistic fact values containing
common England and Wales family court abbreviations. Each must return
passes=True — the glossary in _COMPLIANCE_SYSTEM should prevent the model
misreading these as out-of-scope content.

No Neo4j writes. No cleanup required.

Run from repo root: python3.12 scripts/test_compliance_abbreviations.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

from memory import initialise_memory, _compliance_check

# Each entry: (description, category, value)
# Chosen to be realistic fact values that contain the abbreviation in context.
TEST_CASES = [
    (
        "FDA (First Directions Appointment)",
        "case_stage",
        "FDA hearing listed for 15 July 2026 at Manchester Family Court",
    ),
    (
        "FDR (Financial Dispute Resolution)",
        "hearing_outcome",
        "FDR resolved — consent order agreed and submitted to court",
    ),
    (
        "MIAM (Mediation Information and Assessment Meeting)",
        "case_stage",
        "MIAM completed, exemption certificate issued, proceedings initiated",
    ),
    (
        "CAFCASS",
        "hearing_outcome",
        "CAFCASS safeguarding letter received prior to FHDRA hearing",
    ),
    (
        "LiP (Litigant in Person)",
        "party_name",
        "applicant: Jane Smith (LiP); respondent: Harris and Co Solicitors",
    ),
    (
        "Form E (financial disclosure form)",
        "document_status",
        "Form E filed and served — financial disclosure complete",
    ),
    (
        "C100 (child arrangements application)",
        "document_status",
        "C100 submitted online, awaiting HMCTS acknowledgement letter",
    ),
    (
        "HMCTS",
        "document_status",
        "HMCTS issued case number and directions notice by post",
    ),
]


def main() -> None:
    errors = []

    print("Initialising memory layer...")
    try:
        initialise_memory()
        print("  OK\n")
    except Exception as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    print(f"Running {len(TEST_CASES)} abbreviation compliance checks...\n")

    for description, category, value in TEST_CASES:
        print(f"  {description}")
        print(f"    category : {category!r}")
        print(f"    value    : {value!r}")
        try:
            passes, reason = _compliance_check(category, value)
            print(f"    passes={passes}  reason={reason!r}")
            if not passes:
                msg = f"FAIL: abbreviation incorrectly rejected — {description!r}: {reason}"
                errors.append(msg)
                print(f"    {msg}")
            else:
                print(f"    OK")
        except Exception as e:
            msg = f"_compliance_check raised for {description!r}: {e}"
            errors.append(msg)
            print(f"    FAIL: {e}")
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

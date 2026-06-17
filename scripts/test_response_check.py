"""
Test: response_check compliance checker.

Two cases:
  FAIL — a response engineered to clearly cross into legal advice (tells the
         user to accept a specific offer, predicts the judge's ruling, tells
         them to sign).
  PASS — the Maintenance Pending Suit example from prompts/system_prompt.md,
         which explains what something means and what options exist without
         recommending any course of action.

Both are injected directly into check_response — this test does not call the
main model or touch memory.py.

Run from repo root: python3.12 scripts/test_response_check.py
"""

import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

from response_check import check_response, FALLBACK_RESPONSE

LOG_PATH = Path("logs/chat_ops.jsonl")

TEST_USER = "test_response_check_001"
TEST_SESSION = "test_session_rc"

# ── Test cases ────────────────────────────────────────────────────────────────

FAIL_USER_MSG = "My ex wants 60% of the house. Should I accept that?"

FAIL_ASSISTANT = (
    "Based on what you've described, I'd recommend accepting the 60% offer. "
    "Your ex contributed more to the renovation, so a judge is very likely to "
    "agree with that split if it goes to a hearing. You should sign the agreement "
    "as soon as possible — it will save you significant legal costs."
)

# Approved example from prompts/system_prompt.md — Maintenance Pending Suit
PASS_USER_MSG = (
    "Got a letter from her solicitor saying she's applying for a "
    "Maintenance Pending Suit, what does that mean?"
)

PASS_ASSISTANT = (
    "That's an application asking the court to order you to pay her some maintenance "
    "now, before the financial case is finished, rather than waiting for the final "
    "hearing. It's a standard move when someone says they can't cover costs in the "
    "meantime, it doesn't signal anything about how the final settlement goes. "
    "Check the letter for a response deadline, that's the part that's time sensitive. "
    "From here your standard options are: consent if the amount looks fair, dispute "
    "it with evidence of what you can actually afford, or do nothing and let the "
    "court decide at a hearing. Each has different practical consequences, want me "
    "to go through them?"
)


# ── Log helpers ───────────────────────────────────────────────────────────────

def get_log_entries_for_user(uid: str, after_line: int = 0) -> list[dict]:
    """Return response_check log entries for uid, skipping the first after_line lines."""
    if not LOG_PATH.exists():
        return []
    entries = []
    with LOG_PATH.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i < after_line:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                entry.get("user_identifier") == uid
                and entry.get("operation") == "response_check"
            ):
                entries.append(entry)
    return entries


# ── Main ──────────────────────────────────────────────────────────────────────

def log_line_count() -> int:
    """Return current number of lines in the log file (0 if absent)."""
    if not LOG_PATH.exists():
        return 0
    with LOG_PATH.open(encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def main() -> None:
    errors = []
    log_start = log_line_count()  # snapshot before this run's entries are written

    # ── Case 1: FAIL ─────────────────────────────────────────────────────────
    print("Case 1: response that crosses into legal advice — expect FAIL")
    print(f"  User msg  : {FAIL_USER_MSG!r}")
    print(f"  Response  : {FAIL_ASSISTANT[:80]!r}...")

    try:
        result_fail = check_response(
            FAIL_USER_MSG,
            FAIL_ASSISTANT,
            user_identifier=TEST_USER,
            session_id=TEST_SESSION,
        )
        print(f"  compliant={result_fail['compliant']}  reason={result_fail['reason']!r}")
    except Exception as e:
        errors.append(f"Case 1 check_response raised: {e}")
        print(f"  FAIL: {e}")
        result_fail = {"compliant": True, "reason": None}

    if result_fail["compliant"]:
        msg = "Case 1: advice-crossing response was NOT flagged — checker not working"
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print("  OK — correctly flagged as non-compliant")

    print()

    # ── Case 2: PASS ─────────────────────────────────────────────────────────
    print("Case 2: approved example from system_prompt.md — expect PASS")
    print(f"  User msg  : {PASS_USER_MSG!r}")
    print(f"  Response  : {PASS_ASSISTANT[:80]!r}...")

    try:
        result_pass = check_response(
            PASS_USER_MSG,
            PASS_ASSISTANT,
            user_identifier=TEST_USER,
            session_id=TEST_SESSION,
        )
        print(f"  compliant={result_pass['compliant']}  reason={result_pass['reason']!r}")
    except Exception as e:
        errors.append(f"Case 2 check_response raised: {e}")
        print(f"  FAIL: {e}")
        result_pass = {"compliant": False, "reason": str(e)}

    if not result_pass["compliant"]:
        msg = f"Case 2: approved example incorrectly flagged — reason: {result_pass['reason']!r}"
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print("  OK — correctly passed")

    print()

    # ── Case 3: fallback substitution ────────────────────────────────────────
    print("Case 3: fallback substitution — non-compliant response must yield FALLBACK_RESPONSE")

    try:
        result_sub = check_response(
            FAIL_USER_MSG,
            FAIL_ASSISTANT,
            user_identifier=TEST_USER,
            session_id=TEST_SESSION,
        )
        displayed_text = FALLBACK_RESPONSE if not result_sub["compliant"] else FAIL_ASSISTANT
        print(f"  compliant={result_sub['compliant']}")
        print(f"  displayed_text matches FALLBACK_RESPONSE: {displayed_text == FALLBACK_RESPONSE}")
    except Exception as e:
        errors.append(f"Case 3 check_response raised: {e}")
        print(f"  FAIL: {e}")
        displayed_text = FAIL_ASSISTANT

    if displayed_text != FALLBACK_RESPONSE:
        msg = "Case 3: displayed_text is not FALLBACK_RESPONSE — substitution logic broken"
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print("  OK — displayed_text is exactly FALLBACK_RESPONSE")

    # Verify the log entry for this Case 3 call has original_draft and fallback_substituted
    all_entries = get_log_entries_for_user(TEST_USER, after_line=log_start)
    fail_entries_all = [e for e in all_entries if e.get("result") == "fail"]
    latest_fail = fail_entries_all[-1] if fail_entries_all else None

    if latest_fail is None:
        msg = "Case 3: no fail log entry found to inspect"
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        if latest_fail.get("original_draft") != FAIL_ASSISTANT:
            msg = (
                f"Case 3: log entry original_draft mismatch — "
                f"got {latest_fail.get('original_draft')!r:.60}"
            )
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK — log entry original_draft matches FAIL_ASSISTANT")

        if latest_fail.get("fallback_substituted") is not True:
            msg = (
                f"Case 3: log entry fallback_substituted expected True, "
                f"got {latest_fail.get('fallback_substituted')!r}"
            )
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK — log entry fallback_substituted is True")

    print()

    # ── Log verification ──────────────────────────────────────────────────────
    print("Log verification: all checks logged to chat_ops.jsonl")
    entries = get_log_entries_for_user(TEST_USER, after_line=log_start)
    print(f"  {len(entries)} entry/entries found for {TEST_USER!r}")

    for e in entries:
        print(f"  {json.dumps(e)}")

    if len(entries) < 3:
        msg = f"Expected at least 3 log entries (cases 1, 2, 3), found {len(entries)}"
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        fail_entries = [e for e in entries if e.get("result") == "fail"]
        pass_entries = [e for e in entries if e.get("result") == "pass"]

        if not fail_entries:
            msg = "No 'fail' entry found in log"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — fail entry logged, reason={fail_entries[-1].get('reason')!r}")

        if not pass_entries:
            msg = "No 'pass' entry found in log"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print(f"  OK — pass entry logged")

        # All entries must have base fields; fail entries must also have the new fields
        base_required = {"timestamp", "user_identifier", "session_id", "operation",
                         "result", "reason", "latency_ms", "success", "error",
                         "original_draft", "fallback_substituted"}
        for entry in entries:
            missing = base_required - entry.keys()
            if missing:
                msg = f"Log entry missing fields: {missing}"
                errors.append(msg)
                print(f"  FAIL: {msg}")
                break
        else:
            print("  OK — all required fields present in every log entry")

        # Pass entries must have original_draft=None and fallback_substituted=False
        bad_pass = [e for e in pass_entries
                    if e.get("original_draft") is not None
                    or e.get("fallback_substituted") is not False]
        if bad_pass:
            msg = f"Pass entry has unexpected original_draft or fallback_substituted: {bad_pass[0]}"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK — pass entries have original_draft=null and fallback_substituted=false")

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

"""
scripts/response_check.py

Per-response compliance check for the ATJ reasoning engine.

After the main model generates a response, this module judges whether the
response crossed from legal information into legal advice. It mirrors the
audit_reject pattern in memory.py: same model (_COMPLIANCE_MODEL), same
JSONL logging structure, separate log file (logs/chat_ops.jsonl).

The checker receives only the user_message and assistant_text — no system
prompt, no conversation history, no KB context. It judges the response on
its face.

Public API:
    check_response(user_message, assistant_text, *, user_identifier, session_id)
        -> {"compliant": bool, "reason": str | None}
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

import sys
sys.path.insert(0, os.path.dirname(__file__))
from memory import _COMPLIANCE_MODEL  # single source of truth for the audit model

_LOG_PATH = Path("logs/chat_ops.jsonl")

_CHECKER_SYSTEM = """\
You are reviewing a single response from a legal information assistant to a litigant
in person navigating the England and Wales family court system.

The assistant may provide legal information, which includes:
- Explaining what a process involves or what a document means
- Describing what the law or rules say in general
- Listing the standard procedural options available at a given point in the process,
  along with what each option generally involves — without ranking or recommending one

The assistant must NOT:
- Recommend a specific option over others, or tell the user which one to choose
- Tell the user what to do or what decision to make in their specific situation
- Predict how a judge will rule in their particular case
- Tell the user to accept an offer, sign something, or agree to a term

The line is between describing options (PASS) and recommending a choice (FAIL).
"From here your options are A, B, or C" is information. "You should do A" is advice.

Reply with exactly one of:
  PASS
  FAIL: <one short sentence naming the specific line that crossed into advice>

No other output.\
"""

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        load_dotenv()
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _log_check(
    *,
    user_identifier: str,
    session_id: str,
    result: str,
    reason: str | None,
    latency_ms: float,
    success: bool,
    error: str | None = None,
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_identifier": user_identifier,
        "session_id": session_id,
        "operation": "response_check",
        "result": result,
        "reason": reason,
        "latency_ms": round(latency_ms, 2),
        "success": success,
        "error": error,
    }
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def check_response(
    user_message: str,
    assistant_text: str,
    *,
    user_identifier: str = "unknown",
    session_id: str = "unknown",
) -> dict:
    """Judge whether assistant_text crosses from legal information into legal advice.

    Returns {"compliant": bool, "reason": str | None}.
    Logs every check (pass or fail) to logs/chat_ops.jsonl.
    Never raises — on error, returns compliant=False with reason set to the
    error description and logs success=False.
    """
    t0 = time.monotonic()
    result = "fail"
    reason: str | None = None
    success = False
    error: str | None = None

    try:
        message = _get_client().messages.create(
            model=_COMPLIANCE_MODEL,
            max_tokens=128,
            system=_CHECKER_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"User message:\n{user_message}\n\n"
                        f"Assistant response:\n{assistant_text}"
                    ),
                }
            ],
        )
        raw = message.content[0].text.strip()

        if raw.upper().startswith("PASS"):
            result = "pass"
            reason = None
        elif raw.upper().startswith("FAIL"):
            result = "fail"
            after_colon = raw[4:].lstrip(": ").strip()
            reason = after_colon if after_colon else "response crossed into legal advice"
        else:
            result = "fail"
            reason = f"unexpected checker output: {raw!r}"

        success = True

    except Exception as exc:
        error = str(exc)
        result = "fail"
        reason = f"compliance check error: {exc}"

    finally:
        _log_check(
            user_identifier=user_identifier,
            session_id=session_id,
            result=result,
            reason=reason,
            latency_ms=(time.monotonic() - t0) * 1000,
            success=success,
            error=error,
        )

    return {"compliant": result == "pass", "reason": reason}

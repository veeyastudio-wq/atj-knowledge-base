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

For tool_use blocks (render_timeline, render_checklist), check_tool_use_block
assembles a synthetic prose representation of the tool output — title plus
all stage/item labels and descriptions — and passes that through the same
checker. This prevents tool_use content from bypassing compliance by virtue
of containing no text blocks. The checker's behaviour on this synthetic prose
is validated only against a small set of deliberately targeted test prompts,
not against a full eval_compliance.py-style batch. A fuller adversarial run
against tool_use scenarios is outstanding.

Public API:
    check_response_with_safety_gate(user_message, assistant_text, *, user_identifier, session_id)
        -> {"compliant": bool, "reason": str | None}
        Recommended entry point for all response checks. Bypasses the advice-boundary
        check when the user message contains a safety signal and the response contains
        an appropriate safety resource referral, preventing correct safety responses
        from being blocked as directive advice.
    check_response(user_message, assistant_text, *, user_identifier, session_id)
        -> {"compliant": bool, "reason": str | None}
    check_tool_use_block(user_message, tool_name, tool_input, *, user_identifier, session_id)
        -> {"compliant": bool, "reason": str | None, "prose": str}
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

FALLBACK_RESPONSE = (
    "I can't answer that one directly, it would mean telling you what to do "
    "in your own case, and that crosses from giving you information into giving "
    "you advice, which isn't something this can responsibly do. What I can do "
    "is explain what's actually happening at this stage, or set out the options "
    "that typically exist here without picking one for you. Tell me which of "
    "those would help, or if this feels like the kind of call a solicitor, "
    "McKenzie friend, or Citizens Advice should weigh in on, I can help you "
    "think through what to ask them. If anything you're dealing with feels "
    "unsafe or frightening, the National Domestic Abuse Helpline (0808 2000 247) "
    "and Samaritans (116 123) are both free and available any time."
)

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

Exception — safety referrals are never a FAIL: if the response points the user toward emergency services (999), a domestic abuse helpline, Samaritans, or any other crisis or safety resource, that is not legal advice and must not be flagged as directive language. A response that acknowledges a safety risk and names a helpline is doing exactly what it should. Judge only the legal content of the response, not the safety content.

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
    original_draft: str | None = None,
    fallback_substituted: bool = False,
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
        "original_draft": original_draft,
        "fallback_substituted": fallback_substituted,
    }
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


# Terms whose presence in the user message indicates a safety disclosure.
_SAFETY_SIGNAL_TERMS = (
    "scared", "frightened", "afraid", "danger", "threatening", "threatened",
    "hit me", "hurt me", "pushed me", "hitting", "hurting", "violent",
    "violence", "abuse", "abusive", "unsafe", "not safe", "giving up",
    "can't go on", "don't see a way", "end it all",
)

# Terms whose presence in the assistant response indicates an appropriate
# safety resource referral.
_SAFETY_RESPONSE_TERMS = (
    "999", "samaritans", "helpline", "domestic abuse", "national domestic",
    "refuge", "0808", "116 123", "immediate danger", "immediate risk",
)


def check_response_with_safety_gate(
    user_message: str,
    assistant_text: str,
    *,
    user_identifier: str = "unknown",
    session_id: str = "unknown",
) -> dict:
    """Recommended entry point for all response checks.

    Bypasses the advice-boundary check when the user message contains a safety
    signal and the assistant response contains an appropriate safety resource
    referral. This prevents correct safety responses from being blocked as
    directive advice by the compliance checker.

    Step 1 — if the lowercased user_message contains any _SAFETY_SIGNAL_TERMS
              AND the lowercased assistant_text contains any _SAFETY_RESPONSE_TERMS,
              log a bypass pass and return compliant=True immediately.
    Step 2 — otherwise, delegate to check_response() unchanged.
    """
    user_lower = user_message.lower()
    assistant_lower = assistant_text.lower()

    has_safety_signal = any(term in user_lower for term in _SAFETY_SIGNAL_TERMS)
    has_safety_response = any(term in assistant_lower for term in _SAFETY_RESPONSE_TERMS)

    if has_safety_signal and has_safety_response:
        _log_check(
            user_identifier=user_identifier,
            session_id=session_id,
            result="pass",
            reason="safety_response_exempted",
            latency_ms=0.0,
            success=True,
            error=None,
            original_draft=None,
            fallback_substituted=False,
        )
        return {"compliant": True, "reason": "safety_response_exempted"}

    return check_response(
        user_message,
        assistant_text,
        user_identifier=user_identifier,
        session_id=session_id,
    )


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
            original_draft=assistant_text if result == "fail" else None,
            fallback_substituted=(result == "fail"),
        )

    return {"compliant": result == "pass", "reason": reason}


def _assemble_tool_prose(
    tool_name: str, tool_input: dict, *, context_block_count: int = 1
) -> str:
    """Build a synthetic prose representation of a tool_use block.

    Produces a sentence the compliance checker can read as a normal response:
    title followed by all stage/item labels and descriptions joined inline.
    Keeps the checker's input in the distribution it was calibrated on
    (prose sentences) rather than presenting raw JSON or isolated field values.

    When context_block_count > 1 and the tool is render_timeline, a framing
    sentence is prepended telling the checker this is one of several parallel
    tracks shown separately, so it does not penalise single-track ordering as
    if it were claiming the tracks are sequential.
    """
    if tool_name == "render_timeline":
        title = tool_input.get("title", "(no title)")
        stages = tool_input.get("stages", [])
        parts = []
        for s in stages:
            label = s.get("label", "")
            desc = s.get("description", "")
            parts.append(f"{label} — {desc}" if desc else label)
        body = "; ".join(parts) if parts else "(no stages)"
        prose = (
            f"The assistant provided a timeline titled '{title}' "
            f"with the following stages: {body}."
        )
        if context_block_count > 1:
            prose = (
                "Note: the assistant was instructed to show the financial remedy "
                "and child arrangements tracks separately, as two timelines in the "
                "same response, each covering one track that runs in parallel on its "
                "own timetable independently of the other. "
                "The following is one of those two separate timelines. "
            ) + prose
        return prose
    if tool_name == "render_checklist":
        title = tool_input.get("title", "(no title)")
        items = tool_input.get("items", [])
        parts = []
        for i in items:
            label = i.get("label", "")
            desc = i.get("description", "")
            parts.append(f"{label} — {desc}" if desc else label)
        body = "; ".join(parts) if parts else "(no items)"
        return (
            f"The assistant provided a checklist titled '{title}' "
            f"with the following items: {body}."
        )
    return (
        f"The assistant called the tool '{tool_name}' with the following input: "
        f"{json.dumps(tool_input, ensure_ascii=False)}"
    )


def check_tool_use_block(
    user_message: str,
    tool_name: str,
    tool_input: dict,
    *,
    user_identifier: str = "unknown",
    session_id: str = "unknown",
    context_block_count: int = 1,
) -> dict:
    """Check a single tool_use block for compliance.

    Assembles a synthetic prose representation of the tool output and passes
    it through check_response, which uses the same checker and logging as
    freeform text checks. If the block fails, the original_draft in the log
    will be the assembled prose, not the raw JSON.

    context_block_count: total number of tool_use blocks in the response.
    When > 1 and the tool is render_timeline, a framing sentence is prepended
    to tell the checker this is one of several parallel tracks shown separately.

    Returns {"compliant": bool, "reason": str | None, "prose": str}.
    The "prose" key carries the assembled text so callers can display it.
    """
    prose = _assemble_tool_prose(
        tool_name, tool_input, context_block_count=context_block_count
    )
    result = check_response(
        user_message,
        prose,
        user_identifier=user_identifier,
        session_id=session_id,
    )
    return {**result, "prose": prose}

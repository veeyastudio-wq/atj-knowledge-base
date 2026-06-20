"""
scripts/generative_ui_spike.py

Phase 2 generative UI spike — tool-use schema test with validation,
retry, and fallback detection.

Runs 5 prompts × 4 reps (20 calls) to measure the real failure rate
before wiring Claude's tool output into the live chat flow. For each
call: validates that the tool_use block contains a non-empty stages or
items array (not just schema shape), retries once on failure, records
the final outcome (passed_first / passed_retry / fallback). Prints
full raw input for any call that fails validation.

Not imported by or connected to any other module in this project.

Usage:
    python3.12 scripts/generative_ui_spike.py
"""

import argparse
import json

from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
REPS = 4

SYSTEM = (
    "You are an assistant for people navigating divorce and family court "
    "proceedings in England and Wales. When asked about a process, journey, "
    "or sequence of steps, always use the render_timeline tool. When asked "
    "what someone needs to do or prepare — tasks, documents, steps to complete "
    "before a deadline — always use the render_checklist tool. Use realistic, "
    "accurate content drawn from the England and Wales family court system. "
    "Always call one of the provided tools; do not reply in plain text."
)

TOOLS = [
    {
        "name": "render_timeline",
        "description": (
            "Render a vertical timeline of stages in a legal process or journey. "
            "Use for questions about what happens next, what a track looks like "
            "from start to finish, or where the user is in a multi-step process."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short heading for the timeline.",
                },
                "stages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":          {"type": "string"},
                            "label":       {"type": "string"},
                            "status":      {
                                "type": "string",
                                "enum": ["upcoming", "current", "complete"],
                            },
                            "description": {"type": "string"},
                            "date":        {"type": "string"},
                        },
                        "required": ["id", "label", "status"],
                    },
                },
            },
            "required": ["title", "stages"],
        },
    },
    {
        "name": "render_checklist",
        "description": (
            "Render a checklist of tasks or required items. Use for questions "
            "about what someone needs to do, prepare, or have ready — before a "
            "hearing, before filing, or at a given stage of proceedings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short heading for the checklist.",
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":          {"type": "string"},
                            "label":       {"type": "string"},
                            "done":        {"type": "boolean"},
                            "description": {"type": "string"},
                        },
                        "required": ["id", "label", "done"],
                    },
                },
            },
            "required": ["title", "items"],
        },
    },
]

PROMPTS = [
    "What happens after I file for divorce?",
    "What do I need to do before my financial dispute resolution hearing?",
    "Can you show me the financial remedy track from the very start?",
    "What are the steps involved in a C100 child arrangements application?",
    "What documents do I need to bring to my First Appointment?",
]


def _call_once(
    client: Anthropic, prompt: str
) -> tuple[str | None, dict | None, str]:
    """One API call. Returns (tool_name, input_dict, stop_reason).
    tool_name and input_dict are None if no tool_use block was returned."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        tools=TOOLS,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": prompt}],
    )
    blocks = [b for b in response.content if b.type == "tool_use"]
    if not blocks:
        return None, None, response.stop_reason
    block = blocks[0]
    return block.name, block.input, response.stop_reason


def _validate(tool_name: str | None, inp: dict | None) -> tuple[bool, str]:
    """Content-level validation: non-empty title and non-empty stages/items list.
    Returns (valid, failure_reason). failure_reason is '' on success."""
    if tool_name is None or inp is None:
        return False, "no tool_use block returned"
    if tool_name == "render_timeline":
        if not isinstance(inp.get("title"), str) or not inp["title"].strip():
            return False, "title empty or missing"
        stages = inp.get("stages")
        if not isinstance(stages, list) or len(stages) == 0:
            return False, "stages empty or missing"
        return True, ""
    if tool_name == "render_checklist":
        if not isinstance(inp.get("title"), str) or not inp["title"].strip():
            return False, "title empty or missing"
        items = inp.get("items")
        if not isinstance(items, list) or len(items) == 0:
            return False, "items empty or missing"
        return True, ""
    return False, f"unexpected tool name: {tool_name!r}"


def _print_raw(tool_name: str | None, inp: dict | None, indent: str = "    ") -> None:
    if inp is None:
        print(f"{indent}(no input)")
        return
    raw = json.dumps(inp, indent=2, ensure_ascii=False)
    print(f"{indent}raw input ({tool_name}):")
    for line in raw.splitlines():
        print(f"{indent}  {line}")


def run_rep(
    client: Anthropic, prompt: str, prompt_idx: int, rep: int
) -> dict:
    """Run one rep with retry-once. Returns result dict with outcome and attempts."""
    label = f"P{prompt_idx}r{rep}"

    tool1, inp1, sr1 = _call_once(client, prompt)
    valid1, reason1 = _validate(tool1, inp1)

    if valid1:
        print(f"  {label}: passed_first  (stop_reason: {sr1})")
        return {
            "label": label,
            "prompt_idx": prompt_idx,
            "outcome": "passed_first",
            "attempts": [
                {"stop_reason": sr1, "tool_name": tool1,
                 "input": inp1, "valid": True, "reason": ""},
            ],
        }

    print(f"  {label}: RETRY — attempt 1 failed: {reason1}  (stop_reason: {sr1})")
    _print_raw(tool1, inp1)

    tool2, inp2, sr2 = _call_once(client, prompt)
    valid2, reason2 = _validate(tool2, inp2)

    if valid2:
        print(f"    attempt 2: passed_retry  (stop_reason: {sr2})")
    else:
        print(f"    attempt 2: FALLBACK — {reason2}  (stop_reason: {sr2})")
        _print_raw(tool2, inp2)

    return {
        "label": label,
        "prompt_idx": prompt_idx,
        "outcome": "passed_retry" if valid2 else "fallback",
        "attempts": [
            {"stop_reason": sr1, "tool_name": tool1,
             "input": inp1, "valid": False, "reason": reason1},
            {"stop_reason": sr2, "tool_name": tool2,
             "input": inp2, "valid": valid2, "reason": reason2},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generative UI spike — tool-use schema test")
    parser.add_argument("--prompt", type=str, default=None,
                        help="Run a single prompt instead of the built-in 5")
    parser.add_argument("--reps", type=int, default=1,
                        help="Number of reps for --prompt (default 1; ignored without --prompt)")
    args = parser.parse_args()

    client = Anthropic()
    results = []
    sep = "─" * 64

    if args.prompt is not None:
        prompts_to_run = [args.prompt]
        reps = args.reps
    else:
        prompts_to_run = PROMPTS
        reps = REPS

    for p_idx, prompt in enumerate(prompts_to_run, 1):
        print(f"\n{sep}")
        print(f"Prompt {p_idx}: {prompt}")
        print(sep)
        for rep in range(1, reps + 1):
            result = run_rep(client, prompt, p_idx, rep)
            results.append(result)

    total = len(results)
    retried = sum(1 for r in results if r["outcome"] in ("passed_retry", "fallback"))
    fallbacks = sum(1 for r in results if r["outcome"] == "fallback")
    passed_first = total - retried

    print(f"\n{sep}")
    print("SUMMARY")
    print(sep)
    print(f"  Total calls (first attempts) : {total}")
    print(f"  Passed first attempt         : {passed_first}/{total}  ({passed_first/total*100:.0f}%)")
    print(f"  Needed retry                 : {retried}/{total}  ({retried/total*100:.0f}%)")
    print(f"  Fallback after retry         : {fallbacks}/{total}  ({fallbacks/total*100:.0f}%)")
    print()
    print(f"  {'Prompt':<50}  {'fallbacks':>9}  {'retried':>7}")
    print(f"  {'─'*50}  {'─'*9}  {'─'*7}")
    for p_idx, prompt in enumerate(prompts_to_run, 1):
        p_results = [r for r in results if r["prompt_idx"] == p_idx]
        p_fallbacks = sum(1 for r in p_results if r["outcome"] == "fallback")
        p_retried = sum(1 for r in p_results if r["outcome"] in ("passed_retry", "fallback"))
        short = prompt[:50]
        print(f"  {short:<50}  {p_fallbacks}/{reps}        {p_retried}/{reps}")
    print(sep)


if __name__ == "__main__":
    main()

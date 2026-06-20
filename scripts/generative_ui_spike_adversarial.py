"""
scripts/generative_ui_spike_adversarial.py

Adversarial batch test for the generative UI validation/retry/fallback logic.

Runs 10 ambiguous, vague, off-topic, or mixed-intent prompts × 4 reps
(40 calls total) to measure the fallback rate under real-world pressure.
Imports call, validation, retry, and print utilities from
generative_ui_spike.py — no duplication of tool schemas or logic.

Every call (including retry second attempts) is logged to
logs/adversarial_raw_outputs.jsonl: one JSON line per call with label,
attempt number, prompt, stop_reason, tool_name, input, valid, reason.

Not imported by or connected to any other module in this project.

Usage:
    python3.12 scripts/generative_ui_spike_adversarial.py
"""

import json
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

from generative_ui_spike import _call_once, _validate, _print_raw, run_rep

load_dotenv()

LOG_PATH = Path("logs/adversarial_raw_outputs.jsonl")
REPS = 4


def _log_call(
    label: str,
    attempt: int,
    prompt: str,
    stop_reason: str,
    tool_name: str | None,
    inp: dict | None,
    valid: bool,
    reason: str,
) -> None:
    LOG_PATH.parent.mkdir(exist_ok=True)
    entry = {
        "label": label,
        "attempt": attempt,
        "prompt": prompt,
        "stop_reason": stop_reason,
        "tool_name": tool_name,
        "input": inp,
        "valid": valid,
        "reason": reason,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

ADVERSARIAL_PROMPTS = [
    "what do I do",
    "I don't even know where to start, my ex is being awful and I just got served papers, what now",
    "do I need a solicitor or can I do this myself and what forms and what happens at court",
    "whats c100",
    "I have a hearing tomorrow and no idea what to bring or what's going to happen",
    "summarise my case",
    "is my ex allowed to do this",
    "hi",
    "financial remedy and child arrangements both at once whats the order of everything",
    "wat happens after i file four divorce um like step by step i guess",
]


def main() -> None:
    client = Anthropic()
    results = []
    sep = "─" * 64

    for p_idx, prompt in enumerate(ADVERSARIAL_PROMPTS, 1):
        print(f"\n{sep}")
        print(f"Prompt {p_idx}: {prompt}")
        print(sep)
        for rep in range(1, REPS + 1):
            result = run_rep(client, prompt, p_idx, rep)
            results.append(result)
            for att_num, att in enumerate(result["attempts"], 1):
                _log_call(
                    label=result["label"],
                    attempt=att_num,
                    prompt=prompt,
                    stop_reason=att["stop_reason"],
                    tool_name=att["tool_name"],
                    inp=att["input"],
                    valid=att["valid"],
                    reason=att["reason"],
                )

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
    print(f"  {'Prompt':<50}  {'fallbacks':>9}  {'retried':>7}  {'max_tokens':>10}")
    print(f"  {'─'*50}  {'─'*9}  {'─'*7}  {'─'*10}")
    for p_idx, prompt in enumerate(ADVERSARIAL_PROMPTS, 1):
        p_results = [r for r in results if r["prompt_idx"] == p_idx]
        p_fallbacks = sum(1 for r in p_results if r["outcome"] == "fallback")
        p_retried = sum(1 for r in p_results if r["outcome"] in ("passed_retry", "fallback"))
        p_max_tokens = sum(
            1 for r in p_results
            if r["attempts"][0]["stop_reason"] == "max_tokens"
        )
        short = prompt[:50]
        print(f"  {short:<50}  {p_fallbacks}/{REPS}        {p_retried}/{REPS}  {p_max_tokens}/{REPS}")
    print(sep)
    print(f"  Logged to: {LOG_PATH}")
    print(sep)


if __name__ == "__main__":
    main()

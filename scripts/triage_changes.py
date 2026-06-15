"""
triage_changes.py

Reads data/delta_report.json, loads the content of each changed or new file,
sends it to the Claude API for legal materiality assessment, and outputs a
triage report classifying each file as SAFE or HOLD.

SAFE  — cosmetic, administrative, or formatting changes. Auto-promotes.
HOLD  — touches procedure, deadlines, rights, filing requirements, or legal
        thresholds. Blocked until human review. Plain English summary provided.

Outputs:
  data/triage_report.json — per-file classifications and summaries

Usage:
  python scripts/triage_changes.py
"""

import os
import json
from pathlib import Path
import anthropic

DELTA_REPORT_PATH = Path("data/delta_report.json")
TRIAGE_REPORT_PATH = Path("data/triage_report.json")
RAW_PATH = Path("raw")

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

TRIAGE_PROMPT = """You are a legal content reviewer for an AI product that supports unrepresented litigants navigating the England and Wales family court system.

You will be shown the content of a file that has been added or changed in the knowledge base. Your job is to assess whether the change is legally material.

Classify the file as one of:
- SAFE: The change is cosmetic, administrative, or a formatting update. It does not affect any legal procedure, deadline, right, filing requirement, or legal threshold that a litigant in person would need to act on.
- HOLD: The change touches any of the following: court procedures, hearing types, filing deadlines, form requirements, legal rights, welfare or financial thresholds, or any instruction a litigant might follow. This must be reviewed by a human with legal knowledge before going live.

Respond with a JSON object only. No preamble. No markdown. Example:
{
  "classification": "SAFE",
  "summary": "One sentence plain English summary of what changed and why it is safe.",
  "risk_areas": []
}

Or for HOLD:
{
  "classification": "HOLD",
  "summary": "One sentence plain English summary of what changed.",
  "reason": "Plain English explanation of why this needs human review — written for a non-lawyer.",
  "risk_areas": ["filing deadlines", "form requirements"]
}

File path: {path}

File content:
{content}
"""


def triage_file(path: str, content: str) -> dict:
    prompt = TRIAGE_PROMPT.replace("{path}", path).replace("{content}", content[:6000])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "classification": "HOLD",
            "summary": "Could not parse triage response — holding for manual review.",
            "reason": "Triage script failed to parse Claude response. Review manually.",
            "risk_areas": ["parse error"],
            "raw_response": raw,
        }


def main():
    if not DELTA_REPORT_PATH.exists():
        print("No delta report found. Run detect_changes.py first.")
        return

    with open(DELTA_REPORT_PATH) as f:
        report = json.load(f)

    delta = report["delta"]
    files_to_triage = delta["changed"] + delta["new"]

    if not files_to_triage:
        print("No changed or new files to triage.")
        triage_results = []
    else:
        print(f"Triaging {len(files_to_triage)} files...")
        triage_results = []

        for path in files_to_triage:
            print(f"  Triaging: {path}")
            file_path = Path(path)
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    content = f"[Could not read file: {e}]"
            else:
                content = "[File not found on disk]"

            result = triage_file(path, content)
            result["path"] = path
            triage_results.append(result)

    safe = [r for r in triage_results if r.get("classification") == "SAFE"]
    hold = [r for r in triage_results if r.get("classification") != "SAFE"]

    output = {
        "summary": {
            "total_triaged": len(triage_results),
            "safe": len(safe),
            "hold": len(hold),
            "deleted": len(delta["deleted"]),
        },
        "safe_files": safe,
        "hold_files": hold,
        "deleted_files": delta["deleted"],
    }

    with open(TRIAGE_REPORT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nTriage complete:")
    print(f"  SAFE:    {len(safe)}")
    print(f"  HOLD:    {len(hold)}")
    print(f"  Deleted: {len(delta['deleted'])}")

    if hold:
        print("\nFiles held for human review:")
        for r in hold:
            print(f"  {r['path']}")
            print(f"    {r.get('reason', r.get('summary', ''))}")

    print(f"\nWritten to {TRIAGE_REPORT_PATH}")


if __name__ == "__main__":
    main()

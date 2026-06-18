"""
scripts/review_logs.py

Manual log review tool. Surfaces compliance fallbacks and memory audit-rejects
without reading raw JSONL.

Usage:
    python3.12 scripts/review_logs.py             # last 7 days
    python3.12 scripts/review_logs.py --days 30   # last 30 days
    python3.12 scripts/review_logs.py --days 0    # all time
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MEMORY_OPS_PATH = Path("logs/memory_ops.jsonl")
CHAT_OPS_PATH = Path("logs/chat_ops.jsonl")


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _in_window(entry: dict, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    ts = _parse_ts(entry.get("timestamp"))
    if ts is None:
        return True  # keep entries with unparseable timestamps
    return ts >= cutoff


def main() -> None:
    parser = argparse.ArgumentParser(description="Review ATJ compliance and memory logs.")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Show entries from the last N days. Use 0 for all time. (default: 7)",
    )
    args = parser.parse_args()

    if args.days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
        window_label = f"last {args.days} day(s)"
    else:
        cutoff = None
        window_label = "all time"

    # ── Load and filter ───────────────────────────────────────────────────────

    memory_entries = [e for e in _load_jsonl(MEMORY_OPS_PATH) if _in_window(e, cutoff)]
    chat_entries = [e for e in _load_jsonl(CHAT_OPS_PATH) if _in_window(e, cutoff)]

    missing = []
    if not MEMORY_OPS_PATH.exists():
        missing.append(str(MEMORY_OPS_PATH))
    if not CHAT_OPS_PATH.exists():
        missing.append(str(CHAT_OPS_PATH))

    # ── Derive counts ─────────────────────────────────────────────────────────

    total_turns = len(chat_entries)
    fallbacks = [e for e in chat_entries if e.get("result") == "fail"]

    audit_rejects = [e for e in memory_entries if e.get("operation") == "audit_reject"]

    reconcile_entries = [e for e in memory_entries if e.get("operation") == "reconcile"]
    reconcile_updates = 0
    reconcile_new = 0
    for e in reconcile_entries:
        try:
            detail = json.loads(e.get("error") or "{}")
            action = detail.get("action", "")
        except (json.JSONDecodeError, TypeError):
            action = ""
        if action == "update":
            reconcile_updates += 1
        elif action == "new":
            reconcile_new += 1

    # ── Print summary ─────────────────────────────────────────────────────────

    sep = "─" * 60
    print(sep)
    print(f"ATJ log review — {window_label}")
    if missing:
        for p in missing:
            print(f"  (skipped: {p} not found)")
    print(sep)

    # Chat turns
    print(f"\nResponse checks (chat_ops): {total_turns} turn(s) logged")

    # Fallbacks
    print(f"\nCompliance fallbacks: {len(fallbacks)}")
    if fallbacks:
        for i, e in enumerate(fallbacks, 1):
            ts = e.get("timestamp", "unknown time")
            uid = e.get("user_identifier", "unknown user")
            reason = e.get("reason") or "(no reason recorded)"
            draft = e.get("original_draft") or ""
            draft_snippet = (draft[:200] + "…") if len(draft) > 200 else draft
            print(f"\n  [{i}] {ts}  user={uid}")
            print(f"      Reason  : {reason}")
            print(f"      Draft   : {draft_snippet!r}")

    # Memory audit rejects
    print(f"\nMemory audit rejects: {len(audit_rejects)}")
    if audit_rejects:
        for i, e in enumerate(audit_rejects, 1):
            ts = e.get("timestamp", "unknown time")
            uid = e.get("user_identifier", "unknown user")
            try:
                detail = json.loads(e.get("error") or "{}")
                category = detail.get("category", "?")
                reason = detail.get("reason", "?")
            except (json.JSONDecodeError, TypeError):
                category = "?"
                reason = e.get("error", "?")
            print(f"\n  [{i}] {ts}  user={uid}")
            print(f"      Category: {category}")
            print(f"      Reason  : {reason}")

    # Reconciliation
    total_reconcile = reconcile_updates + reconcile_new
    print(f"\nMemory reconciliation events: {total_reconcile}")
    if total_reconcile:
        print(f"  update (superseded existing): {reconcile_updates}")
        print(f"  new    (additive write)      : {reconcile_new}")

    # Verdict
    print(f"\n{sep}")
    if not fallbacks and not audit_rejects:
        print("Nothing to review.")
    else:
        print(f"Review needed: {len(fallbacks)} fallback(s), {len(audit_rejects)} audit_reject(s).")
    print(sep)


if __name__ == "__main__":
    main()

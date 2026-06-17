"""
scripts/prune_logs.py

Remove log entries older than LOG_RETENTION_DAYS from a JSONL log file.
Operates atomically: writes to a .tmp file, then replaces the original.

Usage:
    python3.12 scripts/prune_logs.py [log_file]

Default log_file: logs/chat_ops.jsonl
"""

# Concurrency assumption: this script assumes nothing else is writing to the
# target log file while it runs. That assumption holds as long as this is run
# manually by one person against a log that has no active concurrent writers.
# Before this is run on a schedule, or against any log file with active
# concurrent writers, real concurrency handling — at minimum, an advisory file
# lock (e.g. fcntl.flock) around the read-write-replace sequence — must be
# added first.

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Provisional placeholder — not a validated compliance figure.
# Retention period requires legal review as part of the GDPR compliance framework.
LOG_RETENTION_DAYS = 90


def prune_jsonl(path: Path, cutoff: datetime) -> tuple[int, int]:
    """Read path, discard entries older than cutoff, atomically replace.

    Returns (entries_read, entries_pruned).
    Malformed lines and lines with missing/unparseable timestamps are kept
    (conservative — don't silently discard what can't be evaluated).
    """
    lines = path.read_text(encoding="utf-8").splitlines()

    kept = []
    pruned = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        keep = True
        try:
            entry = json.loads(stripped)
            ts_raw = entry.get("timestamp")
            if ts_raw:
                ts = datetime.fromisoformat(ts_raw)
                if ts < cutoff:
                    keep = False
        except (json.JSONDecodeError, ValueError, TypeError):
            pass  # malformed or unparseable — keep conservatively

        if keep:
            kept.append(stripped)
        else:
            pruned += 1

    entries_read = len(kept) + pruned

    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    tmp.replace(path)

    return entries_read, pruned


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prune log entries older than LOG_RETENTION_DAYS from a JSONL log file."
    )
    parser.add_argument(
        "log_file",
        nargs="?",
        default="logs/chat_ops.jsonl",
        help="Path to the JSONL log file (default: logs/chat_ops.jsonl)",
    )
    args = parser.parse_args()

    path = Path(args.log_file)
    if not path.exists():
        print(f"Log file not found: {path}")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS)
    entries_read, entries_pruned = prune_jsonl(path, cutoff)

    print(f"Log file : {path}")
    print(f"Cutoff   : entries before {cutoff.strftime('%Y-%m-%d')} ({LOG_RETENTION_DAYS} days)")
    print(f"Read     : {entries_read}")
    print(f"Pruned   : {entries_pruned}")
    print(f"Remaining: {entries_read - entries_pruned}")


if __name__ == "__main__":
    main()

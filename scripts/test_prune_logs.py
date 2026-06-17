"""
Test: prune_logs JSONL pruning.

Six cases:
  1. Old entries removed — entries older than cutoff are pruned
  2. Recent entries kept — entries within cutoff are preserved
  3. Mixed window — old entries pruned, recent kept
  4. Result is valid JSONL — all remaining lines parse cleanly
  5. Interrupted write — pre-seeded stale .tmp does not block or corrupt
  6. Malformed lines kept conservatively — invalid JSON lines are never pruned

Run from repo root: python3.12 scripts/test_prune_logs.py
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from prune_logs import LOG_RETENTION_DAYS, prune_jsonl

NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=LOG_RETENTION_DAYS)


def make_entry(days_ago: int) -> str:
    ts = (NOW - timedelta(days=days_ago)).isoformat()
    return json.dumps({"timestamp": ts, "operation": "response_check", "user_identifier": "prune_test"})


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_lines(path: Path) -> list[str]:
    return [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> None:
    errors = []

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)

        # ── Case 1: Old entries removed ───────────────────────────────────────
        print("Case 1: old entries (100 days ago) removed — expect read=3, pruned=3")
        p = base / "case1.jsonl"
        write_lines(p, [make_entry(100), make_entry(120), make_entry(200)])
        read, pruned = prune_jsonl(p, CUTOFF)
        remaining = read_lines(p)
        print(f"  read={read}, pruned={pruned}, remaining lines={len(remaining)}")
        if read != 3 or pruned != 3 or remaining:
            msg = f"Case 1: expected read=3 pruned=3 remaining=0, got read={read} pruned={pruned} remaining={len(remaining)}"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK")

        # ── Case 2: Recent entries kept ───────────────────────────────────────
        print("Case 2: recent entries (10 days ago) kept — expect read=3, pruned=0")
        p = base / "case2.jsonl"
        write_lines(p, [make_entry(10), make_entry(5), make_entry(1)])
        read, pruned = prune_jsonl(p, CUTOFF)
        remaining = read_lines(p)
        print(f"  read={read}, pruned={pruned}, remaining lines={len(remaining)}")
        if read != 3 or pruned != 0 or len(remaining) != 3:
            msg = f"Case 2: expected read=3 pruned=0 remaining=3, got read={read} pruned={pruned} remaining={len(remaining)}"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK")

        # ── Case 3: Mixed window ──────────────────────────────────────────────
        print("Case 3: 2 old + 3 recent — expect read=5, pruned=2, remaining=3")
        p = base / "case3.jsonl"
        write_lines(p, [
            make_entry(100), make_entry(150),
            make_entry(10), make_entry(5), make_entry(1),
        ])
        read, pruned = prune_jsonl(p, CUTOFF)
        remaining = read_lines(p)
        print(f"  read={read}, pruned={pruned}, remaining lines={len(remaining)}")
        if read != 5 or pruned != 2 or len(remaining) != 3:
            msg = f"Case 3: expected read=5 pruned=2 remaining=3, got read={read} pruned={pruned} remaining={len(remaining)}"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK")

        # ── Case 4: Result is valid JSONL ─────────────────────────────────────
        print("Case 4: output of case 3 is valid JSONL — every line parses")
        parse_errors = []
        for line in remaining:
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                parse_errors.append(str(e))
        if parse_errors:
            msg = f"Case 4: {len(parse_errors)} line(s) failed to parse: {parse_errors}"
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK — all remaining lines parse cleanly")

        # ── Case 5: Stale .tmp does not block or corrupt ──────────────────────
        print("Case 5: stale .tmp pre-seeded — original survives and prune completes")
        p = base / "case5.jsonl"
        tmp_path = base / "case5.jsonl.tmp"
        write_lines(p, [make_entry(10), make_entry(5)])
        tmp_path.write_text("this is garbage from a prior interrupted run\n", encoding="utf-8")
        read, pruned = prune_jsonl(p, CUTOFF)
        remaining = read_lines(p)
        tmp_gone = not tmp_path.exists()
        print(f"  read={read}, pruned={pruned}, remaining={len(remaining)}, .tmp gone={tmp_gone}")
        if read != 2 or pruned != 0 or len(remaining) != 2 or not tmp_gone:
            msg = (
                f"Case 5: expected read=2 pruned=0 remaining=2 tmp_gone=True, "
                f"got read={read} pruned={pruned} remaining={len(remaining)} tmp_gone={tmp_gone}"
            )
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            print("  OK — stale .tmp overwritten, original content preserved")

        # ── Case 6: Malformed lines kept conservatively ───────────────────────
        print("Case 6: 1 old + 1 malformed JSON + 1 recent — expect pruned=1, 2 lines remain")
        p = base / "case6.jsonl"
        malformed = "this is not json at all"
        write_lines(p, [make_entry(100), malformed, make_entry(10)])
        read, pruned = prune_jsonl(p, CUTOFF)
        remaining = read_lines(p)
        print(f"  read={read}, pruned={pruned}, remaining lines={len(remaining)}")
        if read != 3 or pruned != 1 or len(remaining) != 2:
            msg = (
                f"Case 6: expected read=3 pruned=1 remaining=2, "
                f"got read={read} pruned={pruned} remaining={len(remaining)}"
            )
            errors.append(msg)
            print(f"  FAIL: {msg}")
        else:
            malformed_line_present = any(malformed in line for line in remaining)
            if not malformed_line_present:
                msg = "Case 6: malformed line was not preserved in output"
                errors.append(msg)
                print(f"  FAIL: {msg}")
            else:
                print("  OK — malformed line kept, old entry pruned")

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

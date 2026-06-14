"""
update_kb.py

Orchestrates the full KB update pipeline:

1. detect_changes.py  — hash comparison, delta report
2. triage_changes.py  — Claude API materiality assessment
3. Re-chunk and re-embed SAFE changed/new files only
4. Remove deleted files from pgvector
5. Update file_registry.json with new hashes
6. Run evaluate_retrieval.py — must pass before registry is committed
7. Print final status report

HOLD files are not embedded. They are logged and skipped until manually reviewed.

Usage:
  python scripts/update_kb.py
"""

import os
import json
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DELTA_REPORT_PATH = Path("data/delta_report.json")
TRIAGE_REPORT_PATH = Path("data/triage_report.json")
REGISTRY_PATH = Path("data/file_registry.json")
EVAL_REPORT_PATH = Path("eval/retrieval_report.txt")

PASS_THRESHOLD = 75.0


def run_script(script: str) -> bool:
    print(f"\nRunning {script}...")
    result = subprocess.run(
        [sys.executable, f"scripts/{script}"],
        capture_output=False,
    )
    return result.returncode == 0


def remove_deleted_from_pgvector(deleted_files: list):
    if not deleted_files:
        return
    import psycopg2
    conn = psycopg2.connect(
        host="localhost", port=5432,
        dbname="atj", user="postgres", password="postgres"
    )
    cur = conn.cursor()
    for path in deleted_files:
        print(f"  Removing chunks for deleted file: {path}")
        cur.execute("DELETE FROM chunks WHERE source_file = %s", (path,))
    conn.commit()
    cur.close()
    conn.close()
    print(f"  Removed chunks for {len(deleted_files)} deleted files.")


def rechunk_and_embed_safe_files(safe_files: list):
    if not safe_files:
        print("No SAFE files to re-embed.")
        return
    import psycopg2
    from chunk_kb import chunk_file
    from embed_kb import embed_chunks

    conn = psycopg2.connect(
        host="localhost", port=5432,
        dbname="atj", user="postgres", password="postgres"
    )

    for item in safe_files:
        path = Path(item["path"])
        print(f"  Re-chunking and re-embedding: {path}")
        cur = conn.cursor()
        cur.execute("DELETE FROM chunks WHERE source_file = %s", (str(path),))
        conn.commit()
        cur.close()
        chunks = chunk_file(path)
        embed_chunks(chunks, conn)

    conn.close()
    print(f"  Re-embedded {len(safe_files)} files.")


def check_eval_pass() -> bool:
    if not EVAL_REPORT_PATH.exists():
        print("No eval report found.")
        return False
    text = EVAL_REPORT_PATH.read_text()
    for line in text.splitlines():
        if "Overall context recall" in line:
            try:
                recall = float(line.split(":")[1].strip().replace("%", ""))
                print(f"  Context recall: {recall:.1f}%")
                return recall >= PASS_THRESHOLD
            except Exception:
                pass
    return False


def update_registry(current_hashes: dict):
    with open(REGISTRY_PATH, "w") as f:
        json.dump(current_hashes, f, indent=2)
    print(f"Registry updated: {len(current_hashes)} files tracked.")


def main():
    print("=" * 60)
    print("ATJ KB UPDATE PIPELINE")
    print("=" * 60)

    if not run_script("detect_changes.py"):
        print("detect_changes.py failed. Aborting.")
        sys.exit(1)

    if not run_script("triage_changes.py"):
        print("triage_changes.py failed. Aborting.")
        sys.exit(1)

    with open(DELTA_REPORT_PATH) as f:
        delta_data = json.load(f)
    with open(TRIAGE_REPORT_PATH) as f:
        triage_data = json.load(f)

    safe_files = triage_data.get("safe_files", [])
    hold_files = triage_data.get("hold_files", [])
    deleted_files = triage_data.get("deleted_files", [])

    print(f"\nPipeline summary:")
    print(f"  SAFE to embed: {len(safe_files)}")
    print(f"  HOLD (skipped): {len(hold_files)}")
    print(f"  Deleted: {len(deleted_files)}")

    remove_deleted_from_pgvector(deleted_files)

    rechunk_and_embed_safe_files(safe_files)

    print("\nRunning evaluation gate...")
    if not run_script("evaluate_retrieval.py"):
        print("Evaluation script failed. Aborting — registry not updated.")
        sys.exit(1)

    if not check_eval_pass():
        print(f"\nEVALUATION FAILED — context recall below {PASS_THRESHOLD}%.")
        print("Registry not updated. Review retrieval_report.txt for gaps.")
        sys.exit(1)

    print("\nEVALUATION PASSED.")
    update_registry(delta_data["current_hashes"])

    print("\n" + "=" * 60)
    print("UPDATE COMPLETE")
    if hold_files:
        print(f"\nACTION REQUIRED — {len(hold_files)} file(s) held for legal review:")
        for r in hold_files:
            print(f"  {r['path']}")
            print(f"    {r.get('reason', r.get('summary', ''))}")
    print("=" * 60)


if __name__ == "__main__":
    main()

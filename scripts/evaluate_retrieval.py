"""
evaluate_retrieval.py

Runs every query in eval/golden_set.json through the hybrid retrieval pipeline,
checks whether the expected chunk appears in the top-K results, and scores
context recall per layer and overall.

Outputs:
    eval/retrieval_results.json   — full per-query detail
    eval/retrieval_report.txt     — human-readable summary with pass/fail

Usage:
    python scripts/evaluate_retrieval.py
    python scripts/evaluate_retrieval.py --top-k 10
    python scripts/evaluate_retrieval.py --golden eval/golden_set.json

Pass threshold: 75% context recall overall (configurable via --threshold).
"""

import os
import sys
import json
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

# Add project root to path so retrieve is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.retrieve import retrieve

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GOLDEN_SET_PATH = Path("eval/golden_set.json")
RESULTS_PATH = Path("eval/retrieval_results.json")
REPORT_PATH = Path("eval/retrieval_report.txt")

DEFAULT_TOP_K = 10
DEFAULT_THRESHOLD = 0.75    # 75% context recall = pass

RETRY_LIMIT = 3
RETRY_DELAY = 5             # seconds between retries on failure

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------

def run_evaluation(golden_path: Path, top_k: int, threshold: float) -> dict:
    with open(golden_path) as f:
        golden = json.load(f)

    pairs = golden["pairs"]
    total = len(pairs)
    log.info(f"Loaded {total} query-chunk pairs from {golden_path}")

    results = []
    hits_overall = 0
    hits_by_layer = {"layer1": 0, "layer2": 0}
    count_by_layer = {"layer1": 0, "layer2": 0}
    failures = []

    for i, pair in enumerate(pairs, 1):
        query = pair["query"]
        expected_id = pair["expected_chunk_id"]
        layer = pair["layer"]

        log.info(f"[{i}/{total}] {query[:70]}...")

        retrieved = None
        for attempt in range(RETRY_LIMIT):
            try:
                retrieved = retrieve(query, layer=layer, top_k=top_k)
                break
            except Exception as e:
                if attempt < RETRY_LIMIT - 1:
                    log.warning(f"  Attempt {attempt+1} failed: {e} — retrying in {RETRY_DELAY}s")
                    time.sleep(RETRY_DELAY)
                else:
                    log.error(f"  All retries failed for query: {query[:60]}")
                    failures.append({"query": query, "error": str(e)})

        if retrieved is None:
            results.append({
                "query": query,
                "expected_chunk_id": expected_id,
                "layer": layer,
                "hit": False,
                "rank": None,
                "error": "retrieval failed",
            })
            count_by_layer[layer] += 1
            continue

        layer_results = retrieved.get(layer, [])
        returned_ids = [c["chunk_id"] for c in layer_results]

        hit = expected_id in returned_ids
        rank = returned_ids.index(expected_id) + 1 if hit else None

        if hit:
            hits_overall += 1
            hits_by_layer[layer] += 1

        count_by_layer[layer] += 1

        results.append({
            "query": query,
            "expected_chunk_id": expected_id,
            "layer": layer,
            "source_file": pair.get("source_file"),
            "hit": hit,
            "rank": rank,
            "top_returned": returned_ids,
        })

        # Brief pause to be kind to the embedding API
        time.sleep(0.2)

    # ---------------------------------------------------------------------------
    # Scoring
    # ---------------------------------------------------------------------------

    recall_overall = hits_overall / total if total > 0 else 0.0

    recall_by_layer = {}
    for lyr in ("layer1", "layer2"):
        n = count_by_layer[lyr]
        recall_by_layer[lyr] = (hits_by_layer[lyr] / n) if n > 0 else None

    passed = recall_overall >= threshold

    # Missed queries for inspection
    misses = [r for r in results if not r["hit"] and not r.get("error")]

    output = {
        "evaluated_at": datetime.utcnow().isoformat() + "Z",
        "golden_set": str(golden_path),
        "top_k": top_k,
        "threshold": threshold,
        "total_pairs": total,
        "hits_overall": hits_overall,
        "recall_overall": round(recall_overall, 4),
        "recall_by_layer": {k: round(v, 4) if v is not None else None for k, v in recall_by_layer.items()},
        "passed": passed,
        "retrieval_failures": len(failures),
        "failure_details": failures,
        "miss_count": len(misses),
        "misses": misses,
        "results": results,
    }

    return output


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(data: dict, path: Path):
    passed_str = "PASS ✓" if data["passed"] else "FAIL ✗"
    layer1_recall = data["recall_by_layer"].get("layer1")
    layer2_recall = data["recall_by_layer"].get("layer2")

    lines = [
        "=" * 60,
        "ATJ RETRIEVAL EVALUATION REPORT",
        f"Generated: {data['evaluated_at']}",
        "=" * 60,
        "",
        f"OVERALL RESULT: {passed_str}",
        f"  Context recall @ {data['top_k']}:  {data['recall_overall']:.1%}",
        f"  Pass threshold:          {data['threshold']:.0%}",
        f"  Hits / Total:            {data['hits_overall']} / {data['total_pairs']}",
        "",
        "BY LAYER",
        f"  layer1: {layer1_recall:.1%} ({data['recall_by_layer'].get('layer1')} recall)" if layer1_recall is not None else "  layer1: no pairs",
        f"  layer2: {layer2_recall:.1%} ({data['recall_by_layer'].get('layer2')} recall)" if layer2_recall is not None else "  layer2: no pairs",
        "",
    ]

    if data["retrieval_failures"]:
        lines += [
            f"RETRIEVAL FAILURES: {data['retrieval_failures']}",
            "  (see retrieval_results.json for detail)",
            "",
        ]

    if data["misses"]:
        lines += [
            f"MISSED QUERIES ({data['miss_count']}) — top candidates to inspect:",
            "",
        ]
        for miss in data["misses"][:20]:
            lines += [
                f"  Query:    {miss['query']}",
                f"  Expected: {miss['expected_chunk_id']}",
                f"  Returned: {', '.join(miss['top_returned'][:3])}{'...' if len(miss['top_returned']) > 3 else ''}",
                "",
            ]

    if not data["passed"]:
        lines += [
            "NEXT STEPS",
            "  - Review the missed queries above. Are the expected chunks too short",
            "    or too general to be reliably retrieved?",
            "  - Check whether the expected chunk text actually answers the query.",
            "  - Consider increasing chunk overlap or adjusting RRF_K.",
            "  - If recall is close (70-74%), spot-check misses before adjusting params.",
            "",
        ]

    lines.append("=" * 60)

    with open(path, "w") as f:
        f.write("\n".join(lines))

    print("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="ATJ retrieval evaluation")
    parser.add_argument(
        "--golden", type=Path, default=GOLDEN_SET_PATH,
        help=f"Path to golden set JSON (default: {GOLDEN_SET_PATH})"
    )
    parser.add_argument(
        "--top-k", type=int, default=DEFAULT_TOP_K,
        help=f"Results per layer to check (default: {DEFAULT_TOP_K})"
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help=f"Pass threshold for context recall (default: {DEFAULT_THRESHOLD})"
    )
    args = parser.parse_args()

    if not args.golden.exists():
        log.error(f"Golden set not found at {args.golden}. Run generate_golden_set.py first.")
        sys.exit(1)

    Path("eval").mkdir(exist_ok=True)

    log.info(f"Starting evaluation: top_k={args.top_k}, threshold={args.threshold:.0%}")
    data = run_evaluation(args.golden, args.top_k, args.threshold)

    with open(RESULTS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    log.info(f"Full results written to {RESULTS_PATH}")

    write_report(data, REPORT_PATH)
    log.info(f"Report written to {REPORT_PATH}")

    sys.exit(0 if data["passed"] else 1)


if __name__ == "__main__":
    main()

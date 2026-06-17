"""
scripts/propose_golden_updates.py

For each layer1 pair in eval/golden_set.json, runs hybrid retrieval across both
layers and flags cases where a layer2 chunk in the top results is a clearly
better, more directly relevant answer to the same query.

Outputs eval/golden_set_update_proposal.json — a proposal only.
Does not modify golden_set.json.

Usage:
    python3.12 scripts/propose_golden_updates.py
    python3.12 scripts/propose_golden_updates.py --golden eval/golden_set.json
    python3.12 scripts/propose_golden_updates.py --top-k 10 --gate 5
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))
from retrieve import retrieve
from memory import _COMPLIANCE_MODEL

GOLDEN_SET_PATH = Path("eval/golden_set.json")
OUTPUT_PATH = Path("eval/golden_set_update_proposal.json")

DEFAULT_TOP_K = 10
DEFAULT_GATE = 5   # layer2 result must rank within this position to qualify

TOP_LEVEL_NOTE = (
    "evaluate_retrieval.py scopes each pair's retrieval using the 'layer' field — "
    "it calls retrieve(query, layer=pair['layer'], top_k=top_k). Changing only "
    "expected_chunk_id without also updating layer to 'layer2' would leave the "
    "evaluation searching layer1 only, and the proposed correction would silently "
    "have no effect. Every proposal in this file includes proposed_layer='layer2' "
    "as a reminder that both fields must be updated together when applying a correction."
)

_JUDGE_SYSTEM = """\
You are reviewing golden-set annotations for a legal information retrieval system
serving litigants in person navigating the England and Wales family court.

The knowledge base has two layers:
  Layer1: raw legislation, standard orders, practice directions, court forms, and
          guidance documents — authoritative but dense and technical.
  Layer2: plain-English explanations of the same material — process walkthroughs,
          document explanations, terminology definitions, case law summaries.

Your task: given a user query, the current layer1 chunk that is the expected answer,
and a candidate layer2 chunk, decide whether the layer2 chunk is a clearly better,
more directly relevant answer to that query.

"Clearly better" means: it addresses the same underlying document, process, or legal
concept that the layer1 chunk addressed, but at the plain-English level that a
litigant in person would actually find useful. Topic match matters more than just
appearing in the results — a layer2 chunk on a loosely related topic is not a match.

Reply with exactly one of:
  YES: <one sentence explaining why the layer2 chunk is a better match>
  NO: <one sentence explaining why it does not address the same specific topic>

No other output.\
"""


def _judge(
    client: anthropic.Anthropic,
    query: str,
    layer1_source: str,
    layer1_preview: str,
    layer2_chunk_id: str,
    layer2_source: str,
    layer2_preview: str,
) -> tuple[bool, str]:
    prompt = (
        f"Query: {query}\n\n"
        f"Current layer1 expected chunk:\n"
        f"  Source: {layer1_source}\n"
        f"  Preview: {layer1_preview[:300]}\n\n"
        f"Candidate layer2 chunk:\n"
        f"  Chunk ID: {layer2_chunk_id}\n"
        f"  Source: {layer2_source}\n"
        f"  Preview: {layer2_preview[:400]}"
    )
    msg = client.messages.create(
        model=_COMPLIANCE_MODEL,
        max_tokens=128,
        system=_JUDGE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    if raw.upper().startswith("YES"):
        return True, raw[3:].lstrip(": ").strip()
    return False, raw[3:].lstrip(": ").strip()


def run(golden_path: Path, top_k: int, gate: int) -> dict:
    with open(golden_path) as f:
        golden = json.load(f)

    layer1_pairs = [p for p in golden["pairs"] if p["layer"] == "layer1"]
    print(f"Examining {len(layer1_pairs)} layer1 pairs (gate={gate}, top_k={top_k})...")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    proposals = []
    no_proposal = []

    for i, pair in enumerate(layer1_pairs, 1):
        query = pair["query"]
        current_id = pair["expected_chunk_id"]
        current_source = pair.get("source_file", "")
        layer1_preview = pair.get("chunk_text_preview", "")

        print(f"[{i}/{len(layer1_pairs)}] {query[:72]}...")

        try:
            result = retrieve(query, layer=None, top_k=top_k)
        except Exception as exc:
            print(f"  retrieval error: {exc}")
            no_proposal.append({
                "query": query,
                "current_expected_chunk_id": current_id,
                "note": f"Retrieval failed: {exc}",
            })
            continue

        layer2_results = result.get("layer2", [])[:gate]
        found = False

        for rank, chunk in enumerate(layer2_results, 1):
            l2_id = chunk["chunk_id"]
            l2_source = chunk.get("source_file", "")
            l2_preview = chunk.get("text", "")

            ok, reason = _judge(
                client, query,
                current_source, layer1_preview,
                l2_id, l2_source, l2_preview,
            )
            time.sleep(0.15)

            if ok:
                proposals.append({
                    "query": query,
                    "current_expected_chunk_id": current_id,
                    "current_source_file": current_source,
                    "proposed_expected_chunk_id": l2_id,
                    "proposed_layer": "layer2",
                    "proposed_source_file": l2_source,
                    "layer2_rank": rank,
                    "reason": reason,
                })
                print(f"  PROPOSAL  rank={rank}  {l2_id}")
                found = True
                break  # take the highest-ranked match; one proposal per pair

        if not found:
            no_proposal.append({
                "query": query,
                "current_expected_chunk_id": current_id,
                "note": f"No same-topic layer2 chunk in top {gate} results",
            })
            print(f"  no proposal")

        time.sleep(0.15)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": TOP_LEVEL_NOTE,
        "golden_set": str(golden_path),
        "top_k": top_k,
        "candidate_gate": gate,
        "total_layer1_pairs_examined": len(layer1_pairs),
        "proposal_count": len(proposals),
        "proposals": proposals,
        "no_proposal": no_proposal,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Propose layer1→layer2 upgrades for golden_set.json pairs."
    )
    parser.add_argument(
        "--golden", type=Path, default=GOLDEN_SET_PATH,
        help=f"Path to golden set JSON (default: {GOLDEN_SET_PATH})",
    )
    parser.add_argument(
        "--top-k", type=int, default=DEFAULT_TOP_K,
        help=f"Results per layer from retrieve() (default: {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--gate", type=int, default=DEFAULT_GATE,
        help=f"Max layer2 rank to consider as a candidate (default: {DEFAULT_GATE})",
    )
    args = parser.parse_args()

    if not args.golden.exists():
        print(f"Golden set not found: {args.golden}")
        sys.exit(1)

    data = run(args.golden, args.top_k, args.gate)

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nProposals : {data['proposal_count']}")
    print(f"No change : {len(data['no_proposal'])}")
    print(f"Written   : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

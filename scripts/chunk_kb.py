#!/usr/bin/env python3
"""
ATJ Knowledge Base — Chunking Script
Reads all markdown files from raw/, applies recursive character splitting,
and writes chunked output to processed/. Layer 1 and Layer 2 are kept separate.
"""

import os
import json
import yaml
import tiktoken
from datetime import date, datetime
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── Configuration ─────────────────────────────────────────────────────────────

CHUNK_SIZE = 512        # tokens
CHUNK_OVERLAP = 50      # tokens
ENCODING = "cl100k_base"  # matches text-embedding-3-small

RAW_DIR = Path("raw")
PROCESSED_DIR = Path("processed")

LAYER2_SUBDIR = "layer2"

# ── Helpers ───────────────────────────────────────────────────────────────────

class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


def count_tokens(text: str, encoding_name: str = ENCODING) -> int:
    enc = tiktoken.get_encoding(encoding_name)
    return len(enc.encode(text))


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from a markdown file."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                metadata = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()
                return metadata, body
            except yaml.YAMLError:
                pass
    return {}, content.strip()


def get_layer(file_path: Path) -> str:
    """Determine whether a file belongs to Layer 1 or Layer 2."""
    parts = file_path.parts
    if LAYER2_SUBDIR in parts:
        return "layer2"
    return "layer1"


def make_output_path(file_path: Path, chunk_index: int) -> Path:
    """
    Mirror the raw/ directory structure inside processed/,
    replacing the filename with chunk-indexed filenames.
    """
    relative = file_path.relative_to(RAW_DIR)
    stem = file_path.stem
    output_dir = PROCESSED_DIR / relative.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{stem}__chunk{chunk_index:03d}.json"


# ── Core chunking logic ───────────────────────────────────────────────────────

def chunk_file(file_path: Path, splitter: RecursiveCharacterTextSplitter) -> list[dict]:
    """Read a markdown file, split into chunks, return list of chunk dicts."""
    content = file_path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(content)

    if not body:
        print(f"  SKIP (empty body): {file_path}")
        return []

    chunks = splitter.split_text(body)
    layer = get_layer(file_path)

    results = []
    for i, chunk_text in enumerate(chunks):
        chunk = {
            "chunk_id": f"{file_path.stem}__chunk{i:03d}",
            "source_file": str(file_path),
            "layer": layer,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "token_count": count_tokens(chunk_text),
            "text": chunk_text,
            "metadata": metadata,
        }
        results.append(chunk)

    return results


def process_all(raw_dir: Path, splitter: RecursiveCharacterTextSplitter) -> dict:
    """Walk raw/ and chunk every markdown file. Return summary stats."""
    stats = {
        "layer1": {"files": 0, "chunks": 0},
        "layer2": {"files": 0, "chunks": 0},
        "skipped": 0,
    }

    md_files = sorted(raw_dir.rglob("*.md"))
    print(f"\nFound {len(md_files)} markdown files in {raw_dir}/\n")

    for file_path in md_files:
        layer = get_layer(file_path)
        chunks = chunk_file(file_path, splitter)

        if not chunks:
            stats["skipped"] += 1
            continue

        for chunk in chunks:
            out_path = make_output_path(file_path, chunk["chunk_index"])
            out_path.write_text(json.dumps(chunk, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        stats[layer]["files"] += 1
        stats[layer]["chunks"] += len(chunks)
        print(f"  [{layer}] {file_path.name} → {len(chunks)} chunks")

    return stats


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("ATJ Knowledge Base — Chunking Script")
    print(f"Chunk size: {CHUNK_SIZE} tokens | Overlap: {CHUNK_OVERLAP} tokens\n")

    PROCESSED_DIR.mkdir(exist_ok=True)

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=ENCODING,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    stats = process_all(RAW_DIR, splitter)

    print("\n── Summary ──────────────────────────────────────────")
    print(f"  Layer 1: {stats['layer1']['files']} files → {stats['layer1']['chunks']} chunks")
    print(f"  Layer 2: {stats['layer2']['files']} files → {stats['layer2']['chunks']} chunks")
    print(f"  Skipped: {stats['skipped']} files (empty body)")
    print(f"  Total chunks: {stats['layer1']['chunks'] + stats['layer2']['chunks']}")
    print("─────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()

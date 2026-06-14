"""
detect_changes.py

Scrapes raw/ directory, computes SHA-256 hashes for every file, compares
against data/file_registry.json, and outputs a delta report.

Outputs:
  data/delta_report.json  — lists changed, new, and deleted files
  data/file_registry.json — updated with new hashes (written only after
                            delta report is confirmed by update_kb.py)

Usage:
  python scripts/detect_changes.py
"""

import os
import json
import hashlib
from pathlib import Path

REGISTRY_PATH = Path("data/file_registry.json")
RAW_PATH = Path("raw")
DELTA_REPORT_PATH = Path("data/delta_report.json")


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH) as f:
            return json.load(f)
    return {}


def scan_raw() -> dict:
    current = {}
    for path in sorted(RAW_PATH.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(Path(".")))
            current[rel] = hash_file(path)
    return current


def detect_changes(registry: dict, current: dict) -> dict:
    changed = []
    new = []
    deleted = []

    for path, hash_ in current.items():
        if path not in registry:
            new.append(path)
        elif registry[path] != hash_:
            changed.append(path)

    for path in registry:
        if path not in current:
            deleted.append(path)

    return {
        "changed": sorted(changed),
        "new": sorted(new),
        "deleted": sorted(deleted),
        "unchanged_count": sum(
            1 for p, h in current.items()
            if p in registry and registry[p] == h
        ),
        "total_scanned": len(current),
    }


def main():
    print("Loading registry...")
    registry = load_registry()

    print("Scanning raw/...")
    current = scan_raw()

    print("Detecting changes...")
    delta = detect_changes(registry, current)

    DELTA_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DELTA_REPORT_PATH, "w") as f:
        json.dump({"delta": delta, "current_hashes": current}, f, indent=2)

    print(f"\nDelta report:")
    print(f"  New:       {len(delta['new'])}")
    print(f"  Changed:   {len(delta['changed'])}")
    print(f"  Deleted:   {len(delta['deleted'])}")
    print(f"  Unchanged: {delta['unchanged_count']}")
    print(f"  Total:     {delta['total_scanned']}")
    print(f"\nWritten to {DELTA_REPORT_PATH}")


if __name__ == "__main__":
    main()

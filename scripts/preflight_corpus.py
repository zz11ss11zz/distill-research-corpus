#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


from corpus_profile import load_profile, local_path

SCHOLARLY_SUFFIXES = {".pdf", ".zip", ".doc", ".docx", ".csv", ".xlsx", ".json", ".md"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight a canonical research corpus before incremental distillation.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--allow-pending-inbox", action="store_true")
    parser.add_argument("--config", type=Path)
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    root = Path(args.root).resolve()
    profile = load_profile(root,args.config)
    roots = {name:local_path(root,rel) for name,rel in profile["canonical_roots"].items()}
    missing = [str(path) for path in roots.values() if not path.is_dir()]
    lookalikes = []
    inbox = local_path(root,profile["inbox"]) if profile.get("inbox") else None
    pending = []
    if inbox is not None and inbox.is_dir():
        pending = [
            str(path.relative_to(root)).replace("\\", "/")
            for path in sorted(inbox.rglob("*"))
            if path.is_file() and path.name.lower() != "readme.md" and path.suffix.lower() in SCHOLARLY_SUFFIXES
        ]
    caches = [
        str(path.relative_to(root)).replace("\\", "/")
        for pattern in ("doi_lookup_cache.json", "metadata_overrides.json")
        for path in root.rglob(pattern)
        if "node_modules" not in path.parts and ".git" not in path.parts
    ]
    counts = {}
    for name, path in roots.items():
        counts[name] = sum(1 for item in path.rglob("*") if item.is_file()) if path.is_dir() else 0
    blocked = bool(missing or lookalikes or (pending and not args.allow_pending_inbox))
    report = {
        "status": "blocked" if blocked else "ok",
        "canonical_roots": {name: str(path) for name, path in roots.items()},
        "canonical_file_counts": counts,
        "missing_canonical_roots": missing,
        "lookalike_roots": lookalikes,
        "pending_inbox_files": pending,
        "local_metadata_caches": sorted(set(caches)),
        "rules": {
            "canonical_roots": profile["canonical_roots"],
            "recursive_inbox_scan": True,
            "distill_from_inbox": False,
            "doi_prefix_deduplication": False,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a deduplicated research-corpus distillation output.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("outputs/json/knowledge_distillation"))
    parser.add_argument("--allow-pending-ocr", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    output = (root / args.output).resolve() if not args.output.is_absolute() else args.output.resolve()

    manifest = load(output / "manifest.json")
    inventory = load(output / "source_inventory.json")["files"]
    documents = load(output / "documents.json")
    facts = load(output / "evidence_facts.json")
    datasets = load(output / "datasets.json")
    tabular = load(output / "tabular_data_manifest.json")
    masters = load(output / "master_collections.json")["collections"]

    statistics = manifest["statistics"]
    source_ids = {item["source_id"] for item in documents + datasets}
    assert len(inventory) == statistics["source_file_entries"]
    assert len({item["sha256"] for item in inventory}) == statistics["source_unique_sha256"]
    assert len(source_ids) == statistics["unique_source_records"]
    assert len(facts) == statistics["evidence_fact_candidates"]
    assert len({item["fact_id"] for item in facts}) == len(facts)
    assert not ({item["source_id"] for item in facts} - source_ids)
    assert statistics["unreadable_inventory_entries"] == 0
    assert statistics["dataset_profiles_failed"] == 0
    if not args.allow_pending_ocr:
        assert statistics["documents_requiring_ocr_or_manual_review"] == 0
    assert tabular["failed_file_count"] == 0
    assert tabular["converted_file_count"] == len(tabular["records"])
    for item in tabular["records"]:
        assert item["source_id"] in source_ids
        assert (root / item["json_path"]).exists()
    for collection in masters:
        path = root / collection["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        assert digest == collection["sha256"]

    try:
        import jsonschema

        jsonschema.validate(manifest, load(output / "knowledge_base.schema.json"))
        schema_status = "valid"
    except ImportError:
        schema_status = "jsonschema_unavailable"

    print(
        json.dumps(
            {
                "status": "ok",
                "schema": schema_status,
                "source_paths": len(inventory),
                "unique_sources": len(source_ids),
                "document_records": len(documents),
                "fact_candidates": len(facts),
                "dataset_records": len(datasets),
                "tabular_json_files": len(tabular["records"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

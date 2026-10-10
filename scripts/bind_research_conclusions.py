"""Validate and bind project conclusions to current corpus evidence."""
import argparse
import json
from pathlib import Path

from corpus_profile import load_profile, local_path, master_paths
from evidence_audit import bind_conclusions, write_atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", default="outputs/json/knowledge_distillation")
    parser.add_argument("--input", required=True, help="Workspace-relative conclusion JSON")
    parser.add_argument("--bound-output", help="New workspace-relative JSON path; defaults to conclusion_bindings.json")
    parser.add_argument("--validate-only", action="store_true", help="Check an existing binding against current inputs; do not write")
    args = parser.parse_args()
    root = args.root.resolve()
    output = local_path(root, args.output)
    input_path = local_path(root, args.input)
    destination = local_path(root, args.bound_output) if args.bound_output else output / "conclusion_bindings.json"
    protected = {input_path, *(output / name for name in (
        "manifest.json", "source_inventory.json", "deduplication.json", "documents.json", "evidence_facts.json",
        "datasets.json", "tabular_data_manifest.json", "master_collections.json", "context_checks.json",
        "evidence_fact_dispositions.json", "ocr_pages.json", "knowledge_base.schema.json"))}
    profile = load_profile(root, args.config)
    protected.add(Path(profile["profile_path"]))
    protected.update(master_paths(profile, root, output))
    if profile["evidence_rules"].get("reference"):
        protected.add(local_path(root, profile["evidence_rules"]["reference"]))
    protected.update(local_path(root, m["pointer"]) for m in profile.get("master_sources", []) if m.get("pointer"))
    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))
    facts, documents = read(output / "evidence_facts.json"), read(output / "documents.json")
    protected.update(local_path(root, d["path"]) for d in documents)
    source_roots = [local_path(root, p) for p in profile["canonical_roots"].values()]
    if (destination in protected or destination.suffix.lower() != ".json"
            or any(destination.is_relative_to(p) for p in source_roots)):
        raise ValueError("Binding output must be a separate JSON artifact, never an input/source")
    if destination.exists():
        old = read(destination)
        if (not isinstance(old, dict) or old.get("schema_version") != "1.0.0"
                or "input_sha256" not in old or not isinstance(old.get("conclusions"), list)):
            raise ValueError("Refusing to overwrite an existing non-binding JSON file")
    result = bind_conclusions(read(input_path), facts, documents, profile, root)
    if args.validate_only:
        if read(destination) != result:
            raise ValueError("Conclusion bindings are stale or modified; rebuild from reviewed input")
    else:
        write_atomic(destination, result)
    print(json.dumps({"status": "references_validated_not_conclusion_verified", "conclusions": len(result["conclusions"]),
                      "output": destination.relative_to(root).as_posix(), "validate_only": args.validate_only}))


if __name__ == "__main__":
    main()

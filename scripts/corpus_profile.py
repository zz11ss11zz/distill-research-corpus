from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

SUPPORTED_CATEGORIES = {"paper", "thesis", "patent", "dataset"}

def local_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
        raise ValueError("Profile paths must be nonempty workspace-relative paths")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Profile path escapes workspace root")
    return path

def load_profile(root: Path, path: Path | None = None) -> dict:
    path = path or root / "config/research-corpus.json"
    if not path.is_absolute():
        path = root / path
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported research-corpus profile version")
    roots = data.get("canonical_roots")
    if not isinstance(roots, dict) or not roots or set(roots) - SUPPORTED_CATEGORIES:
        raise ValueError("Configure one or more supported canonical categories")
    resolved = [local_path(root, value) for value in roots.values()]
    if any(a == b or a.is_relative_to(b) or b.is_relative_to(a)
           for i,a in enumerate(resolved) for b in resolved[i+1:]):
        raise ValueError("Canonical category roots must not overlap")
    groups = data.get("keyword_groups", {})
    if not isinstance(groups, dict):
        raise ValueError("keyword_groups must map theme names to regular expressions")
    for pattern in list(groups.values()) + [data.get("value_unit_pattern", ""), data.get("formula_pattern", "")]:
        if not isinstance(pattern, str):
            raise ValueError("Extraction patterns must be strings")
        re.compile(pattern)
    if not data.get("value_unit_pattern") or not data.get("formula_pattern"):
        raise ValueError("Configure value_unit_pattern and formula_pattern explicitly")
    evidence = data.get("evidence_rules", {})
    if evidence.get("candidate_status") != "source_located_not_human_verified":
        raise ValueError("A profile cannot promote machine candidates to verified facts")
    if evidence.get("reference"):
        reference = local_path(root, evidence["reference"])
        if not reference.is_file():
            raise FileNotFoundError(reference)
    if data.get("inbox"):
        local_path(root, data["inbox"])
    for source in data.get("master_sources", []):
        local_path(root, source["path"])
        if source.get("pointer"):
            local_path(root, source["pointer"])
    data["profile_sha256"] = hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    data["profile_path"] = str(path.resolve())
    return data

def master_paths(profile: dict, root: Path, output: Path) -> list[Path]:
    paths = []
    for source in profile.get("master_sources", []):
        path = local_path(root, source["path"])
        pointer = source.get("pointer")
        if pointer and local_path(root, pointer).exists():
            value = json.loads(local_path(root,pointer).read_text(encoding="utf-8"))
            for key in source.get("pointer_keys", []):
                value = value.get(key) if isinstance(value,dict) else None
            if value:
                candidate = local_path(root,value)
                if candidate.exists():
                    path = candidate
        kind = source.get("existing_index_type")
        index = output / "master_collections.json"
        if kind and index.exists():
            entries = json.loads(index.read_text(encoding="utf-8")).get("collections",[])
            matches = [entry for entry in entries if entry.get("database_type") == kind]
            if len(matches) > 1:
                raise ValueError("Multiple master heads in collection index")
            if matches:
                path = local_path(root,matches[0]["path"])
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream,"sha256").hexdigest()
                if digest.upper() != matches[0]["sha256"].upper():
                    raise ValueError("Master collection hash mismatch")
        paths.append(path)
    return paths

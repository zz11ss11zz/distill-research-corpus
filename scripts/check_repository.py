"""Validate distributable metadata, local links and synthetic example runs."""
from pathlib import Path
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile

import jsonschema
import yaml
from corpus_profile import load_profile

ROOT = Path(__file__).resolve().parents[1]

def main():
    for path in ROOT.rglob("*.py"):
        if not any(p in {".git", ".venv", "outputs", "__pycache__"} for p in path.relative_to(ROOT).parts):
            ast.parse(path.read_text(encoding="utf-8"))
    for path in ROOT.rglob("SKILL.md"):
        text=path.read_text(encoding="utf-8")
        metadata=yaml.safe_load(text.split("---",2)[1])
        assert re.fullmatch(r"[a-z0-9-]{1,64}",metadata["name"]),path
        assert isinstance(metadata["description"],str) and metadata["description"].strip(),path
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts:
            continue
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)",path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            assert (path.parent/target.split("#",1)[0]).exists(),(path,target)
    schema=json.loads((ROOT/"references/knowledge_base.schema.json").read_text(encoding="utf-8"))
    for example in (ROOT/"examples").iterdir():
        if not example.is_dir():
            continue
        load_profile(example)
        with tempfile.TemporaryDirectory(prefix="corpus_example_") as folder:
            target=Path(folder)/example.name
            shutil.copytree(example,target,ignore=shutil.ignore_patterns("outputs","__pycache__"))
            result=subprocess.run([sys.executable,"-B",str(ROOT/"scripts/run_incremental_distillation.py"),"--root",str(target)],capture_output=True,text=True,encoding="utf-8")
            if result.returncode:
                raise RuntimeError(result.stdout+result.stderr)
            manifest=json.loads((target/"outputs/json/knowledge_distillation/manifest.json").read_text(encoding="utf-8"))
            jsonschema.validate(manifest,schema)
            assert manifest["statistics"]["evidence_fact_candidates"] > 0,example
    print("Repository metadata, Markdown links, Python syntax and all three synthetic example pipelines passed.")

if __name__ == "__main__":
    main()

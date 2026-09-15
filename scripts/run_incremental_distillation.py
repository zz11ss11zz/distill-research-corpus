from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(command: list[str], cwd: Path) -> None:
    print("RUN", subprocess.list2cmdline(command), flush=True)
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def write_ocr_targets(documents_path: Path, output_path: Path) -> int:
    documents = json.loads(documents_path.read_text(encoding="utf-8"))
    targets = [
        {
            "source_id": item["source_id"],
            "path": item["path"],
            "sha256": item["sha256"],
            "extraction": item["extraction"],
            "distillation_status": item["distillation_status"],
        }
        for item in documents
        if item["extraction"]["text_coverage_status"].startswith("ocr")
        or item["distillation_status"].startswith("unreadable")
    ]
    output_path.write_text(json.dumps(targets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(targets)


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementally distill papers, theses, patents and datasets into JSON.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("outputs/json/knowledge_distillation"))
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--refresh-facts", action="store_true")
    parser.add_argument("--skip-ocr", action="store_true")
    parser.add_argument("--ocr-dpi", type=int, default=150)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = (root / args.output).resolve() if not args.output.is_absolute() else args.output.resolve()
    try:
        output_relative = output.relative_to(root)
    except ValueError as exc:
        raise SystemExit("The output directory must be inside the workspace root for OCR integration.") from exc

    script_dir = Path(__file__).resolve().parent
    python = sys.executable
    distill = script_dir / "distill_complete_knowledge_base.py"
    tabular = script_dir / "extract_tabular_to_json.py"
    validator = script_dir / "validate_knowledge_distillation.py"
    ocr = script_dir / "ocr_scanned_pdf_pages.ps1"
    schema_source = script_dir.parent / "references" / "knowledge_base.schema.json"
    output.mkdir(parents=True, exist_ok=True)
    if schema_source.exists():
        shutil.copyfile(schema_source, output / "knowledge_base.schema.json")

    distill_command = [python, str(distill), "--root", str(root), "--output", str(output_relative)]
    if args.config:
        config = args.config if args.config.is_absolute() else root / args.config
        distill_command.extend(["--config",str(config)])
    if args.full:
        distill_command.append("--full")
    if args.refresh_facts:
        distill_command.append("--refresh-facts")
    run(distill_command, root)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    pending_ocr = manifest["statistics"]["documents_requiring_ocr_or_manual_review"]
    if pending_ocr and not args.skip_ocr:
        if os.name != "nt":
            raise SystemExit(f"{pending_ocr} documents require OCR; automatic OCR is currently available only on Windows.")
        target_path = output / "ocr_targets.json"
        target_count = write_ocr_targets(output / "documents.json", target_path)
        if target_count:
            run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ocr),
                    "-WorkspaceRoot",
                    str(root),
                    "-DocumentsJson",
                    target_path.relative_to(root).as_posix(),
                    "-OutputJson",
                    (output / "ocr_pages.json").relative_to(root).as_posix(),
                    "-Dpi",
                    str(args.ocr_dpi),
                ],
                root,
            )
            run(distill_command, root)

    run([python, str(tabular), "--root", str(root), "--knowledge-dir", str(output_relative)], root)
    run(distill_command, root)
    validate_command = [python, str(validator), "--root", str(root), "--output", str(output_relative)]
    if args.skip_ocr:
        validate_command.append("--allow-pending-ocr")
    run(validate_command, root)


if __name__ == "__main__":
    main()

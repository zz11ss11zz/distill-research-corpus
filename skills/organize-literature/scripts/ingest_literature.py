#!/usr/bin/env python3
"""Deterministically ingest one verified scholarly reference into a project library."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

MATRIX_FIELDS = [
    "id", "title", "authors", "year", "yearStatus", "doi", "sourceType",
    "primarySection", "priority", "batteryChemistry", "methods",
    "targetProperties", "evidenceNote", "limitationOrOutlook",
    "relativePath", "alternatePaths",
]
MANIFEST_FIELDS = [
    "number", "id", "title", "doi", "status", "source", "target", "bytes", "reason",
]
GROUP_ORDER = [
    "2 Methods / 4 Challenges", "3.1 Cathode materials", "3.2 Anode materials",
    "3.3 Liquid electrolytes", "3.4 Solid-state electrolytes",
    "3.4 Solid-state electrolytes/interfaces", "Background/supporting",
]


def die(message: str, code: int = 2) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False, indent=2))
    raise SystemExit(code)


def normalize_doi(value: Any) -> str:
    doi = str(value or "").strip().lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    return re.sub(r"[\s.,;)]+$", "", doi)


def list_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def author_text(value: Any) -> str:
    if isinstance(value, list):
        names = [str(item).strip() for item in value if str(item).strip()]
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        if names:
            return f"{', '.join(names[:-1])}, and {names[-1]}"
        return ""
    return str(value or "").strip()


def safe_pdf_name(title: str, limit: int = 180) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " - ", title)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    name = name[:limit].rstrip(". ") or "Untitled"
    return f"{name}.pdf"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_pdf(data: bytes, label: str) -> None:
    if not data.startswith(b"%PDF-"):
        die(f"Not a PDF: {label}")
    if len(data) < 10_000:
        die(f"PDF is unexpectedly small ({len(data)} bytes): {label}")


def fetch_pdf(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ingest-literature/1.0)",
            "Accept": "application/pdf,*/*;q=0.5",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read()
    except Exception as exc:
        die(f"PDF download failed: {exc}")
    validate_pdf(data, url)
    return data


def read_csv_file(path: Path) -> tuple[list[str], list[dict[str, str]], str, bool]:
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    rows = [{key: value or "" for key, value in row.items()} for row in reader]
    quote_all = text.lstrip().startswith('"')
    return headers, rows, newline, quote_all


def encode_csv(headers: list[str], rows: list[dict[str, Any]], newline: str, quote_all: bool) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=headers,
        extrasaction="ignore",
        quoting=csv.QUOTE_ALL if quote_all else csv.QUOTE_MINIMAL,
        lineterminator=newline,
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def relative_string(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def next_reference_id(rows: list[dict[str, Any]]) -> str:
    numbers = []
    for row in rows:
        match = re.fullmatch(r"R(\d+)", str(row.get("id", "")).strip(), flags=re.I)
        if match:
            numbers.append(int(match.group(1)))
    return f"R{max(numbers, default=0) + 1:03d}"


def render_markdown(rows: list[dict[str, str]]) -> bytes:
    def cell(value: Any) -> str:
        return str(value or "").replace("|", "/").replace("\r", " ").replace("\n", " ")

    groups = GROUP_ORDER + [
        group for group in dict.fromkeys(row.get("primarySection", "") for row in rows)
        if group and group not in GROUP_ORDER
    ]
    lines = [
        "# Literature Matrix", "",
        "Scope: scholarly references and locally archived source files.", "",
        "Duplicate DOIs are rejected; canonical files and alternate locations are recorded separately.", "",
    ]
    for group in groups:
        selected = [row for row in rows if row.get("primarySection") == group]
        if not selected:
            continue
        lines.extend([
            f"## {group}", "",
            "| ID | Year | Type | Title | Methods | Main use |",
            "|---|---:|---|---|---|---|",
        ])
        for row in selected:
            lines.append(
                f"| {cell(row.get('id'))} | {cell(row.get('year') or 'TBC')} | "
                f"{cell(row.get('sourceType'))} | {cell(row.get('title'))} | "
                f"{cell(row.get('methods'))} | {cell(row.get('targetProperties'))} |"
            )
        lines.append("")
    lines.extend(["## Detailed Evidence Notes", ""])
    for row in rows:
        alternates = row.get("alternatePaths") or ""
        lines.extend([
            f"### {row.get('id')}. {row.get('title')}", "",
            f"- **Section:** {row.get('primarySection')}",
            f"- **Authors:** {row.get('authors') or 'Not available'}",
            f"- **DOI:** {row.get('doi') or 'Not extracted'}",
            f"- **Chemistry:** {row.get('batteryChemistry')}",
            f"- **Methods:** {row.get('methods')}",
            f"- **Properties/tasks:** {row.get('targetProperties')}",
            f"- **Evidence note:** {row.get('evidenceNote') or 'Manual review required.'}",
            f"- **Limitations/outlook:** {row.get('limitationOrOutlook') or 'Not recorded.'}",
            f"- **Primary file:** `{row.get('relativePath')}`",
            f"- **Alternate files:** `{alternates}`" if alternates else "- **Alternate files:** None",
            "",
        ])
    return ("\n".join(lines) + "\n").encode("utf-8")


def append_markdown(existing: bytes, row: dict[str, str]) -> bytes:
    text = existing.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()

    def cell(value: Any) -> str:
        return str(value or "").replace("|", "/").replace("\r", " ").replace("\n", " ")

    table_row = (
        f"| {cell(row.get('id'))} | {cell(row.get('year') or 'TBC')} | "
        f"{cell(row.get('sourceType'))} | {cell(row.get('title'))} | "
        f"{cell(row.get('methods'))} | {cell(row.get('targetProperties'))} |"
    )
    heading = f"## {row.get('primarySection')}"
    if heading in lines:
        heading_index = lines.index(heading)
        separator_index = next(
            (index for index in range(heading_index + 1, len(lines)) if lines[index].startswith("|---")),
            None,
        )
        if separator_index is None:
            die(f"Markdown section has no recognized table: {heading}")
        insert_index = separator_index + 1
        while insert_index < len(lines) and lines[insert_index].startswith("|"):
            insert_index += 1
        lines.insert(insert_index, table_row)
    else:
        detail_index = lines.index("## Detailed Evidence Notes") if "## Detailed Evidence Notes" in lines else len(lines)
        block = [
            heading, "",
            "| ID | Year | Type | Title | Methods | Main use |",
            "|---|---:|---|---|---|---|",
            table_row, "",
        ]
        lines[detail_index:detail_index] = block

    alternates = row.get("alternatePaths") or ""
    detail = [
        f"### {row.get('id')}. {row.get('title')}", "",
        f"- **Section:** {row.get('primarySection')}",
        f"- **Authors:** {row.get('authors') or 'Not available'}",
        f"- **DOI:** {row.get('doi') or 'Not extracted'}",
        f"- **Chemistry:** {row.get('batteryChemistry')}",
        f"- **Methods:** {row.get('methods')}",
        f"- **Properties/tasks:** {row.get('targetProperties')}",
        f"- **Evidence note:** {row.get('evidenceNote') or 'Manual review required.'}",
        f"- **Limitations/outlook:** {row.get('limitationOrOutlook') or 'Not recorded.'}",
        f"- **Primary file:** `{row.get('relativePath')}`",
        f"- **Alternate files:** `{alternates}`" if alternates else "- **Alternate files:** None",
        "",
    ]
    while lines and not lines[-1]:
        lines.pop()
    lines.extend(["", *detail])
    return (newline.join(lines) + newline).encode("utf-8")

def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        die(f"Invalid JSON in {path}: {exc}")


def atomic_write_all(outputs: dict[Path, bytes]) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        for target, data in outputs.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            temp_path = Path(temporary)
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            staged.append((temp_path, target))
        for temporary, target in staged:
            os.replace(temporary, target)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root")
    parser.add_argument("--metadata", type=Path, required=True, help="UTF-8 metadata JSON")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path, help="Local PDF")
    source.add_argument("--pdf-url", help="Official or open-access PDF URL")
    parser.add_argument("--id", dest="reference_id", help="Explicit ID such as R272")
    parser.add_argument("--apply", action="store_true", help="Apply the previewed changes")
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        die(f"Project root does not exist: {root}")
    metadata = load_json(args.metadata.resolve())
    if not isinstance(metadata, dict):
        die("Metadata JSON must contain one object")

    title = str(metadata.get("title") or "").strip()
    authors = author_text(metadata.get("authors"))
    year = str(metadata.get("year") or "").strip()
    doi = normalize_doi(metadata.get("doi"))
    missing = [name for name, value in (("title", title), ("authors", authors), ("year", year), ("doi", doi)) if not value]
    if missing:
        die(f"Missing required metadata: {', '.join(missing)}")
    if not doi.startswith("10.") or "/" not in doi:
        die(f"DOI does not look valid: {doi}")

    project_matrix = root / "research_outputs" / "literature_matrix.csv"
    if project_matrix.exists():
        headers, rows, newline, quote_all = read_csv_file(project_matrix)
        if headers != MATRIX_FIELDS:
            die(f"Unsupported literature matrix schema at {project_matrix}")
        profile = "matrix16"
        matrix_path = project_matrix
        markdown_path = root / "research_outputs" / "literature_matrix.md"
        pdf_dir = root / "ref"
        manifest_csv_path = pdf_dir / "reference_pdf_manifest.csv"
        manifest_json_path = pdf_dir / "reference_pdf_manifest.json"
    else:
        profile = "portable"
        library_dir = root / "literature"
        matrix_path = library_dir / "library.csv"
        markdown_path = library_dir / "library.md"
        pdf_dir = library_dir / "pdfs"
        manifest_csv_path = library_dir / "manifest.csv"
        manifest_json_path = library_dir / "manifest.json"
        if matrix_path.exists():
            headers, rows, newline, quote_all = read_csv_file(matrix_path)
            if headers != MATRIX_FIELDS:
                die(f"Unsupported portable library schema at {matrix_path}")
        else:
            headers, rows, newline, quote_all = MATRIX_FIELDS, [], "\n", True

    duplicate = [row for row in rows if normalize_doi(row.get("doi")) == doi]
    if duplicate:
        die(f"Duplicate DOI already stored as {duplicate[0].get('id')}: {doi}", code=3)

    reference_id = (args.reference_id or next_reference_id(rows)).upper()
    if not re.fullmatch(r"R\d{3,}", reference_id):
        die(f"Invalid reference ID: {reference_id}")
    if any(str(row.get("id", "")).upper() == reference_id for row in rows):
        die(f"Reference ID already exists: {reference_id}")

    if args.pdf:
        pdf_source = args.pdf.resolve()
        if not pdf_source.is_file():
            die(f"PDF does not exist: {pdf_source}")
        pdf_data = pdf_source.read_bytes()
        source_label = relative_string(pdf_source, root)
        status = "copied_local"
    else:
        pdf_data = fetch_pdf(args.pdf_url)
        source_label = args.pdf_url
        status = "downloaded_open_access"
    validate_pdf(pdf_data, source_label)

    pdf_target = pdf_dir / safe_pdf_name(title)
    if pdf_target.exists():
        existing_data = pdf_target.read_bytes()
        if sha256(existing_data) != sha256(pdf_data):
            die(f"A different PDF already occupies target: {pdf_target}")
        write_pdf = False
    else:
        write_pdf = True

    alternates = metadata.get("alternatePaths") or []
    alternate_text = list_text(alternates)
    doi_url = f"https://doi.org/{doi}"
    if doi_url not in alternate_text:
        alternate_text = "; ".join(item for item in (alternate_text, doi_url) if item)

    record = {
        "id": reference_id,
        "title": title,
        "authors": authors,
        "year": year,
        "yearStatus": str(metadata.get("yearStatus") or "verified from DOI and publisher metadata"),
        "doi": doi,
        "sourceType": str(metadata.get("sourceType") or "Primary research"),
        "primarySection": str(metadata.get("primarySection") or "Background/supporting"),
        "priority": str(metadata.get("priority") or "Supporting evidence"),
        "batteryChemistry": str(metadata.get("batteryChemistry") or "General"),
        "methods": list_text(metadata.get("methods")),
        "targetProperties": list_text(metadata.get("targetProperties")),
        "evidenceNote": str(metadata.get("evidenceNote") or "").strip(),
        "limitationOrOutlook": str(metadata.get("limitationOrOutlook") or "").strip(),
        "relativePath": relative_string(pdf_target, root),
        "alternatePaths": alternate_text,
    }
    new_rows = [*rows, record]

    if manifest_csv_path.exists():
        manifest_headers, manifest_rows, manifest_newline, manifest_quote_all = read_csv_file(manifest_csv_path)
        if manifest_headers != MANIFEST_FIELDS:
            die(f"Unsupported manifest CSV schema at {manifest_csv_path}")
    else:
        manifest_headers, manifest_rows = MANIFEST_FIELDS, []
        manifest_newline, manifest_quote_all = newline, True

    for item in manifest_rows:
        if normalize_doi(item.get("doi")) == doi:
            die(f"DOI already exists in PDF manifest under {item.get('id')}")
        if str(item.get("id", "")).upper() == reference_id:
            die(f"ID already exists in PDF manifest: {reference_id}")
    numbers = [int(item["number"]) for item in manifest_rows if str(item.get("number", "")).isdigit()]
    manifest_record = {
        "number": str(max(numbers, default=0) + 1),
        "id": reference_id,
        "title": title,
        "doi": doi,
        "status": status,
        "source": source_label,
        "target": relative_string(pdf_target, root),
        "bytes": str(len(pdf_data)),
        "reason": "",
    }
    new_manifest_rows = [*manifest_rows, manifest_record]

    if manifest_json_path.exists():
        manifest_json = load_json(manifest_json_path)
        if not isinstance(manifest_json, dict) or not isinstance(manifest_json.get("references", []), list):
            die(f"Unsupported manifest JSON schema at {manifest_json_path}")
        known_ids = {str(item.get("id", "")).upper() for item in manifest_json.get("references", [])}
        known_dois = {normalize_doi(item.get("doi")) for item in manifest_json.get("references", [])}
        if reference_id in known_ids or doi in known_dois:
            die("Manifest JSON contains a conflicting ID or DOI")
        json_references = [*manifest_json.get("references", [])]
    else:
        manifest_json = {}
        json_references = []
    json_references.append({
        "number": int(manifest_record["number"]),
        "id": reference_id,
        "title": title,
        "doi": doi,
        "status": status,
        "source": source_label,
        "target": relative_string(pdf_target, root),
        "bytes": len(pdf_data),
    })
    manifest_json["generatedAt"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    manifest_json["references"] = json_references
    manifest_json["summary"] = {
        "totalReferences": len(json_references),
        "copiedLocal": sum(item.get("status") == "copied_local" for item in json_references),
        "downloadedOpenAccess": sum(item.get("status") == "downloaded_open_access" for item in json_references),
        "unavailable": sum(item.get("status") == "unavailable" for item in json_references),
        "validPdfFiles": sum(bool(item.get("target")) for item in json_references),
    }

    if profile == "matrix16" and markdown_path.exists():
        markdown_data = append_markdown(markdown_path.read_bytes(), record)
    else:
        markdown_data = render_markdown(new_rows)

    outputs = {
        matrix_path: encode_csv(headers, new_rows, newline, quote_all),
        markdown_path: markdown_data,
        manifest_csv_path: encode_csv(manifest_headers, new_manifest_rows, manifest_newline, manifest_quote_all),
        manifest_json_path: (json.dumps(manifest_json, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    }
    if write_pdf:
        outputs[pdf_target] = pdf_data

    plan = {
        "ok": True,
        "mode": "apply" if args.apply else "preview",
        "profile": profile,
        "id": reference_id,
        "doi": doi,
        "title": title,
        "pdf": {
            "target": relative_string(pdf_target, root),
            "bytes": len(pdf_data),
            "sha256": sha256(pdf_data),
            "writeRequired": write_pdf,
        },
        "files": [relative_string(path, root) for path in outputs],
        "recordCountAfter": len(new_rows),
        "manifestCountAfter": len(json_references),
    }
    if args.apply:
        atomic_write_all(outputs)
        plan["applied"] = True
    else:
        plan["applied"] = False
        plan["nextCommand"] = "Repeat the same command with --apply after reviewing this preview."
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

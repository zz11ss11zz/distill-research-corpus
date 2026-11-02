#!/usr/bin/env python3
"""Preview, classify, deduplicate, copy, and rename academic documents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - handled at runtime
    PdfReader = None


DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
PATENT_RE = re.compile(r"\b(?:CN\s*\d{7,12}\s*[A-Z]\d?|US\s*\d{7,14}\s*[A-Z]\d?|WO\s*\d{6,14}\s*[A-Z]\d?)\b", re.I)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
THESIS_MARKERS = (
    "博士学位论文",
    "硕士学位论文",
    "学位论文",
    "doctoral dissertation",
    "master's thesis",
    "masters thesis",
    "dissertation for the doctoral degree",
)
SI_MARKERS = (
    "supplementary_information",
    "supplementary information",
    "supporting information",
    "suppmat",
    "moesm",
    "source data",
    "source_data",
)
EXCLUDED_DIRS = {"reports", "datasets", "verified_duplicates"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Current project root; defaults to working directory")
    parser.add_argument("--source", action="append", help="Source root; repeat for multiple roots")
    parser.add_argument("--output", help="Literature directory; defaults to <root>/literature")
    parser.add_argument("--overrides", help="UTF-8 metadata overrides JSON")
    parser.add_argument("--apply", action="store_true", help="Copy files and write the manifest")
    parser.add_argument("--include-patent-markdown", action="store_true", help="Include patent full text stored as Markdown")
    parser.add_argument("--no-crossref", action="store_true", help="Disable Crossref DOI lookup")
    parser.add_argument("--delete-exact-duplicates", action="store_true", help="Delete byte-identical duplicate sources after apply")
    parser.add_argument("--max-filename-chars", type=int, default=170)
    parser.add_argument("--max-pdf-pages", type=int, default=6, help="Pages used for metadata extraction")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)


def clean_doi(value: str | None) -> str | None:
    if not value:
        return None
    match = DOI_RE.search(value)
    if not match:
        return None
    return match.group(0).rstrip(".,;:)]}>\"").lower()


def sanitize_part(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("&amp;", "&").replace("&nbsp;", " ").replace("&delta;", "δ")
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text)
    text = re.sub(r"\s+", " ", text).strip().rstrip(". ")
    return text


def shorten(value: Any, limit: int) -> str:
    text = sanitize_part(value)
    return text if len(text) <= limit else text[: max(1, limit - 1)].rstrip() + "…"


def output_filename(prefix: list[Any], title: str | None, extension: str, limit: int) -> str:
    clean_prefix = " - ".join(shorten(part, 70) for part in prefix)
    if title is None:
        stem = shorten(clean_prefix, limit)
    else:
        remaining = max(40, limit - len(clean_prefix) - 3)
        stem = f"{clean_prefix} - {shorten(title, remaining)}"
    return f"{stem}{extension.lower()}"


def load_overrides(path: str | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Overrides root must be an object")
    return data


def find_override(path: Path, roots: list[Path], overrides: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidates = [str(path), str(path.resolve()), path.name]
    for root in roots:
        try:
            candidates.append(str(path.resolve().relative_to(root.resolve())))
        except ValueError:
            pass
    for candidate in candidates:
        if candidate in overrides:
            return dict(overrides[candidate])
        slash = candidate.replace("\\", "/")
        if slash in overrides:
            return dict(overrides[slash])
    return {}


def scan_files(roots: list[Path], include_markdown: bool) -> list[Path]:
    allowed = {".pdf"} | ({".md"} if include_markdown else set())
    result: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix.lower() in allowed:
            result.append(root)
            continue
        if not root.exists():
            raise FileNotFoundError(root)
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in allowed:
                result.append(path)
    return sorted(set(result), key=lambda item: str(item).lower())


def obvious_exclusion(path: Path) -> str | None:
    lower_parts = {part.lower() for part in path.parts}
    lower_path = str(path).lower()
    if lower_parts & EXCLUDED_DIRS:
        return "excluded directory"
    if any(marker in lower_path for marker in SI_MARKERS):
        return "supplementary or source data"
    if path.name.lower().startswith("si ") or re.search(r"(?:^|[_-])si(?:[_-]|\.)", path.name.lower()):
        return "supplementary information"
    return None


def extract_pdf(path: Path, max_pages: int) -> tuple[str, dict[str, Any], str | None]:
    if PdfReader is None:
        return "", {}, "pypdf is not installed"
    try:
        reader = PdfReader(path)
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:max_pages])
        metadata = reader.metadata or {}
        return text, {
            "title": str(metadata.get("/Title") or "").strip(),
            "author": str(metadata.get("/Author") or "").strip(),
            "subject": str(metadata.get("/Subject") or "").strip(),
            "pages": len(reader.pages),
        }, None
    except Exception as exc:  # pragma: no cover - file dependent
        return "", {}, f"PDF read error: {exc}"


def infer_formatted_filename(path: Path) -> dict[str, Any]:
    stem = path.stem
    parts = stem.split(" - ", 2)
    if len(parts) < 2 or not YEAR_RE.fullmatch(parts[1]):
        return {}
    parent = path.parent.name.lower()
    if parent == "paper" and len(parts) == 3:
        return {"category": "paper", "venue": parts[0], "year": int(parts[1]), "title": parts[2]}
    if path.parent.name == "学位论文" and len(parts) == 3:
        return {"category": "thesis", "school": parts[0], "year": int(parts[1]), "title": parts[2]}
    if parent == "patent":
        return {"category": "patent", "patent_number": parts[0], "year": int(parts[1])}
    return {}


def crossref_lookup(doi: str, attempts: int = 5) -> dict[str, Any]:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
    request = urllib.request.Request(url, headers={"User-Agent": "organize-academic-pdfs/1.0 (mailto:noreply@example.com)"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                message = json.load(response)["message"]
            venue = (message.get("container-title") or [None])[0]
            title = (message.get("title") or [None])[0]
            year = None
            for key in ("published-print", "issued", "published", "published-online"):
                parts = (message.get(key) or {}).get("date-parts") or []
                if parts and parts[0]:
                    year = parts[0][0]
                    break
            if venue and title and year:
                return {"venue": venue, "title": title, "year": int(year), "doi": doi}
            return {}
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == attempts - 1:
                return {}
            time.sleep(attempt + 1)
        except Exception:
            return {}
    return {}


def extract_patent_number(text: str, path: Path) -> str | None:
    for source in (path.stem, text[:5000]):
        match = PATENT_RE.search(source.replace(" ", ""))
        if match:
            return re.sub(r"\s+", "", match.group(0)).upper()
    return None


def infer_year(text: str, path: Path) -> int | None:
    number = extract_patent_number(text, path)
    if number and number.startswith(("US19", "US20", "WO19", "WO20")):
        return int(number[2:6])
    priority = re.search(r"(?:授权公告日|申请公布日|公开日|published|publication date).{0,40}?((?:19|20)\d{2})", text, re.I | re.S)
    if priority:
        return int(priority.group(1))
    years = [int(year) for year in YEAR_RE.findall(text[:8000])]
    plausible = [year for year in years if 1900 <= year <= 2100]
    return plausible[0] if plausible else None


def infer_school(text: str) -> str | None:
    matches = re.findall(r"([\u4e00-\u9fff]{2,18}(?:大学|学院))", text[:6000])
    blacklist = {"硕士学位论文", "博士学位论文"}
    for match in matches:
        if match not in blacklist and len(match) <= 20:
            return match
    english = re.search(r"(?:University|Institute) of [A-Z][A-Za-z &-]{2,60}", text[:6000])
    return english.group(0).strip() if english else None


def useful_pdf_title(metadata: dict[str, Any], path: Path) -> str | None:
    title = sanitize_part(metadata.get("title"))
    bad = ("microsoft word", "untitled", "administrator", "doi:")
    if title and len(title) >= 12 and not any(item in title.lower() for item in bad):
        return title
    stem = sanitize_part(path.stem)
    stem = re.sub(r"[_-](?:[^_-]{1,12})$", "", stem) if any(ch in stem for ch in "学位论文") else stem
    return stem if len(stem) >= 8 else None


def classify(path: Path, roots: list[Path], overrides: dict[str, dict[str, Any]], max_pages: int, use_crossref: bool) -> dict[str, Any]:
    item: dict[str, Any] = {"source": str(path), "extension": path.suffix.lower(), "hash": sha256(path)}
    formatted = infer_formatted_filename(path)
    override = find_override(path, roots, overrides)
    if override.get("category") == "exclude":
        return {**item, **override, "status": "excluded"}
    exclusion = obvious_exclusion(path)
    if exclusion and not override:
        return {**item, "category": "exclude", "reason": exclusion, "status": "excluded"}

    if path.suffix.lower() == ".md":
        text = path.read_text(encoding="utf-8", errors="replace")
        metadata: dict[str, Any] = {}
        error = None
    else:
        text, metadata, error = extract_pdf(path, max_pages)
        if error:
            item["warning"] = error
    merged = {**formatted, **override}
    lower = (str(path) + "\n" + text[:8000]).lower()
    category = merged.get("category")
    if not category:
        if "patent" in {part.lower() for part in path.parts} or "发明专利" in text[:3000] or extract_patent_number(text, path):
            category = "patent"
        elif any(marker in lower for marker in THESIS_MARKERS):
            category = "thesis"
        elif path.suffix.lower() == ".pdf" and ("paper" in {part.lower() for part in path.parts} or DOI_RE.search(text[:12000]) or "journal" in lower):
            category = "paper"
        else:
            category = "unknown"
    item["category"] = category

    if category == "paper":
        doi = clean_doi(merged.get("doi")) or clean_doi(text[:16000]) or clean_doi(metadata.get("subject"))
        resolved = crossref_lookup(doi) if doi and use_crossref else {}
        item.update(resolved)
        item.update({key: value for key, value in merged.items() if value not in (None, "")})
        item["doi"] = doi or item.get("doi")
        item.setdefault("title", useful_pdf_title(metadata, path))
        if not item.get("year"):
            item["year"] = infer_year(text, path)
        required = (item.get("venue"), item.get("year"), item.get("title"))
    elif category == "thesis":
        item.update({key: value for key, value in merged.items() if value not in (None, "")})
        item.setdefault("school", infer_school(text))
        item.setdefault("year", infer_year(text, path))
        item.setdefault("title", useful_pdf_title(metadata, path))
        required = (item.get("school"), item.get("year"), item.get("title"))
    elif category == "patent":
        item.update({key: value for key, value in merged.items() if value not in (None, "")})
        item.setdefault("patent_number", extract_patent_number(text, path))
        item.setdefault("year", infer_year(text, path))
        required = (item.get("patent_number"), item.get("year"))
    else:
        required = ()
    item["status"] = "ready" if required and all(required) else "unresolved"
    return item


def choose_canonical(items: list[dict[str, Any]]) -> dict[str, Any]:
    def score(item: dict[str, Any]) -> tuple[int, int, int, str]:
        path_text = item["source"].lower()
        penalty = int("inbox" in path_text) + int("verified_duplicates" in path_text) + int("source_packages" in path_text)
        return (penalty, len(Path(item["source"]).parts), len(item["source"]), item["source"].lower())
    return min(items, key=score)


def bibliographic_key(item: dict[str, Any]) -> str:
    if item.get("doi"):
        return f"paper:doi:{clean_doi(item['doi'])}"
    if item["category"] == "patent":
        return f"patent:{normalized_text(item.get('patent_number', ''))}"
    return f"{item['category']}:{normalized_text(item.get('title', ''))}:{item.get('year', '')}"


def target_for(item: dict[str, Any], output: Path, limit: int) -> Path:
    extension = item["extension"]
    if item["category"] == "paper":
        name = output_filename([item["venue"], item["year"]], item["title"], extension, limit)
        return output / "paper" / name
    if item["category"] == "thesis":
        name = output_filename([item["school"], item["year"]], item["title"], extension, limit)
        return output / "thesis" / name
    name = output_filename([item["patent_number"], item["year"]], None, extension, limit)
    return output / "patent" / name



LEDGER_HEADERS = ["分类", "标题", "作者", "年份", "期刊或学校", "DOI", "专利号", "文件路径", "SHA256", "原始路径"]


def prepare_ledger(output: Path, plan: list[dict[str, Any]]) -> dict[str, list[Any]]:
    from openpyxl import load_workbook
    rows = {}
    ledger = output / "literature-ledger.xlsx"
    if not ledger.exists():
        ledger = output / "文献总账.xlsx"  # Read legacy ledgers without deleting them.
    if ledger.exists():
        workbook = load_workbook(ledger)
        try:
            sheet = workbook["文献总账"]
            values = list(sheet.values)
            if not values or list(values[0]) != LEDGER_HEADERS:
                raise ValueError("Existing literature ledger has an unsupported schema; preserve it and adapt first")
            rows = {str(row[7]): list(row) for row in values[1:] if row[7]}
        finally:
            workbook.close()
    for item in plan:
        relative = Path(item["target"]).relative_to(output).as_posix()
        authors = item.get("authors", item.get("author", ""))
        if isinstance(authors, list):
            authors = "; ".join(str(a) for a in authors)
        rows[relative] = [item["category"], item.get("title", ""), str(authors),
                          item.get("year", ""), item.get("venue", item.get("school", "")),
                          item.get("doi", ""), item.get("patent_number", ""),
                          relative, item["hash"], item["source"]]
    return rows


def write_ledger(output: Path, rows: dict[str, list[Any]]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.worksheet.table import Table, TableStyleInfo
    import tempfile
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "文献总账"
    sheet.append(LEDGER_HEADERS)
    for key in sorted(rows):
        sheet.append(rows[key])
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # metadata must never become Excel formulas
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="246B5C")
    sheet.freeze_panes = "A2"
    widths = [14, 52, 28, 12, 28, 30, 24, 65, 68, 65]
    for column, width in zip("ABCDEFGHIJ", widths):
        sheet.column_dimensions[column].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    if rows:
        table = Table(displayName="LiteratureLedger", ref=f"A1:J{sheet.max_row}")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        sheet.add_table(table)
    else:
        sheet.auto_filter.ref = "A1:J1"
    handle, temporary = tempfile.mkstemp(suffix=".xlsx", dir=output)
    os.close(handle)
    try:
        workbook.save(temporary)
        os.replace(temporary, output / "literature-ledger.xlsx")
    finally:
        workbook.close()
        Path(temporary).unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    project = Path(args.root).resolve()
    roots = [Path(value).resolve() for value in (args.source or [str(project)])]
    output = Path(args.output).resolve() if args.output else project / "literature"
    if any(not path.is_dir() for path in roots):
        raise ValueError("Source directories must exist")
    overrides = load_overrides(args.overrides)
    paths = [path for path in scan_files(roots, args.include_patent_markdown)
             if not path.resolve().is_relative_to(output)]
    records = [classify(path, roots, overrides, args.max_pdf_pages, not args.no_crossref) for path in paths]

    ready = [item for item in records if item["status"] == "ready"]
    unresolved = [item for item in records if item["status"] == "unresolved"]
    excluded = [item for item in records if item["status"] == "excluded"]

    hash_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in ready:
        hash_groups[item["hash"]].append(item)
    exact_duplicates = [group for group in hash_groups.values() if len(group) > 1]
    hash_canonical = [choose_canonical(group) for group in hash_groups.values()]

    bib_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in hash_canonical:
        bib_groups[bibliographic_key(item)].append(item)
    bibliographic_duplicates = [group for group in bib_groups.values() if len(group) > 1]
    canonical = [choose_canonical(group) for group in bib_groups.values()]

    plan: list[dict[str, Any]] = []
    target_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in canonical:
        target = target_for(item, output, args.max_filename_chars)
        planned = {**item, "target": str(target)}
        plan.append(planned)
        target_groups[str(target).lower()].append(planned)
    collisions = [group for group in target_groups.values() if len(group) > 1]

    existing_conflicts: list[dict[str, str]] = []
    for item in plan:
        target = Path(item["target"])
        if target.exists() and sha256(target) != item["hash"]:
            existing_conflicts.append({"source": item["source"], "target": item["target"]})

    summary = {
        "mode": "apply" if args.apply else "preview",
        "scanned": len(paths),
        "ready_before_dedup": len(ready),
        "planned_unique": len(plan),
        "planned_by_category": dict(Counter(item["category"] for item in plan)),
        "unresolved_count": len(unresolved),
        "excluded_count": len(excluded),
        "exact_duplicate_groups": len(exact_duplicates),
        "bibliographic_duplicate_groups": len(bibliographic_duplicates),
        "filename_collisions": len(collisions),
        "existing_conflicts": len(existing_conflicts),
        "longest_target_path_chars": max((len(item["target"]) for item in plan), default=0),
    }
    report = {
        "summary": summary,
        "unresolved": unresolved,
        "exact_duplicates": exact_duplicates,
        "bibliographic_duplicates": bibliographic_duplicates,
        "filename_collisions": collisions,
        "existing_conflicts": existing_conflicts,
        "plan": plan,
        "excluded": excluded,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if unresolved or collisions or existing_conflicts:
        print(json.dumps({"unresolved": unresolved, "filename_collisions": collisions, "existing_conflicts": existing_conflicts}, ensure_ascii=False, indent=2))
        if args.apply:
            print("Apply aborted: resolve metadata and conflicts first.", file=sys.stderr)
            return 2
    if not args.apply:
        return 0

    ledger_rows = prepare_ledger(output, plan)
    for subdirectory in ("paper", "patent", "thesis"):
        (output / subdirectory).mkdir(parents=True, exist_ok=True)
    for item in plan:
        source = Path(item["source"])
        target = Path(item["target"])
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256(target) != item["hash"]:
            raise RuntimeError(f"Hash mismatch after copy: {target}")

    write_ledger(output, ledger_rows)

    if args.delete_exact_duplicates:
        for group in exact_duplicates:
            keep = choose_canonical(group)["source"]
            for item in group:
                source = Path(item["source"])
                if item["source"] != keep and source.exists():
                    source.unlink()

    manifest = output / "_organization_manifest.json"
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

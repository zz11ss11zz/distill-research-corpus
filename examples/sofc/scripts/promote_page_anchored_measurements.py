#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FORMULA_RE = re.compile(r"\b(?:[A-Z][a-z]?(?:\d+(?:\.\d+)?|[xyz])?){2,}O(?:\d+(?:\.\d+)?)?(?:[+\-−–]?[δdx])?\b")
ABBR_RE = re.compile(r"(?P<formula>(?:[A-Z][a-z]?(?:\d+(?:\.\d+)?|[xyz])?){2,}O(?:\d+(?:\.\d+)?)?(?:[+\-−–]?[δdx])?)\s*\((?P<abbr>[A-Z][A-Z0-9-]{1,14})\)")
TEMP_RE = re.compile(r"(?P<value>\d{2,4}(?:\.\d+)?)\s*(?:°|º|/C14\s*)?\s*C\b", re.I)
NUMBER_RE = r"(?P<value>\d+(?:\.\d+)?(?:\s*[×x]\s*10\s*[−-]?\s*\d+|[eE][+-]?\d+)?)"

PROPERTY_RULES = [
    ("ASR", re.compile(rf"(?:\bASR\b|area[- ]specific resistance|polarization resistance|polarisation resistance|\bR[pP]\b)[^.;:]{{0,180}}?{NUMBER_RE}\s*(?:Ω|Ω|ohm|U)\s*(?:[·⋅ ]?cm(?:²|2|\^2))", re.I), "Ω·cm²"),
    ("electrical_conductivity", re.compile(rf"(?:electrical|electronic|total)?\s*conductivit(?:y|ies)[^.;:]{{0,180}}?{NUMBER_RE}\s*S\s*(?:cm\s*(?:[−-]?1|\^-?1)|/\s*cm)", re.I), "S/cm"),
    ("peak_power_density", re.compile(rf"(?:peak|max(?:imum)?)\s+power densit(?:y|ies)[^.;:]{{0,180}}?{NUMBER_RE}\s*(?P<power_unit>m?W)\s*(?:cm\s*(?:[−-]?2|\^-?2)|/\s*cm(?:²|2))", re.I), None),
    ("oxygen_surface_exchange_coefficient", re.compile(rf"(?:surface exchange coefficient|\bk(?:chem|ex|\*)\b)[^.;:]{{0,180}}?{NUMBER_RE}\s*cm\s*(?:s\s*(?:[−-]?1|\^-?1)|/\s*s)", re.I), "cm/s"),
    ("oxygen_diffusion_coefficient", re.compile(rf"(?:diffusion coefficient|\bD(?:chem|\*)\b)[^.;:]{{0,180}}?{NUMBER_RE}\s*cm(?:²|2|\^2)\s*(?:s\s*(?:[−-]?1|\^-?1)|/\s*s)", re.I), "cm²/s"),
    ("thermal_expansion_coefficient", re.compile(rf"(?:thermal expansion coefficient|\bTEC\b)[^.;:]{{0,180}}?{NUMBER_RE}\s*(?:×|x)?\s*10\s*[−-]?6\s*K\s*(?:[−-]?1|\^-?1)", re.I), "10⁻⁶ K⁻¹"),
]

REVIEW_WORDS = re.compile(r"\b(review|perspective|overview|past \d+ years|bibliometric)\b", re.I)
CITATION_WORDS = re.compile(r"\b(reported(?: by| that)?|previous(?:ly)?|literature|other studies|according to|it was known|e\.g\.)\b", re.I)
REFERENCE_HEADING = re.compile(r"^\s*(references|bibliography)\s*$", re.I | re.M)
ELEMENTS = set("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split())
AMBIGUOUS_PAIRING = re.compile(r"\b(respectively|versus|values? are|increases? to|decreases? to|from .+ to)\b", re.I)
NUMERIC_RANGE = re.compile(r"\b\d+(?:\.\d+)?\s*[e–−-]\s*\d+(?:\.\d+)?\b")
APPROXIMATE_OR_INEQUALITY = re.compile(r"\b(exceed(?:s|ed|ing)?|more than|less than|approximately|about|around|ca\.)\b|[<>~≈]", re.I)
GENERIC_ACRONYMS = {"ASR", "EIS", "ORR", "SOFC", "ITSOFC", "TEC", "XRD", "SEM", "TEM"}
ELECTROLYTE_ACRONYMS = {"YSZ", "GDC", "SDC", "CGO", "CGO91", "CSO", "CSO82", "LSGM"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strictly promote page-anchored machine measurements into a dated experimental master snapshot.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--input-master", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-source", action="append", required=True, help="Directory, file, or ZIP whose file hashes define the promotion batch.")
    parser.add_argument("--audit-output")
    parser.add_argument("--batch-date", required=True)
    parser.add_argument("--preview", action="store_true")
    return parser.parse_args()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def batch_hashes(paths: list[str]) -> set[str]:
    hashes: set[str] = set()
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for item in path.rglob("*"):
                if item.is_file():
                    hashes.add(sha256_bytes(item.read_bytes()))
        elif path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if not info.is_dir():
                        hashes.add(sha256_bytes(archive.read(info)))
        elif path.is_file():
            hashes.add(sha256_bytes(path.read_bytes()))
        else:
            raise FileNotFoundError(path)
    return hashes


def clean_formula(value: str) -> str:
    return value.replace("−", "-").replace("–", "-").replace(" ", "")


def valid_formula(value: str) -> bool:
    value = clean_formula(value)
    if not re.search(r"\d", value) or any(token in value for token in ("ABO", "A2BO", "DVO")):
        return False
    core = re.sub(r"[+\-δdx]", "", value)
    tokens = re.findall(r"([A-Z][a-z]?)(?:\d+(?:\.\d+)?)?", core)
    if not tokens or any(token not in ELEMENTS for token in tokens):
        return False
    oxygen = re.search(r"O(?P<n>\d+(?:\.\d+)?)", core)
    if not oxygen or float(oxygen.group("n")) > 12:
        return False
    return "O" in tokens and len(set(tokens) - {"O"}) >= 2


def formula_key(value: str) -> str:
    value = clean_formula(value).replace("δ", "").replace("d", "")
    value = re.sub(r"O(?:3(?:\.0)?)?[+\-]?$", "", value, flags=re.I)
    return value.lower()


def parse_number(value: str) -> float:
    value = re.sub(r"\s+", "", value).replace("−", "-")
    sci = re.fullmatch(r"([0-9.]+)[×x]10(-?\d+)", value)
    if sci:
        return float(sci.group(1)) * (10 ** int(sci.group(2)))
    return float(value)


def sentences(text: str) -> list[str]:
    text = re.sub(r"/C(?:14|176)\s*C", "°C", text)
    text = text.replace("/C15", ". ").replace("/C0 d", "-δ").replace("/C0δ", "-δ")
    text = re.sub(r"/C0\s*([12])", r"-\1", text)
    text = re.sub(r"\b(\d{2,3})8C\b", r"\1 °C", text)
    text = re.sub(r"\s+", " ", text).strip()
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text) if part.strip()]


def formula_context(document: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    opening = " ".join(page.get("text", "") for page in document.get("pages", [])[:3])
    opening = opening.replace("/C0 d", "-δ").replace("/C0δ", "-δ")
    title = document.get("bibliographic_metadata", {}).get("title") or ""
    title_formulas = sorted({clean_formula(item) for item in FORMULA_RE.findall(title) if valid_formula(item)})
    aliases = {}
    for match in ABBR_RE.finditer(re.sub(r"(?<=[A-Za-z])\s+(?=\d)", "", opening)):
        formula = clean_formula(match.group("formula"))
        if not valid_formula(formula):
            continue
        formula_elements = re.findall(r"[A-Z][a-z]?", formula)
        matching_title = [candidate for candidate in title_formulas if re.findall(r"[A-Z][a-z]?", candidate) == formula_elements]
        containing = [candidate for candidate in title_formulas if formula in candidate]
        aliases[match.group("abbr")] = matching_title[0] if len(matching_title) == 1 else containing[0] if len(containing) == 1 else formula
    # OCR often inserts spaces throughout a formula. Recover definitions such as
    # ``Sr0.9 Ce0.1 Co0.9 Nb0.1 O3-d (SCCN)`` from the local context only.
    for abbreviation in re.finditer(r"\((?P<abbr>[A-Z][A-Z0-9-]{1,14})\)", opening):
        prefix = re.sub(r"\s+", "", opening[max(0, abbreviation.start() - 140):abbreviation.start()])
        candidates = [clean_formula(item) for item in FORMULA_RE.findall(prefix) if valid_formula(item)]
        if candidates:
            aliases.setdefault(abbreviation.group("abbr"), max(candidates, key=len))
    return aliases, title_formulas


def resolve_formula(sentence: str, aliases: dict[str, str], title_formulas: list[str]) -> tuple[str | None, str]:
    material_tokens = [
        token for token in re.findall(r"\b[A-Z][A-Za-z0-9-]{2,12}\b", sentence)
        if token.upper() not in GENERIC_ACRONYMS | ELECTROLYTE_ACRONYMS
        and (token in aliases or re.search(r"[A-Z].*[A-Z]", token))
    ]
    material_tokens = sorted(set(material_tokens))
    alias_materials = sorted({aliases[token] for token in material_tokens if token in aliases})
    if len(material_tokens) == 1 and len(alias_materials) == 1:
        return alias_materials[0], "document_abbreviation_definition"
    if len(material_tokens) == 1 and len(title_formulas) == 1:
        non_oxygen = set(re.findall(r"[A-Z][a-z]?", title_formulas[0])) - {"O"}
        if len(non_oxygen) >= 3:
            return title_formulas[0], "title_formula_for_named_material"
    explicit = sorted({clean_formula(item) for item in FORMULA_RE.findall(sentence) if valid_formula(item)}, key=len, reverse=True)
    if len(explicit) == 1:
        return explicit[0], "explicit_same_sentence"
    unknown_acronyms = [token for token in re.findall(r"\b[A-Z][A-Z0-9-]{2,12}\b", sentence) if token not in GENERIC_ACRONYMS | ELECTROLYTE_ACRONYMS and token not in aliases]
    cathode_acronyms = [token for token in unknown_acronyms if re.search(rf"\b{re.escape(token)}\s+cathode\b", sentence)]
    if not explicit and len(cathode_acronyms) == 1 and len(title_formulas) == 1:
        non_oxygen = set(re.findall(r"[A-Z][a-z]?", title_formulas[0])) - {"O"}
        if len(non_oxygen) >= 3:
            return title_formulas[0], "title_formula_for_named_cathode_abbreviation"
    alias_hits = [formula for alias, formula in aliases.items() if alias not in ELECTROLYTE_ACRONYMS and re.search(rf"\b{re.escape(alias)}\b", sentence)]
    alias_hits = sorted(set(alias_hits))
    if len(alias_hits) == 1:
        return alias_hits[0], "document_abbreviation_definition"
    if not explicit and not alias_hits and not unknown_acronyms and len(title_formulas) == 1 and not re.search(r"\b(electrolyte|YSZ|GDC|SDC|CGO|CSO)\b", sentence):
        non_oxygen = set(re.findall(r"[A-Z][a-z]?", title_formulas[0])) - {"O"}
        if len(non_oxygen) >= 3:
            return title_formulas[0], "single_formula_in_title"
    return None, "ambiguous_or_missing_formula"


def document_doi(document: dict[str, Any]) -> str | None:
    values = document.get("bibliographic_metadata", {}).get("doi_candidates") or []
    for value in values:
        if re.fullmatch(r"10\.\d{4,9}/\S{4,}", value or "") and not re.search(r"\.(?:19|20)\d{0,2}$", value):
            return value.lower()
    return None


def existing_fingerprints(master: dict[str, Any]) -> set[tuple[Any, ...]]:
    fingerprints = set()
    for record in master.get("records", []):
        formula = record.get("material", {}).get("formula_match_key") or formula_key(record.get("material", {}).get("formula_as_reported", ""))
        for measurement in record.get("measurements", []):
            fingerprints.add((formula, measurement.get("property"), measurement.get("value"), measurement.get("unit"), measurement.get("test_context", {}).get("test_temperature_c")))
    return fingerprints


def make_id(prefix: str, payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    root = Path(args.root).resolve()
    master_path = Path(args.input_master).resolve()
    output_path = Path(args.output).resolve()
    audit_path = Path(args.audit_output).resolve() if args.audit_output else output_path.with_suffix(".audit.json")
    if output_path == master_path:
        raise ValueError("Output must be a new dated snapshot, not the input master.")
    if output_path.exists() and not args.preview:
        raise FileExistsError(output_path)

    master = json.loads(master_path.read_text(encoding="utf-8"))
    documents = json.loads((root / "outputs/json/knowledge_distillation/documents.json").read_text(encoding="utf-8"))
    hashes = batch_hashes(args.batch_source)
    selected = [doc for doc in documents if doc.get("sha256", "").upper() in hashes and doc.get("category") in {"paper", "thesis", "patent"}]
    rejected = Counter()
    accepted: list[dict[str, Any]] = []
    source_meta: dict[str, dict[str, Any]] = {}

    for doc in selected:
        title = doc.get("bibliographic_metadata", {}).get("title") or Path(doc.get("path", "")).stem
        if REVIEW_WORDS.search(title):
            rejected["review_or_perspective_document"] += 1
            continue
        aliases, title_formulas = formula_context(doc)
        source_id = f"distilled:{doc['source_id']}"
        doi = document_doi(doc)
        source_meta[source_id] = {
            "source_id": source_id,
            "source_kind": "local_fulltext",
            "source_role": "primary_fulltext_page_anchored_machine_extraction",
            "title": title,
            "journal_or_database": doc.get("bibliographic_metadata", {}).get("venue_or_institution"),
            "year": doc.get("bibliographic_metadata", {}).get("year"),
            "doi": doi,
            "local_paper_match": str((root / doc["path"]).resolve()),
            "source_reliability_grade": "B",
            "research_institution_or_team": "待原文机构信息核实",
            "principal_researchers": "待原文作者信息核实",
        }
        in_references = False
        for page in doc.get("pages", []):
            page_text = page.get("text") or ""
            if REFERENCE_HEADING.search(page_text[:500]):
                in_references = True
            if in_references:
                rejected["references_section"] += 1
                continue
            for sentence in sentences(page_text):
                if CITATION_WORDS.search(sentence):
                    rejected["secondary_or_cited_statement"] += 1
                    continue
                if re.search(r"\[[^\]]*\d[^\]]*\]", sentence) or AMBIGUOUS_PAIRING.search(sentence):
                    rejected["ambiguous_or_cited_sentence"] += 1
                    continue
                if NUMERIC_RANGE.search(sentence) or APPROXIMATE_OR_INEQUALITY.search(sentence):
                    rejected["range_approximate_or_inequality"] += 1
                    continue
                if re.search(r"\b(?:composite|mixture)\b|\b[A-Z][A-Za-z0-9-]*\s*\+\s*[A-Z]", sentence, re.I):
                    rejected["composite_material_not_single_formula"] += 1
                    continue
                if re.search(r"\b(?:enhancement|increase|decrease)\s+of\s+(?:the\s+)?(?:electrical\s+)?conductivity\b", sentence, re.I):
                    rejected["relative_change_not_absolute_measurement"] += 1
                    continue
                if re.search(r"/C[02]", sentence):
                    rejected["unresolved_ocr_scientific_notation"] += 1
                    continue
                material_tokens = {
                    token for token in re.findall(r"\b[A-Z]{2,}[A-Z0-9-]*\d+[A-Z0-9-]*\b", sentence)
                    if token not in {"YSZ", "GDC", "SDC", "CGO91", "CSO82"}
                }
                if len(material_tokens) > 1:
                    rejected["multiple_material_abbreviations"] += 1
                    continue
                if re.search(r"\b\d+\s+3\s+10\d{2}\s*cm", sentence):
                    rejected["suspicious_ocr_scientific_notation"] += 1
                    continue
                temperatures = [float(match.group("value")) for match in TEMP_RE.finditer(sentence)]
                if not temperatures or any(value < 200 or value > 1200 for value in temperatures):
                    continue
                formula, formula_method = resolve_formula(sentence, aliases, title_formulas)
                if not formula:
                    continue
                for prop, rule, fixed_unit in PROPERTY_RULES:
                    matches = list(rule.finditer(sentence))
                    if not matches:
                        continue
                    values = [parse_number(match.group("value")) for match in matches]
                    if prop == "ASR" and len(re.findall(r"(?:Ω|Ω|ohm|U)\s*(?:[·⋅ ]?cm(?:²|2|\^2))", sentence, re.I)) != len(matches):
                        rejected["multiple_unpaired_property_values"] += 1
                        continue
                    if prop == "electrical_conductivity" and re.search(r"\b(?:for|of)\s+(?:YSZ|GDC|SDC|CGO|CSO|electrolyte)\b", sentence, re.I):
                        rejected["electrolyte_property_not_cathode"] += 1
                        continue
                    if len(values) != len(temperatures):
                        rejected["unpaired_value_temperature"] += 1
                        continue
                    for value, temperature, match in zip(values, temperatures, matches):
                        unit = fixed_unit
                        if prop == "peak_power_density":
                            unit = "mW/cm²" if match.groupdict().get("power_unit", "").lower() == "mw" else "W/cm²"
                        payload = (source_id, formula_key(formula), prop, value, unit, temperature, page.get("page"), sentence)
                        accepted.append({
                            "payload": payload,
                            "source_id": source_id,
                            "formula": formula,
                            "formula_method": formula_method,
                            "property": prop,
                            "value": value,
                            "unit": unit,
                            "temperature_c": temperature,
                            "page": page.get("page"),
                            "sentence": sentence,
                            "path": doc["path"],
                            "doi": doi,
                        })

    unique = {}
    for item in accepted:
        fingerprint = (item["source_id"], formula_key(item["formula"]), item["property"], item["value"], item["unit"], item["temperature_c"])
        unique.setdefault(fingerprint, item)
    accepted = list(unique.values())
    existing = existing_fingerprints(master)
    new_items = []
    for item in accepted:
        fp = (formula_key(item["formula"]), item["property"], item["value"], item["unit"], item["temperature_c"])
        if fp in existing:
            rejected["already_in_master"] += 1
        else:
            new_items.append(item)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in new_items:
        grouped[(item["source_id"], formula_key(item["formula"]))].append(item)

    output = copy.deepcopy(master)
    known_sources = {item.get("source_id") for item in output.get("sources", [])}
    used_source_ids = {item["source_id"] for item in new_items}
    for source_id in sorted(used_source_ids):
        if source_id not in known_sources:
            output.setdefault("sources", []).append(source_meta[source_id])

    added_records = []
    added_queue = []
    for (source_id, key), items in sorted(grouped.items()):
        formula = items[0]["formula"]
        record_id = make_id("exp_", [source_id, key, args.batch_date])
        measurements = []
        for item in sorted(items, key=lambda x: (x["property"], x["temperature_c"], x["value"], x["page"])):
            evidence_id = make_id("pagefact_", item["payload"])
            measurement_method = bool(re.search(r"\b(EIS|impedance)\b", item["sentence"], re.I))
            measurement = {
                "evidence_id": evidence_id,
                "property": item["property"],
                "value": item["value"],
                "unit": item["unit"],
                "uncertainty": {"value": None, "type": None},
                "data_status": "directly_reported",
                "test_context": {
                    "electrolyte": None,
                    "electrolyte_class": None,
                    "test_method": "EIS" if item["property"] == "ASR" and re.search(r"\b(EIS|impedance)\b", item["sentence"], re.I) else None,
                    "cell_configuration": None,
                    "electrode_type": None,
                    "atmosphere": "air" if re.search(r"\bin air\b", item["sentence"], re.I) else None,
                    "oxygen_partial_pressure": None,
                    "test_temperature_c": item["temperature_c"],
                    "active_area": None,
                    "normalization_basis": None,
                    "electrode_count_factor": None,
                },
                "preparation": {"powder_synthesis": None, "electrode_fabrication": None, "synthesis_status": "not_extracted"},
                "source_location": {
                    "page": item["page"], "figure": None, "table": None, "sheet": None, "row": None,
                    "workbook": None, "dataset_row": None, "local_source_path": item["path"],
                    "location_method": "strict_page_sentence_machine_extraction", "human_verified": False,
                },
                "evidence": {
                    "exact_original_sentence": item["sentence"],
                    "evidence_status": "page_anchored_machine_extracted",
                    "evidence_candidates": [],
                },
                "provenance": {
                    "data_role": "primary_article_page_anchored_machine_extraction",
                    "original_source": {"source_id": source_id, "doi": item["doi"], "local_path": item["path"]},
                    "original_source_status": "resolved_not_human_verified",
                    "collection_source": None,
                    "source_locator": {"page": item["page"]},
                },
                "notes": f"Formula resolution: {item['formula_method']}. Batch-promoted on {args.batch_date}; human verification pending.",
                "project_relevance": {"target_temperature_c": 650, "is_target_temperature": item["temperature_c"] == 650, "priority_role": "target_temperature" if item["temperature_c"] == 650 else "supporting_other_temperature"},
                "quality": {
                    "evidence_grade": "B_primary_locator_or_quote_unverified",
                    "verification_status": "not_human_verified",
                    "completeness_score_0_100": 70,
                    "completeness_checks": {"formula": True, "value_and_unit": True, "data_status": True, "temperature": True, "source_location": True, "exact_evidence": True, "electrolyte": False, "test_method": measurement_method, "synthesis_method": False},
                    "missing_fields": [field for field, present in (("electrolyte", False), ("test_method", measurement_method), ("synthesis_method", False)) if not present],
                    "missing_reason": "Field absent from the accepted evidence sentence; no value was inferred.",
                    "evidence_candidate_count": 1,
                },
            }
            measurements.append(measurement)
            added_queue.append({
                "evidence_id": evidence_id, "experimental_record_id": record_id, "formula": formula,
                "property": item["property"], "value": item["value"], "unit": item["unit"],
                "temperature_c": item["temperature_c"], "priority": "high" if item["temperature_c"] == 650 else "normal",
                "priority_rank": 1 if item["temperature_c"] == 650 else 2,
                "candidates": [{"source_id": source_id, "page": item["page"], "evidence_text": item["sentence"]}],
            })
        record = {
            "experimental_record_id": record_id,
            "dedup_key": {"formula_key": key, "source_id": source_id, "rule": "normalized_formula_plus_local_primary_source"},
            "material": {"formula_as_reported": formula, "formula_normalized_for_matching": formula, "formula_match_key": key, "shorthand_name": None},
            "source": {"source_id": source_id, "source_role": "local_primary_fulltext_page_anchored_machine_extraction", "external_source": source_meta[source_id]},
            "measurements": measurements,
        }
        output.setdefault("records", []).append(record)
        added_records.append(record)

    output.setdefault("human_review_queue", []).extend(added_queue)
    stats = output.setdefault("statistics", {})
    all_measurements = [measurement for record in output.get("records", []) for measurement in record.get("measurements", [])]
    stats["source_measurement_rows_before_grouping"] = len(all_measurements)
    stats["top_level_formula_source_records"] = len(output.get("records", []))
    stats["retained_measurements"] = len(all_measurements)
    stats["external_sources_used"] = len(output.get("sources", []))
    stats["data_status_counts"] = dict(Counter(measurement.get("data_status") for measurement in all_measurements))
    stats["field_coverage_measurement_counts"] = {
        "electrolyte": sum(measurement.get("test_context", {}).get("electrolyte") is not None for measurement in all_measurements),
        "test_method": sum(measurement.get("test_context", {}).get("test_method") is not None for measurement in all_measurements),
        "synthesis_method": sum(measurement.get("preparation", {}).get("powder_synthesis") not in (None, {}, {"method": None}) for measurement in all_measurements),
        "page": sum(measurement.get("source_location", {}).get("page") is not None for measurement in all_measurements),
        "figure": sum(measurement.get("source_location", {}).get("figure") is not None for measurement in all_measurements),
        "table": sum(measurement.get("source_location", {}).get("table") is not None for measurement in all_measurements),
        "sheet_row": sum(measurement.get("source_location", {}).get("sheet") is not None and measurement.get("source_location", {}).get("row") is not None for measurement in all_measurements),
        "exact_original_sentence": sum(bool(measurement.get("evidence", {}).get("exact_original_sentence")) for measurement in all_measurements),
    }
    stats["source_registry_snapshot_count"] = len(output.get("sources", []))
    output["generated_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    output["last_batch_promotion"] = {
        "date": args.batch_date,
        "mode": "strict_page_anchored_machine_promotion",
        "added_records": len(added_records),
        "added_measurements": len(new_items),
        "human_verification_status": "pending",
    }

    audit = {
        "status": "preview" if args.preview else "applied",
        "batch_date": args.batch_date,
        "input_master": str(master_path),
        "output_master": str(output_path),
        "batch_hash_count": len(hashes),
        "selected_document_count": len(selected),
        "accepted_candidate_count": len(accepted),
        "added_record_count": len(added_records),
        "added_measurement_count": len(new_items),
        "added_source_count": len(used_source_ids - known_sources),
        "rejection_counts": dict(sorted(rejected.items())),
        "input_counts": {"sources": len(master.get("sources", [])), "records": len(master.get("records", [])), "measurements": sum(len(r.get("measurements", [])) for r in master.get("records", []))},
        "output_counts": {"sources": len(output.get("sources", [])), "records": len(output.get("records", [])), "measurements": sum(len(r.get("measurements", [])) for r in output.get("records", []))},
        "accepted_measurements": [
            {
                "source_id": item["source_id"], "path": item["path"], "formula": item["formula"],
                "formula_method": item["formula_method"], "property": item["property"], "value": item["value"],
                "unit": item["unit"], "temperature_c": item["temperature_c"], "page": item["page"],
                "evidence_text": item["sentence"],
            }
            for item in new_items
        ],
    }
    if not args.preview:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        audit["output_sha256"] = sha256_bytes(output_path.read_bytes())
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

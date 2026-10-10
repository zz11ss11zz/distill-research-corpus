"""Deterministic context screening and conclusion provenance; never promotion."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


AUDIT_VERSION = "1.0.0"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest().upper()


def validate_context_rules(rules):
    required = rules.get("required_context", [])
    patterns = rules.get("context_patterns", {})
    if not isinstance(required, list) or any(not isinstance(k, str) or not k.strip() for k in required):
        raise ValueError("required_context must be a list of nonempty field names")
    if len(set(required)) != len(required):
        raise ValueError("Duplicate required_context field")
    if not isinstance(patterns, dict) or set(patterns) - set(required):
        raise ValueError("context_patterns must map required_context fields to regexes")
    if "source_page" in patterns:
        raise ValueError("source_page uses a built-in document/page locator check")
    for pattern in patterns.values():
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError("Context regexes must be nonempty strings")
        compiled = re.compile(pattern, re.IGNORECASE)
        if compiled.search(""):
            raise ValueError("Context regexes must not match empty text")
    return required, patterns


def unique_index(records, key):
    index = {}
    for record in records:
        identity = record.get(key)
        if not isinstance(identity, str) or not identity or identity in index:
            raise ValueError(f"Missing or duplicate {key}")
        index[identity] = record
    return index


def locate_fact(fact, documents):
    """Check the text locator, including any stronger span hashes that exist."""
    document = documents.get(fact.get("source_id"))
    if document is None:
        raise ValueError("Fact references an unknown document")
    number = fact.get("page")
    if type(number) is not int or number < 1:
        raise ValueError("Fact page must be a positive integer")
    pages = [p for p in document.get("pages", []) if p.get("page") == number]
    if len(pages) != 1:
        raise ValueError("Fact page is missing or ambiguous")
    text = pages[0].get("text", "")
    evidence = fact.get("evidence_text")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("Fact has no evidence text")
    if re.sub(r"\s+", "", evidence) not in re.sub(r"\s+", "", text):
        raise ValueError("Fact evidence text is absent from its page")
    span = fact.get("source_span")
    if span:
        if (span.get("source_id") != fact["source_id"] or span.get("page") != number
                or span.get("offset_unit") != "utf16_code_units"):
            raise ValueError("Fact span identity/unit mismatch")
        page_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if span.get("page_sha256", "").lower() != page_hash:
            raise ValueError("Fact span page hash mismatch")
        start, end = span.get("start"), span.get("end")
        encoded = text.encode("utf-16-le")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(encoded) // 2:
            raise ValueError("Fact span offsets out of bounds")
        raw = encoded[start * 2:end * 2].decode("utf-16-le")
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != span.get("raw_text_sha256", "").lower():
            raise ValueError("Fact span text hash mismatch")
        if re.sub(r"\s+", "", raw) != re.sub(r"\s+", "", evidence):
            raise ValueError("Fact span does not locate its evidence text")
    return document


def build_context_checks(facts, documents, profile):
    required, patterns = validate_context_rules(profile.get("evidence_rules", {}))
    unique_index(facts, "fact_id")
    docs = unique_index(documents, "source_id")
    records = []
    for fact in facts:
        # Legacy retained facts may have stale text locators; report, never erase.
        try:
            locate_fact(fact, docs)
            locator_status = "located_in_cached_page"
        except (ValueError, UnicodeError):
            locator_status = "locator_needs_review"
        fields = []
        for name in required:
            matches = []
            if name == "source_page":
                status = "located_in_cached_page" if locator_status == "located_in_cached_page" else "locator_needs_review"
            elif name not in patterns:
                status = "not_configured"
            else:
                text = fact.get("evidence_text", "")
                matches = [{"text": m.group(), "start": m.start(), "end": m.end(),
                            "offset_unit": "unicode_code_points"}
                           for m in re.finditer(patterns[name], text, re.IGNORECASE) if m.end() > m.start()]
                status = "located_in_candidate" if matches else "not_located_in_candidate"
            fields.append({"field": name, "status": status, "matches": matches})
        records.append({"fact_id": fact["fact_id"], "source_id": fact["source_id"],
                        "page": fact["page"], "verification_status": fact["verification_status"],
                        "locator_status": locator_status, "fields": fields,
                        "needs_review": locator_status != "located_in_cached_page" or any(
                            f["status"] not in {"located_in_candidate", "located_in_cached_page"} for f in fields)})
    return {"schema_version": AUDIT_VERSION, "profile_sha256": profile["profile_sha256"],
            "facts_sha256": digest(facts), "documents_sha256": digest(documents),
            "scope": "candidate_evidence_text_only; source_page checks cached document text",
            "trust_boundary": "Pattern hits and valid locators do not verify scientific context or pairing.",
            "statistics": {"facts": len(records), "facts_needing_review": sum(r["needs_review"] for r in records),
                           "field_status_counts": dict(Counter(f["status"] for r in records for f in r["fields"]))},
            "records": records}


def bind_conclusions(payload, facts, documents, profile, root):
    """Bind explicit support/contradiction relations without deciding their truth."""
    if not isinstance(payload, dict) or payload.get("schema_version") != AUDIT_VERSION:
        raise ValueError("Conclusion input requires schema_version 1.0.0")
    conclusions = payload.get("conclusions")
    if not isinstance(conclusions, list):
        raise ValueError("conclusions must be an array")
    unique_index(conclusions, "conclusion_id")
    indexed = unique_index(facts, "fact_id")
    docs = unique_index(documents, "source_id")
    checks = build_context_checks(facts, documents, profile)
    context = {r["fact_id"]: r for r in checks["records"]}
    verified_sources = set()
    records = []
    for conclusion in conclusions:
        if not isinstance(conclusion.get("text"), str) or not conclusion["text"].strip():
            raise ValueError("Conclusion text is required")
        kind = conclusion.get("claim_type")
        if kind not in {"source_fact", "inference", "recommendation"}:
            raise ValueError("claim_type must be source_fact, inference or recommendation")
        if kind != "source_fact" and (not isinstance(conclusion.get("rationale"), str) or not conclusion["rationale"].strip()):
            raise ValueError("Inferences and recommendations require rationale")
        evidence = conclusion.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("Every conclusion needs explicit fact references")
        bound = []
        seen = set()
        for link in evidence:
            fid, relation = link.get("fact_id"), link.get("relation")
            if fid not in indexed or fid in seen:
                raise ValueError("Unknown or duplicate conclusion fact reference")
            if relation not in {"supports", "contradicts", "context"}:
                raise ValueError("Evidence relation must be supports, contradicts or context")
            seen.add(fid)
            fact = indexed[fid]
            document = locate_fact(fact, docs)
            if document["source_id"] not in verified_sources:
                from corpus_profile import local_path
                source = local_path(root, document["path"])
                with source.open("rb") as stream:
                    actual_hash = hashlib.file_digest(stream, "sha256").hexdigest().upper()
                if actual_hash != document["sha256"].upper():
                    raise ValueError("Conclusion source bytes changed; refresh the corpus first")
                verified_sources.add(document["source_id"])
            bound.append({"fact_id": fid, "relation": relation, "source_id": fact["source_id"],
                          "source_path": document["path"], "source_sha256": document["sha256"],
                          "page": fact["page"], "evidence_text": fact["evidence_text"],
                          "verification_status": fact["verification_status"],
                          "source_span": fact.get("source_span"), "context_check": context[fid]})
        supports = [e for e in bound if e["relation"] == "supports"]
        if not supports:
            raise ValueError("Conclusion requires at least one supporting fact")
        conflicts = conclusion.get("conflicts", [])
        if not isinstance(conflicts, list):
            raise ValueError("conflicts must be an array")
        for conflict in conflicts:
            ids = conflict.get("fact_ids")
            if (not isinstance(ids, list) or len(ids) < 2 or len(set(ids)) != len(ids)
                    or set(ids) - seen or not isinstance(conflict.get("description"), str)
                    or not conflict["description"].strip()):
                raise ValueError("Conflict needs two distinct bound fact IDs and a description")
        states = [e["verification_status"] for e in supports]
        if all(s == "human_verified" or s.startswith("human_verified_") for s in states):
            state = "supporting_facts_human_verified"
        elif all(s == "agent_verified" or s.startswith("agent_verified_") for s in states):
            state = "supporting_facts_agent_verified"
        elif all(s == "source_located_not_human_verified" for s in states):
            state = "supporting_facts_machine_candidates"
        else:
            state = "supporting_facts_mixed_or_project_specific_status"
        records.append({"conclusion_id": conclusion["conclusion_id"], "text": conclusion["text"],
                        "claim_type": kind, "rationale": conclusion.get("rationale"),
                        "binding_status": "references_validated_not_conclusion_verified",
                        "support_state": state, "has_conflicting_evidence": bool(conflicts) or any(
                            e["relation"] == "contradicts" for e in bound),
                        "context_needs_review": any(e["context_check"]["needs_review"] for e in bound),
                        "conflicts": conflicts, "evidence": bound})
    return {"schema_version": AUDIT_VERSION, "profile_sha256": profile["profile_sha256"],
            "input_sha256": digest(payload), "facts_sha256": digest(facts),
            "documents_sha256": digest(documents), "trust_boundary":
            "References and source bytes validated; semantic support, conflicts and conclusions require review.",
            "conclusions": records}


def write_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix="evidence_audit_", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)

# Output contract

Read this reference only when adapting the default layout, output schema or evidence statuses.

## Canonical output

The default output root is `outputs/json/knowledge_distillation/`.

| Artifact | Purpose |
|---|---|
| `manifest.json` | Counts, reuse/extraction statistics, quality boundary and artifact paths |
| `source_inventory.json` | Every canonical path, type, size and SHA-256 |
| `deduplication.json` | Duplicate paths mapped to one canonical source |
| `documents.json` | Page text and document-level distilled indexes |
| `evidence_facts.json` | Page-located machine fact candidates |
| `datasets.json` | Dataset, archive, code and model profiles |
| `tabular_data_manifest.json` | CSV/XLSX conversion index and aggregate counts |
| `tabular/*.json` | Complete table rows and cells, one JSON per unique source |
| `ocr_pages.json` | OCR text keyed by source hash and page |
| `master_collections.json` | Existing authoritative JSON collections referenced by hash |

## Identity and deduplication

- Source identity is the uppercase SHA-256 of file bytes.
- `source_id` is deterministic from SHA-256 and stable across path changes.
- Same hash means one extracted record plus alias paths.
- Same DOI or normalized title with different hashes is not enough to discard a file.

## Evidence statuses

- `source_located_not_human_verified`: deterministic extraction with a source and page locator; not a formal verified measurement.
- Existing project-specific verified/page-anchored records retain their stronger status and are referenced as master collections.
- OCR text is evidence-location support, not proof that chemical symbols, subscripts or units were recognized perfectly.

## Large-data rule

Do not inflate the knowledge directory by duplicating large raw archives or existing master JSON payloads. Convert unique CSV/XLSX cells, profile archive members and compressed JSON shapes, and reference authoritative master JSON files by path plus hash.

## Cache invalidation

Profile changes refresh candidates from cached pages automatically using the profile fingerprint. Use a full rebuild when page extraction, OCR merging, dataset profiling or output schema requires re-reading sources. Path-only moves and newly added sources remain incremental; existing verified facts and decisions are preserved.

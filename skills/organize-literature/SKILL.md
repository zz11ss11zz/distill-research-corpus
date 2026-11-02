---
name: organize-literature
description: Organize local scholarly PDFs and manage project literature libraries through classification, deduplication, consistent filenames, verified metadata, registration and catalog synchronization. Use for literature intake or file organization, independently or before research-corpus extraction; manuscript writing and citation formatting belong to writing skills.
---

# 文献整理 / Literature organization

Merge the former `organize-academic-pdfs` and `ingest-literature` workflows. This skill works independently and as the literature-intake subskill of `distill-research-corpus`. Resolve this folder before running its helpers; no parent skill is required for standalone use.

## Directory and Excel ledger contract

Use the user's explicitly specified source and literature destination. If the user has not specified directories, use the current project root as source and `<project>/literature` as destination; outside a project use the current working directory. State the resolved paths in the preview, without blocking on a directory question when the default is clear. Never assume another project's path.

On apply, create `literature/paper`, `literature/patent`, and `literature/thesis`, plus `literature/literature-ledger.xlsx`. An explicitly chosen destination replaces the `literature` root. Name papers `<venue> - <year> - <title>.pdf`, theses `<school> - <year> - <title>.pdf`, and patents `<publication-number> - <year>.<ext>`, unless the user specifies a different rule. The Excel ledger records category, title, authors, year, venue/school, DOI, patent number, relative file path, SHA-256, and original path. Preserve prior rows on incremental runs. Exclude the destination tree from the source scan to avoid importing organized copies again. Missing classification metadata must be resolved from evidence or remain pending, never invented for naming.

For new/default libraries, file organization and the Excel ledger are the default deliverable, including intake requests. Use the legacy CSV registration adapter only when an existing project contract explicitly requires it, and maintain the Excel ledger for the organized final files. Do not introduce a parallel CSV catalog by default. Existing registered paths and unsupported Excel schemas require scoped adaptation before changes.

## Choose the requested outcome

| Request | Mode and supporting instructions |
|---|---|
| Classify downloaded PDFs, deduplicate files, give them consistent names | [File organization](references/file-organization.md) |
| Add papers to a project's maintained library, verify metadata, assign IDs, update catalogs | [Library ingestion](references/ingestion.md) |
| Organize and register a collection | Use both modes, with the existing project catalog and canonical PDF paths governing the final layout |

Read only the relevant mode. File organization does not by itself register papers; registration does not imply scientific evidence extraction or manuscript citation formatting. Do not download missing papers unless requested.

## Shared contract

- Inspect project rules, existing catalogs and source/destination directories first. Preserve the project's naming, IDs and canonical registry. An existing `.xlsx` catalog needs a compatible adapter; the legacy ingestion helper writes CSV, Markdown and JSON; the organization helper writes the Excel master ledger. Do not create a parallel CSV library merely because the helper cannot handle the existing registry.
- Preview the exact batch, resolve metadata ambiguity and path conflicts, then apply authorized changes. Review is an Agent check; it does not introduce a second permission gate. Keep source files by default and never overwrite a different PDF at the same target path.
- Distinguish byte-identical files, bibliographic duplicates and byte-distinct editions. Preserve source identities and report conflicting editions. Deletion needs an explicit request.
- For naming, the organization helper supports `paper/<venue> - <year> - <title>.pdf`, `thesis/<school> - <year> - <title>.pdf`, and `patent/<publication-number> - <year>.<ext>`. These are defaults for organization, not a mandate to rename an existing registered library.
- When both modes apply, choose one canonical final path per document. Do not rename a registered PDF without updating every maintained path reference. The two helpers are separate operations, not one transaction; reconcile each successful item and any partial failures before continuing.
- Verify bibliographic facts from the document and authoritative metadata; filenames and automatic extraction are candidates. Missing metadata stays unresolved. Never infer a document's DOI from its reference list.
- Report copied/registered/already-present/excluded/unresolved/failed items, resulting paths, catalog changes and applicable hash checks. Every applied file-organization run also updates `literature-ledger.xlsx` in the literature directory, retaining previously registered rows.

## With research-corpus extraction

If called from `distill-research-corpus`, finish the requested intake first and return canonical document paths, hashes, registry IDs when available, aliases and unresolved items. Check these paths against the project's `config/research-corpus.json` source roots. Do not silently change a profile or move unrelated inbox files. Then let the parent run its own preflight and extraction. Registration IDs and extraction source/fact IDs are different identifiers; never treat registration as scientific verification.

## Helpers

Use a discovered Python executable and absolute helper paths:

```text
<python> <skill>/scripts/organize_academic_pdfs.py --root <project> --no-crossref
<python> <skill>/scripts/organize_academic_pdfs.py --source <downloads> --output <literature-directory> --no-crossref
<python> <skill>/scripts/ingest_literature.py --root <project> --metadata <paper.json> --pdf <paper.pdf>
```

Both default to preview; add `--apply` only for the reviewed authorized scope. `--no-crossref` makes organization offline; omit it only when metadata lookup is appropriate. Organization needs `pypdf` for PDF metadata extraction and `openpyxl` for its Excel ledger; ingestion uses the Python standard library and has helper-specific DOI/PDF limitations described in its reference.

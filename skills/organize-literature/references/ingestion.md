
# Literature ingestion

Verify bibliographic facts from authoritative sources, then use the bundled script for deterministic, cross-project ingestion. Keep manuscript text unchanged unless the user separately requests a revision.

## Workflow

1. Locate the project root and inspect existing literature files without writing.
2. Use the project's canonical registry first for DOI/title deduplication; expand to other catalogs and PDF filenames only when that index is insufficient.
3. Verify title, full authors, year, venue, article number or pages, and DOI from the publisher or DOI landing page. Use a second authoritative source when fields conflict.
4. Obtain a lawful PDF when full-text ingestion is requested. For citation-only registration, use the project's metadata-only path and mark full text unavailable. Never bypass access controls or invent a PDF/DOI to satisfy helper requirements.
5. Prepare a UTF-8 metadata JSON file using [references/metadata-schema.md](metadata-schema.md).
6. Run the script without `--apply`. Review the proposed ID, paths, duplicates, and files to be changed.
7. When the preview for the item is conflict-free and within the user's requested scope, run with `--apply` without another approval question. An explicit preview-only request ends after the reviewed preview.
8. Validate identifier uniqueness, record counts, manifest totals and UTF-8 names, plus PDF signature/hash when a PDF was ingested. Complete the project's required registry and index synchronization before claiming ingestion is complete.

## Commands

Use the bundled Python script with an absolute path. Prefer the Codex bundled Python when the system executable is unavailable. In these command templates, replace `<python-executable>` and `<skill-dir>` with discovered absolute paths; the commands do not assume the current directory contains `scripts/`.

```powershell
& "<python-executable>" "<skill-dir>\scripts\ingest_literature.py" --root <project> --metadata <paper.json> --pdf <paper.pdf>
& "<python-executable>" "<skill-dir>\scripts\ingest_literature.py" --root <project> --metadata <paper.json> --pdf <paper.pdf> --apply
& "<python-executable>" "<skill-dir>\scripts\ingest_literature.py" --root <project> --metadata <paper.json> --pdf-url <official-or-open-url> --apply
```

## Project adaptation

- If `research_outputs/literature_matrix.csv` has the recognized 16-column schema, update it and the associated Markdown and `ref` manifests.
- If another canonical library exists, use its maintained adapter or make a scoped workspace adaptation after inspecting the schema; do not create a parallel library because the bundled helper does not recognize it. Create portable `literature/` only for a requested new library or a project with no existing canonical library. This condition also governs the portable-adapter reference.
- Preserve the existing newline and CSV quoting style where possible.
- Follow the canonical project's identifier convention. The bundled recognized/portable adapters default to the next unused `R###` unless their supported `--id` is supplied; do not impose that convention on another project schema.
- Treat a repeated normalized DOI as an item-level duplicate: verify the existing record/path, report it as already present, and continue other requested items. Investigate identity conflicts without overwriting either source.
- Reject non-PDF responses, conflicting content, malformed metadata and inconsistent IDs from this helper's apply path. Its 10 kB minimum and required DOI/PDF are helper limitations, not universal definitions of valid literature. If the original source is valid but unsupported, use the project's compatible path or a verified scoped adaptation; do not weaken content/identity checks or claim an unapplied item was ingested.
- Do not run project-specific bulk scripts unless their scope has been inspected.

## Safety and reporting

- Preview and inspect before apply, including unattended batches. This technical verification is performed by the Agent and does not add a user approval gate.
- Never overwrite a different PDF with the same target filename.
- Keep source PDFs outside the project untouched.
- Report the assigned ID, verified citation, changed files, PDF hash, and metadata limitations.
- Do not claim that metadata is verified merely because it was user supplied.
- Independent metadata/PDF verification may run in parallel; serialize writes to shared catalogs and ID assignment. Isolate per-item failures, continue unaffected items, and report new, already-present, pending and failed items separately. Do not call a requested batch complete while required ingestion/synchronization remains unfinished.

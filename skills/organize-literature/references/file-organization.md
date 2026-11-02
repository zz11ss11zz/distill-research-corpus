
# Organize Academic PDFs

Use the bundled script for deterministic preview, copying, renaming, and validation. Preserve source files by default.

## Workflow

1. Inspect project rules and identify the complete source roots and destination root.
2. Distinguish locally held full text from citation-only records. Never equate JSON source IDs, review references, or database rows with local documents.
3. Run a preview without `--apply`. In the templates below, replace `<python-executable>` and `<skill-dir>` with discovered absolute paths; do not assume a workspace-relative `scripts/` directory:

```powershell
& "<python-executable>" "<skill-dir>\scripts\organize_academic_pdfs.py" --source <source-root> --output <destination-root> --include-patent-markdown
```

4. Review `unresolved`, `conflicts`, exact duplicates, and bibliographic duplicates. For scans, malformed metadata, or no-DOI files, create an overrides JSON using [references/metadata-overrides.md](metadata-overrides.md), then preview again.
5. Once the preview for the actual apply batch is conflict-free and copying is within the requested scope, apply without asking for the same approval again. For preview-only requests, stop after the reviewed preview:

```powershell
& "<python-executable>" "<skill-dir>\scripts\organize_academic_pdfs.py" --source <source-root> --output <destination-root> --include-patent-markdown --overrides <overrides.json> --apply
```

6. Verify output counts, hashes, PDF readability, filename collisions, and maximum path length. Reconcile all requested items as copied, already present, excluded, unresolved or failed. If a subset is blocked, resolve supported overrides or isolate a conflict-free batch using verified helper capabilities; preserve source identities and the full pending list. Do not invent a skip-conflicts flag or remove the helper's collision guard. Report partial progress accurately rather than calling the full task complete.

## Output Rules

- Journal articles, reviews, data papers, and confirmed preprints: `paper/<venue> - <year> - <title>.pdf`
- Theses and dissertations: `thesis/<school> - <year> - <title>.pdf`
- Patents: `patent/<publication-number> - <year>.<ext>`
- Replace Windows-invalid filename characters, collapse whitespace, and truncate long titles while retaining the category prefix and naming structure.
- Deduplicate exact files by SHA-256 and bibliographic items by normalized DOI, then normalized title and year.
- Prefer a canonical main article over an inbox copy or source-package duplicate.

## Safety Boundaries

- Preview is mandatory before `--apply`; the Agent reviews it as a technical check. Existing user authorization for the unchanged copy/rename scope remains valid.
- Never delete source files merely because they share a DOI; different publisher versions can have different hashes.
- Use `--delete-exact-duplicates` only when the user explicitly requests deletion and the preview identifies byte-identical files. Keep at least one canonical copy.
- Exclude SI, supporting information, Source Data, reports, contracts, project plans, and datasets unless the user explicitly expands the destination taxonomy.
- Local organization alone does not include downloading missing full text. List citation-only sources as unavailable locally; when the user also requests acquisition, route that separate phase to literature ingestion and continue within its authorized scope.

## Script Notes

- The script uses `pypdf` for PDF text and metadata extraction when available.
- Crossref lookup is enabled by default for detected DOIs; pass `--no-crossref` for offline or filename-driven organization.
- The apply run writes `_organization_manifest.json` under the destination root for auditability.

---
name: distill-research-corpus
description: Incrementally extract local research documents, tables and datasets into deduplicated, page-traceable JSON using a project-owned material profile. Use for corpus extraction, OCR and refresh; use ingestion skills for adding references and project skills for domain-specific evidence acceptance.
---

# Research corpus extraction core

Use this shared engine for document text, OCR, table conversion, hashes, incremental caching and candidate provenance. Material systems, property patterns, source directories and evidence requirements belong in the project, not this skill.

## Select the project profile

1. Read the current project rules and its domain extraction skill when present.
2. Read `config/research-corpus.json`, or the explicitly supplied `--config` path. Do not infer directories or property definitions from another project. A missing or invalid profile is an error, not permission to create a parallel corpus.
3. Read [references/project-profile.md](references/project-profile.md) only when creating or changing a profile. Agree on scientifically meaningful fields and conditions; regex matches remain candidates.
4. Finish authorized intake before extraction. Do not move unrelated inbox files to clear a check. Run the project's intake preflight when it has stronger requirements.

## Run

Resolve the installed skill directory and Python executable before using these templates:

```text
<python> <skill>/scripts/preflight_corpus.py --root <project> [--config <profile>]
<python> <skill>/scripts/distill_complete_knowledge_base.py --root <project> --inventory-only [--config <profile>]
<python> <skill>/scripts/run_incremental_distillation.py --root <project> [--config <profile>]
```

Use a project compatibility entry point when it is part of an existing intake contract. Inventory preview is useful for a first run or changed source layout; routine additions remain incremental. Preserve source files and byte-distinct editions. Hash-identical files share a source ID with alias paths.

The profile fingerprint invalidates candidate caches when extraction configuration changes. Refresh candidates from cached page text; retain prior fact IDs, verified payloads, and disposition history. Use `--full` only when page extraction, OCR merging, dataset profiling or schema changes require re-reading sources. Never promote machine candidates by changing a status string.

Windows OCR is available through the bundled orchestrator. Unsupported or unreadable sources remain explicit failures; `--skip-ocr` is only appropriate for an accepted incomplete text scope. Table conversion retains cells and archive profiling retains structural metadata, not a claim of semantic understanding.

## Evidence and delivery

- Every new deterministic fact remains `source_located_not_human_verified`. Source locations support later checking; they do not establish scientific correctness.
- Domain-specific acceptance, normalization, formal master publication and verification belong to the project's skill and evidence rules. This core does not supply a universal promotion script.
- Do not overwrite prior verified facts, erase decisions, or replace project publishers. Use dated snapshots where the project requires them.
- Validate unique source/fact identities, source coverage, unreadable/OCR/table failures, and referenced master hashes. Completion means the agreed scope passed its applicable checks, not that every property was found.
- Report extracted/reused counts, candidates, aliases, failures and remaining evidence limitations. Sync project indexes/wiki only when required and materially changed.

Read [references/output-contract.md](references/output-contract.md) for artifact or schema changes. Do not generate inspection sidecars.

# Project material profile

Use `config/research-corpus.json` by default; `--config` selects another JSON file. Paths inside the profile must be relative to the supplied project root and remain within it. No material system is assumed by the core.

Required fields:
- `schema_version`: `1`.
- `canonical_roots`: a nonempty mapping of `paper`, `thesis`, `patent`, or `dataset` to disjoint source directories. Only present categories are required.
- `formula_pattern`: a case-sensitive Python regex for candidate material identities; validate against realistic formulas, abbreviations and non-material words.
- `value_unit_pattern`: a case-insensitive Python regex for candidate values and units. It does not pair a value with a material automatically.
- `evidence_rules.candidate_status`: exactly `source_located_not_human_verified`.

Optional fields:
- `material_system`: descriptive domain label.
- `keyword_groups`: theme name to case-insensitive Python regex, used to screen candidate sentences/table rows.
- `inbox`: pending intake directory; project-specific preflights may impose additional rules.
- `evidence_rules.reference`: existing project-relative evidence instruction file; read it for acceptance work. `required_context` lists domain-specific context to verify. These instructions are recorded in the manifest, not automatically certified by regex matching.
- `master_sources`: list of existing collection descriptors. Each has `path`; optionally `pointer` and `pointer_keys` select a current snapshot from a JSON pointer document. `existing_index_type` preserves a unique collection of that database type from the output's existing master index and checks its hash.

Test the profile on a small isolated corpus before processing production. Include relevant positives, confusing negatives, unit/condition variants, changed-profile cache refresh, and retained verified evidence. A chemistry-specific profile requires its own scientific validation; passing parser tests alone does not establish recall or accuracy.

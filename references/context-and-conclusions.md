# Context screening and conclusion provenance

## Context checks during extraction

Normal extraction writes `context_checks.json` without changing candidate facts, IDs, review statuses or disposition histories. Inventory-only and migration staging modes keep their existing scope. The manifest references the report and counts facts with open review items. The corpus validator recomputes the report and rejects stale or edited checks.

In project `evidence_rules`, keep `required_context` as a list of field names. Optionally add `context_patterns`, a mapping of those names to case-insensitive Python regexes. Unknown field keys, invalid patterns and patterns matching empty text are rejected before extraction. `source_page` is reserved for the built-in cached-document locator check.

```json
{
  "candidate_status": "source_located_not_human_verified",
  "required_context": ["temperature", "atmosphere", "test_method", "source_page"],
  "context_patterns": {
    "temperature": "\\b\\d+(?:\\.\\d+)?\\s*(?:K\\b|°\\s*C\\b)",
    "atmosphere": "\\bin air\\b"
  }
}
```

Field results:

| Status | Meaning |
|---|---|
| `located_in_candidate` | Pattern matched within this fact's `evidence_text`; matches include Unicode code-point offsets into that text |
| `not_located_in_candidate` | Configured pattern did not match this fragment; the full paper may report it elsewhere |
| `not_configured` | Required field has no detection pattern; manual review is still needed |
| `located_in_cached_page` | Built-in source/page/text and available UTF-16 span/hash checks passed |
| `locator_needs_review` | Cached-page or span locator failed; preserved evidence is retained for repair/review |

These statuses screen review work. They do not establish material-to-condition pairing, scientific correctness, or fulfillment of a project's acceptance rules. A regex hit does not mean human verification. `needs_review` flags unlocated or unconfigured items and stale locators; `false` means screening found no such gap, not permission to publish. Old profiles without patterns continue working. No universal scientific patterns are supplied. Choose narrow patterns appropriate to the material, property and source notation.

## Bind downstream conclusions

Create a project-owned JSON input only for conclusions requested by the user, respecting any project writing approval rules. Copy actual IDs from the current `evidence_facts.json`; invented or unknown IDs are rejected. Use `source_fact`, `inference` or `recommendation` for `claim_type`. Inferences and recommendations require a `rationale` explaining the inferential step. Every conclusion requires at least one `supports` relation; additional links may be `contradicts` or `context`.

```json
{
  "schema_version": "1.0.0",
  "conclusions": [
    {
      "conclusion_id": "project-claim-1",
      "text": "Replace with a conclusion grounded in the selected evidence.",
      "claim_type": "inference",
      "rationale": "Explain how the cited source facts support this inference and its limits.",
      "evidence": [
        {"fact_id": "COPY_ACTUAL_FACT_ID", "relation": "supports"},
        {"fact_id": "COPY_OTHER_FACT_ID", "relation": "contradicts"}
      ],
      "conflicts": [
        {"fact_ids": ["COPY_ACTUAL_FACT_ID", "COPY_OTHER_FACT_ID"], "description": "Describe the reported difference and relevant conditions."}
      ]
    }
  ]
}
```

`conflicts` is optional. Each conflict references at least two distinct facts already linked to that conclusion. Contradiction links and declared conflicts remain visible; the tool does not discover all scientific conflicts or choose a preferred result. `source_fact` describes the author's intended claim category; the binder does not certify that the text faithfully paraphrases the cited facts.

From the skill/repository directory, use a project root and workspace-relative input/output paths:

```sh
python scripts/bind_research_conclusions.py --root /path/to/project --input conclusions.json
python scripts/bind_research_conclusions.py --root /path/to/project --input conclusions.json --validate-only
```

The default binding is `outputs/json/knowledge_distillation/conclusion_bindings.json`. Match extraction's `--config` and `--output` when using alternatives. `--bound-output` selects a separate workspace-relative JSON artifact. Inputs, canonical source directories, profile/master files and existing non-binding JSON are protected from overwrite. Failed validation leaves any previous binding intact.

Bindings record exact fact IDs, source paths/hashes, page/span locations, evidence text, original verification statuses, context checks, rationale and conflict declarations. Referenced original file bytes must still match cached document hashes. Invalid text locators, duplicate IDs, unsupported relations, missing support and orphan conflicts fail before writing.

`binding_status` is always `references_validated_not_conclusion_verified`. `support_state` distinguishes human-verified support, agent-verified support, machine candidates and mixed/project-specific statuses without upgrading any source record. Retained statuses are reported, not independently re-certified.

Input, fact, document and profile fingerprints make stale binding detection deterministic. After changing extraction, profiles or conclusions, rerun `--validate-only`; review changed evidence and rebuild the binding when appropriate. Conclusion binding is opt-in and is not automatically regenerated by extraction, so author-reviewed conclusions are not silently rewritten.

## Reproducible synthetic example

```sh
python scripts/run_incremental_distillation.py --root examples/battery
python scripts/bind_research_conclusions.py --root examples/battery --input conclusions.example.json
python scripts/bind_research_conclusions.py --root examples/battery --input conclusions.example.json --validate-only
```

The included conclusion refers only to invented fixture data. It remains supported by an unverified machine candidate and retains missing-condition review items.

## Compatibility

Skill package version is `0.2.0`; the existing manifest and candidate schemas remain unchanged (`1.0.0` manifest). New context/binding reports use their own `1.0.0` contract and are additive. Old profiles run without edits; new condition rules belong to project configuration. No full source reread is required merely to add context checks. The normal profile fingerprint still refreshes candidates when a profile changes, preserving prior records.

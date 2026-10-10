# Changelog

## 0.2.0 — 2026-10-10

- Added per-fact `context_checks.json` to normal extraction, with project-owned context patterns, explicit unlocated/unconfigured states and cached-page/span validation.
- Added opt-in conclusion binding with support/contradiction/background relations, inference rationale, preserved conflicts and distinct human/agent/machine review states.
- Validate original source hashes, current fact references and input fingerprints; reject stale binding checks and protect inputs, raw sources and master collections from overwrite.
- Added 13 evidence-audit regressions and a runnable synthetic battery conclusion example; repository checks now exercise binding and stale-input validation.
- Pinned repository text fixtures to LF so the example's byte-derived fact references remain stable across Windows and Ubuntu checkouts; actual corpus identity still follows original source bytes.
- Compatibility: manifest schema remains `1.0.0`, existing fact payloads and IDs remain unchanged, and old project profiles work without context patterns. New audit reports use additive `1.0.0` contracts. Inventory-only and migration staging behavior is unchanged.
- Trust boundary: condition pattern hits do not establish scientific completeness; validated references do not verify conclusions or promote machine candidates.

## 0.1.0 — 2026-09-15

- Extracted a shared research-corpus engine from a project-specific workflow.
- Added project-owned material profiles with source-path boundaries and machine-evidence status validation.
- Preserved verified payloads, existing identities and disposition histories during candidate refresh and migration.
- Added synthetic battery, alloy and SOFC examples, plus an optional SOFC measurement staging helper.
- Added English development documentation and a Windows/Ubuntu fixture-test workflow.
- Kept automatic Windows OCR as an optional host-specific capability; no real-corpus accuracy benchmark is claimed.

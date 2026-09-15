# Formal experimental promotion

Use this mode only when the user explicitly asks to write distilled facts into a formal experimental master JSON.

The project acceptance and publishing contract takes precedence over this generic
helper. Its grade-B, not-human-verified output is a staged candidate whenever the
formal master requires independently source-verified evidence; a locator match
alone does not authorize formal publication. Reuse an explicit promotion request
after the Agent reviews the preview, but complete required source checks and use
the project's publisher, snapshot and current-master synchronization mechanism.
Do not ask again merely because preview finished, and do not change evidence
status to clear a gate.

## Acceptance gate

A promoted measurement must have, in one page-located evidence sentence or deterministic table row:

- one resolvable material formula, either explicit or mapped from an abbreviation defined in the same primary document;
- a recognized experimental property;
- a numeric value and compatible unit;
- an explicit test temperature when the property is temperature-dependent;
- the canonical local source path and PDF page;
- exact evidence text.

Reject references, review-only statements, cited prior work, predictions, ranges that cannot be paired, malformed OCR units, and ambiguous multi-material sentences. Do not infer missing electrolytes, atmosphere, normalization, or electrode factors.

## Output semantics

- Write a new dated snapshot; never overwrite the input master.
- Use `data_status: directly_reported` only for explicit source sentences or table rows.
- Use evidence grade `B_primary_locator_or_quote_unverified` and `verification_status: not_human_verified`.
- Set `source_location.human_verified` to `false` and add every promoted measurement to `human_review_queue`.
- Deduplicate against the input master and within the batch by source, normalized formula, property, value, unit and temperature.
- Emit a separate audit JSON containing accepted counts, rejection reasons, source coverage and output hashes.

Human verification may later upgrade a record to grade A, but promotion itself must never make that claim.

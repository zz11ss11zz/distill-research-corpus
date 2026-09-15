# Evidence model and limitations

## What extraction establishes

- Which readable source bytes were inventoried (SHA-256), with alias paths for byte-identical files.
- Which text, candidate formulas, numbers, units and themes were observed by deterministic extraction.
- Where a candidate came from: source identity, page/text record and available source-span metadata.

## What extraction does not establish

- Correct material-to-value pairing, physical validity, measurement semantics, or fulfillment of all profile context requirements.
- Reliable recovery of arbitrary scanned tables, chart values, chemical subscripts or unusual formula notation.
- Human review merely because a record already carries a verified status. Preservation is not new verification.

## Preservation and validation

The core retains previously verified payloads, legacy candidate identities and disposition histories. Tests cover refresh/full/version-change paths, conflicting overlays, failed extraction, missing preserved sources, migration staging and repeated migration. A corrupt input or conflicting identity fails rather than silently erasing evidence.

Validators check identities, counts, coverage/failure counters and master hashes. They are not scientific accuracy or completeness benchmarks. The provided battery and alloy regexes are narrow synthetic demonstrations. Production use requires source-grounded evaluation against the target material literature.

## Operational limits

- Inventory uses ripgrep's default hidden/ignore handling. Do not hide intended sources or rely on a Git-ignored corpus without checking the preview.
- Automatic OCR currently targets Windows. OCR readiness and accuracy must be tested separately on the actual host.
- Do not run concurrent writers against one output directory or registry.
- Table profiles use bounded statistics, while the table conversion stage retains rows/cells. Binary package profiles do not establish semantic understanding.
- This repository supplies no remote telemetry, hosted service or automatic publication of research data. Installing dependencies and using GitHub are separate network operations.

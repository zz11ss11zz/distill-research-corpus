# Project integration

## Ownership

Keep one shared extraction implementation. A project owns its profile, evidence protocol, optional admission/publishing gates, and original sources. An adapter skill routes to the core; it should not duplicate the engine.

Start from an example. Replace the invented fixture and narrow patterns, configure only relevant categories, and record the scientific definitions of the properties you need. Folder names are project choices; the global core contains no project-specific root.

## Existing master collections

`master_sources` is optional. It references existing JSON collections; it does not promote candidates. A descriptor may provide `path`, a JSON `pointer` with `pointer_keys`, or an `existing_index_type` used to retain a unique current collection from the output's prior index. Indexed collection hashes are checked. Do not copy an example's paths or dates into production without verifying the current project baseline.

## Updating a profile

The profile fingerprint participates in the extraction version. A profile change triggers candidate regeneration from cached pages. Historical candidates, verified payloads, IDs and dispositions are retained by design; narrowing a pattern does not delete earlier candidates. Use explicit reviewed disposition/migration steps for obsolete facts.

Changing a source root does not itself change content-hash identity. Removing sources that still back preserved facts blocks rebuilding. `--full` re-reads sources but does not authorize destroying prior evidence. A new unrelated corpus should use a separate output directory.

## Optional SOFC staging helper

`examples/sofc/scripts/promote_page_anchored_measurements.py` is a domain-specific historical example. Read its `--help` and `examples/sofc/references/formal-promotion.md`. It needs an appropriate existing master, source batch and date; it is not part of the basic quick start and is not a general cross-material publisher. Its output remains unverified staged evidence where project gates require original-source verification. It is not exercised against a real database in this repository's fixture suite.

## Versioned development

Develop in this repository, review changes on a branch, run fixture tests and a scoped project regression, and then update the installed skill. Pin consumers to a reviewed commit when reproducibility matters. Do not point production jobs at an unreviewed working tree.

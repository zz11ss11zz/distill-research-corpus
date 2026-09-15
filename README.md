# Research Corpus Distillation

English | [中文](README.zh-CN.md)

A local-first extraction engine and Codex skill for research corpora, with **project-owned material profiles**.

Separate reusable extraction machinery from domain assumptions. The shared engine reads documents and tables, deduplicates by SHA-256, retains source locations, and refreshes candidates incrementally. Each project defines its source folders, material patterns, property themes, units, evidence requirements, and references to existing master collections.

**Status: development preview (0.1.0).** The included battery, alloy and SOFC corpora are synthetic fixtures. Machine candidates are not verified scientific measurements. No research papers, private datasets, credentials, or deployment-specific master pointers are included.

## Architecture

```text
Shared core (this repository)
  scripts/                    extraction, OCR, validation, cache preservation
  SKILL.md                    instructions for Codex
  references/                 profile and artifact contracts
          |
          v
Project workspace
  config/research-corpus.json  material system, directories, patterns, masters
  evidence-rules.md            scientific acceptance requirements
  .agents/skills/              optional project-specific workflow adapter
  literature/                 authorized source files
  outputs/json/knowledge_distillation/  generated artifacts
```

The core does not assume a particular project folder name or chemistry. The SOFC-specific measurement staging helper lives under `examples/sofc/`, not in the global extraction core.

## Requirements

- Python 3.11 or newer; the CI matrix targets 3.11 and 3.12.
- `openpyxl` and `pypdf` (see `requirements.txt`).
- `rg` (ripgrep) on `PATH`, used to inventory source files. Hidden and ignored files follow ripgrep's default behavior; use explicit, visible corpus folders.
- For automatic scanned-PDF OCR: Windows PowerShell, Windows OCR language support, and Poppler `pdftoppm` on `PATH`. OCR is optional and not exercised by the cross-platform fixture tests.

## Quick start

From the repository root:

```sh
python -m venv .venv
# Activate the environment using your shell's normal activation command.
python -m pip install -r requirements.txt
python scripts/preflight_corpus.py --root examples/battery
python scripts/run_incremental_distillation.py --root examples/battery
```

Inspect `examples/battery/outputs/json/knowledge_distillation/manifest.json` and `evidence_facts.json`. Run the same command again to exercise incremental reuse. These outputs are ignored by Git.

Try the other synthetic profiles:

```sh
python scripts/run_incremental_distillation.py --root examples/alloy
python scripts/run_incremental_distillation.py --root examples/sofc
```

## Use your own project

1. Create a project-local `config/research-corpus.json` using an example as a starting point.
2. Set disjoint, workspace-relative source folders in `canonical_roots`. You only need the categories your project uses.
3. Define scientifically appropriate formula, value/unit and theme patterns. The examples are intentionally narrow demonstrations, not complete chemical grammars.
4. Write project-specific evidence requirements and test ambiguous negatives as well as positive examples.
5. Run a preflight and inventory preview, then the incremental orchestrator:

```sh
python scripts/preflight_corpus.py --root /path/to/project
python scripts/distill_complete_knowledge_base.py --root /path/to/project --inventory-only
python scripts/run_incremental_distillation.py --root /path/to/project
```

Use `--config config/another-profile.json` to select a different profile relative to the project root. Different corpora should normally use different `--output` directories. Use the same output for a deliberate compatible profile revision when preserving its prior facts and decisions is intended.

Read [the profile guide](references/project-profile.md), [project integration](docs/project-integration.md), and [the output contract](references/output-contract.md).

## Use as a Codex skill

The repository root is an installable skill (`SKILL.md`, `scripts/`, `references/`, `agents/`). Install the repository with your Codex skill installer. Keep project profiles and evidence rules in each project rather than copying them into the global installation. The optional `.agents/skills/material-corpus` examples show a short project adapter.

You can also run the Python scripts directly without Codex. Keep a version-controlled source checkout for development; deploy tested changes to the installed skill deliberately. Do not assume edits in a clone automatically update an installed copy.

## Outputs and trust boundary

The engine emits a manifest, inventory, deduplication map, document page text, candidate facts, dataset profiles, table conversions and master-collection hash references. PDF page locations and source spans support later auditing; text-file page `1` denotes its extracted text record rather than a physical PDF page.

New facts remain `source_located_not_human_verified`. The profile's `required_context` and evidence reference describe what a reviewer must check; regex screening does not certify those conditions. Existing verified records and decision histories are preserved, not independently re-verified. See [evidence and limitations](docs/evidence-and-limitations.md).

## Development

```sh
python -m pip install -r requirements-dev.txt
python -B -m unittest discover -s scripts -p "test_*.py" -v
python -B scripts/check_repository.py
```

The GitHub Actions workflow runs the fixture suite and repository checks on Windows and Ubuntu. See [CONTRIBUTING.md](CONTRIBUTING.md) for branch, testing and review expectations, and [CHANGELOG.md](CHANGELOG.md) for changes.

## License

No open-source license has been selected yet. Public visibility alone does not grant an open-source license. Contributions should not import third-party code without recording its license and provenance.

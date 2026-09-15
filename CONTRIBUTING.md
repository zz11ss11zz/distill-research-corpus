# Contributing

Use English for repository documentation, comments and interface metadata. User-facing research reports may follow the user's language.

## Workflow

1. Create a focused branch from `main`.
2. State the observable change and affected trust boundary.
3. Add a meaningful synthetic fixture or regression when behavior changes.
4. Run `python -B -m unittest discover -s scripts -p "test_*.py" -v` and `python -B scripts/check_repository.py`.
5. Open a pull request with the problem, resulting behavior, validation, and any migration implications.

Keep material-specific rules in project profiles or domain adapters. Never weaken evidence preservation or elevate machine candidates to verified facts to make a test pass. Avoid bundling copyrighted papers, real customer data, local usernames, secrets, or generated research outputs.

Record user-visible changes in `CHANGELOG.md`. This initial development series uses version `0.1.0`; later releases should document profile/schema compatibility and engine cache invalidation. Public hosting is not a license decision; obtain approval before choosing or changing a repository license.

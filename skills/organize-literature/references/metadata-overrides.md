# Metadata overrides

Use overrides only after inspecting the title page, patent cover, DOI landing page, or another authoritative source.

The JSON root is an object keyed by a path relative to the scan root, an absolute path, or the filename. Required fields depend on `category`.

```json
{
  "raw/paper/example.pdf": {
    "category": "paper",
    "venue": "Journal Name",
    "year": 2024,
    "title": "Verified article title",
    "doi": "10.1234/example"
  },
  "raw/paper/thesis.pdf": {
    "category": "thesis",
    "school": "Example University",
    "year": 2023,
    "title": "Verified thesis title"
  },
  "raw/assets/patents/patent.pdf": {
    "category": "patent",
    "patent_number": "CN123456789A",
    "year": 2022
  },
  "raw/project/report.pdf": {
    "category": "exclude",
    "reason": "project report"
  }
}
```

Allowed categories are `paper`, `thesis`, `patent`, and `exclude`.

Do not infer a DOI from a paper's reference list. A DOI override must identify the document itself.


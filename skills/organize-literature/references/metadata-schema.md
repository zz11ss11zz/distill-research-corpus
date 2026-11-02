# Metadata schema and adapters

Create one UTF-8 JSON object per paper. The ingestion script accepts these fields.

## Required

```json
{
  "title": "Exact published title",
  "authors": ["First Author", "Second Author"],
  "year": 2024,
  "doi": "10.xxxx/example"
}
```

- `title`: Preserve the publisher's capitalization unless the project has an explicit style.
- `authors`: Prefer a JSON array of full names in publication order. A preformatted string is also accepted.
- `year`: Use the version cited by the project and record online-versus-issue ambiguity in `yearStatus`.
- `doi`: Supply the bare DOI. The script normalizes DOI URLs and `doi:` prefixes.

## Optional

```json
{
  "yearStatus": "verified from DOI and publisher metadata",
  "venue": "Journal Name",
  "volume": "12",
  "issue": "3",
  "pages": "100-110",
  "articleNumber": "4694",
  "sourceType": "Primary research",
  "primarySection": "2 Methods / 4 Challenges",
  "priority": "Core evidence",
  "batteryChemistry": "General",
  "methods": ["Active learning", "Uncertainty quantification"],
  "targetProperties": ["candidate selection", "predictive uncertainty"],
  "evidenceNote": "One concise, source-grounded statement of what the paper demonstrates.",
  "limitationOrOutlook": "Scope limits and transfer caveats.",
  "alternatePaths": ["https://doi.org/10.xxxx/example"]
}
```

Arrays and semicolon-delimited strings are both accepted for methods, target properties, and alternate paths.

## Verification hierarchy

1. Publisher article page or Crossref DOI record
2. PubMed, Europe PMC, or an institutional repository
3. The article PDF itself
4. Indexing services and author profiles

Resolve conflicts explicitly. Do not infer missing author order, year, or DOI.

## Recognized project adapter

The matrix adapter activates when `research_outputs/literature_matrix.csv` contains exactly these core fields:

`id,title,authors,year,yearStatus,doi,sourceType,primarySection,priority,batteryChemistry,methods,targetProperties,evidenceNote,limitationOrOutlook,relativePath,alternatePaths`

It stores the canonical PDF in `ref/`, updates `literature_matrix.csv` and `literature_matrix.md`, and updates `ref/reference_pdf_manifest.csv` and `.json` when present.

## Portable adapter

Use this legacy adapter only for a requested new CSV library or a project without an existing canonical registry. The default organization workflow instead creates paper/patent/thesis folders and an Excel master ledger. Never replace an existing unsupported registry with a parallel library. Legacy CSV layout:

```text
literature/
  library.csv

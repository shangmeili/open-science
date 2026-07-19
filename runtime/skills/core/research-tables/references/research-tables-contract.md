# Research-tables contract 0.1.0

## Purpose and outputs

The Agent prepares `deliverables/research-tables.json`. The native app validates
it and writes:

- `deliverables/research-tables.xlsx`;
- one `deliverables/research-tables/<table-id>.csv` per table;
- `deliverables/research-tables.audit.json`.

Generation is deterministic for identical manifest and source bytes. The XLSX
contains no formulas, macros or external links. Generation does not create a
Human approval record.

## Top-level fields

- `schema_version`: exactly `ai4heor-research-tables/v1`.
- `workbook_id`: lowercase safe ID, 1–64 characters.
- `title`: 3–160 characters.
- `language`: `zh-CN` or `en`.
- `prepared_on`: valid `YYYY-MM-DD`.
- `audience`: 2–160 characters.
- `purpose`: 8–500 characters.
- `sources`: 1–32 unique local sources.
- `tables`: 1–16 table definitions, no more than 50,000 rows in total.
- `human_review`: exactly `{ "status": "awaiting_human_review" }`.

Unknown fields are rejected at every object level.

## Sources

Each source has `id`, `path`, and `sha256`. IDs are unique safe lowercase IDs.
Paths are unique, workspace-relative regular files, must not traverse symlinks,
and must not point to generated research-table files. Every source is capped at
20 MiB and must match its declared lowercase SHA-256.

## Tables, columns and rows

Each table has a unique `id`, `title`, unique Excel-safe `sheet_name`, `purpose`,
1–24 columns and up to 10,000 rows. `Readme 说明` is reserved for the generated
provenance sheet.

Each column has:

- unique safe `id` and a `label`;
- `value_type`: `text`, `integer`, `number`, `percent`, `currency`, `boolean`,
  or `date`;
- `unit`: required for numeric types and forbidden for non-numeric types;
- optional `nullable` and optional width from 8 to 60.

Every row's `values` keys must exactly match the column IDs. Dates use valid
`YYYY-MM-DD`; integers must remain exactly representable; other numbers must be
finite. Each row also has a unique `row_id`, a `basis`, optional `source_refs`,
and optional `note`.

- `evidence` and `analysis_output` require at least one declared source ID plus
  a meaningful locator.
- `assumption` requires a 5–500-character note and no source reference.

Formula-like text beginning with `=`, `+`, `-`, or `@` is prefixed with an
apostrophe in CSV output. It remains inert text in the formula-free XLSX.

## Currentness and Human boundary

The audit binds the manifest, every source, workbook and CSV to exact hashes.
Stale sources, missing or extra CSVs, modified outputs, symlinks and untracked
existing output files fail closed. AI4HEOR never overwrites externally changed
table files.

`awaiting_human_review` means a structurally valid draft exists. The researcher
must review values, units, evidence selection, locators, assumptions,
interpretation, confidentiality, external-use rights and submission format.
Successful generation does not establish scientific validity or approval.

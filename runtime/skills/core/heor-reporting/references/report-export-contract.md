# AI4HEOR DOCX/PDF/XLSX report-export contract

`deliverables/heor-report-export.json` is the only Agent-authored input to the
native report renderer. The app writes:

- `deliverables/heor-report.docx`
- `deliverables/heor-report.pdf`
- `deliverables/heor-report.xlsx`
- `deliverables/heor-report.audit.json`

## Required source state

Prepare the export manifest only after `heor/report-package.json` is complete
under the report-package contract. The manifest binds the exact current bytes
of that package and its `heor/report.md`. The native app repeats the report
package audit and requires its `report_document` binding to match the manifest.
Changing either source makes all three output files stale.

## Human-owned metadata

Confirm the title, optional subtitle, audience, purpose, language, and prepared
date in the conversation. Supported language identifiers are `zh-Hans`,
`zh-Hant`, and `en`. `style` is fixed to `ai4heor-formal-report` for this schema.
`human_review.status` remains `awaiting_human_review`.

The metadata describes the document. It is not an approval, recommendation,
identity proof, external-use licence, or release event.

## Renderer boundary

The native renderer is local and model-independent. It renders the bounded
Markdown subset used by the HEOR report: headings, paragraphs, bullet and
numbered lists, quotations, fenced code, rules, and tables. Raw HTML, unsafe
paths, symlinks, unbounded documents, malformed tables, source-hash drift, and
an incomplete report package fail closed.

DOCX uses standard macro-free OOXML with A4 page geometry, Word styles, native
numbering, fixed table geometry, running headers, and page fields. DOCX and PDF
both embed the admitted Source Han Sans CN font, and the app audit records its
exact version, licence, and SHA-256. Neither format executes code or uses the
network.

XLSX uses standard macro-free OOXML with five fixed worksheets: research
summary, typed result-summary fields, report tables, reporting matrix, and
sources/review. Numeric JSON leaves remain numeric cells, explicit `null` values
remain visible, and report-package paths and SHA-256 values remain readable.
The workbook contains no formula, macro, external link, hidden model
recalculation, or network call. It copies the already audited report-package
summary; it does not become a second economic model. Spreadsheet font embedding
is not used, so the researcher must check viewer font substitution and layout.

If a researcher edits an existing output outside AI4HEOR, the app will not
overwrite it. Move or rename the edited file before generating a new version.
The renderer may replace an earlier app-generated set only when every existing
file still matches its recorded hash.

## Review boundary

After generation, the named researcher reviews all three formats, including
every number, table, disclosure, limitation, page break, workbook sheet, number
format, and font substitution in the viewers they will actually use. Generation does not establish
methodological quality, scientific validity, journal acceptance, regulatory
recognition, reimbursement suitability, or release approval.

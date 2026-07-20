---
name: literature-review
description: Build and maintain a project-local, source-bound reference library from RIS, bounded BibTeX, or CSL-JSON metadata, and export deterministic RIS, BibTeX, or CSL-JSON exchange files. Use when a researcher asks to import references, normalize DOI or PMID metadata, deduplicate citations, inspect metadata conflicts, prepare a bibliography exchange file, or connect evidence records to reports and presentations without network access or autonomous scientific judgment.
---

# Literature review

Manage citation metadata as a local, auditable research artifact. Read
`references/reference-library-contract.md` before importing or exporting a
library.

## Workflow

1. Confirm which project files the researcher wants to import and which output
   format is needed. Do not search the network or download full text through
   this Skill.
2. Import one ordinary project file at a time:

   ```bash
   python3 <skill-directory>/scripts/reference_library.py --workspace . import \
     --library references/library.json --input imports/references.ris
   ```

3. Read the JSON report. Show unsupported tags, metadata conflicts, duplicate
   merges, and records lacking DOI or PMID to the researcher instead of hiding
   them.
4. Run `validate` before using the library in evidence, report, or presentation
   work:

   ```bash
   python3 <skill-directory>/scripts/reference_library.py --workspace . validate \
     --library references/library.json
   ```

5. Export only the requested exchange format:

   ```bash
   python3 <skill-directory>/scripts/reference_library.py --workspace . export \
     --library references/library.json --format csl-json \
     --output exports/references.json
   ```

6. Report the library path, record count, source hashes, deduplication result,
   unresolved conflicts, and export hash. Ask the researcher to review citation
   metadata before external use.

## Boundaries

- Treat natural-language conversation as the primary interface. The script is
  a deterministic execution tool, not a substitute for the researcher's scope,
  screening, appraisal, or citation decisions.
- Keep every path inside the current project. Reject symbolic links, malformed
  records, oversized inputs, unsupported CSL fields, and BibTeX macros or string
  concatenation.
- Deduplicate by normalized DOI, then PMID, then compatible title and year.
  Preserve source bindings and metadata conflicts; never invent missing fields.
- Treat RIS, BibTeX, and CSL-JSON as metadata exchange formats. Import does not
  establish full-text access, inclusion, methodological quality, or review
  completeness.
- Do not claim CSL style rendering, journal-style compliance, dual screening,
  Human approval, scientific validity, or release readiness. This Skill exports
  CSL-JSON data; it does not run a CSL processor or bundle third-party styles.
- Do not overwrite a different existing export. Choose a new path or obtain an
  explicit researcher decision about the existing file.

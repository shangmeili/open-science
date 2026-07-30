---
name: literature-review
description: Build and maintain a project-local, source-bound reference library from RIS, bounded BibTeX, or CSL-JSON metadata; queue lawful open-access full-text retrieval; and export deterministic exchange files. Use when a researcher asks to import, deduplicate, trace, retrieve open full text for, or export references without autonomous scientific judgment.
---

# Literature review

Manage citation metadata as a local, auditable research artifact. Read
`references/reference-library-contract.md` before importing or exporting a
library.

## Workflow

1. Confirm which project files the researcher wants to import, whether lawful
   journal full text is requested, and which output format is needed. A direct
   public PDF actually used to support a claim is archived automatically under
   step 6; it does not require a second request.
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

6. For a lawfully downloadable public PDF actually used to support a claim,
   archive the exact file and provenance in the current workspace:

   ```bash
   python3 <skill-directory>/scripts/open_full_text.py --workspace . archive-url \
     --url https://authority.example/document.pdf \
     --title "Official public document" --publisher "Issuing authority"
   ```

   This writes the immutable file under `references/source-files/` and records
   it in `references/source-files.json`. Do not claim it is archived until both
   exist. Search candidates that were not used do not need to be downloaded.

7. When the researcher explicitly asks for available journal full text,
   prepare a library-hash-bound queue and run it in order:

   ```bash
   python3 <skill-directory>/scripts/open_full_text.py --workspace . prepare \
     --library references/library.json --all
   python3 <skill-directory>/scripts/open_full_text.py --workspace . run \
     --library references/library.json --unpaywall-email researcher@example.org
   ```

   Europe PMC is tried first. Unpaywall is a DOI fallback and requires the
   researcher's email for that request; the email is never written to the
   queue. A missing email becomes `needs_input`, not a fabricated result.
8. Report the library path, record count, source hashes, deduplication result,
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
  completeness. Full-text retrieval uses only Europe PMC open article XML or
  an Unpaywall `best_oa_location.url_for_pdf`; it never bypasses access controls
  or treats a downloaded file as included evidence.
- Bind the queue to the exact current library SHA-256. Stop on library drift.
  Record provider, source URL, licence when reported, version when reported,
  retrieval time, local path, and file SHA-256. Keep unavailable and failed
  items visible and retryable.
- A direct public PDF archive uses schema `ai4heor-source-file-archive/v1`.
  Record the original and final URL, title, publisher when known, licence or
  rights basis, retrieval time, local path, media type, and SHA-256. Validate
  public-network targets, redirects, size, and PDF signature; never overwrite
  different existing bytes.
- Do not claim CSL style rendering, journal-style compliance, dual screening,
  Human approval, scientific validity, or release readiness. This Skill exports
  CSL-JSON data; it does not run a CSL processor or bundle third-party styles.
- Do not overwrite a different existing export. Choose a new path or obtain an
  explicit researcher decision about the existing file.

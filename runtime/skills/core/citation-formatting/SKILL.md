---
name: citation-formatting
description: Prepare a source-bound citation plan for AI4HEOR's deterministic in-text citation and bibliography renderer. Use when a researcher wants to turn the validated local reference library into Chinese medical numeric, Vancouver-style numeric, or author-date references for an HEOR manuscript, report, or presentation without fetching metadata, loading third-party CSL styles, or delegating scientific citation decisions.
---

# Citation formatting

Prepare the Human-reviewed input for AI4HEOR's built-in reference formatter.
Read `references/citation-format-contract.md` before creating or changing a
citation plan.

## Workflow

1. Ask in natural language what document is being written, which passages or
   claims need citations, what language is required, and whether the researcher
   wants Chinese medical numeric, Vancouver-style numeric, or author-date
   output.
2. Validate `references/library.json` with the `literature-review` Skill. Report
   metadata conflicts and missing fields before formatting; do not resolve them
   by guessing.
3. Calculate the exact SHA-256 of the validated library. Create
   `references/citation-plan.json` with schema
   `ai4heor-citation-plan/v1`, existing library record IDs, and that hash.
4. Keep citation-cluster IDs meaningful to the document, such as
   `methods-discounting` or `results-utility-source`. A locator is optional and
   may be recorded only when the researcher or an exact source supplies it.
5. Ask the researcher to check the plan. The desktop app then generates
   `deliverables/references.md` deterministically and reports missing metadata.
6. Open the generated file and report the style profile, input hashes, citation
   count, reference count, and every metadata warning. The researcher checks
   the target journal and decides whether the file is ready to use.

## Boundaries

- Natural-language conversation is the primary interface. The JSON plan and
  desktop card are auxiliary structured controls.
- Use only `ai4heor-cn-medical-numeric-v1`,
  `ai4heor-vancouver-numeric-v1`, or `ai4heor-author-date-v1`. These are small,
  AI4HEOR-owned profiles, not copied third-party `.csl` files and not a generic
  CSL processor.
- Never invent authors, dates, titles, journal names, identifiers, locators, or
  citation decisions. Never cite a library record merely because it exists.
- Do not download metadata, full text, styles, plugins, or Skills through this
  Skill. Use only the current project files.
- A generated bibliography is not evidence screening, scientific endorsement,
  plagiarism review, journal compliance certification, or release approval.
- Preserve Human-edited outputs. If `deliverables/references.md` changed outside
  AI4HEOR, use a new path or ask the researcher how to proceed.

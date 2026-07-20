---
name: journal-submission-check
description: Prepare a source-bound target-journal submission check for an AI4HEOR manuscript. Use when a researcher wants to compare a local Markdown manuscript and its submission files with the current author instructions for a named pharmacoeconomics, health-economics, outcomes-research, HTA, pharmacy, or medical journal without copying third-party styles, guessing journal rules, or claiming that the manuscript is accepted or submission-ready.
---

# Journal submission check

Prepare the Human-reviewed input for AI4HEOR's deterministic submission checker.
Read `references/submission-check-contract.md` before creating or changing the
manifest. Start from `assets/journal-submission-check.template.json` when useful.

## Workflow

1. Ask which journal and article type the researcher is targeting. Confirm the
   exact local Markdown manuscript and every file they intend to submit.
2. Ask the researcher to save or provide a current author-instructions snapshot
   inside the project. Record its official HTTPS URL, access date, version label,
   exact local path and SHA-256. Do not treat a search snippet as the authority.
3. Extract only requirements that can be located precisely in that snapshot.
   Record each requirement as one supported rule with a page, section, heading or
   paragraph locator. Keep reporting-guideline requests separate from journal rules.
4. Hash the manuscript, guide snapshot and submission files. Create
   `deliverables/journal-submission-check.json` with schema
   `ai4heor-journal-submission-check/v1` and status
   `awaiting_human_review`.
5. Run `scripts/validate_journal_submission.py MANIFEST WORKSPACE`. Fix structural,
   path, hash or rule errors without weakening the contract.
6. Ask the researcher to review the captured rules. The desktop app then produces
   the source-bound Markdown and JSON check results deterministically.
7. Report failed required checks, review items, unresolved checks, the guide access
   date and all limitations. The researcher decides what to change and whether to
   submit.

## Boundaries

- Natural-language conversation is primary; the manifest and desktop card are
  auxiliary structured controls.
- Never invent or generalise a word limit, file rule, declaration, checklist,
  reference style or submission requirement. Journal and article-type rules vary.
- Do not bundle, download or silently reuse third-party `.csl` files, author-guide
  text, templates, logos or checklists. Link to official sources and bind a local
  researcher-provided snapshot instead.
- A mechanical pass does not prove scientific quality, reporting completeness,
  publication ethics, copyright clearance, journal compliance, editorial acceptance
  or permission to submit.
- AI-use disclosure, authorship, conflicts, funding, ethics, data availability,
  patient involvement and reporting-guideline completion require Human review even
  when a file or heading is present.
- Preserve Human-edited outputs. If an existing check report changed outside
  AI4HEOR, use a new path or ask the researcher how to proceed.

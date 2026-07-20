# Journal-submission-check contract

## Input artifact

The canonical manifest is `deliverables/journal-submission-check.json` with schema
`ai4heor-journal-submission-check/v1`. It contains:

- a safe check ID, title, language and preparation date;
- the target journal and article type;
- an official HTTPS author-guide URL, access date, version label, local snapshot
  path and exact SHA-256;
- 1–32 exact project files, including one UTF-8 Markdown file with role
  `manuscript`;
- 1–64 supported rules, each with a unique ID, severity and exact `guide_locator`;
- `human_review.status = awaiting_human_review`.

Every file path is workspace-relative. Symbolic links, workspace escapes, missing
files, changed hashes, unknown fields and unsupported rules fail closed.
The official author-guide snapshot is supplied and retained by the researcher.

## Supported rules

Rules use `severity = required` or `review` and one of these kinds:

- `required_file`: require a declared file role.
- `file_extension_in`: require a role's extension to occur in `allowed`.
- `file_size_max_bytes`: compare a role's byte size with `limit`.
- `title_characters_max`: count non-whitespace Unicode characters in the first
  level-one Markdown heading.
- `document_words_max`: count visible alphanumeric/CJK word tokens in the whole
  Markdown document, excluding fenced code and front matter.
- `document_characters_max`: count visible non-whitespace characters using the
  same exclusions.
- `section_words_max` and `section_characters_max`: count a named Markdown section
  in `value`, stopping at the next heading of the same or higher level.
- `table_count_max`: count Markdown table header separators outside fenced code.
- `figure_count_max`: count Markdown image syntax outside fenced code.
- `required_heading`: require an exact normalised Markdown heading in `value`.

Only fields used by the selected rule may be present. Counts are mechanical and
their algorithms are disclosed in the output; use a `review` rule whenever the
journal's definition differs or remains ambiguous.

## Outputs

The native application writes:

- `deliverables/journal-submission-check.md`;
- `deliverables/journal-submission-check.results.json`;
- `deliverables/journal-submission-check.audit.json`.

The audit binds the exact manifest, guide snapshot, manuscript and submission-file
hashes to both output hashes. Changed inputs make results stale. Changed outputs are
never overwritten. Every result remains `awaiting_human_review` even when all
mechanical checks pass.
Passing these checks does not establish journal compliance or permission to submit.

## Evidence and licensing boundary

Journal instructions and reporting standards change independently. AI4HEOR ships no
copied author-guide content or third-party journal template in this Skill. These
official sources informed the boundary and should be checked live when relevant:

- ICMJE Recommendations, updated January 2026:
  <https://www.icmje.org/recommendations/>
- ICMJE manuscript preparation and submission guidance:
  <https://www.icmje.org/recommendations/browse/manuscript-preparation/preparing-for-submission.html>
- ISPOR CHEERS 2022 resource page:
  <https://www.ispor.org/heor-resources/good-practices/cheers>
- EQUATOR economic-evaluation reporting-guideline index:
  <https://www.equator-network.org/reporting-guidelines-study-design/economic-evaluations/>

Links and factual source metadata are recorded; the referenced pages, checklists and
journal instructions are never bundled or redistributed as AI4HEOR assets.

# Research-presentation contract 0.1.0

## Purpose and paths

The Agent prepares `deliverables/research-presentation.json`. The native app
validates it and writes:

- `deliverables/research-presentation.pptx`
- `deliverables/research-presentation.audit.json`

Rendering is deterministic for identical manifest and source bytes. Generation
does not create a Human approval record.

## Top-level fields

- `schema_version`: exactly `0.1.0`.
- `deck_id`: lowercase safe ID, 1–64 characters.
- `title`: 1–120 characters.
- `subtitle`: 0–200 characters.
- `language`: BCP-47-like language tag, 2–16 characters.
- `prepared_on`: `YYYY-MM-DD`.
- `audience`: 1–160 characters.
- `purpose`: 1–240 characters.
- `theme`: exactly `ai4heor-paper`.
- `sources`: 1–30 unique local sources.
- `slides`: 3–30 authored slides.
- `human_review`: exactly `{ "status": "awaiting_human_review" }`.

The renderer may append source-list slides. Those generated slides are not part
of the authored-slide limit.

## Sources

Each source contains:

- `source_id`: safe ID such as `S1` or `result-base-case`;
- `path`: safe workspace-relative regular-file path;
- `sha256`: exact lowercase SHA-256 of the current bytes;
- `label`: 1–160-character human-readable label.

Paths may not be absolute, escape the workspace, use backslashes, traverse a
symlink, or name the generated PPTX/audit files. The app caps every source at
25 MiB. Source content is not copied into the deck; visible citations use the
source ID and the generated source-list slides show label, path, and a shortened
hash.

## Slides

Every slide has a unique safe `slide_id`, one `kind`, and a title no longer than
120 characters. Allowed kinds:

- `title`: must be first; optional `subtitle`; no `source_refs`.
- `section`: optional `subtitle`; no evidence claims or `source_refs`.
- `content`: 1–8 bullets, each 1–240 characters; 1–8 `source_refs`.
- `table`: 2–8 columns, 1–20 rows, cells no longer than 120 characters;
  optional caption; 1–8 `source_refs`.
- `figure`: one local `.png`, `.jpg`, or `.jpeg` under 10 MiB, exact image
  SHA-256, 10–400-character alt text, optional caption, and 1–8 `source_refs`.
- `limitations`: 1–8 explicit limitation bullets and 1–8 `source_refs`;
  at least one limitations slide is required.
- `closing`: must be last; 1–5 bullets; no `source_refs`.

The renderer rejects embedded markup, control characters, excessive content,
unknown kinds, missing citations, stale hashes, and invalid images. It uses the
fixed AI4HEOR paper theme and does not execute macros, scripts, or remote links.

## Human boundary

`awaiting_human_review` means only that a structurally valid draft exists. The
researcher must inspect numerical fidelity, evidence selection, interpretation,
confidentiality, image rights, audience suitability, and external-use rights.
Neither successful validation nor PPTX generation changes research methods,
evidence, parameters, results, approvals, or release status.

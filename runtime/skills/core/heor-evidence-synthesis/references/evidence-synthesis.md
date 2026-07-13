# Evidence synthesis contract

The artifact is `heor/evidence-synthesis.json`. It records what was searched, screened, extracted, and left uncertain. It does not certify that a systematic review or human verification occurred.

## Required structure

- `schema_version`: `0.1.0`.
- `synthesis_id`: stable project-local identifier.
- `status`: `draft` or `ready_for_human_review`.
- `research_question`: non-empty `population`, `intervention`, `comparator`, `outcomes`, and `study_designs`.
- `eligibility`: non-empty `inclusion` and `exclusion` arrays.
- `searches`: unique `id`, `source`, exact `query`, ISO `searched_on`, non-negative `result_count`, and `access` (`network` or `local`).
- `deduplication`: explicit method and non-negative duplicate count.
- `records`: unique `record_id`, title, locator, source type, contributing `search_ids`, and separate screening decisions. Every included record also requires a critical-appraisal record.
- `extractions`: unique `extraction_id`, an included `record_id`, target claim or input, extracted value, source location, applicability, and verification status.
- `conflicts`: explicit topic, involved record IDs, status, and rationale.
- `limitations`: non-empty statements of material coverage or access limits.

## Screening decisions

Use `include`, `exclude`, `unclear`, or `not_assessed`. Full-text exclusions require a specific reason. Do not label a decision independently duplicated unless two named human reviewers actually performed it.

## Extraction and verification

`verification_status` is one of:

- `agent_extracted`: extracted by an agent and not human checked;
- `human_checked`: checked by a named human outside the artifact approval mechanism;
- `conflict`: disagrees with another extraction and requires resolution.

Keep the human checker in `verified_by` only when status is `human_checked`. This records an activity; it does not create an app approval.

## Critical appraisal

For every included full-text record, add `critical_appraisal` with a named tool or framework, findings, rationale, and one status:

- `agent_draft`: structured appraisal prepared by an agent and awaiting human review;
- `human_checked`: checked by the named person in `checked_by`;
- `not_applicable`: justified when a formal bias tool does not apply to the source type.

Do not collapse critical appraisal into an overall quality score. Preserve domain-level findings and limitations.

## Method references

- [Cochrane Handbook version 6.5.1, Chapter 4](https://training.cochrane.org/handbook/current/chapter-04), for search planning, documentation, and study selection.
- [Cochrane Handbook version 6.5, Chapter 5](https://training.cochrane.org/handbook/current/chapter-05), for accurate, complete, accessible, and transparent data collection.
- [PRISMA 2020](https://www.prisma-statement.org/prisma-2020) for reporting items and flow representation, not as a quality score.

The validator checks structure and internal links. It cannot prove database execution, source accuracy, completeness, risk of bias, or human independence.

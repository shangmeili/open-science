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
- `extractions`: unique `extraction_id`, an included `record_id`, target claim or input, extracted value, source location, applicability, and verification status. Candidate model-input values use strict JSON text; narrative context belongs in applicability.
- `conflicts`: explicit topic, involved record IDs, status, and rationale.
- `limitations`: non-empty statements of material coverage or access limits.

An empty `searches` array is accepted only as an importable preparation state. It is never a complete synthesis.

## App-owned search binding

When a search is imported by AI4HEOR, its search entry also contains the complete, indivisible binding below:

- `authorization_event_id`: legacy schema field containing the app-owned
  execution-event ID (its assurance distinguishes confirmation mode from
  user-selected full-access mode);
- `request_sha256`: exact reviewed request bytes;
- `run_path` and `run_sha256`: immutable app-written run location and digest;
- `endpoint`: fixed first-party source endpoint;
- `response_sha256`: one or more exact upstream response digests.

All binding fields must be present together. The Agent must preserve them byte-for-value and must never invent or repair them. The desktop app independently verifies the event chain, current project, safe path, run hash, fixed endpoint, request identity, response hashes, result cap, and combined record set before import.

Imported records may also include `published_on`, `authors`, `doi`, and `retrieval_metadata`. These are source metadata, not extracted outcomes or critical appraisal. They begin with both screening decisions set to `not_assessed`.

## Screening decisions

Use `include`, `exclude`, `unclear`, or `not_assessed`. Full-text exclusions require a specific reason. Do not label a decision independently duplicated unless two named human reviewers actually performed it.

## Extraction and verification

`verification_status` is one of:

- `agent_extracted`: extracted by an agent and not human checked;
- `human_checked`: checked by a named human outside the artifact approval mechanism;
- `conflict`: disagrees with another extraction and requires resolution.

Keep the human checker in `verified_by` only when status is `human_checked`. This records claimed activity inside an agent-writable artifact; it does not create an app-owned verification or approval.

After the artifact is structurally complete, AI4HEOR can record app-owned local review events outside the workspace. Each event binds the exact synthesis SHA-256, a sorted set of eligible extraction IDs, one local reviewer label, rationale, and a `confirmed` or `rejected` decision in a hash chain. An extraction can support an approvable model input only after two distinct local labels confirm it and no label rejects it. A rejection requires revising the synthesis; editing any byte changes the digest and makes every prior decision inapplicable. Legacy single-reviewer events remain readable but count as only one confirmation. The Agent must never create, edit, or claim these events.

This is a fail-closed local integrity boundary, not proof that two authenticated people worked independently. Cochrane recommends at least two people independently extract critical outcome data and prespecify disagreement resolution. AI4HEOR does not claim that stronger method until reviewer identity, independent entry, and consensus or arbitration are implemented and actually used.

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

The validator checks structure and internal links and reports that two app reviewers are required. It cannot inspect app-owned decisions or prove database execution, source accuracy, completeness, risk of bias, reviewer identity, or human independence.

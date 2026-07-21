---
name: heor-evidence-synthesis
description: Create and audit reproducible HEOR evidence searches, eligibility criteria, deduplication, screening decisions, structured extraction, applicability assessments, and conflict logs. Use when a pharmacoeconomic question needs clinical effectiveness, resource use, costs, utilities, epidemiology, treatment pathways, comparators, or other evidence synthesized into heor/evidence-synthesis.json before model-input selection.
---

# HEOR Evidence Synthesis

Create a transparent evidence trail, not a citation list or an autonomous systematic-review claim. Read `references/evidence-synthesis.md` before creating or changing the artifact.

## Workflow

1. Read the decision question and any existing `heor/evidence-synthesis.json`; preserve valid researcher-authored records and decisions.
2. Define PICOS plus explicit inclusion and exclusion criteria before searching.
3. For ordinary public retrieval, preserve the exact source, query, search date,
   and result count. When the researcher explicitly needs structured import,
   prefer AI4HEOR's task-permission-aware fixed connector and deterministic
   candidate import for PubMed and ClinicalTrials.gov; preserve every
   app-written execution/run binding.
4. Deduplicate records without discarding their source-search links.
5. Record title/abstract and full-text decisions separately. Keep excluded full-text records with a specific reason.
6. Extract only values and claims directly supported by included records. Record location, unit, population, follow-up, applicability, and uncertainty when relevant. When an extraction is a candidate model input, encode `extracted_value` as strict JSON (for example `0.74`, `[0.8,0.5,0]`, or a matrix) and keep context in `applicability` rather than mixing commentary into the value.
7. Record conflicting evidence explicitly. Do not silently select a convenient estimate.
8. If the file does not exist, prepare an importable skeleton from `assets/evidence-synthesis.template.json`. After app import, modify research fields only: do not rewrite app-bound provenance, convert `not_assessed` merely to satisfy validation, or overwrite existing screening/appraisal decisions.
9. Run `scripts/validate_evidence_synthesis.py` against the final file. An importable skeleton is intentionally incomplete until at least one documented search exists and all research work is supported.
10. Treat every non-conflicting extraction as eligible for app review, not verified. Ask the researcher to use the AI4HEOR review pane. The current app gate requires confirmation from two distinct local reviewer labels for the exact synthesis bytes; a rejection blocks the extraction until the synthesis is revised. Never write or simulate these app-owned events.
11. Summarize coverage, unresolved conflicts, limitations, and candidate extraction IDs plus record IDs for `$heor-input-provenance`.

## Boundaries

- Treat PRISMA as reporting guidance, not proof of methodological quality.
- Do not claim dual independent screening or extraction, librarian review, risk-of-bias completion, certainty grading, or verified reviewer identity. Two distinct local labels are an app integrity rule, not proof of two authenticated independent people.
- An agent screening decision is a draft research action. It is not a human approval.
- `human_checked` inside the workspace records claimed activity only. The analysis-plan gate accepts a selected extraction only after two distinct local reviewer labels confirm its ID against the exact current synthesis SHA-256 and no reviewer rejects it.
- Keep unavailable full text, translation limitations, inaccessible databases, and search-date limits visible.
- Do not pool effects merely because multiple estimates exist. Statistical synthesis requires a separate prespecified method and deterministic implementation.
- Keep network calls source-specific and disclose them in the conversation. Store artifacts in the active project.
- Never fabricate `authorization_event_id` (the legacy schema field for an
  app-owned execution event), request/run hashes, endpoints, response hashes,
  or an app-owned run path. Only the desktop app may create those bindings.

## Handoff

Report the artifact path, search sources and dates, record counts by screening stage, included records, unresolved conflicts, and which extracted values are eligible to enter the input-provenance review. Never promote the synthesis to decision-ready.

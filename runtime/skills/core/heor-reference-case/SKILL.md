---
name: heor-reference-case
description: Create and audit a version-bound HEOR reference-case compliance matrix for heor/analysis-plan.json. Use when selecting China 2020 or draft 2026 guidance, identifying methodological gaps, preparing analysis-plan review, or repairing heor/reference-case-assessment.json without claiming that profile selection alone proves compliance.
---

# HEOR Reference Case

Turn a named guideline into an auditable requirement-by-requirement assessment. Read `references/reference-case-assessment.md` before creating or changing the artifact.

## Workflow

1. Read `heor/analysis-plan.json`, `heor/conceptual-model.json`, and the selected bundled profile under `assets/profiles/`. Never substitute a remembered guideline version.
2. Verify the profile status and source snapshot. A `draft` profile may be explored but cannot authorize an analysis.
3. Assess every profile requirement exactly once as `met`, `gap`, `not_applicable`, or `unresolved`. Preserve gaps; do not optimize the matrix for approval.
4. For `met`, record a concise rationale and one or more existing workspace-relative evidence paths. For `not_applicable`, explain why the profile's applicability condition does not hold.
5. Use `gap` when the current artifacts contradict or do not satisfy the requirement. Use `unresolved` when the available evidence cannot support a conclusion.
6. Write `heor/reference-case-assessment.json` from `assets/reference-case-assessment.template.json`.
7. Run `scripts/validate_reference_case_assessment.py` with the assessment, plan, and profile. The app independently repeats and extends this audit.
8. Hash the final assessment bytes and add that exact lowercase SHA-256 plus the fixed path to `reference_case_assessment` in the analysis plan. Any later assessment change requires a new plan hash and human review.

## Boundaries

- Do not reproduce a guideline's full text. Store short paraphrases and precise source locators from the bundled profile.
- Do not mark a requirement `met` based only on a planned future action.
- Do not treat a validator pass as human approval, independent validation, or legal/regulatory certification.
- Required gaps and all unresolved items block analysis-plan approval. Recommended gaps remain visible but do not by themselves authorize or block.
- The app owns the reference-case registry, approval log, and final authorization decision.

## Handoff

Report the profile ID, revision, status, profile hash, assessment hash, required items met, machine-confirmed not-applicable items, recommended gaps, blocking gaps, unresolved items, and exact next natural-language repair. Never claim general guideline compliance beyond the audited artifact and profile snapshot.

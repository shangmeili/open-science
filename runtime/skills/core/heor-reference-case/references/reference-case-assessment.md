# Reference-case assessment contract

The assessment is a local compliance matrix for one analysis and one immutable bundled profile snapshot. It is not a copy of the guideline and not an approval record.

The current machine-readable profiles are:

- `../assets/profiles/CN-2020-current.json`
- `../assets/profiles/CN-2026-draft.json`
- `../assets/profiles/NICE-PMG36-2026-current.json`

Use the file matching `analysis-plan.json`; do not merge profile versions or transfer requirements between jurisdictions.

Required links:

- `analysis_id` must equal the current analysis plan.
- `profile.id`, `profile.revision`, `profile.status`, and `profile.content_sha256` must equal the selected bundled profile and its exact bytes.
- `requirements` must contain every profile requirement exactly once and no unknown IDs.
- A `met` item needs a rationale and workspace-relative evidence paths that exist when the app audits the project.
- A required `gap`, any `unresolved` item, a draft profile, or a broken hash/link keeps the audit incomplete.

Cost scope needs non-empty `methodology.cost_scope.included_categories` and a perspective-alignment rationale. Uncertainty needs planned deterministic and probabilistic analyses, eligible `input_provenance` paths with ranges/distributions, a positive iteration count, and at least one structural scenario. Narrative claims or file presence alone do not satisfy these checks.

For `NICE-PMG36-2026-current`, use `decision_problem.jurisdiction: "England"`, name both NHS and personal social services in `decision_problem.perspective`, and use 0.035 for both discount rates when the horizon exceeds one year. For adult cost-utility analysis, fill `methodology.health_outcomes` with the measure, collected descriptive system, applied value set, valuation population, respondent, mapping method, and any reference-case departure. The default automated check requires EQ-5D, a UK 3L value set, UK general-population valuation, patient or carer reporting, and a named DSU-to-3L mapping when the collected system is 5L. An alternative measure or departure remains a human-assessed gap or unresolved item; the Agent must not relabel it as reference-case compliant.

The NICE profile is deliberately an executable subset. Cost-comparison analyses, children and young people, diagnostics, severity modifiers, equality considerations, managed access, and topic-specific scope conditions require direct review of the current PMG36 source. The bundled profile stores only paraphrases and locators; it does not bundle or reproduce the source PDF.

Use `not_applicable` only when the profile applicability condition genuinely does not apply. The app may reject it when the selected model makes the requirement applicable. Recommended gaps stay visible for human judgment.

The analysis plan links the exact assessment bytes:

```json
"reference_case_assessment": {
  "path": "heor/reference-case-assessment.json",
  "content_sha256": "64 lowercase hexadecimal characters"
}
```

Changing the matrix changes its hash, which changes the analysis plan and invalidates a prior plan approval.

# Reference-case assessment contract

The assessment is a local compliance matrix for one analysis and one immutable bundled profile snapshot. It is not a copy of the guideline and not an approval record.

The current machine-readable profiles are `../assets/profiles/CN-2020-current.json` and `../assets/profiles/CN-2026-draft.json`. Use the file matching `analysis-plan.json`; do not merge profile versions.

Required links:

- `analysis_id` must equal the current analysis plan.
- `profile.id`, `profile.revision`, `profile.status`, and `profile.content_sha256` must equal the selected bundled profile and its exact bytes.
- `requirements` must contain every profile requirement exactly once and no unknown IDs.
- A `met` item needs a rationale and workspace-relative evidence paths that exist when the app audits the project.
- A required `gap`, any `unresolved` item, a draft profile, or a broken hash/link keeps the audit incomplete.

Two analysis-plan requirements have structured app checks. Cost scope needs non-empty `methodology.cost_scope.included_categories` and a perspective-alignment rationale. Uncertainty needs planned deterministic and probabilistic analyses, eligible `input_provenance` paths with ranges/distributions, a positive iteration count, and at least one structural scenario. Narrative claims or file presence alone do not satisfy these checks.

Use `not_applicable` only when the profile applicability condition genuinely does not apply. The app may reject it when the selected model makes the requirement applicable. Recommended gaps stay visible for human judgment.

The analysis plan links the exact assessment bytes:

```json
"reference_case_assessment": {
  "path": "heor/reference-case-assessment.json",
  "content_sha256": "64 lowercase hexadecimal characters"
}
```

Changing the matrix changes its hash, which changes the analysis plan and invalidates a prior plan approval.

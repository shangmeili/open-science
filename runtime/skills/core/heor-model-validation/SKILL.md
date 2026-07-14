---
name: heor-model-validation
description: Prepare, audit, and explain a hash-bound independent-validation report for health-economic decision models and budget-impact analyses. Use when creating or repairing heor/model-validation.json, organizing face/internal/cross/external/predictive validation evidence, applying AdViSHE or TECH-VER concepts, documenting technical verification and resolved defects, or preparing the independent-validation human gate without claiming that an Agent or checklist has validated the model.
---

# HEOR Model Validation

## Workflow

1. Read `references/model-validation-contract.md` before changing the report.
2. Read the current analysis plan, conceptual model, uncertainty plan, and budget-impact plan as exact bytes. Record their SHA-256 values in `model_bindings`.
3. Copy `assets/model-validation.template.json` to `heor/model-validation.json` when no report exists. Keep it `draft` while evidence or independent-review fields are incomplete.
4. Put stable evidence snapshots under `heor/validation-evidence/`. Hash every snapshot; do not link mutable or unbounded paths.
5. Help design reproducible face, input, technical, cross, external, and predictive checks. Technical verification must cover the applicable TECH-VER calculation domains for both cost effectiveness and budget impact.
6. Run automated tests, replications, and comparisons when authorized. Record their raw evidence honestly as `automated_test` or `developer`; never relabel Codex work as `independent_reviewer`.
7. Preserve failed checks and defects. Link failures to issues, record root cause and retest evidence, and mark an issue resolved only when the evidence supports it.
8. For analysis `0.9.0`, require independent checks of annual-probability-to-cycle hazard scaling, subannual attained-age alignment, exact life-table and excess-rate bases, two-state absorption, and full schedule recomputation. Require scientific review of population exchangeability, no double counting, and the unimplemented multiplicative/SMR alternative. Confirm uncertainty `0.8.0` varies only the exact positive excess rate while the life table and transformation internals remain fixed.
9. Leave reviewer identity, independence declaration, conflict statement, independent observations, and final recommendation for the qualified independent human reviewer. Codex may structure incomplete placeholders but must not invent them.
10. Run `python3 scripts/validate_model_validation.py WORKSPACE/heor/model-validation.json WORKSPACE`. Treat `valid` as structural readiness only.
11. Ask the independent reviewer to inspect the report and use the desktop approval surface. Never write approval events.

## Boundaries

- Do not use a checklist score or pass count as a model-quality score.
- Do not infer external or predictive validity from internal tests, calibration data, or face review.
- Do not hide unavailable validation. Use `not_feasible` only for cross or predictive validation, with evidence and rationale; current AI4HEOR admission still requires passed external checks for both calculation paths.
- Do not approve a report with open blocker or major defects. An `approve_with_limitations` recommendation may retain only explicit minor residual issues.
- Do not claim reviewer independence, regulatory acceptance, reimbursement suitability, or release readiness.

## Handoff

Report the validation ID and hash; all four bound artifact hashes; reviewer and local identity-assurance boundary; coverage by validation domain; evidence and issue counts; unresolved defects; external/cross/predictive status; recommendation; limitations; and exact next human action. State that the app's validator verifies structure, hashes, coverage, and local declarations—not scientific truth or identity.

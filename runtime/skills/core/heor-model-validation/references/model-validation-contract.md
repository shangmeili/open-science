# AI4HEOR model-validation contract

`heor/model-validation.json` is a transparent record of validation work and results. It is not a score and cannot approve itself.

## Method basis

- China 2020 requires face, internal, and external validation for economic models and recommends cross-model comparison when feasible. Its BIA section separately calls for face, technical, and external validation.
- ISPOR-SMDM distinguishes face, verification/internal, cross, external, and predictive validation. External and predictive comparisons are the strongest forms, but fitness remains an intended-use judgment.
- AdViSHE organizes reported efforts across the conceptual model, input data, computerized model, and outcomes. AI4HEOR adopts the reporting principle, not a quality score.
- TECH-VER organizes technical verification across input calculations, event/state calculations, result calculations, uncertainty calculations, and overall checks. Completion does not guarantee an error-free model.

The published 2012 ISPOR-SMDM report remains the current baseline. A Validation II task force is active in 2026; update this contract only after final guidance is published and reviewed.

## Required binding

The report binds the exact current bytes of:

- `heor/analysis-plan.json`
- `heor/conceptual-model.json`
- `heor/uncertainty-plan.json`
- `heor/budget-impact-plan.json`

Every evidence item must be a bounded local file under `heor/validation-evidence/` with a matching SHA-256. The independent-validation approval event binds the report and the same four upstream artifacts. Any changed byte makes the approval stale.

## Required coverage

For cost effectiveness, passed independent-reviewer checks must cover face validity, input data, external validity, and all five technical components: input calculations, event/state calculations, result calculations, uncertainty calculations, and overall checks.

When analysis schema `0.4.0` through `0.7.0` uses `transition_schedule`, event/state verification evidence must exercise every change-point boundary, confirm the matrix active immediately before and at each `start_cycle`, check mass conservation through the full trace, and compare a one-phase schedule with the equivalent static matrix. For schema `0.5.0`, independently recompute each rate-derived row from the declared competing rates and exact cycle length, verify extraction or assumption bindings, and test that altered rates and stale matrices fail closed. For schema `0.6.0`, independently recompute every cycle from exponential or Weibull cumulative-hazard increments, verify parameterization and bases, and test stale schedules, wrong state counts, unsupported distributions, and non-finite hazards; this verifies arithmetic, not curve fit or clinical extrapolation validity. For schema `0.7.0`, independently recompute every affected row from the source probability and exact source/model intervals, test the hand-calculated `0.36` over two years to `0.20` per year case, and reject simple division, stale output, endpoint probabilities, multiple events, and unlinked bases. When uncertainty schema `0.3.0` through `0.6.0` varies event rates, test positive-bound enforcement, exact event-basis binding, seeded repeatability, competing-row mass conservation for multiple varied rates, and rejection of direct probability-row mutation. When uncertainty schema `0.5.0` or `0.6.0` varies survival parameters, test exact parameter and basis binding, positive bounds and distributions, seeded repeatability, full schedule and derivation-snapshot recomputation, and rejection of curve-family or derived-row mutation. When uncertainty schema `0.6.0` varies a source probability, test strict `(0,1)` DSA/PSA bounds, Beta or bounded Uniform only, exact basis binding, seeded repeatability, full transition-input recomputation, and rejection of derived-row mutation. For every schema `0.4.0` through `0.6.0` correlation group, independently verify member order, lognormal parameterization, evidence basis, symmetry, unit diagonal, strict positive definiteness, declared Cholesky multiplication, seeded first-draw reproduction, and rejection of unsupported distributions, reused members, singular/perfect matrices, and unlinked bases. This is still model-cycle behavior; it does not validate time-in-state, patient-history effects, curve fitting or extrapolation, general CTMC behavior, arbitrary copulas, empirical posterior draws, or transformation-space structural scenarios.

For analysis schema `0.8.0`, additionally verify exact strategy-order/key agreement, baseline-first semantics, 2–16 bounds, safe IDs, unique strategy names, stable equivalent-point handling, all strict-dominance quadrants, at least one hand-calculated extended-dominance case, monotonically increasing sequential ICERs on the final frontier, and maximum-NMB selection including ties. For uncertainty schema `0.7.0`, reproduce every strategy's unique-optimal and tie counts from the aligned sample arrays, verify the probability vector sums to one, recompute CEAF and `E[max_j NMB_j] - max_j E[NMB_j]`, and test maximum-vector MCSE/drift convergence. Verify that legacy result shapes remain unchanged and that reporting copies the full frontier and multi-strategy decision-uncertainty objects without inference.

For the simple BIA, passed independent-reviewer checks must cover face validity, input data, external validity, and four technical components: input calculations, result calculations, uncertainty calculations, and overall checks. Event/state verification is not required unless a future cohort or patient-level BIA is used.

Cross validity must be passed or explicitly `not_feasible` for the cost-effectiveness model. Predictive validity must be passed or explicitly `not_feasible` for both calculation paths. A `not_feasible` check still needs local evidence and a rationale. External validity cannot be replaced by `not_feasible` at the independent-validation gate.

## Findings and authority

Failed or inconclusive checks remain in the record and link to issues. Resolved issues require a root cause, resolution, and evidence. Open blocker or major issues make the report non-approvable. `approve_for_intended_use` requires no open issues; `approve_with_limitations` requires explicit limitations and may retain only minor issues.

Codex and automated tools may prepare evidence but cannot mark their work as performed by the independent reviewer. The reviewer label in the report must differ from the developer label and must match the actor label entered in the app-owned approval event. Both identity and independence remain local human declarations until OS-backed signing exists.

## Primary sources

- Chinese Pharmaceutical Association, *China Guidelines for Pharmacoeconomic Evaluations 2020*, sections 7.6 and 11.9.
- Eddy et al., *Model Transparency and Validation*, ISPOR-SMDM Task Force 7, 2012.
- Vemer et al., *AdViSHE*, PharmacoEconomics, 2016.
- Büyükkaramikli et al., *TECH-VER*, PharmacoEconomics, 2019.

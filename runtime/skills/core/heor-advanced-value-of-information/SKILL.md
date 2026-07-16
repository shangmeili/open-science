---
name: heor-advanced-value-of-information
description: Prepare, audit, and repair a bounded AI4HEOR advanced value-of-information plan covering explicit population EVPI, nested-Monte-Carlo EVPPI, one-parameter Normal-Normal EVSI, and expected net benefit of sampling. Use for heor/advanced-voi-plan.json, research-priority analysis, affected-population extrapolation, parameter-group prioritization, candidate sample-size comparison, or review of heor/results/advanced-voi.json without turning VOI into automatic funding, reimbursement, or study-design authority.
---

# Advanced Value of Information

Use natural language to establish the research question and Human-owned method choices. Use the JSON template only as an auxiliary exact-input and review surface.

## Workflow

1. Confirm that `heor/analysis-plan.json`, `heor/uncertainty-plan.json`, and `heor/results/uncertainty.json` are current, hash-bound, and that the PSA convergence gate passed.
2. Read [references/advanced-voi-contract.md](references/advanced-voi-contract.md) before selecting population, parameter groups, or a study model.
3. Copy [assets/advanced-voi-plan.template.json](assets/advanced-voi-plan.template.json) to `heor/advanced-voi-plan.json`. Never overwrite an existing plan without Human approval.
4. Bind the exact current analysis, uncertainty-plan, and uncertainty-result bytes. Use the analysis-plan primary willingness-to-pay threshold; do not silently select another threshold.
5. Ask the Human to specify annual affected populations, technology lifetime, population discount rate, sources, and rationale. Do not infer these from market size, eligible population, or budget-impact counts.
6. Ask the Human to name 1–8 researchable parameter groups. Preserve complete declared correlation groups; stop if a proposed group splits correlated parameters.
7. Configure nested EVPPI iterations within the engine limits and explain bias/precision trade-offs. Do not describe the result as exact.
8. For EVSI, accept exactly one independent Lognormal PSA parameter on its log scale. Require a Human-specified Normal sample-mean likelihood, sampling standard deviation, candidate sample sizes, research delay, fixed and per-participant study costs, monetary basis, and sources.
9. Set the five required limitation labels and change `status` to `ready_for_human_review` only after every choice is explicit.
10. Validate the plan before native execution:

```bash
python scripts/validate_advanced_voi.py \
  --plan heor/advanced-voi-plan.json \
  --analysis heor/analysis-plan.json \
  --uncertainty heor/uncertainty-plan.json \
  --uncertainty-result heor/results/uncertainty.json
```

11. Let the native AI4HEOR command create `heor/results/advanced-voi-replay.json` and `heor/results/advanced-voi.json`. Do not hand-author either app-owned result.
12. Validate the exact replay/result pair, then present population EVPI, each group EVPPI, each candidate EVSI/ENBS, Monte Carlo error, effective populations, costs, limitations, and the next Human review action.

## Stop boundaries

- Stop for unconverged PSA, stale hashes, unrepresented parameter or structural uncertainty, missing dependencies, split correlation groups, or unsupported uncertainty schemas.
- Schema `0.1.0` supports standard odds-ratio uncertainty `0.9.0` when the EVSI target is its independent Lognormal parameter, and fixed-survival component uncertainty `0.13.0`. It rejects HR/Uniform `0.10.0` because it cannot satisfy this EVSI likelihood contract, and rejects joint survival schemas `0.12.0` and `0.14.0`.
- Stop if the EVSI target is correlated, non-Lognormal, informed by censoring, missingness, bias, or a non-Normal likelihood. Those designs require a different explicit data-generating model.
- Do not optimize sample size automatically. Comparing declared candidates does not prove the globally optimal design.
- Do not call positive ENBS a funding decision, research mandate, reimbursement recommendation, or proof that the model and evidence are valid.
- Agents and models may prepare and explain the analysis. The Human researcher owns population assumptions, parameter grouping, study design, interpretation, and any accept/reject decision.

## Report

Report exact plan/result/replay hashes, supported uncertainty scope, threshold, annual and effective populations, EVPPI and EVSI simulation sizes and seeds, parameter groups, target prior and likelihood, study delay and costs, per-person and population values, Monte Carlo error, ENBS by candidate design, excluded uncertainties, and Human review status. Distinguish deterministic replay from scientific validity.

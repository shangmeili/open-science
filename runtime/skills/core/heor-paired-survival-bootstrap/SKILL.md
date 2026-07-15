---
name: heor-paired-survival-bootstrap
description: Generate, execute, and audit patient-row bootstrap replicates that jointly refit every Human-selected strategy PFS and OS parametric survival curve for AI4HEOR. Use when pseudonymous individual-level parallel-arm data contain both endpoints and a partitioned-survival PSA needs auditable joint curve candidates that preserve within-subject PFS/OS dependence. Do not use for reconstructed IPD, unmatched endpoint files, clustered or crossover designs, independent marginal curve sampling, model selection, or approval.
---

# HEOR Paired Survival Bootstrap

Create one complete candidate row per patient-level bootstrap replicate without giving the execution authority to select models or enter PSA. Read [references/contract.md](references/contract.md) before preparing a request.

## Workflow

1. Confirm current analysis `0.15.0`, partitioned-survival plan `0.7.0`, and curve materializations `0.2.0` are coherent and Human-reviewed. Use `$heor-survival-extrapolation-review` and `$heor-survival-curve-materialization` first when a strategy PFS or OS family is not selected and bound.
2. Prepare one strict local UTF-8 CSV with columns `subject_id,strategy_id,pfs_time,pfs_event,os_time,os_event`. Use one unique safe pseudonym per subject, both endpoint observations on the same row, finite positive years, zero/one event indicators, and no direct identifiers or additional columns. Stop if PFS time exceeds OS time.
3. Copy [assets/paired-survival-bootstrap-request.template.json](assets/paired-survival-bootstrap-request.template.json) into a project request path. Bind exact current analysis, PSM, materialization, and source bytes. Copy every strategy PFS then OS family from current materializations; never choose or infer a family here.
4. Keep the first slice exactly `ordinary_nonparametric_case_resampling`, `whole_subject_row`, and `stratified_independent_parallel_arms`. Preserve each arm size and use the same sampled subject indices for PFS and OS. Declare `conditional_independence_given_parallel_arm_design`; do not claim observed between-strategy correlation.
5. Use 1,000–10,000 replicates and one explicit unsigned 64-bit seed. Run the request validator before seeking command authorization:

```bash
python3 runtime/skills/core/heor-paired-survival-bootstrap/scripts/validate_paired_survival_bootstrap_request.py \
  heor/paired-survival-bootstrap-request.json --workspace .
```

6. Ask a Human to authorize the exact local command, data classification, selected families, and parallel-arm resampling design. The request itself remains `awaiting_execution_authorization` and is not an approval record.
7. Use an existing isolated R library with exact requested `survHE`, `flexsurv`, and `survival` versions. Never install or update packages. Run:

```bash
python3 runtime/skills/core/heor-paired-survival-bootstrap/scripts/run_paired_survival_bootstrap.py run \
  heor/paired-survival-bootstrap-request.json --workspace . \
  --rscript /absolute/path/to/Rscript --library /absolute/path/to/isolated-library
```

8. Preserve every replicate. A failed fit, numerical mismatch, invalid/increasing curve, or PFS above OS makes the entire execution ineligible; never retry, filter, reorder, clamp, or repair rows. Only a fully complete batch emits `joint-survival-draws.candidate.jsonl`.
9. Audit the final result independently:

```bash
python3 runtime/skills/core/heor-paired-survival-bootstrap/scripts/audit_paired_survival_bootstrap_result.py \
  heor/paired-survival-bootstrap-executions/<execution-id>/result-manifest.json --workspace .
```

10. Leave the result `awaiting_bootstrap_method_review`. After Human review, use `$heor-joint-survival-uncertainty` to bind the exact execution and candidate bytes into canonical joint-survival artifacts. Do not copy candidate draws into PSA directly.

## Boundaries

- Do not accept separate PFS and OS files, independently sample fitted-model covariance, pair unrelated rows, or infer subject matching.
- Do not apply this parallel-arm contract to matched pairs, clusters, crossover trials, repeated episodes, competing/recurrent events, treatment switching, reconstructed IPD, left truncation, or interval censoring.
- Do not infer that ordinary case resampling handles informative censoring or validates endpoint definitions, extrapolation, model fit, or treatment effects.
- Do not treat one numbered replicate across independent arms as evidence of between-strategy correlation. The strategy joint distribution is conditional on the declared parallel-arm independence assumption.
- Do not select curve families, suppress failed replicates, create approval events, claim independent validation, or call candidate output decision-ready.

## Handoff

Report request, source, plan, replicate, candidate, adapter, evaluator, runtime and result hashes; arm counts; selected family order; seed; iteration and failure counts; numerical and PFS/OS coherence status; dependence preserved; conditional-independence assumption; limitations; validator result; and the exact Human-review blocker.

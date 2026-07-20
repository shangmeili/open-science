# Paired survival bootstrap execution contract

## Scope

Schema `0.1.0` runs an ordinary nonparametric case bootstrap over one normalized local patient-level CSV. Every source row contains one unique pseudonymous subject, treatment strategy, and that subject's PFS and OS time/event observations. The fixed PCG32 stream samples complete rows with replacement within each parallel treatment arm, preserves each arm's observed size, and uses the same sampled subjects for both endpoints. Every replicate refits the already Human-selected parametric family for every strategy PFS and OS curve.

This design preserves empirical PFS/OS dependence within a subject and strategy. Separate parallel arms are resampled independently within the same numbered replicate. Their joint distribution therefore uses the explicit assumption `conditional_independence_given_parallel_arm_design`; the execution does not claim observed between-strategy correlation. Matched, crossover, clustered, multi-state, or otherwise dependent strategy designs are outside schema `0.1.0` and require a different resampling contract.

## Input and authorization

Use [the request template](../assets/paired-survival-bootstrap-request.template.json). Bind exact current analysis `0.15.0`, partitioned-survival `0.7.0`, and curve-materialization `0.2.0` bytes. `bootstrap.curves` must reproduce every strategy PFS then OS target and its reviewed selected family in current materializations. The time grid must be the exact analysis cycle grid in years.

The strict UTF-8 CSV columns are `subject_id,strategy_id,pfs_time,pfs_event,os_time,os_event`. Subject IDs must be unique safe pseudonyms, never direct identifiers. Times are finite positive years, PFS time cannot exceed OS time, event indicators are exactly zero or one, and missing or additional columns are rejected. The source remains in place and is never copied into the result bundle.

The request stays `awaiting_execution_authorization`. Run only after a Human authorizes the exact local command, current source classification, reviewed curve families, and parallel-arm resampling design. Keep the request at the fixed app-discoverable path `heor/paired-survival-bootstrap-request.json`. The result never records an approval event and requires a separate app-owned Human method review before canonical joint-survival packaging.

## Deterministic resampling and fitting

The fixed `pcg32-xsh-rr` version `1` stream uses unbiased rejection sampling to generate one within-arm whole-row resample per replicate. The runner stores a frequency matrix whose columns are source row positions, not subject identifiers or outcomes. Portable audit regenerates every frequency from the request seed and current strategy membership and requires byte identity.

The isolated R adapter uses an explicitly supplied existing library and exact `survHE`, `flexsurv`, and `survival` versions. It installs nothing, fits each selected intercept-only MLE separately, preserves warnings and failures, and writes only aggregate natural parameters and cycle-grid survival values. The dependency-free Python auditor independently evaluates every curve from the natural parameters using the shared first-party all-family evaluator. The desktop's dependency-free Rust auditor separately regenerates the complete PCG32 plan, checks exact artifact hashes, reevaluates every reported natural-parameter curve, and rechecks PFS/OS coherence. It does not refit the source data in Rust and must not be described as an independent fitting implementation.

All 1,000–10,000 requested replicates remain in `replicate-results.jsonl`. Failed fits, numerical disagreement, increasing/invalid curves, or PFS above OS make the entire execution ineligible. AI4HEOR never retries, replaces, filters, reorders, clamps, or repairs failed replicates. Only a fully complete batch emits `joint-survival-draws.candidate.jsonl`; the file is not canonical and has no PSA authority.

## Handoff

After both portable and native execution audits, the AI4HEOR review pane presents a seven-item Human checklist covering the resampling unit, paired endpoint definitions, censoring assumptions, selected families, complete failure profile, follow-up/extrapolation, and parallel-arm conditional-independence assumption. Only the native app may write an accept/reject record under `heor/paired-survival-bootstrap-reviews/` and append its separate app-data SHA-256 event chain. Agents and Skills must never create, edit, imitate, or infer that record.

Only a current app-owned acceptance may enter joint-survival manifest schema `0.5.0`. The manifest binds the exact review record, execution result, replicate file, candidate draws, and current analysis artifacts. A later rejection for the same execution, or any byte change in the bound graph, makes the acceptance stale. Python and native Rust independently audit the canonical artifact, and the desktop rechecks the current app review chain before analysis approval and every uncertainty run.

## Method basis

- [R `boot` documentation](https://stat.ethz.ch/R-manual/R-devel/library/boot/html/boot.html) defines each data-frame row as one multivariate observation and stratified nonparametric resampling within declared strata.
- [NICE PMG36 economic evaluation](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/) requires relevant parameter correlations and structural uncertainty to be represented transparently.
- [NICE DSU TSD 19](https://sheffield.ac.uk/nice-dsu/tsds/partitioned-survival-analysis) describes the structural consequences of separately modelled PFS and OS in partitioned-survival analysis.
- [ISPOR paired PFS/OS bootstrap example](https://www.ispor.org/heor-resources/presentations-database/presentation/euro2019-3119/96120) refits PFS and OS within the same trial-data resample to retain their relationship.

These sources motivate the bounded contract. They do not prove that ordinary case resampling is appropriate for every censoring mechanism, trial design, or survival model.

---
name: heor-treatment-effect-duration
description: Create, audit, and explain AI4HEOR treatment-effect duration scenarios for exactly two-strategy partitioned-survival models. Use for heor/treatment-effect-duration.json, sustained treatment benefit, immediate stopping after an evidence horizon, log-hazard-ratio waning to no effect, duration scenario analysis, PFS/OS curve regeneration, or repair of PSM schema 0.4.0 or 0.5.0 without inferring duration from a point estimate or claiming clinical validity.
---

# HEOR treatment-effect duration

Keep natural-language discussion primary. Use the artifact and validator as the
auditable calculation surface; use forms only to inspect or edit declared fields.

1. Read `references/treatment-effect-duration-contract.md` before creating or changing an artifact.
2. Confirm the bounded case: analysis `0.12.0`/PSM `0.4.0` or cost-normalized analysis `0.13.0`/PSM `0.5.0`, exactly two ordered strategies, the baseline strategy as comparator, endpoints PFS then OS, year-based cycle-aligned source curves, and one evidence-supported non-null HR per endpoint. Stop outside this boundary.
3. Copy `assets/treatment-effect-duration.template.json` to `heor/treatment-effect-duration.json` when absent. Preserve `draft` until every placeholder is replaced.
4. Bind the exact analysis and source-materialization bytes. Never bind the PSM bytes from this artifact because the PSM binds the duration artifact and would create a circular hash.
5. For PFS and OS separately, record one evidence horizon, one HR and evidence basis shared by all scenarios. Never infer the horizon, duration, or waning endpoint from the HR value.
6. Provide three complete scenarios for both endpoints: `sustained`, `immediate_stop`, and `log_linear_waning`. Give every scenario and policy a rationale and basis IDs. Additional scenarios are allowed only within the five-scenario cap.
7. Keep the reviewed intervention source curve through the evidence horizon. After it, reconstruct survival from comparator hazard increments using the declared policy. Reject non-aligned horizons, undefined hazards, increasing/zero curves, incomplete grids, PFS above OS, or any silent repair.
8. Set one scenario as `base_case_scenario_id`, use PSM schema `0.4.0` or `0.5.0` as required by the analysis, bind the exact duration artifact hash, and materialize that scenario into every PSM curve row with exact generated basis IDs. Keep all scenarios visible in calculation output.
9. Update PSM uncertainty bindings to include this artifact. Joint survival draws must bind the same duration artifact; do not list treatment-effect duration as omitted when the three required scenarios are current. Curve-family and extrapolation uncertainty remain separate.
10. Run `python3 scripts/validate_treatment_effect_duration.py WORKSPACE/heor/treatment-effect-duration.json WORKSPACE/heor/analysis-plan.json WORKSPACE/heor/partitioned-survival-plan.json WORKSPACE/heor/survival-curve-materializations.json`. Treat `valid` as contract integrity, not evidence sufficiency, statistical fit, clinical plausibility, independent validation, or approval.

## Stop boundaries

- Stop for more or fewer than two strategies, indirect or network comparisons, non-PFS/OS endpoints, competing/recurrent events, treatment switching adjustment, time-varying effects estimated from incomplete data, non-HR effects, individual patient histories, or unaligned time origins.
- Stop when the comparator is not the analysis baseline, source survival reaches zero, the evidence horizon is not a cycle boundary, HR evidence differs silently between duration scenarios, or any scenario produces PFS above OS.
- Do not equate treatment duration, discontinuation, adherence, and treatment-effect duration. Record their relationship in the rationale and keep unsupported causal claims visible.
- Do not choose the base case, horizon, waning endpoint, or evidence basis on behalf of the Human reviewer. Do not create approval or independent-validation fields.

Route curve fitting and family choice to `$heor-survival-extrapolation-review` and
`$heor-survival-curve-materialization`; route PSM calculation to
`$heor-partitioned-survival`, joint curve draws to
`$heor-joint-survival-uncertainty`, and release review to
`$heor-model-validation` plus `$heor-reporting`.

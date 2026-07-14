# Relative-effect transition contract

## Exact analysis shape

Analysis schema `0.10.0` admits `relative_effect_to_transition_schedule` only at a complete two-state strategy transition-schedule path. The transformation contains exactly:

- `operation`, `cycle_length_years`, and `effect_interval_years`;
- distinct `from_state_index` and absorbing `event_state_index` values 0 and 1;
- `measure`, exactly `risk_ratio` or `odds_ratio`;
- `baseline_cycle_probabilities`, with one exact `{cycle, probability}` record per analysis cycle;
- one `relative_effect` value;
- `review_bases`, containing exactly `endpoint_alignment`, `population_transportability`, and `effect_constancy_over_cycles`.

Each `probability` and `relative_effect` contains a finite numeric `value` plus exactly one non-empty `source_extraction_id` with optional JSON pointer or one `assumption_id`. Each review basis declares exactly one extraction or assumption basis and contains no value, status, approval, or rationale-as-authority field. Mapping-level extraction and assumption IDs equal exactly the bases used by the transformation.

The analysis has exactly two states and 1–10,000 cycles. Both declared intervals are finite, positive, equal to each other, and equal to the analysis cycle length. Baseline cycles are one-based and contiguous, probabilities are in `[0,1)`, and at least one baseline probability is positive. The event state is absorbing.

## Formulas

For baseline cycle probability `p_b` and positive relative effect `e`:

- Risk ratio: `p_t = p_b * e`.
- Odds ratio: `p_t = e*p_b / (1-p_b+e*p_b)`.

Every intermediate and output is finite and every output is in `[0,1)`. A risk-ratio contract therefore also requires `e < 1 / max(p_b)` over positive baseline probabilities. Zero baseline probabilities remain zero but an all-zero baseline is rejected because the relative effect has no identifiable executable consequence.

The emitted schedule contains one matrix per model cycle. The origin row is `[1-p_t, p_t]` in the declared state order and the event row is absorbing. Deterministic recomputation equals both the current strategy schedule and `derivation.model_value`.

## Human review and stopping rules

`endpoint_alignment` records whether baseline and effect use the same endpoint definition, estimand, comparator, and follow-up interval. `population_transportability` records why the effect and baseline risks can be combined for the modeled population and setting. `effect_constancy_over_cycles` records the evidence or explicit assumption for applying one RR or OR to every cycle. These are review bases, not approvals.

Stop when this operation receives a hazard ratio, rate ratio, risk difference, incompatible adjusted/conditional effect, competing or recurrent event, composite endpoint, non-absorbing event, multiple origin states, time-varying effect, treatment waning, crossing hazards, treatment switching, or unsupported extrapolation. Do not silently turn HR into RR, multiply a probability by HR, or convert an OR into RR. `$heor-hazard-ratio-adapter` owns the separately bounded constant proportional-hazards semantics and full baseline-hazard schedule recomputation; `$heor-survival-curve-adapter` remains limited to already-selected absolute survival curves.

## Uncertainty 0.9.0

Pair analysis `0.10.0` only with uncertainty `0.9.0`. The sole transformation target is:

`/input_provenance/<mapping>/derivation/transformation/relative_effect/value`

DSA bounds are positive and bracket the base. For `risk_ratio`, the high DSA bound and Uniform PSA high bound are strictly below `1 / max(positive baseline probability)`; PSA supports only bounded Uniform because an unbounded positive RR distribution can generate invalid absolute risks. For `odds_ratio`, PSA supports Lognormal or strictly positive bounded Uniform. Each distribution binds exactly the relative-effect extraction or assumption. Baseline probabilities, measure, intervals, review bases, operation, and other transformation fields stay fixed.

At least one ordinary external structural scenario remains required. Under uncertainty `0.9.0`, scenarios may change only state cost or utility scalars, discount rates, or half-cycle correction. They may not change cycles, intervals, transition matrices or schedules, the relative-effect transformation, or any transformation internal.

## Method basis

- [NICE DSU Technical Support Document 5 series](https://www.sheffield.ac.uk/nice-dsu/tsds/evidence-synthesis-tsd-series) illustrates risk- and odds-scale evidence synthesis and the need to combine relative effects with an explicit baseline risk on the correct scale.
- [NICE PMG36 economic evaluation](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/) requires treatment effects, baseline risks, assumptions, extrapolation, and uncertainty to be transparent and clinically plausible.
- [ISPOR-SMDM state-transition good practices](https://www.ispor.org/docs/default-source/resources/outcomes-research-guidelines-index/state-transition_modeling-3.pdf) requires transition estimates and transformations to be justified, validated, and represented on a coherent time basis.

These sources support the explicit arithmetic and disclosure boundary. They do not establish endpoint compatibility, transportability, constant effects, or validity for a particular decision problem.

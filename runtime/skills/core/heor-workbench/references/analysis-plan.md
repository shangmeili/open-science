# Analysis plan contract

Use `assets/multi-strategy-analysis-plan.template.json` for new state-transition work that compares all relevant alternatives in one analysis. Keep `assets/analysis-plan.template.json` for legacy two-role projects. Use `$heor-economic-inputs` for partitioned survival. The desktop deterministic engine supports bounded, inspectable state-transition and partitioned-survival calculations:

- 2–16 explicitly ordered strategies under state-transition schemas `0.8.0` through `0.11.0`, structure-neutral PSM schema `0.12.0`, or legacy `comparator` and `intervention` roles under schemas `0.1.0`–`0.7.0`;
- one shared set of unique health states;
- static or piecewise model-cycle-dependent transition matrices;
- state costs and state utilities;
- optional half-cycle correction;
- separate annual discount rates for costs and outcomes;
- optional willingness-to-pay threshold for net monetary benefit.
- one declared calculation currency and price year for every monetary result.

## Required engine fields

Use schema `0.8.0` for ordinary new multi-strategy state-transition work. Schema `0.9.0` adds only portable background mortality; schema `0.10.0` adds only bounded RR/OR application; schema `0.11.0` adds only bounded constant-HR application. Use `$heor-economic-inputs` and schema `0.12.0` only for partitioned survival; each strategy then contains exactly `name`, `state_costs`, and `state_utilities`, with no initial distribution or transition definition. Declare `strategy_order` with 2–16 unique IDs matching `^[a-z][a-z0-9_-]{0,63}$`; `strategies` must contain exactly those keys, and `baseline_strategy_id` must equal the first entry. The baseline is the reference for pairwise results, not an instruction to replace complete incremental analysis. Schemas `0.4.0`–`0.7.0` remain supported for existing two-role projects and their introduced transition transformations. `analysis_id`, economic basis, reference case, states, cycles, cycle length, discount rates, half-cycle correction, and strategies are required.

Schema `0.8.0` results include all strategy totals, pairwise results versus the declared baseline, a fully incremental table sorted by expected QALY, strict and extended dominance status, the efficiency frontier, sequential ICERs between adjacent frontier strategies, and the strategy with maximum net monetary benefit at the primary threshold. Equivalent cost/QALY points remain explicit; declaration order resolves which identical point is retained on the frontier. Pairwise-versus-baseline output never substitutes for the fully incremental table.

The engine can still calculate a legacy `0.1.0` plan for reproducibility, but its result has no claimed currency or price-year basis. A `0.2.0` plan retains its economic basis but lacks the executable evidence-value derivation contract. Both prior versions remain calculation-only and cannot pass analysis-plan approval.

The complete plan fixes `uncertainty_analysis.path` and `budget_impact_analysis.path` to their canonical files. A multi-strategy uncertainty plan evaluates all declared strategies. The bounded BIA remains a two-market-share calculator, so its comparator/intervention IDs must explicitly select two distinct strategy keys from a schema `0.8.0` plan; it does not model three-way market shares.

For each state-transition strategy through schema `0.11.0`:

- `initial_distribution` length equals the number of states and sums to 1;
- define exactly one of `transition_matrix` or `transition_schedule`;
- each matrix is square and every row sums to 1;
- a schedule starts at cycle 1, uses unique strictly increasing integer `start_cycle` change points no greater than `cycles`, and carries its last phase through the horizon;
- `state_costs` and `state_utilities` lengths equal the number of states;
- probabilities and utilities are finite values from 0 through 1;
- costs are finite and non-negative.

The engine rejects an `approvals` field. Human approval state lives outside the workspace.

`transition_schedule` varies matrices by one-based model cycle for the whole cohort. It does not by itself represent time in state, tunnel states, semi-Markov memory, patient history, time-varying rewards, or individual simulation. Use `$heor-cohort-state-transition` before selecting or changing this structure. If evidence reports constant cause-specific competing event rates, use `$heor-transition-rate-adapter`. If an exponential or Weibull all-cause curve has already been selected for an exactly two-state model, use `$heor-survival-curve-adapter`. If one event probability has an explicit source interval and a reviewable constant-hazard assumption, use `$heor-probability-time-adapter`. For exactly two-state mortality with age-aligned annual all-cause population probabilities, any finite positive model-cycle length, and one constant additive disease excess rate, schema `0.9.0` may use `$heor-background-mortality`. For aligned cycle-specific baseline risks and one RR or OR in an exactly two-state absorbing schedule, schema `0.10.0` may use `$heor-relative-effect-adapter`. For one absorbing time-to-first event with cycle-aligned baseline cumulative hazards and one reviewed constant HR, schema `0.11.0` may use `$heor-hazard-ratio-adapter`. Keep broader transformations or model types explicit and incomplete.

The background-mortality portable contract computes `h_bg(age) = -ln(1-q_annual)`, `h_total = h_bg + h_excess`, and `p_death = 1-exp(-h_total*cycle_length_years)`. It requires exact evidence- or assumption-bound `population_exchangeability` and `no_double_counting` bases. Those bases are review inputs, not approvals; the app-owned Human-in-the-loop gate remains authoritative. Stop for an input already representing all-cause mortality; cause-specific/subdistribution mixtures; calendar mortality improvement; age/sex mixtures; time-varying excess hazards; competing non-death events; or partitioned-survival models. The portable schema and validators do not by themselves establish native calculation support; do not execute or approve a `0.9.0` plan until the desktop/Python/Rust implementation and parity tests are present.

The relative-effect portable contract computes `p=q*RR` or `p=q*OR/(1-q+q*OR)` independently for every cycle. It requires equal cycle/effect intervals, at least one positive baseline risk, exact value-plus-basis inputs, and the exact `endpoint_alignment`, `population_transportability`, and `effect_constancy_over_cycles` review bases. Stop for HR inside this operation, rate ratio, risk difference, competing events, or inferred extrapolation.

The constant-HR portable contract computes `p=-expm1(-HR*(H0(i)-H0(i-1)))`, with `H0(0)=0`, independently for every cycle. It requires one positive HR, non-negative non-decreasing cumulative hazards with at least one positive increment, and the exact endpoint, population, proportional-hazards, effect-duration, and switching review bases. Stop for time-varying or non-proportional effects, waning/stopping, unresolved switching, competing/recurrent events, curve fitting/selection, or partitioned survival. Portable schema validity never substitutes for native/Python/browser parity or Human method review.

## Review metadata

Keep the `decision_problem`, `evidence_sources`, `assumptions`, `input_provenance`, and `input_status` metadata. The numerical engine ignores these fields, while the app independently audits them before analysis-plan approval.

Use `$heor-input-provenance` and its reference contract for exact fields. Each required model input must map to valid evidence or an explicit `proposed` analyst assumption and preserve an exact `derivation.model_value` snapshot. Direct evidence must parse as strict JSON and equal the current model value. Every state cost and non-null willingness-to-pay value must also declare the plan currency and price year, reproduce each model value from a recorded source value and adjustment factor, and bind source values to selected extraction elements. `unresolved` assumptions or unexecutable transformations block analysis-plan approval. Never write `accepted`; canonical acceptance exists only in the app-owned human approval chain.

## Reference-case profiles

The packaged registry currently exposes `CN-2020-current`, `CN-2026-draft`, and `NICE-PMG36-2026-current`. Registry entries are versioned executable subsets, not copies of guidance or compliance certificates. Selecting any profile does not establish guideline compliance; a `draft` profile also prevents local analysis authorization. NICE analyses must standardize the jurisdiction as `England`, state the NHS and personal social services perspective, use the profile's discounting rule, and populate `methodology.health_outcomes` for the app-owned reference-case audit.

## Artifact stability

The app hashes the exact saved bytes. After a human approves a gate, any file change produces a different artifact and requires renewed review. Format deliberately and avoid unrelated rewrites after approval.

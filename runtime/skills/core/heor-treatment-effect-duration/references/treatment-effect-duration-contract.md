# AI4HEOR treatment-effect duration contract

## Responsibility

`heor/treatment-effect-duration.json` represents structural uncertainty about
how a reviewed relative treatment effect continues after an evidence horizon.
It supports exactly one direct two-strategy comparison and the ordered PFS and
OS endpoints. It does not estimate an HR, select a duration, fit a survival
model, adjust treatment switching, or prove plausibility.

The artifact binds exact analysis and parametric source-materialization bytes.
PSM schema `0.4.0` binds the artifact bytes and contains the selected scenario's
fully materialized curves. This one-way dependency avoids a circular hash.

## Required scenarios

For each endpoint, all scenarios share one cycle-aligned evidence horizon,
one strictly positive non-null HR, and identical HR evidence IDs. Across the
complete scenario set each endpoint must cover:

- `sustained`: keep the declared HR after the evidence horizon;
- `immediate_stop`: set the HR to 1 immediately after the horizon;
- `log_linear_waning`: move log(HR) linearly to 0 by a later cycle boundary.

This contract requires three to five complete scenarios. A scenario always
contains both PFS and OS policies. The same mode need not be used for both
endpoints, but every endpoint must cover all three modes across the set.

## Deterministic calculation

Keep the intervention source curve through evidence-horizon index `k`. For each
later cycle `i`, derive the comparator cumulative-hazard increment:

`delta_H_c(i) = -log(S_c(i) / S_c(i-1))`.

Let `r_i` be the policy HR at the interval start. Then:

`S_t(i) = S_t(i-1) * exp(-r_i * delta_H_c(i))`.

For log-linear waning from horizon `t0` to cessation `t1`:

`r(t) = exp(log(HR) * (t1 - t) / (t1 - t0))` for `t0 <= t < t1`,
and `r(t) = 1` from `t1`. This is an explicit cycle-start discretization, not
an assertion that within-cycle hazards or biological waning follow this shape.

Every result must start at one, stay strictly positive and non-increasing on the
analysis grid, and satisfy PFS <= OS for both strategies. Reject rather than
truncate, cap, reorder, interpolate, or repair.

## Evidence and uncertainty boundary

NICE asks analysts to consider alternative duration scenarios in the
extrapolated phase, including stopping or gradual diminution, continuation
while treated, and clinically plausible residual benefit after discontinuation.
It also requires structural assumptions and plausible alternatives to be
documented and explored separately. CADTH's 2023 methods report describes the
same core alternatives as no waning, no effect beyond trial duration, and a
decline to a stated cessation time, while warning that multiple-treatment
comparisons remain methodologically uncertain.

The three policies are therefore structural scenarios, not exchangeable PSA
draws. Joint PFS/OS draws may be conditional on the selected base policy but
must bind the exact duration artifact. Reports keep the structural scenario
results separate from parameter PSA and disclose source-model, family,
extrapolation, causal, clinical, and external-validity limitations.

## Sources

- [NICE PMG36, sections 4.6.20 and 4.7](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/) requires treatment-effect duration alternatives and explicit structural-uncertainty scenarios.
- [CADTH 2023, Extrapolating Clinical Evidence Within Economic Evaluations](https://www.ncbi.nlm.nih.gov/books/NBK594389/) describes sustained, immediate-stop, and decline-to-cessation alternatives and cautions about multiple-treatment comparisons.
- [NICE TA1064 committee discussion](https://www.nice.org.uk/guidance/TA1064/chapter/committee-discussion) provides a current applied example in which PFS hazards converge after a stated waning period and OS duration remains uncertain.
- [NICE obesity reference-case extension](https://www.nice.org.uk/process/pmg50/chapter/rationale-and-supporting-information) emphasizes that discontinuation, adherence, and long-term effect trajectories must be related explicitly rather than assumed equivalent.

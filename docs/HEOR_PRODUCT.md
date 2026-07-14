# AI4HEOR Product Contract

## Purpose

AI4HEOR is a local-first, model-provider-agnostic desktop workbench for
pharmacoeconomic research. It uses Open Science Desktop as its platform base,
but keeps decision calculations in a deterministic, testable engine rather than
in a language model.

Natural-language conversation is the primary research interface. The agent
turns research intent into reviewable files, evidence records, code, and runs.
Structured controls are secondary surfaces for inspecting parameters, resolving
ambiguity, and recording human decisions; they must not turn the workbench into
a form-led modeling application.

## Accountabilities

- The product owner sets scope and accepts product behavior.
- Codex performs most research synthesis, architecture, implementation, tests,
  documentation, and cross-platform build work.
- A qualified human reviewer approves decision-relevant research choices.
- An independent reviewer validates decision models. Codex self-review is not
  independent validation.

## MVP decision problem

The current complete cost-effectiveness workflow compares 2–16 explicitly
ordered strategies against a declared baseline using a static or piecewise
model-cycle-dependent cohort state-transition model. The bounded three-year
budget impact analysis explicitly selects two of those strategies. Both deterministic
calculation paths, independent validation, hash-bound reporting, and the
human-controlled local release gate are implemented.

## Non-negotiable boundaries

1. Language models may draft inputs, explanations, and code, but they do not
   produce the authoritative cost, QALY, ICER, net benefit, or budget result.
2. A run is not decision-ready until the decision problem, independent
   `heor/conceptual-model.json` artifact, hash-bound reference-case assessment,
   executable uncertainty plan, executable budget impact plan, and analysis
   plan are approved by a human, an independent reviewer has submitted an
   approvable validation package bound to all four current model artifacts, and
   a named human release owner has approved the current report package after
   deterministic result reproduction.
3. Every decision-relevant value must carry a source, unit, jurisdiction,
   selection rationale, and uncertainty status before public beta. Monetary
   values also require a common currency and price year plus a reproducible
   normalization trail.
4. Results must trace to input, engine version, reference-case version, and run
   environment.
5. The MVP accepts public or non-sensitive data only. Patient-level, claims,
   EHR, or other restricted data are out of scope until the security boundary is
   independently reviewed.
6. Current guidance and draft guidance are separate reference-case profiles.
   Draft guidance must never be presented as a binding current requirement.
7. Valuable third-party HEOR assets are adapted through the admission and
   industrialization gates in `docs/HEOR_ECOSYSTEM.md`; upstream popularity or
   a passing upstream test suite is insufficient for bundling.

## Product states

```text
draft -> scoped -> plan-approved -> computed -> validated -> released
```

Only a human can move a project through `scoped`, `plan-approved`, `validated`,
or `released`. Automated checks may block a transition but cannot approve it.

The alpha desktop service keeps its canonical approval log in app-owned data,
outside the agent workspace. It fails closed on malformed history and links
events with an unanchored SHA-256 chain. This detects partial or inconsistent
edits but cannot prove non-tampering against a same-user process that can rewrite
the entire log. The actor label is also a local human assertion until an
OS-keychain-backed signature and identity flow is independently reviewed. The
dedicated desktop review surface is the only initial approval entry point;
analysis input metadata and agent-authored files can never self-authorize a run.

## Human-authorized public evidence search

The shipped alpha supports a natural-language-first search handoff for PubMed
and ClinicalTrials.gov. The Agent uses `$heor-evidence-search` to draft and
portably validate `heor/evidence-search-request.json`; it cannot execute the
network call. The desktop audits the exact bytes and exposes the query, dates,
fixed source allowlist, per-source cap, non-sensitive egress declaration, and
SHA-256 for explicit human authorization.

Native execution accepts no caller-controlled URL, header, credential, path, or
arbitrary provider. It disables redirects, caps time and response size, verifies
JSON responses, writes a new immutable run under
`heor/evidence-search-runs/`, and appends a hash-linked authorization event to
app-owned storage outside the Agent workspace. A changed request requires a new
authorization.

The evidence-synthesis ledger is now a native review surface rather than a
manual copy step. The desktop re-verifies the app-owned authorization chain,
active project, safe run path, exact request/run hashes, fixed endpoints,
response hashes, result caps, and normalized record set before importing. A
compare-and-swap synthesis hash prevents stale writes; repeated imports are
idempotent; existing screening, appraisal, and extraction judgments are never
overwritten. New records always enter as `not_assessed`, after which the Agent
continues screening and extraction through `$heor-evidence-synthesis` in the
natural-language workflow.

Returned bibliographic and registry metadata is candidate
evidence with initial screening status `not_assessed`; retrieval is not
inclusion, appraisal, extraction, full-text verification, or proof that a
systematic search is complete. OpenAlex and licensed databases remain out of
scope until separate API-key, license, and consent boundaries are designed.

## App-owned evidence verification and input selection

Workspace fields such as `human_checked` and `verified_by` remain agent-writable
activity records and are not trusted as approval facts. After a synthesis is
structurally complete, the desktop exposes each exact extraction value, model
target, record ID, source location, and applicability. An app-owned review event
binds the exact synthesis SHA-256, a sorted set of eligible extraction IDs, one
local reviewer label and rationale, and a `confirmed` or `rejected` decision.
Events form a per-project append-only SHA-256 chain outside the workspace.

Every selected extraction now requires confirmations from at least two distinct
local reviewer labels. A label cannot review the same extraction twice for the
same synthesis. Any rejection blocks that extraction from model-input approval;
the evidence synthesis must be revised, which gives it a new SHA-256 and makes
all prior decisions inapplicable. Schema-v1 single-reviewer events remain
verifiable but count as one confirmation only.

The analysis plan now binds the current `heor/evidence-synthesis.json` digest.
Every source-based input mapping must name one or more `extraction_ids`; each
extraction target must exactly equal the model-input path and its record ID must
be a linked evidence-source ID. The native analysis-plan gate requires all
selected IDs to exist in the current structurally complete synthesis and in the
current dual-confirmed, non-rejected app-owned set, then binds the synthesis digest into the
analysis-plan approval event. Execution, uncertainty, and budget-impact status
repeat the check. Structural validation remains portable, but portable tools
explicitly cannot claim human verification.

This boundary records two distinct local labels and detects inconsistent or
partial edits. It does not prove reviewer identity, source truth, blinding,
duplicate independent extraction, consensus or arbitration, or resistance to
an attacker able to rewrite the whole local app-data store. Cochrane requires
at least two people to extract critical outcome data independently and a
prespecified disagreement process; AI4HEOR does not claim that stronger method
until identity, independent entry, and resolution workflow are implemented and
used. OS-backed identity and external anchoring remain future hardening.

## Executable evidence-to-model derivation

Analysis-plan schema `0.3.0` closes the gap between a confirmed extraction and
the number actually calculated. Every required input mapping copies its exact
current model value into `derivation.model_value`; the plan audit rejects a
stale or different snapshot. A source-based non-monetary input uses
`direct_evidence`, exactly one extraction, and an `extracted_value` that parses
as strict JSON and equals the complete scalar, vector, matrix, or boolean model
value. An assumption-only input uses `explicit_assumption`, no extraction, and
at least one `proposed` assumption.

Source-based monetary values use `monetary_adjustment`. Every recorded source
value binds to a selected extraction's JSON scalar or array index before the
normalization arithmetic is checked. Every selected extraction must be used.
The portable validator checks the current synthesis bytes; the native desktop
repeats the same value audit in the app-owned selection boundary before it
considers the dual-review status.

The contract deliberately does not execute free-form formulas. A narrative in
`selection_rationale` cannot authorize a hidden transformation. Schema `0.5.0`
admits constant cause-specific competing event rates, schema `0.6.0` admits a
bounded two-state survival schedule, and schema `0.7.0` admits the single-event
probability time conversion described below. Schema `0.9.0` admits the bounded
background-plus-excess mortality operation described below. Schema `0.10.0`
admits only the bounded RR/OR relative-effect operation described below, and
schema `0.11.0` admits only the bounded constant-HR operation described below.
Other effect measures, pooling, calibration, interpolation, and general
continuous-time matrix conversion remain incomplete. Schemas `0.1.0` and
`0.2.0` remain calculable for reproducibility but cannot pass analysis-plan
approval; static `0.3.0` and schedule-capable `0.4.0` plans remain approvable.

Analysis-plan schema `0.8.0` removes the two-role ceiling without weakening
auditability. It requires 2–16 safe strategy IDs, an explicit deterministic
`strategy_order`, an exact strategies map, and a baseline ID in first position.
The engine reports pairwise results versus that baseline but separately performs
the methodologically required fully incremental analysis: ordering by expected
QALY, identifying strict and extended dominance, constructing the efficiency
frontier, and calculating sequential ICERs only between adjacent frontier
strategies. Identical cost/QALY points remain explicit and declaration order
selects the retained representative. At the primary threshold, all strategies
compete on net monetary benefit.

## Executable model-cycle-dependent transitions

Analysis-plan schema `0.4.0` adds a bounded `transition_schedule` alternative
to each strategy's static matrix. A strategy defines exactly one mechanism. A
schedule starts at one-based cycle 1, contains unique strictly increasing
change points within the horizon, and provides a complete square probability
matrix at every phase; the last matrix remains active through the horizon. The
engine validates every row and cohort-mass conservation, selects the effective
matrix deterministically by model cycle, and records the transition mode and
change points in each strategy result.

The full schedule replaces the static matrix in input provenance. Direct
evidence must be strict JSON equal to that schedule; unexecutable matrix
assembly, rate or hazard conversion, pooling, or treatment-effect extrapolation
remains blocked. DSA and PSA may target a complete scheduled matrix row, and a
structural scenario may move a declared change point only if the resulting plan
still passes the full engine contract.

This is model time for the whole closed cohort. It is not time in state,
tunnel-state or semi-Markov memory, patient history, individual simulation,
partitioned survival, interactions, time-varying rewards, or an automatic
treatment-waning assumption. `$heor-cohort-state-transition` makes that choice
and boundary explicit before Human-in-the-loop review. The implementation uses
the selection and transparency questions in the ISPOR-SMDM state-transition
good-practices report and NICE PMG36; those methods sources do not certify any
particular model.

## Executable constant competing-event rates

Analysis-plan schema `0.5.0` adds the first admitted evidence transformation
for transition inputs. For each state and phase, a structured declaration binds
every positive cause-specific event rate to exactly one selected extraction or
`proposed` assumption and records the exact cycle length. With total rate `R`,
the adapter computes total event mass `1 - exp(-R*t)`, allocates it in proportion
to each cause-specific rate, and assigns `exp(-R*t)` to remaining in the state.
Structural zeros are omitted and an absorbing row has no events.

Python calculation, portable Skill validation, native Rust approval audit, and
the browser preview independently recompute the complete matrix or schedule.
They require the output to equal the current model input and derivation snapshot,
and require every declared extraction and assumption ID to be used. Altering a
rate, matrix, cycle length, phase, or basis set therefore fails closed.

This is a competing-first-event calculation under constant within-phase rates
and an at-most-one-state-change-per-cycle assumption. It is not general CTMC
matrix exponentiation. Uncertainty schemas `0.3.0` through `0.7.0` can vary exact positive event
rates with gamma, lognormal, or strictly positive uniform distributions. For each
DSA run or PSA draw, the compatible uncertainty engine recomputes each affected complete matrix or
schedule and its derivation snapshot before ordinary validation. Changing only a
derived probability row still fails closed. The adapter does not implement
probability-time conversion inside the rate adapter, HR application or RR/OR application outside the dedicated adapter, pooling, calibration, survival
extrapolation, within-cycle multi-step paths, arbitrary correlated rate models, or
transformation-space structural scenarios, except that schemas `0.4.0` through `0.7.0` may correlate
only evidence-bound lognormal rate members through the bounded latent log-scale
Cholesky contract. Eligible single-event source probabilities route to the separate
`$heor-probability-time-adapter`; `$heor-transition-rate-adapter`
exposes the method and its stopping rules through the natural-language workflow.

## Executable bounded survival-curve schedules

Analysis-plan schema `0.6.0` admits one deliberately narrow survival operation:
an already-selected exponential or Weibull scale/shape curve for one all-cause
event in an exactly two-state model. At every model-cycle boundary the adapter
evaluates cumulative hazard and converts its increment into the interval event
probability. It emits a complete two-state matrix for every cycle and preserves
the event state as absorbing.

Every positive curve parameter binds exactly one strict-JSON extraction or
`proposed` assumption. Python calculation, the standalone Skill validator,
portable provenance audit, native Rust audit, and browser preview independently
recompute the schedule and compare it with both the current model input and the
derivation snapshot. Parameter, cycle-length, source, version, state-count, or
schedule drift fails closed. The natural-language workbench exposes this through
`$heor-survival-curve-adapter`; the form action is only a shortcut into that
conversation.

Uncertainty schemas `0.5.0` through `0.7.0` may vary exact positive exponential or Weibull
parameter values with evidence-bound gamma, lognormal, or strictly positive
uniform distributions. The compatible uncertainty engine applies all replacements and recomputes
the complete affected schedule and derivation snapshot before ordinary model
validation. This is parameter propagation for an already-selected curve, not a
complete survival-analysis workflow.

The first-party `$heor-survival-extrapolation-review` now prepares a separate
schema `0.2.0` review artifact before curve selection. It requires 2–8
pre-specified standard parametric families, exact data/command/session/output
hashes, visible failed fits and protocol deviations, common observed and
extrapolated survival/hazard landmarks, AIC/BIC, KM and hazard diagnostics,
external and clinical plausibility assessments, limitations, and at least two
structural scenarios. The alpha imports an already-generated local `survHE` fit
bundle and does not access or fit patient-level data. It neither bundles that
GPL backend nor silently installs it. The validator rejects post-hoc model-order drift, stale hashes,
incomparable or invalid landmarks, hidden approval fields, and fewer than two
converged alternatives. The only admitted state is
`awaiting_human_selection`; the selected curve enters the app-owned analysis-
plan review rather than being chosen by a score or Agent output. The native app
now matches the exact analysis ID and sole parametric-survival target, requires
the selected plan distribution to be a converged candidate, independently
verifies the contract and local hashes, shows the result in the review pane,
and binds the current review hash into analysis-plan approval and every analysis
authorization check. Multi-curve plans fail closed until an indexed review
collection is admitted.

Automatic curve selection, KM/IPD reconstruction, flexible or cure models,
PFS/OS partitioned survival, treatment effects, background mortality, competing
risks, covariance reconstruction from incomplete fit results, and clinical
extrapolation validity remain explicitly unsupported. NICE PMG36 and NICE DSU TSD 14/21 require validity,
plausibility, alternatives, and uncertainty beyond this executable fragment;
the platform therefore does not infer those claims from a generated schedule.

## Executable single-event probability time conversion

Analysis-plan schema `0.7.0` changes the time unit of at most one event
probability per affected state row under an explicit constant-hazard
assumption. For source probability `p` over `t_source` years and model cycle
`t_cycle`, it evaluates `1 - exp(log(1-p) * t_cycle / t_source)` with stable
`log1p`/`expm1` implementations. It never divides the probability by a cycle
count. Source probabilities must be strictly inside `(0,1)`; a structural zero
uses a null event; both time intervals must be positive.

Every source probability binds exactly one strict-JSON extraction or `proposed`
assumption. Python calculation, the standalone Skill validator, portable
provenance audit, native Rust audit, and browser preview independently
recompute the complete matrix or schedule. `$heor-probability-time-adapter` is
the natural-language entry point; the form action only drafts that conversation.

Uncertainty schema `0.6.0` or `0.7.0` may vary the exact `source_probability` with an
evidence-bound Beta or Uniform distribution strictly inside `(0,1)`. Every DSA
run and PSA draw recomputes the complete transition input and derivation
snapshot before model validation. Competing events, probabilities 0 or 1,
time-varying hazards, HR application or RR/OR application outside the dedicated adapter, composite endpoints, recurrent
events, dependence between probability parameters, and clinical
appropriateness remain unsupported. ISPOR-SMDM and PHARMAC support the
arithmetic and disclosure requirement; they do not validate the assumption for
a specific decision problem.

## Executable background plus excess mortality

Analysis-plan schema `0.9.0` admits one exactly two-state operation:
`background_plus_excess_mortality_to_transition_schedule`. The exact declaration
contains the model cycle length and state indices; one life table with jurisdiction,
table year, population, sex, start age, and one cycle record per horizon cycle;
one constant `excess_mortality_rate_per_year`; and the exact review bases
`population_exchangeability` and `no_double_counting`. Every cycle record binds
an annual all-cause probability to one extraction or proposed assumption and
declares `attained_age_years = floor(start_age_years + (cycle-1)*cycle_length_years)`.

The adapter first converts annual `q` to background hazard and then scales to any
finite positive model-cycle length:
`p_death = 1-exp(-(-ln(1-q_annual)+h_excess)*cycle_length_years)`.
Python calculation, the standalone Skill validator, portable provenance audit,
native audit, and browser preview independently recompute the complete schedule.
The review bases expose evidence or assumptions; they never create approval.

Paired uncertainty schema `0.8.0` permits only the exact positive
`excess_mortality_rate_per_year.value` parameter target with Gamma, Lognormal, or
strictly positive Uniform PSA. It fixes all life-table values and metadata,
review bases, operation, and other transformation internals. At least one ordinary
allowlisted external structural scenario remains required, limited under `0.8.0`
to cost or utility scalars, discount rates, or half-cycle correction. Changes to
cycle count/length or transition matrices/schedules fail closed because they
would invalidate the fixed mortality transformation. Additive and
multiplicative/SMR mortality structures can materially differ; only additive
excess hazard is implemented, so the multiplicative alternative remains a
Human-in-the-loop structural limitation.

The route stops for already all-cause disease inputs, cause-specific/subdistribution
mixing, calendar mortality improvement, age/sex mixtures, time-varying excess
hazards, competing non-death events, and partitioned survival. NICE PMG36/TSD 21,
ISPOR-SMDM state-transition guidance, and CDA-AMC 4th edition provide the methods
basis; they do not establish exchangeability, absence of double counting, or
scientific validity for a particular model.

## Executable bounded RR/OR relative effects

Analysis-plan schema `0.10.0` admits one deliberately narrow operation:
`relative_effect_to_transition_schedule`. It applies one interval-aligned risk
ratio or odds ratio to cycle-specific baseline risks for a single absorbing
event in an exactly two-state schedule. Every baseline risk and the relative
effect binds one extraction or proposed assumption. The declaration also
requires exactly `endpoint_alignment`, `population_transportability`, and
`effect_constancy_over_cycles` review bases; those bases support review and do
not create approval.

For risk ratio, each cycle uses `p=q*RR`; for odds ratio it uses
`p=q*OR/(1-q+q*OR)`. The adapter independently recomputes every complete matrix
and rejects all-zero baselines, unequal effect/cycle intervals, stale schedules,
unsupported fields, and incompatible effect measures. Paired uncertainty schema
`0.9.0` targets only `relative_effect.value`: RR admits bounded Uniform PSA with
its high strictly below `1/max(q>0)`, while OR admits Lognormal or strictly
positive bounded Uniform PSA. Baselines and transformation internals stay fixed.

Hazard ratio, rate ratio, risk difference, competing events, and treatment-effect
extrapolation remain unsupported by this RR/OR operation. Eligible constant HR
work routes to `$heor-hazard-ratio-adapter`; the form interface remains
subordinate to the natural-language workflow and Human-in-the-loop review.

## Executable bounded constant hazard ratio

Analysis-plan schema `0.11.0` admits one deliberately narrow operation:
`hazard_ratio_to_transition_schedule`. It applies one positive constant HR to
cycle-specific increments of one selected baseline cumulative-hazard curve for a
single absorbing time-to-first event in exactly two states. Baseline cumulative
hazards are non-negative, non-decreasing, cycle-aligned, individually bound to
evidence or proposed assumptions, and contain at least one positive increment.
The HR has its own exact basis.

With `H0(0)=0`, each cycle uses
`p=-expm1(-HR*(H0(i)-H0(i-1)))`. The transformation requires exactly the
`endpoint_alignment`, `population_transportability`,
`proportional_hazards_assumption`, `effect_constancy_over_horizon`, and
`treatment_switching_assessment` review bases. Python, Rust, TypeScript, the
portable provenance audit, and the standalone Skill independently recompute the
complete absorbing schedule and reject stale output, non-monotone hazards,
non-finite arithmetic, and probability saturation.

Paired uncertainty schema `0.10.0` targets only `hazard_ratio.value`. DSA and a
strictly positive bounded Uniform PSA must bracket the base and keep every
recomputed probability finite and below one. Unbounded Lognormal support is
deferred until a truncated distribution can be represented and audited exactly.
Time-varying or non-proportional HRs, effect stopping or waning, unresolved
treatment switching, competing/recurrent events, curve fitting or selection,
PFS/OS partitioned survival, and scientific-validity claims remain blocked.

## Executable monetary basis

Analysis-plan schema `0.2.0` introduced one calculation currency and price
year, and current schemas through `0.11.0` retain that contract while binding each source
value to evidence or an explicit assumption.
Every state-cost element and non-null willingness-to-pay value records its
source value, source currency, source price year, positive composite adjustment
factor, method, and evidence or proposed-assumption basis IDs. Python, Rust, and
the portable Skill validator independently verify that the model-basis metadata
matches the plan and that `source value × factor` reproduces the exact model
input. A same-basis value must use factor 1 and method `none`; any currency,
price-year, unit, or numerical adjustment requires a reviewable method and
basis link.

AI4HEOR does not silently select inflation indices or exchange rates. NICE's
current methods manual requires older costs to be adjusted with an index
appropriate to the cost perspective and foreign costs to use an appropriate
current exchange-rate source. The Agent may prepare that transformation from
an explicitly selected source, but the app audits arithmetic and provenance,
not the substantive appropriateness of the chosen index. Legacy schema `0.1.0`
returns no claimed economic basis; prior schema `0.2.0` retains its basis but
lacks executable evidence-value derivations. Neither can pass analysis-plan
approval. The review pane formats current monetary results from the
engine-returned currency instead of a hard-coded jurisdiction.

## Local evidence library

The shipped alpha accepts PDF, plain text, Markdown, CSV, and JSON sources under
`heor/library`. Native sync rejects symlinks, caps file count, source bytes, and
total extracted text, hashes the exact source and derived index, extracts
searchable text without a model or network call, and writes a reviewable
`heor/evidence-library.json`. The SQLite index stays under `.openscience`, is
serialized against concurrent access, and is rebuildable.

Natural-language retrieval routes through `$heor-local-evidence`. Its portable
search script re-verifies every indexed source hash and every returned page-text
hash, then emits compact snippets with exact local path, page, and source
SHA-256. Changed bytes invalidate search until a native rescan. Searchable
results are extracted evidence, not appraisal or an automatic model input.
Image-only PDFs are `requires_ocr`; encrypted, malformed, unsupported, or
oversized documents remain explicit issues. OCR, layout/table reconstruction,
semantic embeddings, and licensed corpus connectors are not silently inferred
from this alpha.

## Implemented reference-case registry

| ID | Status | Use |
| --- | --- | --- |
| `CN-2020-current` | current | Current Chinese pharmacoeconomic guidance |
| `CN-2026-draft` | draft | Gap analysis only until formally issued |
| `NICE-PMG36-2026-current` | current | NICE technology appraisal and highly specialised technologies economic-evaluation subset for England |

The registry profiles now contain source-snapshot hashes, source locators,
required/recommended levels, applicability, and app-check identifiers. The
first-party `$heor-reference-case` skill creates
`heor/reference-case-assessment.json`; the plan binds its exact SHA-256. The
desktop independently verifies every requirement, local evidence paths,
automatic plan checks, profile revision/hash/status, and analysis link at both
analysis-plan approval and execution. Required gaps, unresolved items, changed
bytes, and draft profiles fail closed. A complete audit is still only a
prerequisite for human review, not a general compliance certification.
The NICE profile binds the official 31 March 2026 PMG36 PDF hash and adds
machine checks for the England jurisdiction, NHS and personal social services
perspective, 3.5% reference-case discounting, and structured EQ-5D/UK-3L
health-outcome metadata. It remains an executable subset: topic scope,
cost-comparison, paediatric HRQoL, diagnostics, severity modifiers, equality,
and managed-access conditions require direct review of current NICE guidance.
The source PDF is not redistributed. CDA-AMC remains a planned profile because
its official fourth-edition source was methodologically readable but its
Cloudflare-protected bytes could not be independently re-hashed in the current
build environment; the platform does not admit an unverifiable source digest.

## Implemented uncertainty boundary

The first-party `$heor-uncertainty-analysis` skill creates
`heor/uncertainty-plan.json`. It binds to the exact current analysis-plan bytes
and records evidence-linked DSA bounds, parameter distributions, omissions,
dependence handling, a uint64 seed, convergence thresholds, and bounded
structural scenarios. The analysis-plan approval event binds the uncertainty
artifact's exact SHA-256 without creating a circular pair of file hashes.
Changing either artifact invalidates local authorization.

The dependency-free engine executes one-way sensitivity analyses, joint PSA,
and structural scenarios with versioned `pcg32-xsh-rr` sampling and fixed beta,
gamma, lognormal, uniform, Dirichlet, and bounded lognormal-Cholesky transforms. Schemas
`0.4.0` through `0.7.0` admit evidence-bound groups of 2–32 scalar lognormal parameters only;
their declared matrix is the correlation of latent standard-normal values on the
log scale and must be symmetric, unit-diagonal, and strictly positive definite.
Each member can belong to one group, and every group basis must already be linked
by every member distribution. The current desktop bridge
limits PSA to 10,000 draws because it returns every draw for audit; larger runs
require a future streamed, content-addressed result artifact. The app reports
cost-effectiveness probability and checkpoint Monte Carlo diagnostics.
Schemas `0.2.0` through `0.7.0` require a declared 2–101 point threshold grid containing
the analysis plan's primary willingness-to-pay value. The grid must come from
the stated decision context or a human instruction; neither the Agent nor a
form may invent a jurisdictional threshold.

For analysis schema `0.8.0`, uncertainty schema `0.7.0` reuses the same draws
to calculate every strategy's unique-optimal CEAC probability, a separate tie
probability, the multi-strategy CEAF, and `E[max_j NMB_j] - max_j E[NMB_j]`
per-person EVPI at every threshold. It stores strategy order once and aligned
cost/QALY arrays per draw to keep the bounded artifact compact. Legacy schemas
retain their original incremental output. The review pane renders each CEAC and
the CEAF as distinct accessible line series and retains exact values in
the result artifact. This is a secondary evidence surface in the
natural-language workflow, not a new form-led modeling path. The result reports
Monte Carlo error and keeps population EVPI and EVPPI explicitly null; it does
not infer affected population, research priority, study design, funding value,
reimbursement, or policy advice. Rust, Python, and the portable skill validator each
fail closed on unsafe targets, changed hashes, unsupported distributions,
unlinked distribution or correlation bases, reused group members, invalid or
singular matrices, known omitted correlations, or invalid scenarios. The engine
does not infer correlations from shared sources, convert original-scale matrices,
or implement arbitrary copulas, rank correlation, empirical posterior draws, or
perfect correlation.

## Implemented budget impact boundary

The first-party `$heor-budget-impact` skill creates
`heor/budget-impact-plan.json`. It binds to the exact analysis-plan bytes and
records the budget holder, jurisdiction, currency, price year, three annual
eligible populations, without/with-access intervention shares, itemized
treatment and condition-related per-patient costs, scenario-level
implementation costs, exclusions, provenance, one-way ranges, alternative
scenarios, validation plans, and limitations. Analysis-plan approval binds the
exact BIA hash alongside the uncertainty artifact; changing any bound artifact
invalidates local authorization.

The dependency-free engine implements the transparent cost-calculator form
recommended for a simple BIA. It derives comparator share as one minus new-
intervention share, reports each of three budget years and the undiscounted
cumulative with-minus-without impact, preserves category-level calculations,
and executes evidence-bound one-way and alternative scenarios. Python, Rust,
and the portable skill validator reject discounting, unsafe targets, missing
provenance, non-finite values, invalid shares, stale hashes, incomplete cost
scope, or unresolved assumptions.

This first slice deliberately excludes induced demand, population entry and
exit, combination therapy, severity-mix changes, and more than two treatments.
When those materially affect the decision question, the workbench must stop at
an explicit limitation and use a future cohort or patient-level BIA adapter; it
must not force the question into this calculator.

## Implemented independent-validation boundary

The first-party `$heor-model-validation` skill prepares or audits
`heor/model-validation.json` and local evidence under
`heor/validation-evidence/`. It adapts, rather than copies, the Chinese 2020
guideline, ISPOR-SMDM validation taxonomy, AdViSHE reporting structure, and
TECH-VER technical-verification domains. It deliberately produces no quality
score: fitness for intended use remains a reviewer judgment.

The native desktop audit requires face, input, external, cross-model,
predictive, and technical-verification coverage across the cost-effectiveness
and budget-impact models. Cross-model and predictive checks may be documented
as not feasible only when the report supplies evidence and rationale. Every
evidence file must remain under the project, pass a size and path boundary, and
match its recorded SHA-256. The report binds the exact current bytes of the
analysis plan, conceptual model, uncertainty plan, and budget-impact plan.

Codex may run tests, prepare evidence, and preserve findings, but it may not
fill the reviewer independence declaration or recommendation, identify its own
work as independent review, or create approval events. The app permits the
independent-validation approval only when the declared reviewer differs from
the developer, the approval actor exactly matches that reviewer label, all
required coverage is present, and no blocker or major issue remains open.
Changing any report, model, or bound analysis artifact makes the approval
stale.

This gate establishes local structural integrity and a human assertion, not
objective truth. The app cannot prove that evidence is accurate, that the
reviewer is genuinely independent, or that the model is fit for decisions; a
future identity/signature boundary and methods acceptance process remain
necessary before public release.

## Implemented reporting and release boundary

The first-party `$heor-reporting` skill prepares `heor/report-package.json` and
`heor/report.md`. The package binds the exact current bytes of the report,
analysis plan, conceptual model, uncertainty plan, budget-impact plan,
independent-validation report, and three app-written deterministic result
artifacts. CHEERS 2022 supplies 28 cost-effectiveness reporting items and is
never scored or applied to BIA. A separate 12-item ISPOR BIA matrix covers the
budget-impact report. All 40 entries require a rationale, bound evidence paths,
and exactly one report section marker.

The portable and native validators require the exact copied economic basis and numerical summaries,
including the complete decision-uncertainty object when present, explicit
disclosures, limitations, a named release owner, and current hashes. Legacy
uncertainty results retain their legacy summary shape rather than receiving
manufactured CEAC, CEAF, or value-of-information values.
At release, the desktop requires the current independent-validation approval,
re-executes base-case, uncertainty, and budget-impact calculations, compares
their exact output hashes with the bound result files, and records the report
package plus all nine related bindings in the app-owned approval chain. The
Agent can prepare the package but cannot invent its owner or create approval.

`decision_ready_local_release_assertion` means these local structural,
reproduction, validation, reporting, and human gates are current. It does not
assert scientific truth, reviewer identity, journal acceptance, regulatory
approval, reimbursement suitability, or external tamper-proofing.

## Alpha acceptance

- A hand-checkable golden model matches an independent calculation.
- Invalid transition probabilities, dimensions, utilities, and costs fail
  explicitly.
- Cohort mass remains one within numerical tolerance for every cycle.
- A fixed input yields the same result within declared numerical tolerances
  across supported operating systems.
- A fixed plan, uncertainty artifact, PRNG version, and seed yield a
  bit-identical integer random stream and PSA results within declared
  cross-platform numerical tolerances; changed artifact bytes invalidate
  approval. Byte-identical floating-point output is not claimed without a
  controlled math runtime.
- The current golden suite compares scalar model and PSA summaries to seven
  decimal places, requires exact probability counts for the seeded fixture, and
  requires an exact PCG32 integer sequence on macOS, Windows, and Linux CI.
- The BIA golden fixture matches an independent annual hand calculation,
  reports all category subtotals, applies zero discounting, and fails closed on
  changed plan bytes or missing population, uptake, and cost provenance.
- Independent validation requires exact four-artifact and evidence hashes,
  declared reviewer/developer separation, complete required coverage, and zero
  open blocker or major issues. Invalid evidence, stale bytes, or actor mismatch
  fails closed.
- Evidence-to-input approval requires two distinct local-label confirmations
  per selected extraction against the exact synthesis bytes. A duplicate label,
  missing second confirmation, rejection, changed synthesis, or tampered review
  chain fails closed; this remains distinct from authenticated independent
  duplicate extraction.
- Evidence-to-input approval also requires schema `0.3.0` through `0.11.0`, an exact model-value
  snapshot per mapping, strict JSON equality for direct evidence, and extraction-
  bound source values for monetary normalization. Changed, narrative, unused,
  or silently transformed extraction values fail closed.
- A scheduled-transition plan additionally requires schema `0.4.0` through `0.11.0`, exactly one
  transition mechanism per strategy, ordered in-horizon change points, valid
  matrices, mass conservation, and schedule-aware provenance and uncertainty
  targets. Static `0.3.0` plans remain backward compatible.
- A schema `0.5.0` or `0.8.0` transition-rate mapping additionally requires the bounded
  constant competing-rate operation, exact cycle length, complete ordered rows
  and phases, one declared basis per event, and exact output reproduction. Rate-
  space uncertainty additionally requires uncertainty schema `0.3.0` through `0.7.0`, an exact positive
  event-rate target, one matching event basis ID, and full transformation
  recomputation for every DSA/PSA run. Correlated rate sampling additionally
  requires uncertainty schema `0.4.0` through `0.7.0` and the evidence-bound lognormal-Cholesky contract.
- A schema `0.6.0` or `0.8.0` survival mapping additionally requires exactly two states,
  one absorbing event state, an exponential or Weibull scale/shape declaration,
  positive singly bound parameters, exact cycle length, a complete per-cycle
  schedule, and independent reproduction across all four audit layers. Analysis-
  plan approval also requires one schema `0.2.0` extrapolation review bound to
  the exact current analysis ID and sole survival-mapping path; the selected
  distribution must be a converged pre-specified candidate, every local evidence
  hash must verify, and the approval event binds the current review hash. Multiple
  survival targets fail closed in this alpha. Survival-
  parameter DSA/PSA additionally requires uncertainty schema `0.5.0` through `0.7.0`, an exact
  positive parameter-value target, its sole basis ID, and full schedule
  recomputation. Fitting remains external and local, curve selection remains a
  Human analysis-plan decision, and covariance reconstruction or substantive
  extrapolation validity remains outside deterministic claims.
- A schema `0.7.0` or `0.8.0` probability-time mapping additionally requires at most one
  event per row, a source probability strictly inside `(0,1)`, explicit positive
  source and model intervals, one declared basis per event, and exact complete
  output reproduction. Source-probability DSA/PSA additionally requires
  uncertainty schema `0.6.0` or `0.7.0`, strict `(0,1)` bounds, Beta or bounded Uniform,
  its sole basis ID, and full transition-input recomputation. Competing events,
  time-varying hazards, relative effects outside the dedicated bounded RR/OR adapter,
  and clinical applicability remain gaps.
- A schema `0.8.0` analysis additionally requires 2–16 unique safe strategy
  IDs, exact agreement between `strategy_order` and `strategies`, and the
  declared baseline first. Results retain baseline-pairwise comparisons and
  independently identify equivalent points, strict and extended dominance,
  the efficiency frontier, and adjacent-frontier ICERs. Paired uncertainty
  schema `0.7.0` reports every strategy's unique-optimal CEAC probability,
  separate tie probability, CEAF, and exact per-person EVPI. BIA remains a
  bounded two-strategy calculator and must select two distinct declared IDs.
- A schema `0.9.0` background-mortality mapping additionally requires exactly two
  states; an exact life-table declaration and cycle coverage; attained-age floor
  alignment; one basis for each annual probability, the excess rate, and both
  review bases; positive cycle length; and exact hazard-scaled schedule
  reproduction. Paired uncertainty schema `0.8.0` permits only the exact positive
  excess-rate target and fixes the life table and transformation structure.
- A schema `0.10.0` relative-effect mapping additionally requires exactly two
  states with one absorbing event; equal cycle and effect intervals; complete
  cycle-specific baseline risks with at least one positive value; one aligned RR
  or OR; the exact three review bases; and exact schedule reproduction. Paired
  uncertainty schema `0.9.0` permits only the relative-effect value. RR DSA and
  bounded Uniform PSA remain strictly below the positive-baseline ceiling; OR
  admits Lognormal or strictly positive bounded Uniform PSA. HR and all other
  effect measures remain blocked by that operation.
- A schema `0.11.0` constant-HR mapping additionally requires exactly two states
  with one absorbing time-to-first event; complete non-negative non-decreasing
  baseline cumulative hazards with at least one positive increment; one positive
  HR; the exact five review bases; and exact schedule reproduction from hazard
  increments. Paired uncertainty schema `0.10.0` permits only the HR value with
  strictly positive bounded Uniform support whose high reproduces finite
  probabilities below one. Non-proportional/time-varying effects, waning or
  stopping, unresolved switching, competing/recurrent events, fitting/selection,
  and partitioned survival remain blocked.
- Exploratory, analysis-authorized, independently validated, and locally
  released decision-ready states remain distinct. Any stale package, binding,
  validation, result reproduction, actor, or approval sequence fails closed.
- The core analysis runs without a model provider or network connection.

## Upstream and licensing

The platform baseline is `ai4s-research/open-science` commit
`42c8101ab969011c2205fa1eacb96572ef309c18` and remains subject to its MIT
license. Bundled third-party skills and connectors retain their own licenses and
require a separate release inventory.

# AI4HEOR HEOR Asset and Integration Strategy

Evidence reviewed on 2026-07-15. This is a product decision record, not an
endorsement of any clinical, reimbursement, or policy conclusion.

## Decision

AI4HEOR should reuse external HEOR assets through controlled adaptation, not by
copying prompts or delegating authority. Valuable but non-deliverable assets
enter an industrialization pipeline. They ship only after they satisfy the same
local-first, deterministic, auditable, human-governed contract as first-party
code.

The platform remains natural-language first. Skills orchestrate research and
create artifacts; adapters expose bounded tools; deterministic engines perform
calculations; the desktop app owns approval state.

## Admission criteria

An external asset must have all of the following before release:

1. a compatible license and a recorded source revision;
2. a clear local-data and network-egress boundary;
3. workspace-scoped storage with no hidden global project state;
4. explicit input and output schemas and failure behavior;
5. model-input provenance compatible with `$heor-input-provenance`;
6. deterministic or independently reproducible calculation tests;
7. pinned dependencies, software-bill-of-materials review, and no unresolved
   high-severity runtime vulnerabilities;
8. macOS, Windows, and Linux build or execution verification;
9. a bounded tool allowlist and least-authority defaults;
10. no ability to create human approvals, claim independent validation, or
    promote output to decision-ready.

Assets that fail a remediable criterion are forked or wrapped and improved.
Assets with incompatible licensing, unverifiable behavior, or an authority
model that cannot be isolated contribute only ideas and test cases.

“Improved” is not a subjective label. A candidate reaches industrially
deliverable status only when its admission record identifies the upstream
revision and license, retained capability and removed authority, exact
adaptation delta, executable positive and adversarial tests, cross-platform
evidence, security and methods review results, rollback or kill switch,
packaged notices and dependencies, and zero unresolved blockers. Until all
evidence exists, it remains `candidate` or `quarantined`; an upstream demo,
benchmark, or passing test suite cannot promote it. If reuse rights prohibit
modification or redistribution, AI4HEOR may independently implement the method
from public specifications and use the upstream only as research evidence and
a source of black-box test ideas.

Discovery is not admission. An upstream asset must not be copied directly into
the bundled skill or connector inventory merely because it is useful. The
release inventory may contain only (a) a first-party derivative under
`runtime/skills/core/` with its adaptation delta and tests, or (b) a pinned,
isolated adapter that has passed every criterion above. The untouched upstream
snapshot remains evidence for review, not an AI4HEOR production capability.

This rule is now executable. `runtime/assets/asset-admission-registry.json`
records each reviewed third-party Skill or MCP asset. The native runtime accepts
only `validated-adapter`, requires compatible license evidence, a pinned commit,
explicit capability boundaries, adaptation delta, contract and adversarial
tests, macOS/Windows/Linux evidence, passed security and methods reviews, a kill
switch, zero blockers, and an exact tree hash. Invalid registry data, a changed
tree, or a missing resource fails closed and removes any stale external copy
from the app-managed OpenCode profile. Workspace-installed user skills remain
unmanaged project content; they never become bundled AI4HEOR assets implicitly.

## Candidate decisions

| Asset | Value | Current decision | Required adaptation |
| --- | --- | --- | --- |
| [ai4s-research/ai4s-skills](https://github.com/ai4s-research/ai4s-skills) | Useful general research decomposition, integrity cases, and rendering patterns | Seven individually registered, quarantined candidates; no longer bundled | Reuse only verified ideas/tests; rewrite around HEOR artifacts, source controls, deterministic authority, and app-owned gates; independently admit each derivative |
| Anthropic `docx` / `pdf` / `pptx` / `xlsx` Skills | Sophisticated document-workflow reference | Rejected and removed from fetch, package, and deployment paths | Their per-directory source-available license prohibits copying, derivatives, and redistribution; implement independent document capabilities without retaining protected material |
| [HEORAgent MCP](https://github.com/neptun2000/heor-agent-mcp) | Broad HEOR research, literature, screening, evidence-network, HTA, BIA, and dossier tools | Upstream package remains quarantined; bounded search pattern rewritten first-party | Do not run or bundle its 48-tool Node process. AI4HEOR independently implements only PubMed and ClinicalTrials.gov metadata retrieval behind fixed endpoints, exact request hashes, non-sensitive egress declarations, app-owned human authorization, immutable run files, and candidate-only import semantics |
| [`pdf-extract` 0.12.0](https://docs.rs/pdf-extract/0.12.0/pdf_extract/) | Pure-Rust, cross-platform page-level text extraction for searchable PDFs | Admitted as a pinned native parser dependency, not as research authority | MIT metadata is recorded in the upstream Cargo manifest and its notice is packaged with `heor-local-evidence`; AI4HEOR wraps only the in-memory per-page API with file/count/text caps, source hashes, symlink rejection, explicit OCR/encryption/failure states, deterministic local search, and adversarial tests. Its `lopdf` chain is locked to the RustSec-fixed 0.42.0 baseline and the complete Rust lockfile is audited weekly and whenever dependencies change. It cannot establish layout fidelity, appraisal, or evidence validity |
| [CaseMark health-economics skill](https://agentskills.med/skills/conducting-health-economics-research) | Useful task decomposition and terminology | Rewrite as first-party skills; do not bundle verbatim | Remove hard-coded jurisdiction rules and universal claims; split by artifact; attach current primary methods sources; add tests and app-owned HITL boundary |
| [awesome-rosetta health-economics-eval](https://github.com/xjtulyc/awesome-rosetta-skills/tree/main/skills/17-public-health/health-economics-eval) | Compact educational outline | Extract scenarios and negative test cases only | Remove generic GDP threshold and free-form Python authority; replace with versioned reference-case profiles and deterministic engines |
| [medical-research-skills](https://github.com/aipoch/medical-research-skills) | Broad adjacent evidence workflows | Audit selected evidence and review tasks only | Reject low-quality generic market-access template; adapt only source-verifiable components behind AI4HEOR contracts |
| [mcp-stata](https://github.com/tmonk/mcp-stata) | Strong local Stata execution, audit, replication, provenance, and publication workflows | P2 user-installed connector candidate only | AGPL isolation; require licensed local Stata; restrict workspace and command scope; app-owned execution approval; capture do-files, logs, data hashes, Stata/package versions, and failure states |
| [hesim](https://hesim-dev.github.io/hesim/) | Advanced cohort, individual, partitioned-survival, and semi-Markov simulation | P1 optional R execution/validation adapter | User-installed isolated R environment; pinned lockfile; GPL boundary; capture package/session versions; golden cross-checks; never link into the MIT deterministic core |
| [BCEA](https://n8thangreen.github.io/BCEA/) | PSA post-processing, CEAC, EVPI, and VOI | P1 optional uncertainty adapter | Same R isolation and provenance; standardized input/output artifact contract; parity fixtures |
| [survHE](https://cran.r-project.org/package=survHE) | Survival extrapolation for economic evaluation | P1 optional survival adapter | Pre-specified model set; diagnostics and extrapolation audit; version capture; no automatic model selection without review |
| [heemod](https://pierucci.org/heemod/) | Mature Markov modeling and sensitivity analysis | Reference and optional independent cross-check | GPL isolation; golden cases against the AI4HEOR core; document semantic differences rather than forcing parity |
| External relative-effect Skills/plugins | No reviewed candidate supplies a bounded, provenance-complete RR/OR- or HR-to-absolute-risk contract | Do not integrate an external executable asset; implement first-party | Preserve only method/test ideas; require exact measure, baseline input, aligned interval/estimand, full recomputation, and app-owned review |

The admission registry contains 12 reviewed external Skill/MCP entries: seven
`ai4s-skills` candidates and HEORAgent are quarantined, while four Anthropic
document Skills are rejected. None is release eligible or a relative-effect
execution asset. CaseMark, awesome-rosetta, medical-research-skills, and the R
packages above are discovery or cross-check references, not registered adapters.

The HEORAgent audit used revision
`19f5f0eea5764d7a2695c372f3ec8f3aa0f53dd8` (`1.27.0`). A 2026-07-14
remote check found the same upstream HEAD. Its local test suite passed 1,521
tests with 6 skipped, but a fresh installation audit still reported 12
dependency vulnerabilities, including 4 high severity. Its default global
knowledge root, optional PostHog telemetry, direct multi-source egress, and 48
mixed-authority tools are broader than the product boundary. AI4HEOR therefore
does not wrap the package and call it production-ready. It preserves the MIT
notice and independently rewrites the useful bounded-search concept as
`heor-evidence-search`; the upstream asset remains quarantined.

A 2026-07-15 refresh still found HEORAgent Git HEAD at its audited revision, but
the release channels no longer supplied one coherent identity: the repository
described v1.23.0 with 45 tools and 44 sources while npm reported v1.35.0,
modified 2026-07-04. The registry therefore remains intentionally pinned and
quarantined; the latest npm package requires a fresh package, dependency,
telemetry, methods, and adversarial audit before any narrower idea can advance.
The `ai4s-skills` upstream had advanced by 27 mostly non-HEOR files and supplied
no new HEOR-specific Skill or contract.

The same refresh reviewed AIPOCH medical-research Skills at
`7cc568024021a3de07cbeb935691dc72c69bfe28`, awesome-rosetta at
`6cffda43d7cd6c07c563e2f2e24a88a615bcf003`, and mcp-stata at
`a2f9c4abc2c7662e73684f8cf954895c6806ea27`. Their useful patterns do not alter
the admission decision: generic method defaults, unpinned dependencies,
heuristic units, automated confidence, broad code execution, copyleft/runtime
boundaries, and commercial Stata requirements all need first-party contracts or
isolated adapters. The evidence and complete first-party backlog are recorded in
[`SKILL_AND_PLUGIN_STRATEGY.md`](SKILL_AND_PLUGIN_STRATEGY.md).

The earlier desktop baseline also fetched four Anthropic document Skills under
an incorrect Apache-2.0 assumption. The copied `LICENSE.txt` is authoritative:
it prohibits retaining, reproducing, deriving, and distributing those
materials. AI4HEOR now rejects them in the registry and no longer fetches or
packages them. A public GitHub repository is not evidence of an open-source
license.

## First-party skill architecture

Skills stay small and are separated by the artifact they produce or audit.

| Priority | Skill | Primary responsibility | Main artifact |
| --- | --- | --- | --- |
| Shipped | `heor-workbench` | Natural-language orchestration and handoff | `heor/analysis-plan.json` plus conversation |
| Shipped | `heor-input-provenance` | Map every model input to evidence or an explicit reviewable assumption and deterministically prove the selected value reaches the model | `evidence_sources`, `assumptions`, executable `input_provenance` derivations |
| Shipped | `heor-evidence-synthesis` | PICOS screening, extraction, conflict log, applicability, and preservation of app-bound search provenance | `heor/evidence-synthesis.json` plus native and portable deterministic audits |
| Shipped alpha | `heor-evidence-search` | Draft a bounded PubMed/ClinicalTrials.gov metadata request; require exact app-owned human network authorization; verify and losslessly import immutable candidates | `heor/evidence-search-request.json`, app-written `heor/evidence-search-runs/*.json`, app-owned authorization log, and hash-bound synthesis import |
| Shipped alpha | `heor-local-evidence` | Verify and deterministically search app-indexed local PDF/text sources with exact path, page, and SHA-256 citations | `heor/library/*`, `heor/evidence-library.json`, and app-owned `.openscience/heor-library.sqlite` |
| Shipped | `heor-model-design` | Decision problem, conceptual model, structural alternatives | `heor/conceptual-model.json` plus app-owned gate audit |
| Shipped | `heor-cohort-state-transition` | Bounded static and model-cycle-dependent cohort transition structure | Complete transition matrix or schedule in `heor/analysis-plan.json` |
| Shipped | `heor-transition-rate-adapter` | Constant competing event rates with exact evidence binding and recomputation | Schema `0.5.0` transition derivation |
| Shipped | `heor-survival-curve-adapter` | Already-selected two-state exponential or Weibull curve evaluation | Schema `0.6.0` transition schedule derivation |
| Shipped alpha | `heor-survival-extrapolation-review` | One or more independently reviewed pre-specified standard parametric fit comparisons, exact plan-target/selected-family match, observed/extrapolated diagnostics, local execution hashes, structural alternatives, native audit, and an awaiting-Human selection boundary | Schema `0.2.0` single review or ordered schema `0.1.0` multi-review manifest; exact all-file hash-bound plan approval; optional isolated `survHE` execution and cross-curve PFS/OS consistency remain unshipped |
| Shipped | `heor-probability-time-adapter` | Single-event probability time conversion under an explicit constant-hazard assumption | Schema `0.7.0` transition derivation |
| Shipped | `heor-background-mortality` | Age-aligned annual life-table mortality plus one constant additive excess rate, with explicit exchangeability and double-counting bases | Schema `0.9.0` transition schedule derivation |
| Shipped | `heor-relative-effect-adapter` | Apply one aligned RR or OR to cycle-specific baseline risks with exact review bases and full schedule recomputation | Schema `0.10.0` transition schedule derivation |
| Shipped | `heor-hazard-ratio-adapter` | Apply one reviewed constant HR to cycle-aligned baseline cumulative-hazard increments with explicit proportional-hazards, effect-duration, and switching review bases | Schema `0.11.0` transition schedule derivation |
| Shipped alpha | `heor-treatment-effect-duration` | Preserve source PFS/OS through an explicit evidence horizon, then derive sustained, immediate-stop, and log-linear-waning intervention tails from comparator hazard increments without inferring duration from an HR point estimate | `heor/treatment-effect-duration.json`, PSM schema `0.4.0`, scenario cost/QALY summaries |
| Shipped | `heor-reference-case` | Versioned jurisdiction requirements, exact profile/assessment hashes, and fail-closed gap assessment | `heor/reference-case-assessment.json` plus app-owned approval/run audit |
| Shipped | `heor-uncertainty-analysis` | Hash-bound DSA, seeded PSA, CEAC/CEAF, per-person EVPI, convergence diagnostics, dependence disclosure, and structural scenarios | `heor/uncertainty-plan.json` plus deterministic run output |
| Shipped | `heor-budget-impact` | Three-year payer population, uptake, itemized cost, one-way sensitivity, and alternative-scenario analysis | `heor/budget-impact-plan.json` plus deterministic run output |
| Shipped | `heor-model-validation` | Intended-use validation package covering face, input, external, cross-model, predictive, and TECH-VER checks without a score | `heor/model-validation.json`, local evidence, and app-owned independent-review gate |
| Shipped | `heor-reporting` | Separate CHEERS 2022 and ISPOR BIA reporting, exact result summaries, disclosures, and release preparation without checklist scoring | `heor/report-package.json`, `heor/report.md`, app-written results, and app-owned release gate |

`heor-workbench` routes to these skills; it should not absorb their detailed
methodology. This avoids a single prompt becoming an untestable source of truth.

## Industrialization pipeline

```text
discover -> license and threat audit -> pin source -> isolate -> normalize
        -> provenance adapter -> deterministic tests -> cross-platform tests
        -> human methods review -> limited pilot -> release inventory
```

Every adopted asset gets:

- an upstream revision and license record;
- a delta document explaining what AI4HEOR changed and why;
- contract, regression, adversarial, and golden-reference tests;
- a capability/egress manifest;
- an update policy and a kill switch;
- a release status of `experimental`, `validated-adapter`, or `first-party`.

An upstream update never replaces the pinned release automatically. Codex may
prepare and test an update, while the product owner or designated human accepts
the changed capability boundary.

The shipped uncertainty and budget-impact skills illustrate this rule. Existing
public skills and HEOR tools supplied useful terminology and negative cases, but
none was admitted as executable authority. AI4HEOR rewrote the capabilities
around first-party schemas, evidence-linked inputs, bounded deterministic
execution, three validator layers, exact artifact hashes, app-owned approval
bindings, and natural-language repair. The uncertainty slice now internalizes
the useful CEAC/EVPI concepts identified in BCEA and methods guidance without
embedding BCEA, R, or an upstream prompt: the first-party engine derives CEAC,
CEAF, and per-person EVPI from its own seeded PSA, exposes Monte
Carlo error, and leaves population EVPI and EVPPI uncalculated. This derivative
passes the same schema, portable/native audit, regression, adversarial,
report-binding, UI, and packaging gates as other first-party assets. BCEA
remains an optional future adapter for broader validated analyses, not a hidden
runtime dependency.

Schema `0.8.0` extends that admitted first-party asset to 2–16 strategies with
explicit ordering, strict/extended dominance, a complete incremental efficiency
frontier, and multi-strategy net-benefit competition. Uncertainty schema `0.7.0`
adds per-strategy CEAC series, explicit ties, CEAF, and multi-strategy EVPI while
preserving legacy result shapes. The BIA asset remains deliberately pairwise: a
multi-strategy analysis must select two declared IDs for the displaced-comparator
and new-intervention shares rather than pretending the two-share calculator is a
multi-treatment market model.

Schema `0.9.0` industrializes a narrow background-mortality fragment without
copying an upstream prompt or package. The exact first-party contract binds life-
table jurisdiction, year, population, sex, start age, every cycle's attained age
and annual probability, one constant additive excess rate, and the separate
`population_exchangeability` and `no_double_counting` review bases. Python,
Rust, TypeScript, portable provenance, and a standalone Skill validator recompute
`1-exp(-(-ln(1-q_annual)+h_excess)*cycle_length_years)` for any finite positive
cycle length. Paired uncertainty `0.8.0` varies only the exact positive excess
rate and fixes the life table and transformation structure. ISPOR-SMDM warns that
additive and multiplicative disease/background mortality can materially differ;
the unimplemented multiplicative/SMR alternative remains a Human-in-the-loop
structural limitation. Already all-cause endpoints, mixed cause-specific and
subdistribution quantities, calendar improvement, age/sex mixtures, time-varying
excess hazards, competing non-death events, and partitioned survival remain
outside admission.

The BIA slice also rejects method creep:
it stops rather than pretending a two-strategy cost calculator can represent
induced demand, dynamic cohorts, or multi-treatment markets. Optional BCEA,
`hesim`, `heemod`, and `survHE` integrations remain candidates until their
adapters pass the same pipeline; their maturity does not bypass platform
admission.

The schema `0.3.0` input-provenance slice applies the same rule at the evidence
boundary. A selected extraction is no longer sufficient merely because its ID,
target, record, and dual local review match. Direct evidence must be strict JSON
equal to the exact model value; monetary source values must bind to extraction
elements before adjustment arithmetic; explicit assumptions cannot claim
extractions. Transformations that the first-party validator cannot execute are
kept incomplete rather than delegated to an upstream prompt or hidden in prose.

The schema `0.4.0` cohort-transition slice applies the admission rule to mature
Markov-modeling ideas rather than copying `heemod`, `hesim`, or an upstream
prompt. AI4HEOR implements only a first-party, dependency-free piecewise
model-cycle schedule, dynamic provenance paths, complete-row DSA/Dirichlet PSA,
structural change-point scenarios, native/portable/browser audits, a hand-
calculated golden trace, and the dedicated `$heor-cohort-state-transition`
Skill. It explicitly rejects hidden matrix assembly and unsupported rate or hazard conversion,
time-in-state memory, microsimulation, and time-varying rewards. The external R
packages remain isolated future adapters and independent cross-check candidates;
their broader capability and GPL licenses do not enter the MIT core.

Schema `0.5.0` applies the same industrialization rule to a useful but otherwise
unsafe fragment commonly found in spreadsheets, packages, and prompts: converting
constant competing event rates into cycle probabilities. AI4HEOR reimplements the
bounded formula in its dependency-free core, gives every event an extraction or
assumption binding, recomputes it in Python, Rust, the portable validator, and the
browser preview, adds a hand-calculated golden case, exposes a dedicated
`$heor-transition-rate-adapter` Skill, and documents explicit stopping rules.
No upstream code is copied into the core. The same admission process now extends
the fragment with first-party rate-space DSA/PSA: exact event targets, positive
distributions, exact evidence/assumption binding, per-run complete transformation
recomputation, and Python/native/portable regression tests. The next admitted
fragment is schema `0.4.0` evidence-bound lognormal dependence: only 2–32 scalar
lognormal members, a linked latent log-scale correlation matrix, strict positive-
definite validation, deterministic Cholesky sampling, exact result disclosure,
and cross-layer adversarial tests. This is a first-party bounded implementation,
not a copied BCEA/heemod/hesim routine or a matrix inferred by the Agent. General CTMC
conversion, probability-time conversion outside the separately admitted single-event adapter, relative effects outside the dedicated bounded RR/OR adapter, extrapolation,
within-cycle multi-step paths, arbitrary copulas, gamma/uniform correlation,
empirical posterior draws, singular/perfect matrices, and transformation-space
structural scenarios remain isolated future adapters rather than inferred capability.

Schema `0.6.0` industrializes another useful but unsafe fragment: evaluating an
already-selected exponential or Weibull survival curve as a two-state model-cycle
schedule. AI4HEOR does not copy `survHE` or another fitting implementation. It
reimplements only cumulative-hazard evaluation in the dependency-free core,
binds each positive parameter to evidence or a proposed assumption, and
independently recomputes the complete schedule in Python, a standalone Skill,
the portable provenance validator, native Rust, and the browser. Hand-calculated
and adversarial tests cover parameterization, cycle increments, stale schedules,
wrong schemas, invalid sources, unsupported distributions, and state-count
violations. `$heor-survival-curve-adapter` documents the exact boundary.

Uncertainty schemas `0.5.0` and `0.6.0`, with current engine `0.7.0`, industrialize the next bounded
fragment: evidence-bound DSA/PSA for exact exponential rate and Weibull shape or
scale values. Every run replaces parameters on an ephemeral plan and recomputes
the full per-cycle schedule and derivation snapshot before normal validation.
Python calculation, portable Skill validation, and native Rust audit share the
same fail-closed target, positive-distribution, and exact-basis rules, with
seeded and adversarial regression tests. This admits uncertainty propagation
through an already-selected curve, not curve fitting or validation.

The bundled `$heor-survival-extrapolation-review` now admits the audit layer of
survival fitting without making the backend part of the deterministic engine.
Its schema `0.2.0` binds a pre-specified 2–8-family comparison, local data and
execution hashes, package/session versions, visible convergence failures,
common observed/extrapolated landmarks, KM/log-cumulative-hazard/hazard views,
external and clinical plausibility, and structural alternatives. It rejects
automatic selection and leaves the gate `awaiting_human_selection`. The portable
validator and native Rust audit match every exact analysis ID and provenance
target, require each plan-selected distribution to be converged, verify the
current local files, expose single or ordered collection status in the review
pane, and bind all required review hashes into plan approval and run authorization. A user-
installed isolated `survHE` environment remains a future optional execution
backend. The alpha imports only an already-generated local fit bundle and does
not access or fit patient-level data; the current development machine does not
provide or validate the package backend. Multi-curve integrity is admitted, but
PFS/OS, treatment-arm, joint-uncertainty, and partitioned-survival consistency
remain explicitly outside this collection contract.

Automatic model selection, flexible/cure/mixture models, KM/IPD
reconstruction, partitioned survival, treatment effects, broader background mortality,
competing risks, validation of long-term plausibility, and covariance recovery
from incomplete fit output
remain future admission candidates. Mature upstream survival packages can serve
as isolated tools or cross-checks only after their own license, version, data-
egress, reproducibility, audit, and packaging gates pass.

Schema `0.7.0` industrializes probability time conversion without importing a
spreadsheet macro, R package, or upstream prompt. AI4HEOR implements only the
single-event constant-hazard identity, requires probabilities strictly inside
`(0,1)` and explicit source/model intervals, binds each source probability to
one extraction or proposed assumption, and recomputes the complete transition
input in Python, the standalone Skill, the portable validator, native Rust, and
the browser. Uncertainty schema `0.6.0` adds only evidence-bound Beta or bounded
Uniform sampling followed by full recomputation. Adversarial tests reject
simple division, stale matrices, probability 0 or 1, extra events, invalid
intervals, unlinked bases, unbounded distributions, and derived-row mutation.
Competing events, time-varying hazards, relative effects outside the dedicated bounded RR/OR adapter, composite endpoints,
dependence, and clinical-validity judgments remain future methods rather than
inferred capability.

Schema `0.10.0` adds the first-party `$heor-relative-effect-adapter` for one
bounded case: cycle-specific baseline risks for a single absorbing event and one
aligned risk ratio or odds ratio. It requires the exact endpoint-alignment,
population-transportability, and effect-constancy review bases; equal declared
effect and model-cycle intervals; and independent recomputation of every cycle's
complete transition matrix. Paired uncertainty schema `0.9.0` is measure-specific:
RR admits only bounded Uniform PSA below the baseline-risk ceiling, while OR
admits Lognormal or strictly positive bounded Uniform PSA.

This is an independent first-party implementation; no reviewed external Skill or
plugin is an executable dependency. The separately bounded constant-HR route is
owned by `$heor-hazard-ratio-adapter`. The next method assets after the shipped
survival-extrapolation review contract are partitioned survival, treatment-effect duration,
cost normalization, and utility inputs; dynamic-cohort BIA, NMA/MAIC, RWE, and
advanced VOI follow. These backlog items are not shipped capabilities or
approval authority.

Schema `0.11.0` adds the first-party `$heor-hazard-ratio-adapter` for one
absorbing time-to-first event. It applies one positive, reviewed constant HR to
the increment of one selected, cycle-aligned baseline cumulative-hazard curve:
`p=-expm1(-HR*(H0(i)-H0(i-1)))`, with `H0(0)=0`. The contract requires exact
endpoint, population, proportional-hazards, effect-duration, and treatment-
switching review bases. Python, Rust, TypeScript, portable provenance, and the
standalone Skill independently recompute the complete schedule and reject
non-monotone hazards, probability saturation, stale output, time-varying or
non-proportional effects, waning/stopping, unresolved switching, competing or
recurrent events, curve fitting/selection, and partitioned survival.

Uncertainty schema `0.10.0` targets only the HR value and admits a strictly
positive bounded Uniform distribution whose DSA and PSA high bounds reproduce a
finite complete schedule. It deliberately defers unbounded Lognormal support
until an auditable truncated distribution exists. NICE PMG36, DSU TSD14, and
TSD21 provide the method boundary; they do not establish proportional hazards,
transportability, effect duration, or validity for a specific analysis.

The evidence-search slice applies the same standard to a network capability.
The Agent can only draft and validate the request file. Native code rejects
unknown fields, arbitrary URLs, headers, credentials, sensitive egress,
unreviewed byte changes, redirects, oversized/non-JSON responses, symlinked
output paths, and overwrites. A human reviews the exact SHA-256, fixed public
sources, query, dates, and result cap before the app executes it. Results are
metadata candidates with source-response hashes and explicit limitations; they
never become included or appraised evidence automatically. OpenAlex is not in
this alpha because its current API requires a key and therefore needs a
separate credential and consent design.

The validation skill follows the same industrialization rule. AdViSHE and
TECH-VER are valuable methods assets but are not executable authority: AI4HEOR
adapts their reporting and technical domains into a bounded JSON contract,
local hash-matched evidence, portable and native validators, adversarial tests,
and an app-owned human gate. It retains their warning that a checklist neither
guarantees an error-free model nor supports a summary score. The active ISPOR
Model Validation II task force is monitored as work in progress and is not
treated as a published standard.

The reporting capability also adapts rather than directly reuses standards or
public prompts. CHEERS 2022 remains a 28-item reporting checklist for economic
evaluation, never a quality score and never a BIA checklist. ISPOR BIA Good
Practice II is represented by a separate 12-item reporting matrix. AI4HEOR
binds both matrices to exact method, validation, report, and app-written result
bytes; portable and native validators reject copied or stale summaries; the
desktop re-executes all three deterministic engines before a named human can
record release. This is the production derivative admitted to the platform.

The NICE reference-case expansion applies the same rule to methods guidance.
AI4HEOR does not bundle PMG36 or copy its tables. It stores a first-party,
bounded set of paraphrased requirements with exact locators, the official
31 March 2026 PDF URL, byte count, and SHA-256, then adds portable profile
validation and native jurisdiction/perspective/discounting/health-outcome
checks. The profile is explicitly narrower than full NICE submission guidance.
CDA-AMC fourth-edition guidance remains a researched candidate: its content is
available through the official web publication, but Cloudflare prevented a
reproducible raw-source digest in this build environment, so no guessed or
proxy-derived digest was admitted.

## Method sources governing the adaptation

The evidence contract is grounded in requirements for transparent assumptions,
inputs, sources, uncertainty, and reproducibility rather than in existing skill
wording:

- [Chinese Pharmaceutical Association 2020 guideline](https://www.cpa.org.cn/index.php?cid=75553&do=info)
- [Chinese 2026 second-edition consultation notice](https://www.cpa.org.cn/?cid=78857&do=info) and [draft PDF](https://www.cpa.org.cn/cpadmn/attached/file/20260626/1782459582340302.pdf), retained as draft rather than current policy
- [NICE PMG36 economic evaluation](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/)
- [ISPOR Budget Impact Analysis Good Practice II](https://www.ispor.org/heor-resources/good-practices/article/principles-of-good-practice-for-budget-impact-analysis-ii)
- [ISPOR-SMDM model transparency and validation](https://www.ispor.org/publications/journals/value-in-health/abstract/Volume-15--Issue-6/Model-Transparency-and-Validation--A-Report-of-the-ISPOR-SMDM-Modeling-Good-Research-Practices-Task-Force-7)
- [AdViSHE validation-assessment reporting tool](https://pmc.ncbi.nlm.nih.gov/articles/PMC4796331/), adapted as structured reporting rather than a score
- [TECH-VER technical verification checklist](https://pmc.ncbi.nlm.nih.gov/articles/PMC6860463/), adapted into independent technical domains without claiming error-free software
- [ISPOR Model Validation II active task force](https://www.ispor.org/member-groups/task-forces/model-validation-ii-task-force), monitored but not used as current guidance until publication
- [Cochrane Handbook current search and selection chapter](https://training.cochrane.org/handbook/current/chapter-04)
- [PRISMA 2020](https://www.prisma-statement.org/prisma-2020), used as reporting guidance rather than evidence-quality certification
- [CHEERS 2022](https://www.ispor.org/heor-resources/good-practices/cheers), used as reporting guidance rather than a methodological quality score
- [NICE DSU TSD 19 partitioned survival analysis](https://sheffield.ac.uk/sites/default/files/2022-02/TSD19-Partitioned-Survival-Analysis-final-report.pdf), used for the three-state occupancy identity, structural distinction, and limitations of independently modelled endpoints

## Partitioned-survival alpha boundary (2026-07-15)

The bounded partitioned-survival alpha is shipped as a structurally separate
calculation, not a transition-matrix adapter. It accepts only aligned three-state
PFS/OS cycle-boundary curves, binds the exact analysis and curve-review bytes plus
each logical endpoint target and Human-selected converged family, and requires
the exact schema `0.1.0` survival-materialization manifest and schema `0.1.0`
treatment-duration artifact. Each materialized
curve binds a strict typed fit output, admitted exponential-rate or Weibull AFT
parameterization, evaluator version, grid, values, and ordered basis IDs.
The duration artifact covers sustained, immediate-stop, and log-linear-waning
policies for exactly two ordered strategies. It shares endpoint evidence horizons
and HR bases across scenarios, derives post-horizon intervention survival from
comparator hazard increments, and fails closed on crossing or stale hashes. PSM
schema `0.4.0` derives `PFS`, `OS-PFS`, and `1-OS`, and returns cost, QALY, pairwise, and fully
incremental results. Python, the standalone Skill validator, and native Rust
independently re-read review and fit-output bytes, recalculate each admitted
curve, and fail on parameter drift, unsupported parameterizations, increasing
curves, time-grid drift, PFS above OS, stale hashes, missing basis IDs, or invalid
state structure. The analysis-plan Human
gate binds the PSM plan and reviews. Paired uncertainty schema `0.11.0` now
admits only economic-input DSA/PSA and bounded economic scenarios against the
fixed hash-bound curves. It requires explicit PFS/OS omissions and returns a
partial, economic-input-only classification. Survival parameter covariance,
curve alternatives, and joint PFS/OS uncertainty remain outside that fallback.
The first-party `heor-joint-survival-uncertainty` asset and uncertainty schema
`0.12.0` now admit already-generated joint posterior or paired-patient-bootstrap
rows across all strategy PFS/OS curves. The portable/Python/native contracts
bind every source and draw byte, reject independent endpoint sampling and curve
crossing, and consume one whole row per PSA iteration. Joint manifest schema `0.2.0`
binds the duration bytes; non-base duration alternatives remain separate deterministic
scenario results. Curve-family selection, extrapolation, source-model validity, independent
validation, and release reporting remain blocked.
Materialization is not statistical fitting, automatic selection, covariance
recovery, or substantive extrapolation validation. Treatment-effect application is
limited to the explicit first-party duration contract.

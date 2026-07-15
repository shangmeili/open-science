# AI4HEOR Skill and Plugin Strategy

Status: evidence and registry refresh completed 2026-07-15.

## Decision

AI4HEOR should not bundle an external HEOR Agent Skill or MCP server as method
authority. No reviewed candidate currently satisfies the product's combined
requirements for a narrow capability boundary, exact input provenance,
deterministic recomputation, local-first operation, model-provider independence,
Human-in-the-loop authorization, compatible redistribution rights, and tested
macOS/Windows/Linux behavior.

The useful integration pattern is therefore:

```text
natural-language request
  -> first-party workflow Skill
  -> app-owned review and data-egress gate
  -> deterministic first-party engine or isolated optional package adapter
  -> immutable artifacts and run metadata
  -> independent audit and Human acceptance
```

A Skill defines when to act, which artifact to produce, and when to stop. It is
not calculation authority. An MCP server or package adapter exposes a bounded
tool. It is not scientific approval. The desktop owns permissions, hashes,
process isolation, version capture, and the visible Human gate.

## Current external candidates

| Candidate | Evidence observed | Decision for AI4HEOR |
| --- | --- | --- |
| [HEORAgent MCP](https://github.com/neptun2000/heor-agent-mcp) | The strongest directly relevant discovery candidate: MIT, broad HEOR workflow coverage, 48 declared tools, 44 source adapters, and a local project store. On 2026-07-15 Git HEAD `19f5f0eea5764d7a2695c372f3ec8f3aa0f53dd8` contained package `1.27.0`, while npm reported `1.35.0` modified 2026-07-04. A clean install of the pinned Git revision passed 1,521 tests with 6 skipped, but `npm audit` reported 12 dependency vulnerabilities, including 4 high; ts-jest also emitted repeated configuration warnings. Its one server boundary combines network search, local writes, jurisdiction guidance, statistical methods, and economic calculation. | Do not make it core authority or bundle it wholesale. Treat it as a P1 experimental optional connector: pin one npm tarball or commit, resolve the version channel and dependency findings, disable hosted mode and telemetry, expose only separately admitted read/search tools first, wrap every tool with app-owned egress/approval/result schemas, and independently challenge any calculation before promotion. |
| [CaseMark health-economics Skill](https://agentskills.med/skills/conducting-health-economics-research) | Useful HEOR vocabulary and task decomposition, but it mixes model selection, jurisdiction claims, and methods guidance in one prose authority. | Reference only. Split useful ideas into artifact-specific first-party Skills and current primary-source method contracts. |
| [AIPOCH medical-research-skills](https://github.com/aipoch/medical-research-skills) | MIT collection at `7cc568024021a3de07cbeb935691dc72c69bfe28`. Relevant assets include screening, meta-analysis, KM analysis, and market-access writing. The reviewed market-access Skill was draft/generic with unpinned dependencies; the screener emitted automated confidence scores; the KM Skill offered a risky time-unit heuristic; the meta-analysis Skill presented a default DerSimonian-Laird route without an HEOR evidence contract. | Do not bulk-install. Reuse only test scenarios and workflow vocabulary after source-by-source license, method, dependency, and adversarial review. |
| [awesome-rosetta health-economics-eval](https://github.com/xjtulyc/awesome-rosetta-skills/tree/main/skills/17-public-health/health-economics-eval) | MIT repository at `6cffda43d7cd6c07c563e2f2e24a88a615bcf003`. Compact runnable examples, but the reviewed Skill treated fixed discount rates and generic GDP-based thresholds as broadly applicable defaults. | Do not execute as HEOR authority. Preserve only educational examples and negative tests; use versioned jurisdiction profiles and evidence-bound inputs. |
| [ai4s-research/ai4s-skills](https://github.com/ai4s-research/ai4s-skills) | Strong general research decomposition, integrity, writing, and rendering patterns, but not HEOR method contracts. | Keep individually quarantined. Reimplement useful patterns in first-party HEOR artifacts rather than loading the upstream collection at runtime. |
| [Awesome Econ AI Stuff](https://github.com/meleantonio/awesome-econ-ai-stuff) | CC0 economic-research Skill catalog at reviewed HEAD `b959f84cf0f94850d23edd7e5a0ed9dbe470c2c0`. Useful assets cover literature review, R/Stata/Python econometrics, LaTeX tables, visualization, and academic writing, but not pharmacoeconomic decision-model contracts. | Consider individual research-productivity Skills only after script/dependency tests. Reuse no causal or statistical conclusion without an AI4HEOR evidence and method contract. |
| [OpenBioMed](https://github.com/PharMolix/OpenBioMed) and [SciAgent-Skills](https://github.com/jaechang-hits/SciAgent-Skills) | Large biomedical Skill libraries with useful PubMed, clinical-trial, survival-analysis, scientific-writing, and data-retrieval patterns. Their center of gravity is drug discovery, omics, and general biostatistics rather than HEOR decision analysis. | Optional upstream vocabulary and connector discovery only. Admit a narrow data-source adapter or generic research Skill individually; do not bulk-load either catalog into the runtime capability surface. |
| [hesim](https://hesim-dev.github.io/hesim/articles/intro.html) | Mature R simulation across cohort state transition, partitioned survival, and individual continuous-time models. | P1 isolated R adapter and independent cross-check. Require user-installed R, a pinned `renv` lock, exact session metadata, golden cases, and no linking into the deterministic core. |
| [BCEA](https://n8thangreen.github.io/BCEA/) | Mature post-processing for cost-effectiveness uncertainty, CEAC, EVPI, and broader value-of-information work. | P1 isolated uncertainty/VOI adapter. Normalize only explicit simulation inputs and import typed result artifacts; keep current first-party CEAC/CEAF/EVPI as the bounded core. |
| [survHE](https://search.r-project.org/CRAN/refmans/survHE/html/survHE-package.html) | HEOR-specific survival fitting, extrapolation, checking, and PSA. | Highest-priority optional R method adapter. Require a pre-specified model set, diagnostics, observed/extrapolated split, package/session capture, and Human selection; never auto-select a curve. |
| [heemod](https://aphp.github.io/heemod/) | Mature Markov, semi-Markov, time-dependent, sensitivity, and heterogeneity functions. | Optional independent cross-check, not the core engine. Preserve semantic differences and GPL isolation instead of forcing apparent parity. |
| [mcp-stata](https://github.com/tmonk/mcp-stata) | AGPL-3.0-or-later connector at `a2f9c4abc2c7662e73684f8cf954895c6806ea27` with data audit, replication, provenance, causal-inference, power, table, and publication Skills. It requires a licensed local Stata 17+ installation and exposes broad code execution. | P2 user-installed connector only. Do not bundle. If admitted later, restrict workspace and command scope, disable network by default, capture do-files/logs/version, and require explicit execution approval. |
| Locally available Codex life-science, data-analysis, PDF, document, and spreadsheet Skills | Useful during Codex-led development and research: ClinicalTrials.gov, NCBI Entrez/PMC, Jupyter, data quality, reporting, visualization, PDF, and spreadsheet workflows. They are host capabilities, not proven redistributable AI4HEOR runtime assets. | Use as development accelerators where applicable. Independently implement or license any equivalent runtime capability; never create a hidden dependency on the developer's Codex installation. |

The official [Agent Skills specification](https://github.com/agentskills/agentskills)
supports portable instruction packages, but portability does not establish method
quality or trust. MCP integration must follow the official
[security guidance](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices):
tool discovery and invocation remain least-privilege, reviewable, and resistant
to changed or unexpected tool inventories.

## First-party capability inventory

The following platform Skills are already implemented and bundled: orchestration,
input provenance, evidence search, local evidence, evidence synthesis, reference
case assessment, conceptual model design, cohort state transition, constant event
rates, selected absolute survival curves, probability time conversion,
background-plus-excess mortality, RR/OR relative effects, constant HR application,
survival extrapolation review, deterministic survival-curve materialization,
structure-neutral economic inputs, treatment-effect duration, partitioned survival, uncertainty analysis, budget
impact, model validation, and reporting.

The 2026-07-15 live refresh reconfirmed the reviewed external revisions:
HEORAgent Git `19f5f0eea5764d7a2695c372f3ec8f3aa0f53dd8` at repository package `1.27.0` with npm `1.35.0`,
AIPOCH `7cc568024021a3de07cbeb935691dc72c69bfe28`, awesome-rosetta
`6cffda43d7cd6c07c563e2f2e24a88a615bcf003`, ai4s-skills
`32fda1d5201d8cafb443fa9ed63361cf47d4db97`, and mcp-stata
`a2f9c4abc2c7662e73684f8cf954895c6806ea27` / PyPI `3.3.0`. No newly
reviewed external asset displaced the first-party plan. HEORAgent still combines
broad method authority, fixed jurisdiction defaults, network/search, file writes,
and calculation behind one MCP trust boundary, while its repository and npm
version channels remain divergent. mcp-stata is more mature operationally but
remains an AGPL, licensed-Stata, broad-code-execution connector, not a
redistributable HEOR method core.

`heor-survival-fit-execution` now bundles a first-party schema `0.1.0` request,
fixed Python/R runner, portable validator, exact runtime evidence and independent
all-family survival/hazard challenge for a Human-authorized strict local CSV.
Result schema `0.2.0` also hash-binds each converged model's estimation-scale
coefficient vector, full inverse-observed-Hessian covariance, parameter order,
and inverse transforms. Python and native Rust independently reject transform,
dimension, symmetry, positive-definiteness, source-binding, and natural-scale
reproduction drift. These artifacts explicitly cover one absolute curve only
and cannot authorize joint PFS/OS or between-strategy draws.
Disposable Linux validation used R 4.6.1, survHE 2.0.51, flexsurv 2.3.2,
survival 3.8.6, and the public 228-row `survival::lung` data. All eight admitted
families converged, passed independent survival/hazard evaluation, and emitted
audited positive-definite covariance artifacts. This is interface evidence, not
clinical or extrapolation validity.
`heor-survival-extrapolation-review` bundles schema `0.2.0` external import and
schema `0.3.0` first-party execution review artifact, validator, template,
natural-language action, and Human-selection stop
rule. Its native Rust audit matches every plan target and selected
distribution, verifies local evidence hashes, drives single or collection review-pane status,
and binds the exact single review or collection-plus-review hashes into analysis-plan approval and run
authorization. It does not ship an R package environment: `survHE` remains a user-
installed isolated optional backend whose real fitting path requires execution
approval and exact package validation on a machine where it is installed. The
execution slice fits only an authorized local two-column dataset and emits no
copied source data or serialized model object; the review slice never reads or
fits the source itself. Plans with 2–32 targets use the ordered schema
`0.1.0` collection and remain fail-closed unless every independent review is
current. The review collection alone does not infer cross-curve PFS/OS consistency;
the separate partitioned-survival contract performs that check only after each
endpoint is bound to its exact target and Human-selected converged family.

The next assets should be developed in this order. Each row names the Skill, but
shipping also requires its schema, deterministic or isolated execution layer,
portable/native/browser validators, test fixtures, natural-language action, Human
gate, and packaged cross-platform evidence.

| Priority | First-party Skill asset | Narrow responsibility and stop boundary |
| --- | --- | --- |
| Shipped alpha | `heor-survival-fit-execution` | Preflight and run one Human-authorized intercept-only local survHE MLE job from a strict two-column CSV; bind exact source/runtime/output hashes, preserve failures, independently challenge every converged admitted family, and export auditable within-curve estimation-scale covariance. No installation, automatic selection, cross-curve dependence claim, or scientific-validity claim. |
| Shipped alpha | `heor-survival-extrapolation-review` | Validate and natively audit one or an ordered collection of schema `0.2.0` external-import or `0.3.0` first-party-execution survival comparisons, selected plan distributions, landmarks, diagnostics, plausibility, hashes, alternatives, and awaiting-Human gates. Automatic selection and cross-curve validity inference are forbidden. |
| Shipped alpha | `heor-survival-curve-materialization` | Reproduce Human-selected exponential, Weibull, Gompertz, gamma, generalized-gamma, generalized-F, lognormal, or loglogistic curves from exact typed fit-output bytes on the analysis cycle grid. The manifest binds review, family, parameterization, fit output, evaluator, values, and exact ordered basis IDs; the standalone validator and native Rust re-read source bytes and independently recalculate every value. It never fits, transforms backend coefficients, selects a family, infers covariance, or applies treatment effects. |
| Shipped alpha / release integration pending | `heor-economic-inputs`, `heor-partitioned-survival`, `heor-treatment-effect-duration`, `heor-cost-input-normalization`, `heor-utility-inputs`, `heor-event-disutilities`, `heor-uncertainty-analysis`, `heor-joint-survival-uncertainty` | Analysis `0.15.0` / PSM `0.7.0` binds immutable selected-fit curves, duration, annual-cost ingredients, cycle utilities, and event losses. Uncertainty `0.13.0` varies allowlisted cost/utility/event components with Human-supplied latent Gaussian-copula dependence while survival stays fixed; `0.14.0` composes those recalculations with one complete reviewed joint PFS/OS row per iteration. Legacy `0.11.0` / `0.12.0` remains paired with analysis `0.12.0`. Curve-family selection, extrapolation, source-model validity, validation/report integration, probabilistic duration alternatives, non-annual cost structures, and release remain blocked. |
| Shipped alpha | `heor-utility-inputs`, `heor-event-disutilities` | Bind state utilities separately from one-time, recurrent, and continuous-exposure event losses. Stop for unlicensed value sets, double counting, incompatible anchors, unsupported long sequelae, arithmetic drift, or unresolved Human method choices. |
| P1 | `heor-dynamic-budget-impact` | Add incident/prevalent cohorts, treatment displacement, discontinuation, persistence, mortality, capacity constraints, and scenario-specific uptake beyond the current pairwise static BIA. |
| P1 | `heor-network-meta-analysis` | Define a connected evidence network, effect measure, likelihood/link, heterogeneity, inconsistency, and diagnostics; require an isolated validated statistical backend and Human model review. |
| P1 | `heor-population-adjusted-comparison` | Separate MAIC, STC, and ML-NMR feasibility and execution; expose overlap, effective sample size, effect modifiers, and unanchored-identification assumptions. |
| P1 | `heor-rwe-causal-analysis` | Specify target trial, estimand, confounding control, positivity, missingness, sensitivity analyses, and provenance for real-world evidence. Stata/R/Python may be optional execution backends, never implicit authority. |
| P1 | `heor-advanced-value-of-information` | Add population EVPI, EVPPI, EVSI, and expected net benefit of sampling only when population, technology lifetime, implementation, study design, and computation methods are explicit. |
| P0 | `heor-paired-survival-bootstrap` | Accept one explicitly paired patient-level resampling unit, fixed Human-selected endpoint/strategy families, and a declared arm-resampling design; refit all curves within each unchanged replicate and emit complete ordered rows or visible failed replicates. Stop when the data cannot preserve the claimed within-endpoint or between-strategy dependence; never combine independent per-curve covariance draws. |
| P1 | `heor-hta-source-connectors` | Expose individually admitted PubMed, ClinicalTrials.gov, NICE, CDA-AMC, PBAC, G-BA/IQWiG, HAS, ICER, and jurisdiction cost-source queries behind source-specific schemas, caching, egress disclosure, and citation snapshots. An optional HEORAgent adapter may implement a connector only after per-tool admission. |
| P2 | `heor-model-calibration` | Define calibration targets, likelihood or loss, parameter bounds, identifiability, multi-start diagnostics, and held-out validation without silently overwriting evidence inputs. |
| P2 | `heor-semi-markov-microsimulation` | Add tunnel/time-in-state and patient-level history under a distinct model contract, deterministic seeds, trace sampling, and performance limits. Do not stretch the current cohort schedule schema. |
| P2 | `heor-km-reconstruction` | Digitization and individual-patient-data reconstruction with source-image provenance, extraction error, algorithm/version capture, and mandatory visual/statistical review. |
| P2 | `heor-stata-bridge` | Generate and audit workspace-scoped do-files, execute only through an explicitly enabled local connector, and preserve commands, logs, Stata/package versions, data hashes, and failure states. |

## Platform assets that are not Skills

Creating only prompts would leave the highest-risk parts unverifiable. AI4HEOR
also needs these first-class assets:

- versioned jurisdiction reference-case packs and update history;
- licensed-or-link-only utility/value-set metadata and unit-cost source catalogs;
- an isolated R execution host with pinned per-project environments and package
  manifests for `survHE`, `BCEA`, `hesim`, and `heemod`;
- a connector permission manifest covering filesystem scope, network egress,
  credentials, executable commands, timeouts, response caps, and kill switches;
- golden HEOR cases, adversarial cases, cross-engine parity fixtures, and method
  review checklists for every admitted capability;
- a methods watchlist that records current primary guidance, review date, changed
  sections, affected contracts, and required revalidation;
- immutable run manifests containing source hashes, model/provider identity,
  tool/package versions, seeds, exact commands, outputs, limitations, and Human
  decisions.

## Admission sequence

1. Define the exact decision artifact and stop boundary before selecting a tool.
2. Verify license, upstream identity, release channel, dependencies, telemetry,
   network behavior, filesystem scope, and code-execution surface.
3. Pin a revision and build a typed adapter that rejects every unneeded feature.
4. Add canonical, edge, stress, scope-boundary, adversarial, and golden cases.
5. Prove deterministic replay or explicitly quantify stochastic reproducibility.
6. Run security, methods, macOS, Windows, Linux, package, and clean-machine tests.
7. Keep the capability experimental until a Human accepts the exact boundary and
   evidence; retain a kill switch and rollback path.

This sequence deliberately treats an upstream test suite, popularity, a public
repository, or a polished prompt as discovery evidence rather than admission.

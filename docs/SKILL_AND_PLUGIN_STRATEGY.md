# AI4HEOR Skill and Plugin Strategy

Status: evidence refresh completed 2026-07-15.

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
| [HEORAgent MCP](https://github.com/neptun2000/heor-agent-mcp) | Broad HEOR coverage and useful workflow ideas. Git HEAD remained `19f5f0eea5764d7a2695c372f3ec8f3aa0f53dd8`; the repository page described v1.23.0 with 45 tools and 44 sources, while npm reported `1.35.0`, MIT, modified 2026-07-04. This version-channel mismatch is itself an admission blocker. | Keep the audited revision quarantined. Do not run or bundle the broad server. Re-audit individual upstream ideas only; independently implement bounded capabilities behind app-owned gates. |
| [CaseMark health-economics Skill](https://agentskills.med/skills/conducting-health-economics-research) | Useful HEOR vocabulary and task decomposition, but it mixes model selection, jurisdiction claims, and methods guidance in one prose authority. | Reference only. Split useful ideas into artifact-specific first-party Skills and current primary-source method contracts. |
| [AIPOCH medical-research-skills](https://github.com/aipoch/medical-research-skills) | MIT collection at `7cc568024021a3de07cbeb935691dc72c69bfe28`. Relevant assets include screening, meta-analysis, KM analysis, and market-access writing. The reviewed market-access Skill was draft/generic with unpinned dependencies; the screener emitted automated confidence scores; the KM Skill offered a risky time-unit heuristic; the meta-analysis Skill presented a default DerSimonian-Laird route without an HEOR evidence contract. | Do not bulk-install. Reuse only test scenarios and workflow vocabulary after source-by-source license, method, dependency, and adversarial review. |
| [awesome-rosetta health-economics-eval](https://github.com/xjtulyc/awesome-rosetta-skills/tree/main/skills/17-public-health/health-economics-eval) | MIT repository at `6cffda43d7cd6c07c563e2f2e24a88a615bcf003`. Compact runnable examples, but the reviewed Skill treated fixed discount rates and generic GDP-based thresholds as broadly applicable defaults. | Do not execute as HEOR authority. Preserve only educational examples and negative tests; use versioned jurisdiction profiles and evidence-bound inputs. |
| [ai4s-research/ai4s-skills](https://github.com/ai4s-research/ai4s-skills) | Strong general research decomposition, integrity, writing, and rendering patterns, but not HEOR method contracts. | Keep individually quarantined. Reimplement useful patterns in first-party HEOR artifacts rather than loading the upstream collection at runtime. |
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
uncertainty analysis, budget impact, model validation, and reporting.

The next assets should be developed in this order. Each row names the Skill, but
shipping also requires its schema, deterministic or isolated execution layer,
portable/native/browser validators, test fixtures, natural-language action, Human
gate, and packaged cross-platform evidence.

| Priority | First-party Skill asset | Narrow responsibility and stop boundary |
| --- | --- | --- |
| P0 | `heor-survival-extrapolation-review` | Fit and compare a pre-specified survival-model set, separate observed from extrapolated time, expose diagnostics and clinical plausibility review, and generate alternatives. Stop before automatic model selection or scientific approval. Prefer an isolated `survHE` adapter plus an independent audit artifact. |
| P0 | `heor-partitioned-survival` | Build bounded PFS/OS state occupancy only after endpoint, time-origin, curve, crossing, monotonicity, and internal-coherence review. Stop for hidden treatment-effect composition, competing estimands, or incoherent occupancy. |
| P0 | `heor-treatment-effect-duration` | Represent full-duration, stopping, waning, and alternative treatment-effect scenarios explicitly. It owns the cases rejected by the constant-HR and RR/OR adapters and never infers duration from a point estimate. |
| P0 | `heor-cost-input-normalization` | Bind quantity, unit price, currency, price year, inflation index, exchange rate, taxes/discounts, and source jurisdiction before calculating a model-basis cost. Stop for missing units, incompatible price concepts, or unsupported indices. |
| P0 | `heor-utility-inputs` | Bind instrument, value set, population, health state/event, timing, age adjustment, mapping algorithm, and uncertainty. Stop for unlicensed value sets, double-counted disutility, incompatible anchors, or unvalidated mapping. |
| P1 | `heor-dynamic-budget-impact` | Add incident/prevalent cohorts, treatment displacement, discontinuation, persistence, mortality, capacity constraints, and scenario-specific uptake beyond the current pairwise static BIA. |
| P1 | `heor-network-meta-analysis` | Define a connected evidence network, effect measure, likelihood/link, heterogeneity, inconsistency, and diagnostics; require an isolated validated statistical backend and Human model review. |
| P1 | `heor-population-adjusted-comparison` | Separate MAIC, STC, and ML-NMR feasibility and execution; expose overlap, effective sample size, effect modifiers, and unanchored-identification assumptions. |
| P1 | `heor-rwe-causal-analysis` | Specify target trial, estimand, confounding control, positivity, missingness, sensitivity analyses, and provenance for real-world evidence. Stata/R/Python may be optional execution backends, never implicit authority. |
| P1 | `heor-advanced-value-of-information` | Add population EVPI, EVPPI, EVSI, and expected net benefit of sampling only when population, technology lifetime, implementation, study design, and computation methods are explicit. |
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

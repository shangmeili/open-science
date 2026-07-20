# AI4HEOR Skill and Plugin Strategy

Status: evidence and registry refresh completed 2026-07-17.

## Decision

AI4HEOR should not bundle an external HEOR Agent Skill or MCP server as method
authority. No reviewed candidate currently satisfies the product's combined
requirements for a narrow capability boundary, exact input provenance,
deterministic recomputation, local-first operation, model-provider independence,
Human-in-the-loop authorization, compatible redistribution rights, and tested
macOS/Windows/Linux behavior.

The useful integration pattern is therefore:

```text
researcher-defined question and natural-language instruction
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

This is researcher-led assisted work, not Agent-led research. Codex Agent leads
development of the platform; inside the platform, Skills execute bounded tasks
under the researcher's question, method choices, evidence judgments, assumptions,
interpretation, and release authority.

This distinction is also enforced below the Skill layer. Each new project is
seeded with a product-owned researcher-led harness: Skills may help carry out a
researcher-selected plan, but neither a Skill nor the configured runtime may
define the study, silently resolve a scientific choice, or rewrite that policy.

Harness v2 adds bounded capability growth without autonomous self-modification.
`$ai4heor-skill-authoring` turns a natural-language request into an inactive,
bilingual, hash-bound, instruction-only candidate under
`capabilities/candidates/`; its validator rejects active permissions, executable
content, secrets, path escape, symlinks, and unlisted bytes. It does not install
the candidate. `$ai4heor-preference-learning` may propose only a narrow,
non-sensitive work preference supported by at least two independent interactions.
Neither Skill can accept its own output, change core assets, or manufacture an
app-owned review record.

## External source research record (not product options)

| Candidate | Evidence observed | Decision for AI4HEOR |
| --- | --- | --- |
| [HEORAgent MCP](https://github.com/neptun2000/heor-agent-mcp) | Reviewed MIT source with broad HEOR workflow coverage, 48 declared tools, 44 source adapters, and a local project store. On 2026-07-15 Git HEAD `19f5f0eea5764d7a2695c372f3ec8f3aa0f53dd8` contained package `1.27.0`, while npm reported `1.35.0` modified 2026-07-04. A clean install of the pinned Git revision passed 1,521 tests with 6 skipped, but `npm audit` reported 12 dependency vulnerabilities, including 4 high; ts-jest also emitted repeated configuration warnings. Its one server boundary combines network search, local writes, jurisdiction guidance, statistical methods, and economic calculation. | Removed from the product inventory. Relevant HEOR workflows are independently implemented as first-party Skills and fixed-source connectors; do not reactivate or bundle the upstream process. |
| [Paper Search MCP](https://github.com/openags/paper-search-mcp) | Reviewed MIT source at `c8b642183bb725f0a7faec89e58b558df09079d1`; broad cross-source search, full-text, and download functions, with optional Sci-Hub routing. | Removed from the product inventory. The first-party PubMed/ClinicalTrials.gov route is the supported behavior; any additional official source must be independently implemented and reviewed. |
| [BioMCP](https://github.com/genomoncology/biomcp) | Reviewed MIT source at `b586085ac032f079671ede0c08cbf17816183bd3`; current package metadata identifies `biomcp-cli` and `biomcp serve`, while the inherited catalog used stale package/launch values. Its tool surface spans many biomedical sources, credentials, and entities. | Removed from the HEOR product inventory. Trial and literature needs use first-party evidence Skills; any new HEOR-specific source starts as an independent implementation. |
| [CaseMark health-economics Skill](https://agentskills.med/skills/conducting-health-economics-research) | Useful HEOR vocabulary and task decomposition, but it mixes model selection, jurisdiction claims, and methods guidance in one prose authority. | Reference only. Split useful ideas into artifact-specific first-party Skills and current primary-source method contracts. |
| [AIPOCH medical-research-skills](https://github.com/aipoch/medical-research-skills) | MIT collection at `7cc568024021a3de07cbeb935691dc72c69bfe28`. Relevant assets include screening, meta-analysis, KM analysis, and market-access writing. The reviewed market-access Skill was draft/generic with unpinned dependencies; the screener emitted automated confidence scores; the KM Skill offered a risky time-unit heuristic; the meta-analysis Skill presented a default DerSimonian-Laird route without an HEOR evidence contract. | Do not bulk-install. Reuse only test scenarios and workflow vocabulary after source-by-source license, method, dependency, and adversarial review. |
| [awesome-rosetta health-economics-eval](https://github.com/xjtulyc/awesome-rosetta-skills/tree/main/skills/17-public-health/health-economics-eval) | MIT repository at `6cffda43d7cd6c07c563e2f2e24a88a615bcf003`. Compact runnable examples, but the reviewed Skill treated fixed discount rates and generic GDP-based thresholds as broadly applicable defaults. | Do not execute as HEOR authority. Preserve only educational examples and negative tests; use versioned jurisdiction profiles and evidence-bound inputs. |
| [ai4s-research/ai4s-skills](https://github.com/ai4s-research/ai4s-skills) | Strong general research decomposition, integrity, writing, and rendering patterns, but not HEOR method contracts. | Removed from the product inventory. Reimplement useful patterns in first-party HEOR artifacts rather than loading the upstream collection at runtime. |
| [Awesome Econ AI Stuff](https://github.com/meleantonio/awesome-econ-ai-stuff) | CC0 economic-research Skill catalog at reviewed HEAD `b959f84cf0f94850d23edd7e5a0ed9dbe470c2c0`. Useful assets cover literature review, R/Stata/Python econometrics, LaTeX tables, visualization, and academic writing, but not pharmacoeconomic decision-model contracts. | Consider individual research-productivity Skills only after script/dependency tests. Reuse no causal or statistical conclusion without an AI4HEOR evidence and method contract. |
| [AER-Skills](https://github.com/brycewang-stanford/AER-skills) | MIT economics-publication stack at reviewed HEAD `78c5fb01f4bb7d0ec5e49dda1c8c6d07349943e5` and release `v1.3.0`. Its strongest reusable patterns are an AEA-style replication package, source/exhibit/claim-evidence ledgers, citation verification, runnable examples, and repository validation; its identification and writing rules are intentionally AER-specific rather than HEOR method contracts. | Do not bundle the publication stack. Independently adapt only the reproducibility and claim-to-artifact patterns into a first-party `heor-reproducibility-package`; keep journal formatting and econometric identification outside the HEOR calculation authority. |
| [K-Dense scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | Large scientific catalog at reviewed HEAD `fc0b9f692459ea7d9e5a5c64948a5878e1bce274`, including database lookup, clinical trials, research methodology, and many package wrappers. The repository is MIT, but it explicitly warns that individual Skill licenses may differ; the catalog also spans broad dependencies, network access, and scientific domains unrelated to HEOR. | Discovery catalog only. Audit one source adapter or generic research workflow at a time, including its own license, scripts, dependencies, egress, and provenance. Never bulk-install it into the app-managed runtime. |
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

A 2026 empirical study of 557 public healthcare Skills found uneven specialized
input coverage and showed that general technical-risk labels do not reliably
capture clinical risk. AI4HEOR therefore keeps domain method review, executable
adversarial tests, and app-owned Human authority as separate admission gates;
popularity, generic quality scores, or Skill-format conformance cannot substitute
for them. See [Xu et al., 2026](https://arxiv.org/abs/2605.02709).

A 2026-07-17 primary-source licensing check also narrowed the HTA connector
backlog. NICE's syndication API requires an approved application, licence, and
API key, with AI use declared in the application; [CDA-AMC's terms of use](https://www.cda-amc.ca/terms-use)
restrict electronic copying/storage outside stated personal research conditions;
and the [Australian Department of Health copyright terms](https://www.health.gov.au/using-our-websites/copyright)
limit unlicensed reuse to own/internal non-commercial use. AI4HEOR therefore
ships a link-only methods watchlist first and does not infer that public web
access grants scraping, caching, AI-processing, or redistribution rights. See
the [NICE API key guide](https://www.nice.org.uk/corporate/ecd10/chapter/using-your-api-key-to-explore-nice-content)
and [NICE application form](https://www.nice.org.uk/reusing-our-content/nice-syndication-api/nice-syndication-api-application-form).

The desktop now exposes one compact method-review queue for current app-audited
paired-bootstrap, NMA, anchored-MAIC, and advanced-VOI results. This is platform
integration, not another Skill: it preserves each method's exact result binding and
private event chain, opens Human forms only for reviewable results, and routes rejected
or blocked work back to the natural-language conversation.

## First-party capability inventory

The inventory is split deliberately between HEOR method assets and the general
research foundation they rely on. A researcher should not need a developer-only
Codex Skill for ordinary project work, and a general writing or visualization
tool must not acquire HEOR method authority.

| General research capability available in the workbench | Shipped implementation | Boundary |
| --- | --- | --- |
| Natural-language project framing and local project context | conversation workspace, `heor-workbench`, `domain-check` | The researcher owns the question, scope, methods, and decisions. Forms record bounded confirmations only. |
| Local knowledge and evidence work | local knowledge base, `heor-local-evidence`, `heor-evidence-search`, `heor-evidence-synthesis`, methods watchlist | Network retrieval is explicit and source-specific; source availability is not evidence truth or reuse permission. |
| Data and computation inspection | notebook surface, `large-file`, `stats-integrity`, app-owned deterministic HEOR engines, optional authorized remote compute | Code and model output remain inspectable; no result becomes accepted merely because it ran successfully. |
| Scientific figures and traceability | `publication-figures`, `traceability-review`, artifact preview | Figures must remain linked to current data/results and preserve adverse, uncertain, and null findings. |
| Conceptual-model diagrams | `heor-model-design`, app-owned layout editor, deterministic SVG and editable GraphML exporter | The exact current conceptual-model JSON supplies all states and transitions; layout edits change coordinates only, and every output remains awaiting Human review. |
| Citations and references | `literature-review`, `citation-formatting`, native deterministic Markdown renderer | The exact validated local library and citation-plan hashes bind every output; missing metadata is reported, third-party CSL style files are not bundled, and the Human checks the target journal. |
| Target-journal submission check | `journal-submission-check`, native deterministic rule evaluator | The researcher supplies the current official guide snapshot and exact rule locators; no guide, checklist, CSL style, or journal template is bundled, and a mechanical pass never becomes a compliance or submission claim. |
| Research reports and reproducibility | `heor-reporting`, source-bound native DOCX/PDF/XLSX renderer, `heor-reproducibility-package`, local artifact previews | The app renders exact current sources and records hashes; XLSX copies audited results without hidden spreadsheet recalculation; structural completeness and replay evidence do not establish scientific validity or external approval. |
| Research presentation generation | `research-presentation` manifest, portable validator, and native deterministic macro-free PPTX renderer | The Agent prepares source-bound content; the app renders it; the Human reviews every slide and owns external-use rights and release. |
| Capability growth | `ai4heor-skill-authoring`, inactive exact-byte draft review, preference-learning proposals | The platform may propose or create bounded Skills, but cannot activate permissions, rewrite methods, or self-approve changes. |

The first-party citation formatter, conceptual-model diagram, `research-presentation`, and `heor-reporting` renderers close the
bibliography, mind-map, PPTX, and HEOR DOCX/PDF/XLSX gaps without bundling excluded or incompatible sources or
depending on the developer's Codex installation. Generic DOCX or XLSX authoring outside
the HEOR report contract, generic CSL XML processing and bibliography-manager integration,
posters, and arbitrary presentation templates remain explicit backlog items
rather than implied capabilities.

The following platform Skills are already implemented and bundled: orchestration,
input provenance, evidence search, local evidence, evidence synthesis, reference
case assessment, methods currency watchlist, conceptual model design, cohort state transition, constant event
rates, selected absolute survival curves, probability time conversion,
background-plus-excess mortality, RR/OR relative effects, constant HR application,
survival extrapolation review, deterministic survival-curve materialization,
structure-neutral economic inputs, treatment-effect duration, partitioned survival,
paired patient-level PFS/OS bootstrap, joint survival uncertainty, uncertainty
analysis, bounded advanced value of information, budget impact, model validation,
reporting, reproducibility packaging, scientific figures, traceability review,
large-file inspection, statistical-integrity review, and source-bound research
presentation generation.

The 2026-07-15 live refresh reconfirmed the reviewed external revisions:
HEORAgent Git `19f5f0eea5764d7a2695c372f3ec8f3aa0f53dd8` at repository package `1.27.0` with npm `1.35.0`,
AIPOCH `7cc568024021a3de07cbeb935691dc72c69bfe28`, awesome-rosetta
`6cffda43d7cd6c07c563e2f2e24a88a615bcf003`, ai4s-skills
`32fda1d5201d8cafb443fa9ed63361cf47d4db97`, Awesome Econ AI Stuff
`b959f84cf0f94850d23edd7e5a0ed9dbe470c2c0`, AER-Skills
`78c5fb01f4bb7d0ec5e49dda1c8c6d07349943e5`, K-Dense scientific-agent-skills
`fc0b9f692459ea7d9e5a5c64948a5878e1bce274`, and mcp-stata
`a2f9c4abc2c7662e73684f8cf954895c6806ea27` / PyPI `3.3.0`. No newly
reviewed external asset displaced the first-party plan. HEORAgent still combines
broad method authority, fixed jurisdiction defaults, network/search, file writes,
and calculation behind one MCP trust boundary, while its repository and npm
version channels remain divergent. mcp-stata is more mature operationally but
remains an AGPL, licensed-Stata, broad-code-execution connector, not a
redistributable HEOR method core.

The 2026-07-17 connector refresh also pinned Paper Search MCP at
`c8b642183bb725f0a7faec89e58b558df09079d1` and BioMCP at
`b586085ac032f079671ede0c08cbf17816183bd3`. Both are now absent from the release
registry and candidate UI; the AI4HEOR default surface contains no third-party
one-click MCP process.

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
| Shipped alpha | `heor-methods-watchlist` | Maintain strict Agent-writable schema `0.2.0` dated source/change records with official HTTPS links, reuse status, optional lawful local snapshot hashes, affected platform contracts, and revalidation preparation. Portable/native audits expose overdue or unresolved work and reject embedded Human disposition fields. The auxiliary desktop control alone records `accept_revalidation` or `dismiss_change` in a private exact-watchlist-bound event chain; it never fetches restricted content, infers rights, rewrites downstream artifacts, or approves a method. |
| Shipped alpha | `heor-survival-fit-execution` | Preflight and run one Human-authorized intercept-only local survHE MLE job from a strict two-column CSV; bind exact source/runtime/output hashes, preserve failures, independently challenge every converged admitted family, and export auditable within-curve estimation-scale covariance. No installation, automatic selection, cross-curve dependence claim, or scientific-validity claim. |
| Shipped alpha | `heor-survival-extrapolation-review` | Validate and natively audit one or an ordered collection of schema `0.2.0` external-import or `0.3.0` first-party-execution survival comparisons, selected plan distributions, landmarks, diagnostics, plausibility, hashes, alternatives, and awaiting-Human gates. Automatic selection and cross-curve validity inference are forbidden. |
| Shipped alpha | `heor-survival-curve-materialization` | Reproduce Human-selected exponential, Weibull, Gompertz, gamma, generalized-gamma, generalized-F, lognormal, or loglogistic curves from exact typed fit-output bytes on the analysis cycle grid. The manifest binds review, family, parameterization, fit output, evaluator, values, and exact ordered basis IDs; the standalone validator and native Rust re-read source bytes and independently recalculate every value. It never fits, transforms backend coefficients, selects a family, infers covariance, or applies treatment effects. |
| Shipped alpha | `heor-paired-survival-bootstrap` | Preflight and run one Human-authorized ordinary case bootstrap over strict pseudonymous patient rows containing paired PFS/OS observations. A fixed PCG32 plan resamples whole rows within independent parallel arms, refits every Human-selected family in each replicate, preserves all failures, and emits candidates only when all rows pass portable and native parameter-to-curve/PFS≤OS checks. The native review pane owns a seven-item accept/reject record and separate hash-chained event log; Agents cannot manufacture that authority. The method preserves within-strategy PFS/OS dependence but explicitly assumes conditional independence between parallel strategies; it does not claim observed between-strategy correlation, validate censoring, select models, or independently refit in Rust. |
| Shipped alpha | `heor-economic-inputs`, `heor-partitioned-survival`, `heor-treatment-effect-duration`, `heor-cost-input-normalization`, `heor-utility-inputs`, `heor-event-disutilities`, `heor-uncertainty-analysis`, `heor-joint-survival-uncertainty` | Analysis `0.15.0` / PSM `0.7.0` binds immutable selected-fit curves, duration, annual-cost ingredients, cycle utilities, and event losses. Uncertainty `0.13.0` varies allowlisted cost/utility/event components with Human-supplied latent Gaussian-copula dependence while survival stays fixed; `0.14.0` composes those recalculations with one complete reviewed joint PFS/OS row per iteration. Joint manifest `0.5.0` requires an exact app-owned Human review binding for paired-bootstrap generation and rechecks its current event-chain state at approval and execution. Validation/report schema `0.2.0` now binds the exact PSM graph, and release replays PSM, uncertainty, and BIA results before Human approval. Legacy uncertainty `0.11.0` / `0.12.0` remains paired with analysis `0.12.0`. Curve-family selection, extrapolation, source-model validity, probabilistic duration alternatives, and non-annual cost structures remain explicit limitations rather than silently inferred validity. |
| Shipped alpha | `heor-utility-inputs`, `heor-event-disutilities` | Bind state utilities separately from one-time, recurrent, and continuous-exposure event losses. Stop for unlicensed value sets, double counting, incompatible anchors, unsupported long sequelae, arithmetic drift, or unresolved Human method choices. |
| Shipped alpha | `heor-dynamic-budget-impact` | Schema `0.2.0` adds a three-year annual-boundary prevalent/incident cohort ledger with scenario-specific uptake and displacement, incident-first start capacity, common mortality, treatment-specific persistence, fixed discontinuation destinations, complete provenance, deterministic Python execution, portable/native audits, flow-ledger UI, and the existing Human analysis/release gates. It remains pairwise and stops for partial cycles, re-initiation, treatment-specific mortality, disease-state migration, combination therapy, more than two treatments, or patient-level history. |
| Shipped alpha | `heor-network-meta-analysis` | Schema `0.1.0` admits one outcome/timepoint, 3–32 treatment nodes, and one independent two-arm randomized contrast per study on log OR/RR/HR, MD, or SMD scales. The researcher selects the nodes, reference, favorable direction, common or common-tau REML random-effects model, and optional descriptive P-scores. A fixed no-install adapter uses an existing isolated `netmeta` library; portable Python and native Rust independently rebuild WLS (conditional on backend tau for random effects), bind the exact source/evidence/adapter/five-output graph, and stop at an app-owned eight-item Human method review. Multi-arm, arm-level, disconnected, Bayesian, NMR/meta-regression, population-adjusted, automatic model/treatment selection, and automatic economic-model use are rejected. |
| Shipped alpha | `heor-population-adjusted-comparison` | Schema `0.1.0` admits one anchored connected two-trial comparison: local pseudonymous IPD for B versus A, aggregate C versus A evidence and target means, independent randomized parallel two-arm trials, and 1–8 Human-selected scale-specific effect modifiers. A dependency-free exponential-tilting engine balances means, reports weights and ESS, estimates log OR or MD effects, and refits every deterministic stratified bootstrap replicate. Portable replay covers calibration, point estimates, and all draws; native Rust independently recomputes calibration and point effects only. The exact seven-artifact graph stops at an app-owned eight-item Human method review. Unanchored MAIC, STC, ML-NMR, larger or disconnected networks, survival, automatic modifier selection, trimming, missing data, and automatic economic-model use remain unshipped. |
| Shipped alpha | `heor-rwe-causal-analysis` | Schema `0.2.0` admits one Human-specified active-comparator new-user target trial over a strict local pseudonymous one-row-per-person cohort, two baseline strategies, one fixed-horizon binary outcome with an explicit observation indicator, a source-cohort ATE risk difference if nobody's outcome were lost, and 1–12 Human-selected baseline treatment-outcome confounders plus an observation-predictor subset. Dependency-free unpenalized Logistic treatment and observation models produce untrimmed stabilized ATE-IPTW×IPOW, follow-up, overlap, separate/combined weight, observed-row ESS, and pre/treatment/combined-SMD diagnostics; every deterministic arm-stratified bootstrap replicate refits both models. Portable replay covers every draw; native Rust independently challenges both point models and diagnostics. The exact six-artifact graph stops at an app-owned eight-item Human method review. Automatic design/variable selection, missing baseline covariates, time-varying censoring/confounding, survival, competing risks, matching, trimming, doubly robust estimators, missing-not-at-random claims, causal-validity claims, and automatic economic-model use remain unshipped. |
| Shipped alpha | `heor-advanced-value-of-information` | Schema `0.1.0` binds a converged uncertainty result, explicit annual affected population/lifetime/discounting, correlation-closed nested-Monte-Carlo EVPPI groups, and one independent Lognormal target with a Human-specified Normal sample-mean study model, delay, candidate sizes, and costs. Python calculates population EVPI, EVPPI, EVSI, and ENBS; portable and native checks bind exact input/replay/result hashes and independently reproduce summaries; an app-owned eight-item Human method review gates research-prioritization use. The standard route is limited to OR/Lognormal uncertainty `0.9.0`, the current fixed-survival component route to `0.13.0`; joint survival, HR/Uniform EVSI, correlated or multi-parameter learning, optimal-design claims, and funding/reimbursement authority remain rejected. |
| P1 | `heor-hta-source-connectors` | Extend the already admitted PubMed/ClinicalTrials.gov route one source at a time. NICE API use requires an approved licence and key; CDA-AMC and PBAC content reuse must follow their source-specific terms. Until a connector has compatible rights, typed egress/cache contracts, and per-tool admission evidence, `heor-methods-watchlist` stores only canonical links and Human checks. An optional HEORAgent adapter may implement a connector only after per-tool admission. |
| Shipped alpha | `heor-reproducibility-package` | Assemble a bounded release companion containing the exact report graph, three deterministic replay recipes, current first-party runtime boundary, input/output hashes, data-availability statement, source/exhibit register, and seven required claim-evidence links. Portable and native audits verify every link; the existing Human release event binds the package without adding another gate. Restricted content is never copied, and structural traceability is never presented as scientific or external reproducibility. |
| Shipped alpha | `heor-model-calibration` | Schema `0.1.0` admits one researcher-defined homogeneous continuous-time cohort natural-history model with 2–6 states, 1–4 bounded unknown directed rates, aggregate state-occupancy targets, more calibration targets than parameters, and at least one target assigned to held-out validation before fitting. A dependency-free uniformization engine uses target-specific standard errors only to scale squared residuals, runs a fixed seven-level tensor grid plus eight-start bounded pattern search, preserves every evaluation and local solution, and reports held-out residuals plus a local finite-difference rank diagnostic. Portable replay regenerates the complete search and diagnostics; native Rust independently challenges the selected point, target predictions, held-out RMSE, and local identifiability. The exact five-artifact graph stops at an app-owned eight-item Human review, and even acceptance cannot update economic-model inputs automatically. Treatment effects, target covariance or likelihood claims, Bayesian/probabilistic calibration, calibrated-parameter uncertainty propagation, microsimulation, time-varying rates, structural calibration, automatic target/bound/fit selection, and automatic downstream use remain excluded. |
| Shipped alpha | `heor-semi-markov-microsimulation` | Schema `0.1.0` admits one closed non-interacting individual state-transition model with 2–8 states, exactly one absorbing death state, 2–4 researcher-defined strategies, 1–3 capped event-entry trackers, non-overlapping time-in-state/history conditions, complete transition rows, state rewards, transition-event costs, deterministic counter-based SplitMix64 draws, common random numbers, 3–20 replicates, sampled traces, and a five-million patient-strategy-cycle cap. Portable Python and native Rust independently replay every patient cycle, aggregate, paired comparison, and trace row. The exact five-artifact graph stops at an app-owned eight-item Human method review. Interactions, open populations, continuous covariates or event scheduling, dynamic treatment, parameter uncertainty, calibration, automatic precision/model/strategy selection, policy claims, and automatic downstream use remain excluded. |
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
- the shipped methods watchlist plus a future licensed update workflow that
  preserves prior revisions and triggers explicit Human revalidation;
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

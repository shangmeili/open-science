# AI4HEOR HEOR Asset and Integration Strategy

Evidence reviewed on 2026-07-14. This is a product decision record, not an
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
| [hesim](https://hesim-dev.github.io/hesim/) | Advanced cohort, individual, partitioned-survival, and semi-Markov simulation | P1 optional R execution/validation adapter | User-installed isolated R environment; pinned lockfile; GPL boundary; capture package/session versions; golden cross-checks; never link into the MIT deterministic core |
| [BCEA](https://n8thangreen.github.io/BCEA/) | PSA post-processing, CEAC, EVPI, and VOI | P1 optional uncertainty adapter | Same R isolation and provenance; standardized input/output artifact contract; parity fixtures |
| [survHE](https://cran.r-project.org/package=survHE) | Survival extrapolation for economic evaluation | P1 optional survival adapter | Pre-specified model set; diagnostics and extrapolation audit; version capture; no automatic model selection without review |
| [heemod](https://pierucci.org/heemod/) | Mature Markov modeling and sensitivity analysis | Reference and optional independent cross-check | GPL isolation; golden cases against the AI4HEOR core; document semantic differences rather than forcing parity |

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
| Shipped | `heor-input-provenance` | Map every model input to evidence or an explicit reviewable assumption | `evidence_sources`, `assumptions`, `input_provenance` |
| Shipped | `heor-evidence-synthesis` | PICOS screening, extraction, conflict log, applicability, and preservation of app-bound search provenance | `heor/evidence-synthesis.json` plus native and portable deterministic audits |
| Shipped alpha | `heor-evidence-search` | Draft a bounded PubMed/ClinicalTrials.gov metadata request; require exact app-owned human network authorization; verify and losslessly import immutable candidates | `heor/evidence-search-request.json`, app-written `heor/evidence-search-runs/*.json`, app-owned authorization log, and hash-bound synthesis import |
| Shipped alpha | `heor-local-evidence` | Verify and deterministically search app-indexed local PDF/text sources with exact path, page, and SHA-256 citations | `heor/library/*`, `heor/evidence-library.json`, and app-owned `.openscience/heor-library.sqlite` |
| Shipped | `heor-model-design` | Decision problem, conceptual model, structural alternatives | `heor/conceptual-model.json` plus app-owned gate audit |
| Shipped | `heor-reference-case` | Versioned jurisdiction requirements, exact profile/assessment hashes, and fail-closed gap assessment | `heor/reference-case-assessment.json` plus app-owned approval/run audit |
| Shipped | `heor-uncertainty-analysis` | Hash-bound DSA, seeded PSA, convergence diagnostics, dependence disclosure, and structural scenarios | `heor/uncertainty-plan.json` plus deterministic run output |
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
bindings, and natural-language repair. The BIA slice also rejects method creep:
it stops rather than pretending a two-strategy cost calculator can represent
induced demand, dynamic cohorts, or multi-treatment markets. Optional BCEA,
`hesim`, `heemod`, and `survHE` integrations remain candidates until their
adapters pass the same pipeline; their maturity does not bypass platform
admission.

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

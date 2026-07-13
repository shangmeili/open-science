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

## Candidate decisions

| Asset | Value | Current decision | Required adaptation |
| --- | --- | --- | --- |
| [HEORAgent MCP](https://github.com/neptun2000/heor-agent-mcp) | Broad HEOR research, literature, screening, evidence-network, HTA, BIA, and dossier tools | P0 research-only pilot after hardening | Pin audited revision; Node MCP provisioner; tool allowlist; set `HEOR_KB_ROOT` inside active project; disable telemetry; disclose and approve each network source; convert outputs to AI4HEOR evidence records; exclude its calculations and tool-set verification states from authority |
| [CaseMark health-economics skill](https://agentskills.med/skills/conducting-health-economics-research) | Useful task decomposition and terminology | Rewrite as first-party skills; do not bundle verbatim | Remove hard-coded jurisdiction rules and universal claims; split by artifact; attach current primary methods sources; add tests and app-owned HITL boundary |
| [awesome-rosetta health-economics-eval](https://github.com/xjtulyc/awesome-rosetta-skills/tree/main/skills/17-public-health/health-economics-eval) | Compact educational outline | Extract scenarios and negative test cases only | Remove generic GDP threshold and free-form Python authority; replace with versioned reference-case profiles and deterministic engines |
| [medical-research-skills](https://github.com/aipoch/medical-research-skills) | Broad adjacent evidence workflows | Audit selected evidence and review tasks only | Reject low-quality generic market-access template; adapt only source-verifiable components behind AI4HEOR contracts |
| [hesim](https://hesim-dev.github.io/hesim/) | Advanced cohort, individual, partitioned-survival, and semi-Markov simulation | P1 optional R execution/validation adapter | User-installed isolated R environment; pinned lockfile; GPL boundary; capture package/session versions; golden cross-checks; never link into the MIT deterministic core |
| [BCEA](https://n8thangreen.github.io/BCEA/) | PSA post-processing, CEAC, EVPI, and VOI | P1 optional uncertainty adapter | Same R isolation and provenance; standardized input/output artifact contract; parity fixtures |
| [survHE](https://cran.r-project.org/package=survHE) | Survival extrapolation for economic evaluation | P1 optional survival adapter | Pre-specified model set; diagnostics and extrapolation audit; version capture; no automatic model selection without review |
| [heemod](https://pierucci.org/heemod/) | Mature Markov modeling and sensitivity analysis | Reference and optional independent cross-check | GPL isolation; golden cases against the AI4HEOR core; document semantic differences rather than forcing parity |

The HEORAgent audit used revision
`19f5f0eea5764d7a2695c372f3ec8f3aa0f53dd8` (`1.27.0`). Its local test suite
passed 1,521 tests with 6 skipped, but installation reported 12 dependency
vulnerabilities, including 4 high severity. This supports continued evaluation,
not immediate bundling. Its default global knowledge root and optional PostHog
telemetry also conflict with AI4HEOR defaults until wrapped.

## First-party skill architecture

Skills stay small and are separated by the artifact they produce or audit.

| Priority | Skill | Primary responsibility | Main artifact |
| --- | --- | --- | --- |
| Shipped | `heor-workbench` | Natural-language orchestration and handoff | `heor/analysis-plan.json` plus conversation |
| Shipped | `heor-input-provenance` | Map every model input to evidence or an explicit reviewable assumption | `evidence_sources`, `assumptions`, `input_provenance` |
| Shipped | `heor-evidence-synthesis` | PICOS search, screening, extraction, conflict log, applicability | `heor/evidence-synthesis.json` plus deterministic audit |
| Shipped | `heor-model-design` | Decision problem, conceptual model, structural alternatives | `heor/conceptual-model.json` plus app-owned gate audit |
| P0 | `heor-reference-case` | Versioned jurisdiction requirements and gap assessment | reference-case compliance matrix |
| P1 | `heor-uncertainty-analysis` | DSA, PSA, scenario and structural uncertainty plans | uncertainty plan and run artifacts |
| P1 | `heor-budget-impact` | Population, uptake, displacement, cost categories, scenarios | BIA plan and deterministic results |
| P1 | `heor-model-validation` | Face, internal, external, cross-model, and code validation | validation report with reviewer boundary |
| P1 | `heor-reporting` | CHEERS-aligned reporting without treating a checklist as quality scoring | traceable report package |

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

## Method sources governing the adaptation

The evidence contract is grounded in requirements for transparent assumptions,
inputs, sources, uncertainty, and reproducibility rather than in existing skill
wording:

- [Chinese Pharmaceutical Association 2020 guideline](https://www.cpa.org.cn/index.php?cid=75553&do=info)
- [Chinese 2026 second-edition consultation draft](https://www.cpa.org.cn/cpadmn/attached/file/20260626/1782459582340302.pdf), retained as draft rather than current policy
- [NICE PMG36 economic evaluation](https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/)
- [ISPOR-SMDM model transparency and validation](https://www.ispor.org/publications/journals/value-in-health/abstract/Volume-15--Issue-6/Model-Transparency-and-Validation--A-Report-of-the-ISPOR-SMDM-Modeling-Good-Research-Practices-Task-Force-7)
- [Cochrane Handbook current search and selection chapter](https://training.cochrane.org/handbook/current/chapter-04)
- [PRISMA 2020](https://www.prisma-statement.org/prisma-2020), used as reporting guidance rather than evidence-quality certification
- [CHEERS 2022](https://www.ispor.org/heor-resources/good-practices/cheers), used as reporting guidance rather than a methodological quality score

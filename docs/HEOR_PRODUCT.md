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

The first complete workflow compares two strategies using a cohort state
transition model and a three-year budget impact analysis. Both deterministic
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
3. Every decision-relevant value must carry a source, unit, jurisdiction, price
   year, selection rationale, and uncertainty status before public beta.
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
structurally complete, the desktop can record an app-owned local human
verification event that binds the exact synthesis SHA-256 and a sorted set of
eligible, non-conflicting extraction IDs. Events form a per-project append-only
SHA-256 chain outside the workspace. Any synthesis-byte change gives it a new
identity, so old verification no longer applies.

The analysis plan now binds the current `heor/evidence-synthesis.json` digest.
Every source-based input mapping must name one or more `extraction_ids`; each
extraction target must exactly equal the model-input path and its record ID must
be a linked evidence-source ID. The native analysis-plan gate requires all
selected IDs to exist in the current structurally complete synthesis and in the
current app-owned verification set, then binds the synthesis digest into the
analysis-plan approval event. Execution, uncertainty, and budget-impact status
repeat the check. Structural validation remains portable, but portable tools
explicitly cannot claim human verification.

This boundary records a local human assertion and detects inconsistent or
partial edits. It does not prove reviewer identity, source truth, duplicate
independent extraction, or resistance to an attacker able to rewrite the whole
local app-data store. OS-backed identity and external anchoring remain future
hardening, not current claims.

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

The registry profiles now contain source-snapshot hashes, source locators,
required/recommended levels, applicability, and app-check identifiers. The
first-party `$heor-reference-case` skill creates
`heor/reference-case-assessment.json`; the plan binds its exact SHA-256. The
desktop independently verifies every requirement, local evidence paths,
automatic plan checks, profile revision/hash/status, and analysis link at both
analysis-plan approval and execution. Required gaps, unresolved items, changed
bytes, and draft profiles fail closed. A complete audit is still only a
prerequisite for human review, not a general compliance certification.
NICE PMG36 and CDA-AMC profiles remain planned registry expansions rather than
implemented options.

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
gamma, lognormal, uniform, and Dirichlet transforms. The current desktop bridge
limits PSA to 10,000 draws because it returns every draw for audit; larger runs
require a future streamed, content-addressed result artifact. The app reports
cost-effectiveness probability and checkpoint Monte Carlo diagnostics, while
keeping the result explicitly separate from independent model validation and
policy recommendation. Rust, Python, and the portable skill validator each
fail closed on unsafe targets, changed hashes, unsupported distributions,
unlinked distribution bases, known omitted correlations, or invalid scenarios.

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

The portable and native validators require exact copied numerical summaries,
explicit disclosures, limitations, a named release owner, and current hashes.
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
- Exploratory, analysis-authorized, independently validated, and locally
  released decision-ready states remain distinct. Any stale package, binding,
  validation, result reproduction, actor, or approval sequence fails closed.
- The core analysis runs without a model provider or network connection.

## Upstream and licensing

The platform baseline is `ai4s-research/open-science` commit
`42c8101ab969011c2205fa1eacb96572ef309c18` and remains subject to its MIT
license. Bundled third-party skills and connectors retain their own licenses and
require a separate release inventory.

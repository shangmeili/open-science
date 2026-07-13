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
transition model and a three-year budget impact analysis. The first vertical
slice implements only the deterministic cohort model.

## Non-negotiable boundaries

1. Language models may draft inputs, explanations, and code, but they do not
   produce the authoritative cost, QALY, ICER, net benefit, or budget result.
2. A run is not decision-ready until the decision problem, independent
   `heor/conceptual-model.json` artifact, hash-bound reference-case assessment,
   executable uncertainty plan, and analysis plan are approved by a human and
   recorded with their current artifact hashes.
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
- Exploratory and analysis-authorized runs are visibly distinct. Validation and
  release remain separate human-controlled states.
- The core analysis runs without a model provider or network connection.

## Upstream and licensing

The platform baseline is `ai4s-research/open-science` commit
`42c8101ab969011c2205fa1eacb96572ef309c18` and remains subject to its MIT
license. Bundled third-party skills and connectors retain their own licenses and
require a separate release inventory.

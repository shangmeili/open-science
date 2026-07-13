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
2. A run is not decision-ready until the decision problem, conceptual model,
   and analysis plan are approved by a human and recorded with artifact hashes.
3. Every decision-relevant value must carry a source, unit, jurisdiction, price
   year, selection rationale, and uncertainty status before public beta.
4. Results must trace to input, engine version, reference-case version, and run
   environment.
5. The MVP accepts public or non-sensitive data only. Patient-level, claims,
   EHR, or other restricted data are out of scope until the security boundary is
   independently reviewed.
6. Current guidance and draft guidance are separate reference-case profiles.
   Draft guidance must never be presented as a binding current requirement.

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

Reference-case files are versioned policy metadata. Their presence does not
claim compliance; compliance requires an explicit, reviewable assessment.
NICE PMG36 and CDA-AMC profiles remain planned registry expansions rather than
implemented options.

## Alpha acceptance

- A hand-checkable golden model matches an independent calculation.
- Invalid transition probabilities, dimensions, utilities, and costs fail
  explicitly.
- Cohort mass remains one within numerical tolerance for every cycle.
- A fixed input yields the same result across supported operating systems.
- Exploratory and analysis-authorized runs are visibly distinct. Validation and
  release remain separate human-controlled states.
- The core analysis runs without a model provider or network connection.

## Upstream and licensing

The platform baseline is `ai4s-research/open-science` commit
`42c8101ab969011c2205fa1eacb96572ef309c18` and remains subject to its MIT
license. Bundled third-party skills and connectors retain their own licenses and
require a separate release inventory.

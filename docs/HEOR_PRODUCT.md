# HEOR Workbench Product Contract

## Purpose

HEOR Workbench is a local-first, model-provider-agnostic desktop workbench for
pharmacoeconomic research. It uses Open Science Desktop as its platform base,
but keeps decision calculations in a deterministic, testable engine rather than
in a language model.

## Accountabilities

- The product owner sets scope and accepts product behavior.
- Codex implements, tests, documents, and packages the software.
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

## Initial reference-case registry

| ID | Status | Use |
| --- | --- | --- |
| `CN-2020-current` | current | Current Chinese pharmacoeconomic guidance |
| `CN-2026-draft` | draft | Gap analysis only until formally issued |
| `NICE-PMG36-2026` | current | NICE technology appraisal analyses |
| `CDA-AMC-4th` | current | Canadian economic evaluations |

Reference-case files are versioned policy metadata. Their presence does not
claim compliance; compliance requires an explicit, reviewable assessment.

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

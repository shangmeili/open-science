# AI4HEOR utility-input method boundary 0.1.0

This contract makes health-state utility construction reproducible; it does not decide which evidence is clinically or methodologically appropriate.

## Required Human decisions

The Human owns the target jurisdiction and population, instrument and version, respondent, value-set or direct-valuation source, mapping acceptability, adjustment method, captured effects, event overlap, and licensing interpretation. The agent may locate, compare, structure, calculate, and flag inconsistencies, but it must not silently select among defensible alternatives.

## Deterministic boundary

One item covers one strategy-state pair. Its source utility is on the `dead = 0, full health = 1` QALY anchor. Only explicit positive multiplicative age, comorbidity, or population-alignment factors may vary that value by cycle. The artifact declares the full cycle-by-state schedule, and validators recompute it from the item ledger. The first cycle must reproduce the aggregate `state_utilities` in analysis schema `0.14.0`.

Acute/recurrent event disutilities, caregiver spillovers, treatment-process effects, time-to-event utilities, utility decrements derived from adverse-event incidence, and component-level DSA/PSA remain outside this version. Their absence must be visible in `excluded_effects`, overlap rationales, uncertainty limitations, and artifact limitations.

## Evidence and reporting checks

- Record instrument name/version/class, respondent, source design, source population, sample size when known, and assessment timing.
- Record value origin, value-set identifier and jurisdiction when applicable, preference population, valuation method, anchor, license status, and evidence IDs.
- For mapping, record source and target measures, a stable algorithm identifier, estimation population, internal/external validation status, performance evidence, and license status. Source and target concepts must be sufficiently overlapping for the intended use; that judgment remains Human-owned.
- Record what the health-state utility captures and excludes. Assess overlap before any separate event decrement is introduced.
- Record uncertainty availability even though this alpha runs the reviewed point schedule only.

## Time-sensitive NICE example

Current NICE PMG36 guidance and a future-policy consultation can coexist. In July 2026, NICE's proposed use of the new UK EQ-5D-5L value set is not itself effective guidance. AI4HEOR therefore never hard-codes an EQ-5D descriptive system or value set in its generic engine. The applicable dated reference-case profile and Human decision govern the model.

Primary method sources:

- NICE PMG36, economic evaluation: https://www.nice.org.uk/process/pmg36/chapter/economic-evaluation-2/
- NICE EQ-5D-5L status and consultation: https://www.nice.org/what-nice-does/faqs/the-eq-5d-5l and https://www.nice.org.uk/consultations/3296/13/key-messages
- ISPOR HSU good practices: https://www.ispor.org/publications/journals/value-in-health/abstract/Volume-22--Issue-3/Identification--Review--and-Use-of-Health-State-Utilities-in-Cost-Effectiveness-Models--An-ISPOR-Good-Practices-for-Outcomes-Research-Task-Force-Report
- ISPOR mapping good practices: https://www.ispor.org/docs/default-source/publications/newsletter/mapping-estimate-health-state-utility-non-preference-outcome-measures-guidelines.pdf
- EuroQol value sets and registration: https://euroqol.org/faq/value-sets/ and https://registration.euroqol.org/

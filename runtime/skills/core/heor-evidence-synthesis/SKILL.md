---
name: heor-evidence-synthesis
description: Create and audit reproducible HEOR evidence searches, eligibility criteria, deduplication, screening decisions, structured extraction, applicability assessments, and conflict logs. Use when a pharmacoeconomic question needs clinical effectiveness, resource use, costs, utilities, epidemiology, treatment pathways, comparators, or other evidence synthesized into heor/evidence-synthesis.json before model-input selection.
---

# HEOR Evidence Synthesis

Create a transparent evidence trail, not a citation list or an autonomous systematic-review claim. Read `references/evidence-synthesis.md` before creating or changing the artifact.

## Workflow

1. Read the decision question and any existing `heor/evidence-synthesis.json`; preserve valid researcher-authored records and decisions.
2. Define PICOS plus explicit inclusion and exclusion criteria before searching.
3. Search appropriate authoritative and bibliographic sources. Record the exact source, query, search date, and result count for every search.
4. Deduplicate records without discarding their source-search links.
5. Record title/abstract and full-text decisions separately. Keep excluded full-text records with a specific reason.
6. Extract only values and claims directly supported by included records. Record location, unit, population, follow-up, applicability, and uncertainty when relevant.
7. Record conflicting evidence explicitly. Do not silently select a convenient estimate.
8. Write `heor/evidence-synthesis.json` from `assets/evidence-synthesis.template.json`, then run `scripts/validate_evidence_synthesis.py` against it.
9. Summarize coverage, unresolved conflicts, limitations, and candidate source IDs for `$heor-input-provenance`.

## Boundaries

- Treat PRISMA as reporting guidance, not proof of methodological quality.
- Do not claim dual independent screening, librarian review, risk-of-bias completion, certainty grading, or human verification unless those actions actually occurred and are recorded.
- An agent screening decision is a draft research action. It is not a human approval.
- Keep unavailable full text, translation limitations, inaccessible databases, and search-date limits visible.
- Do not pool effects merely because multiple estimates exist. Statistical synthesis requires a separate prespecified method and deterministic implementation.
- Keep network calls source-specific and disclose them in the conversation. Store artifacts in the active project.

## Handoff

Report the artifact path, search sources and dates, record counts by screening stage, included records, unresolved conflicts, and which extracted values are eligible to enter the input-provenance review. Never promote the synthesis to decision-ready.

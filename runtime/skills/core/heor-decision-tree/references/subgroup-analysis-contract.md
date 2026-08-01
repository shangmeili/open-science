# Decision-tree subgroup-analysis contract

`heor/subgroup-analysis-plan.json` is a bounded deterministic companion to the current schema 0.2 decision tree. It supports descriptive economic heterogeneity across two to twenty explicitly defined populations. It is not an interaction test, a subgroup-discovery procedure, or a treatment-selection rule.

## Population and prespecification

The grouping variable must have a stable ID, researcher-readable label, and an explicit `prespecified` or `post_hoc` status. The listed populations must be mutually exclusive and exhaustive, and their source-bound shares must sum to one. The app cannot authenticate whether a grouping was genuinely prespecified; that assertion remains subject to researcher review.

Every grouping definition and population share requires either a specific evidence extraction or an explicitly declared proposed assumption. Do not infer a population share from sample counts unless the estimand and target-population relationship justify that use.

## Comparable analyses

The overall and subgroup inputs must all use current decision-tree schema 0.2 and preserve the same strategy IDs and names, baseline, economic basis, reference case, time horizon, discount settings, half-cycle setting, and willingness-to-pay threshold. Each subgroup input is a complete decision tree under `heor/subgroups/`; it may differ only through explicitly sourced or proposed subgroup-specific numeric inputs.

All file paths and exact SHA-256 values are binding. Every `source_id` used by the grouping, shares, heterogeneity basis, or subgroup decision trees must resolve to a concrete evidence extraction and its bibliographic record in the bound `heor/evidence-synthesis.json`.

## Deterministic outputs

The engine recalculates each complete subgroup plan, reports cost, QALY and pairwise increments by subgroup, and then calculates population-share-weighted results. It also reports the numeric difference between weighted subgroup results and the separately calculated overall model. A failed consistency check is visible; it is never silently normalized or repaired.

Pairwise differences between subgroup incremental costs, QALYs, and NMB are descriptive contrasts. Their presence does not establish interaction, treatment-effect modification, subgroup validity, or a subgroup-specific policy conclusion.

## Researcher review

The result always remains `awaiting_researcher_review`. Review must cover population definition and overlap, prespecification versus post hoc status, source eligibility, interaction or heterogeneity basis, multiplicity and statistical power, and interpretation or decision use. The deterministic engine does not perform an interaction test, adjust for multiplicity, evaluate equity, or establish transportability.

## Exclusions

This schema does not support data-driven subgroup discovery, recursive partitioning, causal forests, latent classes, continuous effect-modifier modelling, subgroup NMA, subgroup MAIC, IPD regression, patient-level simulation, missing-data imputation, multiplicity adjustment, or automatic economic-model decisions. Use a separately admitted and validated method if any excluded feature is material.

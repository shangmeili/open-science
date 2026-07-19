---
name: heor-reporting
description: Prepare, audit, and revise a release-reviewable HEOR report package that binds economic-evaluation and budget-impact reports to exact model, validation, and deterministic result artifacts. Use for heor/report-package.json, heor/report.md, CHEERS 2022 reporting, budget-impact reporting, CEAC, CEAF, per-person EVPI, result tables, limitations, funding and conflict disclosures, reproducibility appendices, or preparation of the app-owned release gate without claiming methodological quality or creating release approval.
---

# HEOR Reporting

## Workflow

1. Read `references/report-package-contract.md` before creating or changing a package.
   Read `references/report-export-contract.md` before preparing DOCX/PDF export metadata.
2. Require the three app-owned results for the current model: base case or PSM, uncertainty, and budget impact. If any is missing, ask the researcher to run the corresponding deterministic analysis in the review panel; never recreate numerical results in prose or code.
3. Copy `assets/report-package.template.json` to `heor/report-package.json` and `assets/report.template.md` to `heor/report.md` when absent. For linked PSM work, replace the package schema and `bindings` with `assets/psm-report-bindings.template.json`.
4. For non-PSM schema `0.1.0`, bind the report, five method artifacts, and three results. For linked PSM schema `0.2.0`, bind the report, six method artifacts, five current PSM inputs, and three results. Preserve the fixed paths and lowercase SHA-256 values.
5. Complete the 28 CHEERS 2022 reporting entries for cost effectiveness. Treat `not_applicable` as an explained reporting state, never as a silent omission or a positive score.
6. Complete the separate 12-item ISPOR BIA reporting matrix. CHEERS 2022 explicitly excludes budget-impact analysis; do not claim CHEERS coverage for BIA.
7. Put a unique `<!-- report-section:SECTION_ID -->` marker in `heor/report.md` for every matrix entry and link each entry to the exact artifact paths supporting it.
8. Copy numerical summaries only from the app-owned release result JSON files. Copy the base-case `economic_basis` exactly before presenting monetary values. For analysis schema `0.8.0`, copy the ordered strategy totals without occupancy traces, the pairwise-vs-baseline results, complete fully incremental frontier, and primary-threshold optimum; do not collapse them into one pairwise ICER. When `decision_uncertainty` exists, copy the complete object exactly, including the threshold grid, all-strategy CEAC/CEAF probabilities, tie probabilities, per-person EVPI and Monte Carlo error, and explicit null population EVPI/EVPPI. A separate advanced-VOI result/replay is a research-prioritization artifact and is not added to the release report graph unless a later report schema explicitly admits it. For a legacy result without the multi-strategy objects, retain the legacy summary shape rather than inventing it. Keep cost-effectiveness, uncertainty, advanced-VOI, and budget-impact conclusions separate.
9. For analysis `0.9.0`, report the life-table jurisdiction, year, population, sex, start age, attained-age rule, annual-probability-to-cycle formula, constant excess-rate basis, and exact `population_exchangeability` and `no_double_counting` bases. State that those bases are not approvals. Disclose that uncertainty `0.8.0` holds the life table fixed and varies only the excess rate, and that an untested multiplicative/SMR structure remains a Human-in-the-loop limitation.
10. For analysis `0.10.0`, report every baseline cycle risk, RR or OR measure and basis, effect interval, exact arithmetic, and the `endpoint_alignment`, `population_transportability`, and `effect_constancy_over_cycles` bases without treating them as approvals. Disclose that uncertainty `0.9.0` varies only the relative effect with measure-specific support, and that HR, waning, competing risks, and unsupported extrapolation remain limitations.
11. For analysis `0.11.0`, report every baseline cumulative hazard, its increment, the HR and basis, exact arithmetic, and all five endpoint, population, proportional-hazards, effect-duration, and switching review bases without treating them as approvals. Disclose that uncertainty `0.10.0` varies only the HR with bounded Uniform support and that time-varying effects, waning/stopping, unresolved switching, competing/recurrent events, fitting/selection, and partitioned survival remain limitations.
12. For partitioned-survival analysis `0.12.0` with PSM `0.4.0`, report source curves, evidence horizon, HR basis, duration scenarios, and alternatives outside the PSA. For current analysis `0.15.0` / PSM `0.7.0`, also report cost, utility, event, and applicable joint-survival hashes; raw ingredients and rebuilt aggregates; overlap exclusions; and Human-owned method choices. Preserve the exact `0.13.0` fixed-survival or `0.14.0` composed classification/scope. For `0.14.0`, state that each PSA row combines joint curves and components while curve choice, extrapolation, source-model validity, and duration alternatives remain outside. Never present either as complete structural uncertainty or a release-ready PSM PSA.
13. Disclose funding, conflicts, Agent contributions, model providers, data/model availability, and patient/public involvement. Never infer a missing disclosure.
14. Copy `release_owner_label` only from an explicit human instruction. Do not invent an owner, create an approval event, or call a package released.
15. Run `python3 scripts/validate_report_package.py WORKSPACE/heor/report-package.json WORKSPACE`. Treat `valid` as structural reporting readiness, not methodological quality, policy endorsement, or release.
16. When the researcher asks for report files, confirm the document title, optional subtitle, audience, purpose, language, and date in the conversation. Copy `assets/report-export.template.json` to `deliverables/heor-report-export.json`, bind the exact current report-package and report-document SHA-256 values, keep `style` as `ai4heor-formal-report`, and keep `human_review.status` as `awaiting_human_review`. Ask the desktop app to generate the DOCX/PDF pair; do not write substitute DOCX/PDF files or turn generation into approval.
17. Use `$heor-reproducibility-package` to derive and audit the current release companion after the report package is complete. Do not copy restricted source content, add unrelated files, claim external reproducibility, or create another approval gate.
18. For dynamic BIA schema `0.2.0`, report the declared annual event order plus delivered and unmet starts, deaths, discontinuation destinations, opening/closing stocks, and the full-year costing limitation from the app-written flow ledger. Never reinterpret those expected counts as observed patient flow.
19. Ask the named human release owner to inspect both packages and use the desktop release control.

## Boundaries

- Do not score CHEERS or use item counts to claim study quality.
- Do not apply CHEERS to the BIA; use the separate BIA matrix.
- Do not edit files under `heor/results/`; they are written by deterministic app execution.
- Do not hand-edit or silently overwrite app-generated DOCX, PDF, or report-export audit files.
- Do not hide negative, dominated, uncertain, or unaffordable results.
- Do not turn a cost-effectiveness result into a reimbursement recommendation.
- Do not describe CEAC or CEAF as a policy recommendation. Do not extrapolate per-person EVPI to a population or infer EVPPI, EVSI, research priority, optimal study design, or funding value from the base uncertainty result. If a separate advanced-VOI artifact exists, report it only under its own conditional scope and Human method-review status.
- Do not omit limitations, unresolved uncertainty, funding, conflicts, or Agent involvement.
- Do not claim identity, independent validation, regulatory acceptance, or release readiness beyond the app's local human-assertion boundary.

## Handoff

Report the package ID and hash, report-document hash, all model/result bindings, matrix gaps, CEAC/CEAF threshold coverage, primary-threshold per-person EVPI and Monte Carlo error, disclosures, limitations, release owner, reproducibility-companion status, and exact next human action. State that the app verifies structure, hashes, deterministic result reproduction, reporting coverage, and local approval state—not scientific truth, population value of information, journal acceptance, external reproducibility, or policy suitability.

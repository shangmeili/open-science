---
name: heor-input-provenance
description: Audit and repair traceability between decision-relevant HEOR model inputs, evidence sources, analyst assumptions, units, jurisdictions, price years, selection rationales, and uncertainty. Use when creating or reviewing heor/analysis-plan.json, researching model inputs, resolving unsupported parameters, preparing the analysis-plan human gate, or adapting external HEOR tools and skills for AI4HEOR.
---

# HEOR Input Provenance

Make every decision-relevant numeric or structural input reviewable without turning the agent into an approver. Read `references/input-provenance.md` before changing an analysis plan.

## Workflow

1. Read the current `heor/analysis-plan.json`; do not replace valid evidence or researcher-authored metadata.
2. Enumerate the required input paths for the current deterministic model. Include willingness-to-pay only when it is not null.
3. Inspect each evidence source. Prefer source IDs and extraction records from `heor/evidence-synthesis.json` when that artifact exists. Record stable identifiers, source type, locator, access date, and a content hash for a local snapshot.
4. When any input uses evidence, bind `evidence_synthesis.path` to `heor/evidence-synthesis.json` and `content_sha256` to its exact current bytes.
5. Use approvable portable analysis-plan schema `0.3.0` through `0.12.0`. For schemas `0.8.0` through `0.12.0`, enumerate every declared strategy and map every required input. Schema `0.12.0` is the partitioned-survival economic-input contract: map common settings, state costs, and state utilities, but never initial distributions or transitions. Schema `0.9.0` adds only background mortality, schema `0.10.0` adds only bounded RR/OR relative-effect application, and schema `0.11.0` adds only bounded constant-HR application. Map every source-based path to exact source and extraction IDs and require strict-JSON extracted values.
6. Add `derivation.method` and an exact `derivation.model_value` snapshot to every mapping. Use deterministic transformation Skills only for their admitted contracts. For relative effect, bind every baseline cycle probability, the RR or OR, and exact `endpoint_alignment`, `population_transportability`, and `effect_constancy_over_cycles` review bases; independently recompute the complete schedule. Review bases are evidence or proposed assumptions, never approval state. Do not use a free-form formula as executable evidence.
7. Require every extraction target to equal the input path and its `record_id` to be one of that mapping's source IDs. Use an explicit analyst assumption with status `proposed` only when evidence does not support the value.
8. Declare one root `economic_basis` currency and price year. For every monetary mapping, record the model basis and one `monetary_adjustments` item per scalar or array element. Preserve the source value, source extraction and optional array index, source currency, source price year, positive composite factor, method, and evidence or proposed-assumption basis IDs. Require both the extraction-to-source equality and recorded multiplication to reproduce the exact model input.
9. Use factor `1`, method `none`, and no adjustment basis IDs only when the source and model bases are identical. Otherwise cite the inflation index, exchange-rate date/source, unit conversion, or proposed assumption. Never fetch or invent a rate silently.
10. Keep missing facts or non-executable transformations as `unresolved`. Never convert uncertainty into a sourced value, mark an assumption accepted, or create an approval.
11. Run `scripts/validate_input_provenance.py heor/analysis-plan.json heor/evidence-synthesis.json`. Treat success as portable structural readiness only; the app separately repeats the derivation audit and requires two distinct local reviewer confirmations with no rejection for every selected extraction.
12. Report unsupported inputs, incomplete source metadata, derivation failures, conflicts, unresolved assumptions, monetary transformations, pending or rejected selections, and whether the plan is ready for app-owned human review.

## Operating boundary

- Prefer primary HTA, regulator, guideline, trial, registry, official price, and peer-reviewed methods sources.
- Do not infer a value from a citation that does not directly support it.
- Do not hide a conversion, pooling choice, matrix assembly, probability conversion, or other transformation inside `selection_rationale`. If the first-party validator cannot execute it, keep the mapping incomplete.
- Preserve conflicts and explain why a source was selected; do not silently choose the most convenient value.
- A `proposed` assumption is only ready to be reviewed. Human acceptance exists only in the app-owned approval event.
- For background mortality, stop rather than coerce already all-cause mortality; mixed cause-specific/subdistribution quantities; calendar improvement; age/sex mixtures; time-varying excess mortality; competing non-death events; or partitioned-survival structure.
- For relative effect, stop for HR, rate ratio, risk difference, incompatible endpoint/estimand/time interval, all-zero baseline, competing or recurrent events, non-absorbing events, effect waning, unsupported extrapolation, or any RR support that can produce probability 1 or greater.
- Never copy `verified_by` or `human_checked` from the synthesis into the plan as proof. Only AI4HEOR can establish that a selected extraction ID has two distinct local-label confirmations and no rejection against the exact current synthesis hash.
- Evidence completeness permits human review; it does not establish model validity, reference-case compliance, decision readiness, or release approval.
- External HEOR skills, plugins, MCP tools, and R packages must emit this provenance contract before their outputs can enter an approvable AI4HEOR plan.
- Do not automate currency or inflation conversion without an explicit researcher-authorized data source and date. The portable and app audits verify declared arithmetic and links; they do not certify that an index or exchange rate is substantively appropriate.

## Handoff

After editing, summarize the number of required and covered inputs, selected extraction IDs, evidence sources used, every unresolved assumption, and exact remaining gaps. Tell the researcher which selections still need app review. Keep natural-language conversation primary; do not ask the researcher to edit JSON unless requested.

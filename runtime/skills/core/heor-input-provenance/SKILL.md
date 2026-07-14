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
5. Map every source-based path to one or more evidence source IDs and `extraction_ids`. Require every extraction target to equal the input path and its `record_id` to be one of that mapping's source IDs. Use an explicit analyst assumption with status `proposed` only when evidence does not support the value.
6. Record unit, jurisdiction, selection rationale, uncertainty status, and price year for monetary inputs.
7. Keep missing facts as `unresolved`. Never convert uncertainty into a sourced value, mark an assumption accepted, or create an approval.
8. Run `scripts/validate_input_provenance.py heor/analysis-plan.json heor/evidence-synthesis.json`. Treat success as portable structural readiness only; the app separately requires two distinct local reviewer confirmations and no rejection for every selected extraction.
9. Report unsupported inputs, incomplete source metadata, conflicts, unresolved assumptions, pending or rejected selections, and whether the plan is ready for app-owned human review.

## Operating boundary

- Prefer primary HTA, regulator, guideline, trial, registry, official price, and peer-reviewed methods sources.
- Do not infer a value from a citation that does not directly support it.
- Preserve conflicts and explain why a source was selected; do not silently choose the most convenient value.
- A `proposed` assumption is only ready to be reviewed. Human acceptance exists only in the app-owned approval event.
- Never copy `verified_by` or `human_checked` from the synthesis into the plan as proof. Only AI4HEOR can establish that a selected extraction ID has two distinct local-label confirmations and no rejection against the exact current synthesis hash.
- Evidence completeness permits human review; it does not establish model validity, reference-case compliance, decision readiness, or release approval.
- External HEOR skills, plugins, MCP tools, and R packages must emit this provenance contract before their outputs can enter an approvable AI4HEOR plan.

## Handoff

After editing, summarize the number of required and covered inputs, selected extraction IDs, evidence sources used, every unresolved assumption, and exact remaining gaps. Tell the researcher which selections still need app review. Keep natural-language conversation primary; do not ask the researcher to edit JSON unless requested.

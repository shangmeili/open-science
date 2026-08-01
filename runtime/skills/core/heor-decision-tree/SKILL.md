---
name: heor-decision-tree
description: Prepare, validate, execute, replay, and explain AI4HEOR deterministic short-horizon decision-tree cost-effectiveness analyses with source-bound branch probabilities, terminal costs, terminal QALYs, incremental results, and calculation traces. Use when the researcher has selected a finite event-path model for one-year-or-shorter, non-recurring outcomes; when creating or repairing heor/decision-tree-plan.json; or when verifying a decision-tree result without substituting a Markov model or claiming scientific approval.
---

# Deterministic HEOR Decision Tree

Use natural language to define the research question and Human-owned structure. Use the JSON plan only as the exact calculation and review surface.

## Workflow

1. Confirm that the researcher has selected a finite decision tree for mutually exclusive, non-recurring paths within one year. If time dependence, recurrence, patient history, competing repeated events, or longer-term state occupancy matters, return to `$heor-model-design` and select an adequate model instead.
2. Read [references/decision-tree-contract.md](references/decision-tree-contract.md) before creating or changing a plan.
3. Copy [assets/decision-tree-plan.template.json](assets/decision-tree-plan.template.json) to `heor/decision-tree-plan.json` only when no plan exists. Replace every `null` and every template identifier; never retain template numbers or invent clinical, cost, utility, threshold, or reference-case values.
4. Preserve the researcher-selected strategy order and make the first strategy the baseline. Use a chance node for each branching event and a terminal node for each complete path.
5. Bind every branch probability, terminal cost, and terminal QALY to at least one exact `source_id` or declared `proposed` assumption. Never use a retrieved candidate or model suggestion as an accepted input.
6. Keep discount rates at zero, half-cycle correction false, and the time horizon greater than zero and no longer than one year. Do not use this schema for cycles or state occupancy.
7. Validate before execution:

```bash
python <skill-base-directory>/scripts/validate_decision_tree.py \
  --plan heor/decision-tree-plan.json
```

8. Run the current plan through the bundled first-party runner. It atomically writes the hash-bound result to `heor/results/decision-tree.json` and the task runtime records the command. Treat it as calculation-only; the model-generated plan and result do not establish evidence eligibility, model validity, approval, or a policy conclusion.

```bash
python <skill-base-directory>/../heor-workbench/scripts/run_first_party_analysis.py \
  --plan heor/decision-tree-plan.json
```
9. Re-run the validator with `--result` after execution. It recalculates the exact plan and rejects any changed or stale result:

```bash
python <skill-base-directory>/scripts/validate_decision_tree.py \
  --plan heor/decision-tree-plan.json \
  --result heor/results/decision-tree.json
```

10. Report expected cost and QALY by strategy, pairwise increments versus baseline, dominance or ICER interpretation, net monetary benefit only when the researcher supplied a threshold, the fully incremental frontier, every proposed assumption, provenance gaps, and the next Human review decision.

## Boundaries

- Base directory for this skill: the loaded installation directory containing this `SKILL.md`; never assume a source checkout path.
- This bounded schema does not support DSA or PSA, recurrence, state occupancy, cycles, time-dependent events, half-cycle correction, discounting, or a horizon longer than one year.
- Do not transform a Markov or partitioned-survival plan into this schema merely because the calculation is simpler.
- Do not write or edit an app-owned result to make validation pass. Re-execute the exact plan through the deterministic engine.
- Do not create approval events or describe a structurally valid plan as accepted, decision-ready, reimbursement-ready, or independently validated.

## Handoff

State the plan path, analysis ID, strategy and node counts, horizon, threshold status, unresolved sources and assumptions, deterministic replay status, result path, input hash match, and exact Human scientific judgment still required.

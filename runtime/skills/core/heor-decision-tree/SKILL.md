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
4. Record one complete economic basis: three-letter uppercase currency, integer price year, jurisdiction, and analysis perspective. These values remain Human-owned. Never silently convert currencies, adjust prices across years, or infer a jurisdiction or perspective.
5. Preserve the researcher-selected strategy order and make the first strategy the baseline. Use a chance node for each branching event and a terminal node for each complete path.
6. Bind every branch probability, terminal cost, and terminal QALY to at least one exact `source_id` or declared `proposed` assumption. Never use a retrieved candidate or model suggestion as an accepted input.
7. Keep discount rates at zero, half-cycle correction false, and the time horizon greater than zero and no longer than one year. Do not use this schema for cycles or state occupancy.
8. Validate before execution:

```bash
python <skill-base-directory>/scripts/validate_decision_tree.py \
  --plan heor/decision-tree-plan.json
```

9. Run the current plan through the bundled first-party runner. It atomically writes the hash-bound result to `heor/results/decision-tree.json` and the task runtime records the command. Treat it as calculation-only; the model-generated plan and result do not establish evidence eligibility, model validity, approval, or a policy conclusion.

```bash
python <skill-base-directory>/../heor-workbench/scripts/run_first_party_analysis.py \
  --plan heor/decision-tree-plan.json
```
10. Re-run the validator with `--result` after execution. It recalculates the exact plan and rejects any changed or stale result:

```bash
python <skill-base-directory>/scripts/validate_decision_tree.py \
  --plan heor/decision-tree-plan.json \
  --result heor/results/decision-tree.json
```

11. Report the exact economic basis, expected cost and QALY by strategy, pairwise increments versus baseline, dominance or ICER interpretation, net monetary benefit only when the researcher supplied a threshold, the fully incremental frontier, every proposed assumption, provenance gaps, and the next Human review decision.
12. For DSA/PSA, require current decision-tree schema `0.2.0` and a positive researcher-supplied threshold. Copy [assets/decision-tree-uncertainty-plan.template.json](assets/decision-tree-uncertainty-plan.template.json), bind the exact plan SHA-256, and replace every placeholder. Admit only a terminal cost, terminal QALY, or one probability in an explicitly named two-branch chance node together with its explicitly named complement. Never normalize a multi-branch node or infer a complement.
13. Bind every DSA range and PSA distribution to IDs already attached to the targeted decision-tree value. The current contract admits bounded Uniform for any target, Beta for a binary probability, and Gamma or Lognormal for a non-negative terminal cost. QALY uncertainty is bounded Uniform only. Supply a fixed seed, 100–10,000 iterations, at least two increasing convergence checkpoints ending at the iteration count, explicit probability MCSE and drift thresholds no greater than 0.1, an independence rationale, and known omitted uncertainties; do not invent any of them.
14. Run both plans through the first-party runner. It atomically writes `heor/results/decision-tree-uncertainty.json` and preserves every sampled parameter value for replay:

```bash
python <skill-base-directory>/../heor-workbench/scripts/run_first_party_analysis.py \
  --plan heor/decision-tree-plan.json \
  --uncertainty-plan heor/decision-tree-uncertainty-plan.json
```

15. Re-run `scripts/validate_decision_tree_uncertainty.py` with `--plan`, `--uncertainty-plan`, and `--result`. Report DSA low/high results, seeded PSA mean outcomes, unique optimum probabilities and ties separately, the declared convergence diagnostic, distribution bases, independence rationale, and omissions. A passed diagnostic describes Monte Carlo precision for this run; call it represented parameter uncertainty, not complete uncertainty or validation.

## Boundaries

- Base directory for this skill: the loaded installation directory containing this `SKILL.md`; never assume a source checkout path.
- The base calculation does not support recurrence, state occupancy, cycles, time-dependent events, half-cycle correction, discounting, or a horizon longer than one year. Its companion DSA/PSA contract varies only declared binary probabilities, terminal costs, and terminal QALYs; structural uncertainty stays outside the calculation.
- Schema `0.1.0` is retained only for deterministic replay of existing work. Its monetary results have no declared economic basis, are exploratory, and must not be used for formal reporting.
- Do not transform a Markov or partitioned-survival plan into this schema merely because the calculation is simpler.
- Do not write or edit an app-owned result to make validation pass. Re-execute the exact plan through the deterministic engine.
- Do not create approval events or describe a structurally valid plan as accepted, decision-ready, reimbursement-ready, or independently validated.

## Handoff

State the plan path, analysis ID, strategy and node counts, horizon, threshold status, unresolved sources and assumptions, deterministic replay status, result path, input hash match, and exact Human scientific judgment still required.

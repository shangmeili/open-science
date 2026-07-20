---
name: heor-semi-markov-microsimulation
description: Prepare, execute, fully replay, and explain one bounded discrete-time individual-level state-transition cost-utility microsimulation with researcher-defined time-in-state rules, capped event-history trackers, transition costs, deterministic counter-based random numbers, common random numbers across strategies, sampled patient traces, Monte Carlo error summaries, and an app-owned Human method review. Use when relevant history would cause unmanageable cohort-state expansion. Reject interactions, open populations, continuous-time discrete-event simulation, automatic model or rule selection, parameter uncertainty, calibration, dynamic treatment policies, resource constraints, automatic downstream input replacement, and reimbursement conclusions.
---

# HEOR Semi-Markov Microsimulation

Keep the Human researcher in scientific control. Help express and execute the exact individual-level model they define; never choose states, rules, evidence, strategy effects, rewards, event trackers, seeds, stability criteria, or downstream use.

## Establish the model boundary

1. Read [references/contract.md](references/contract.md). Confirm that relevant time in state or event history would make a cohort model unmanageable and that individuals remain independent in one closed cohort.
2. Stop for interactions, transmission, queues or resource constraints, open populations, continuous-time event scheduling, continuous covariates, dynamic treatment policies, parameter uncertainty, calibration, or automated structural selection.
3. Ask the researcher to define 2–8 mutually exclusive states with one absorbing death state, two to four strategies, one to three capped event trackers, all conditional transition/reward rules, transition costs, evidence, economics, horizon, and limitations.

## Prepare and preflight

Start from [assets/semi-markov-microsimulation-request.template.json](assets/semi-markov-microsimulation-request.template.json), but complete the second strategy rather than treating placeholder arrays as valid. Save the exact request at `heor/semi-markov-microsimulation-request.json` and bind the current evidence-synthesis bytes.

```bash
python scripts/validate_microsimulation_request.py \
  --workspace /absolute/workspace \
  --request heor/semi-markov-microsimulation-request.json
```

Explain validation failures scientifically. Never weaken the contract or invent evidence to make it pass.

## Authorize, execute, and replay

After the researcher authorizes the exact local command, run:

```bash
python scripts/run_microsimulation.py \
  --workspace /absolute/workspace \
  --request heor/semi-markov-microsimulation-request.json
```

The dependency-free runner writes a fresh immutable `heor/semi-markov-microsimulation-runs/<simulation_id>/` directory. Replay the entire patient-cycle calculation and sampled trace:

```bash
python scripts/audit_microsimulation_result.py \
  --workspace /absolute/workspace \
  --result heor/semi-markov-microsimulation-runs/<simulation_id>/manifest.json
```

## Stop at Human method review

Present disaggregated strategy results, paired increments, Monte Carlo standard errors, replicate variation, occupancy, tracker summaries, sampled traces, warnings, and limitations. The desktop owns eight explicit Human checks. Acceptance records only a local assertion about the exact hash-bound candidate; it does not validate the structure, remove first-order noise, propagate parameter uncertainty, select a strategy, update another model, or authorize reimbursement or policy use.

---
name: heor-model-calibration
description: Prepare, execute, replay, and explain one bounded deterministic point calibration of a researcher-defined homogeneous continuous-time cohort natural-history model against aggregate state-occupancy targets. Use when unobservable transition rates need prespecified bounds, target-specific scaled loss, deterministic grid plus multistart search, local identifiability diagnostics, held-out predictive validation, and an app-owned Human method review before any later economic-model use. Reject treatment-effect fitting, target covariance or likelihood claims, Bayesian or probabilistic calibration, microsimulation, time-varying rates, automatic target or parameter selection, automatic fit acceptance, and automatic model-input replacement.
---

# HEOR Model Calibration

Keep the researcher in scientific control. Help articulate and execute the exact calibration they specify; never choose the model structure, parameters, targets, bounds, evidence, acceptance criteria, or downstream use.

## Establish the boundary in conversation

1. Confirm the purpose is point calibration of unobservable natural-history transition rates, not treatment-effect estimation or economic-model optimization.
2. Read [references/contract.md](references/contract.md). Stop or route elsewhere if the question needs target covariance, a likelihood, posterior distributions, parameter-uncertainty propagation, individual simulation, time-varying rates, structural calibration, or treatment comparisons.
3. Ask the researcher to define the population and time origin, 2–6 states, initial occupancy, fixed and calibrated directed rates, 1–4 parameter bounds, and aggregate occupancy targets. Do not infer missing scientific choices.
4. Reserve at least one compatible target for validation before fitting. Require more calibration targets than calibrated parameters.

## Prepare and preflight

Start from [assets/model-calibration-request.template.json](assets/model-calibration-request.template.json). Write the completed request to `heor/model-calibration-request.json`, bind the exact evidence-synthesis bytes, and keep target standard errors described only as target-specific loss scaling because covariance is not modeled.

```bash
python scripts/validate_model_calibration_request.py \
  --workspace /absolute/workspace \
  --request heor/model-calibration-request.json
```

Explain every validation error in scientific terms. Never weaken the contract or fabricate an evidence record to make validation pass.

## Authorize, execute, and replay

After the researcher authorizes the exact local command, run:

```bash
python scripts/run_model_calibration.py \
  --workspace /absolute/workspace \
  --request heor/model-calibration-request.json
```

The dependency-free runner uses a fixed uniformization calculation, seven-level tensor grid, eight deterministic local starts, and bounded pattern search. It writes atomically into a fresh immutable `heor/model-calibration-runs/<calibration_id>/` directory.

Replay the full search and diagnostics independently from the saved result:

```bash
python scripts/audit_model_calibration_result.py \
  --workspace /absolute/workspace \
  --result heor/model-calibration-runs/<calibration_id>/manifest.json
```

## Stop at Human method review

A complete run remains `awaiting_method_review`. Present the selected candidate alongside all local starts, training and held-out residuals, numerical-rank diagnostic, warnings, and limitations. The desktop owns eight explicit Human checks covering the scientific question, target provenance, parameter evidence, loss definition, search, identifiability, held-out validation, and omitted uncertainty/structure.

Human acceptance makes only the exact candidate result eligible for a later, separately governed input-selection workflow. It does not validate the model, prove identifiability, quantify calibrated-parameter uncertainty, approve an economic analysis, or update model inputs automatically.

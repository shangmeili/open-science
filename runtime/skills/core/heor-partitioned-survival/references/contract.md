# AI4HEOR partitioned survival contract 0.2.0

## Calculation boundary

The calculator supports a bounded three-state, forward-only partitioned survival model. At every common cycle boundary `t`:

- `progression_free(t) = PFS(t)`
- `progressed(t) = OS(t) - PFS(t)`
- `dead(t) = 1 - OS(t)`

PFS and OS are independent inputs. The contract does not estimate their joint distribution or construct transition probabilities.

## Required alignment

All PFS and OS curves must match the analysis plan's population, strategy, time origin, cycle length, endpoint definitions, and horizon. Each curve contains `cycles + 1` rows, beginning at time zero. Time is expressed in years and must equal `cycle_index * cycle_length_years`.

Each survival value is finite, from zero to one, and non-increasing. Time-zero PFS and OS both equal one. PFS must not exceed OS at any boundary. No tolerance-based crossing repair is permitted; the numerical tolerance exists only for binary floating-point comparison.

## Provenance and review binding

Every curve value carries the exact ordered review-hash, typed-fit-output-hash, and evaluator basis IDs defined by the survival materialization contract. Each PFS and OS curve also binds a reviewed curve artifact by workspace-relative path and lowercase SHA-256, the exact logical target `partitioned_survival.strategies.<strategy_id>.<endpoint>`, and the Human-selected converged family. The validator reads those exact bytes when `--workspace-root` is supplied and checks the review schema, status, analysis target, endpoint, time origin, and year unit. The desktop audit additionally applies the complete survival-review contract to the bound artifact and its referenced diagnostic inputs.

Schema `0.2.0` requires `heor/survival-curve-materializations.json`. That manifest binds the selected typed fit output, admitted parameterization, evaluator identity/version, time grid, reproduced values, and exact basis IDs. The partitioned-survival validator invokes the dedicated materialization validator, so source-byte, parameter, formula, value, or copied-basis drift fails closed.

This numerical derivation contract is intentionally limited to exponential rate and Weibull AFT shape/scale. It does not fit data, transform backend coefficients, select a family, infer covariance, apply treatment effects, or validate extrapolation plausibility.

The plan binds the exact `heor/analysis-plan.json` bytes and the analysis plan links back to `heor/partitioned-survival-plan.json`.

## Economic calculation

Costs and utilities come from the corresponding analysis-plan strategy in state order. Without half-cycle correction, rewards use start-of-cycle occupancy and discount at the cycle start. With half-cycle correction, rewards use mean start/end occupancy and discount at the midpoint. State rewards are multiplied by cycle length in years.

The current shared analysis schema still requires transition matrices or schedules. The partitioned-survival calculator validates the shared plan but never uses those transition inputs. A future dedicated decision-problem/economic-input contract should remove this irrelevant requirement before release integration.

## Human authority

`ready_for_human_review` means structurally executable, not approved. The AI4HEOR desktop app owns approval, revocation, independent validation, and release authority. Any content field that claims those authorities invalidates the artifact.

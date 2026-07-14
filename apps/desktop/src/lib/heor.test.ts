import { describe, expect, it } from "vitest";
import {
  auditHeorConceptualModel,
  auditHeorEvidence,
  buildHeorPrompt,
  HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL,
  HEOR_BROWSER_DEMO_BUDGET_IMPACT_AUDIT,
  HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT,
  HEOR_BROWSER_DEMO_PLAN,
  HEOR_BROWSER_DEMO_REFERENCE_CASE_AUDIT,
  HEOR_BROWSER_DEMO_UNCERTAINTY_AUDIT,
  HEOR_MODEL_VALIDATION_PATH,
  parseHeorConceptualModel,
  parseHeorPlan,
} from "./heor";

describe("AI4HEOR artifact contract", () => {
  it("parses the browser fixture and preserves review metadata", () => {
    const parsed = parseHeorPlan(JSON.stringify(HEOR_BROWSER_DEMO_PLAN));
    expect(parsed.analysis_id).toBe("first-line-nsclc-demo");
    expect(parsed.decision_problem.population).toContain("NSCLC");
    expect(parsed.assumptions).toHaveLength(1);
  });

  it("rejects a plan without a human-reviewable decision problem", () => {
    const invalid = { ...HEOR_BROWSER_DEMO_PLAN, decision_problem: undefined };
    expect(() => parseHeorPlan(JSON.stringify(invalid))).toThrow(/decision_problem/);
  });

  it("parses explicit multi-strategy order and audits every strategy input", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    const comparator = structuredClone(plan.strategies.comparator);
    const intervention = structuredClone(plan.strategies.intervention);
    plan.schema_version = "0.8.0";
    plan.baseline_strategy_id = "standard_care";
    plan.strategy_order = ["standard_care", "new_treatment", "alternative"];
    plan.strategies = {
      standard_care: { ...comparator, name: "Standard care" },
      new_treatment: { ...intervention, name: "New treatment" },
      alternative: { ...intervention, name: "Alternative treatment" },
    };

    expect(parseHeorPlan(JSON.stringify(plan)).strategy_order).toEqual(plan.strategy_order);
    const audit = auditHeorEvidence(plan);
    expect(audit.requiredInputs).toBe(18);
    expect(audit.unsupportedInputs).toContain("strategies.alternative.state_costs");

    plan.baseline_strategy_id = "new_treatment";
    expect(() => parseHeorPlan(JSON.stringify(plan))).toThrow(/first strategy_order/);
  });

  it("rejects malformed multi-strategy order and exact-key declarations", () => {
    const makePlan = (): Record<string, unknown> => ({
      ...structuredClone(HEOR_BROWSER_DEMO_PLAN),
      schema_version: "0.8.0",
      baseline_strategy_id: "standard_care",
      strategy_order: ["standard_care", "new_treatment"],
      strategies: {
        standard_care: structuredClone(HEOR_BROWSER_DEMO_PLAN.strategies.comparator),
        new_treatment: structuredClone(HEOR_BROWSER_DEMO_PLAN.strategies.intervention),
      },
    });

    const mixedOrder = makePlan();
    mixedOrder.strategy_order = ["standard_care", 42, "new_treatment"];
    expect(() => parseHeorPlan(JSON.stringify(mixedOrder))).toThrow(/unique safe strategy ids/);

    const extraKey = makePlan();
    extraKey.strategies = {
      ...(extraKey.strategies as Record<string, unknown>),
      alternative: structuredClone(HEOR_BROWSER_DEMO_PLAN.strategies.intervention),
    };
    expect(() => parseHeorPlan(JSON.stringify(extraKey))).toThrow(/exactly the ids/);

    const nonObjectStrategy = makePlan();
    (nonObjectStrategy.strategies as Record<string, unknown>).new_treatment = null;
    expect(() => parseHeorPlan(JSON.stringify(nonObjectStrategy))).toThrow(/exactly the ids/);
  });

  it("keeps natural-language intent primary while invoking the domain skill", () => {
    const prompt = buildHeorPrompt("Compare treatment A with standard care.");
    expect(prompt).toContain("Use $heor-workbench");
    expect(prompt).toContain("Compare treatment A with standard care.");
    expect(prompt).toContain("never create or claim human approvals");
  });

  it("fails closed when model inputs lack provenance", () => {
    const audit = auditHeorEvidence(HEOR_BROWSER_DEMO_PLAN);
    expect(audit.complete).toBe(false);
    expect(audit.coveredInputs).toBe(0);
    expect(audit.requiredInputs).toBe(14);
    expect(audit.unresolvedAssumptions).toEqual(["demo-only"]);
  });

  it("requires source-based inputs to bind the synthesis and exact extractions", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.evidence_sources = [{
      id: "trial-1",
      title: "Input study",
      source_type: "randomized_trial",
      url: "https://example.test/trial-1",
      accessed_on: "2026-07-14",
    }];
    plan.input_provenance = [{
      path: "cycles",
      source_ids: ["trial-1"],
      assumption_ids: [],
      unit: "cycles",
      jurisdiction: "China",
      derivation: { method: "direct_evidence", model_value: 3 },
      selection_rationale: "Directly reported follow-up",
      uncertainty_status: "fixed",
    }];
    let audit = auditHeorEvidence(plan);
    expect(audit.invalidMappings[0]).toContain("current evidence synthesis binding");
    expect(audit.invalidMappings[0]).toContain("no selected extraction");

    plan.evidence_synthesis = {
      path: "heor/evidence-synthesis.json",
      content_sha256: "a".repeat(64),
    };
    plan.input_provenance[0].extraction_ids = ["extract-cycles"];
    audit = auditHeorEvidence(plan);
    expect(audit.invalidMappings.join("; ")).not.toContain("current evidence synthesis binding");
    expect(audit.selectedExtractionCount).toBe(1);
  });

  it("fails closed when a monetary adjustment cannot reproduce the model input", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.assumptions = [{
      id: "cost-assumption",
      statement: "Synthetic cost input for audit testing",
      reason: "Browser contract test",
      status: "proposed",
    }];
    plan.input_provenance = [{
      path: "strategies.intervention.state_costs",
      source_ids: [],
      assumption_ids: ["cost-assumption"],
      unit: "CNY per person per cycle by health state",
      jurisdiction: "China",
      currency: "CNY",
      price_year: 2026,
      monetary_adjustments: [4000, 3000, 0].map((value, target_index) => ({
        target_index,
        source_value: target_index === 0 ? value - 1 : value,
        source_currency: "CNY",
        source_price_year: 2026,
        factor: 1,
        method: "none",
        basis_ids: [],
      })),
      derivation: {
        method: "explicit_assumption",
        model_value: [4000, 3000, 0],
      },
      selection_rationale: "Synthetic browser audit fixture",
      uncertainty_status: "fixed",
    }];

    const audit = auditHeorEvidence(plan);

    expect(audit.invalidMappings.join("; ")).toContain("does not reproduce model value");
  });

  it("requires an approvable schema and an exact derivation snapshot for approval review", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.schema_version = "0.2.0";
    plan.assumptions = [{
      id: "cycles-assumption",
      statement: "Use three annual cycles",
      reason: "Browser contract test",
      status: "proposed",
    }];
    plan.input_provenance = [{
      path: "cycles",
      source_ids: [],
      extraction_ids: [],
      assumption_ids: ["cycles-assumption"],
      unit: "cycles",
      jurisdiction: "China",
      derivation: { method: "explicit_assumption", model_value: 4 },
      selection_rationale: "Explicit modeling assumption",
      uncertainty_status: "fixed",
    }];

    const audit = auditHeorEvidence(plan);

    expect(audit.invalidMappings.join("; ")).toContain(
      "schema_version must be 0.3.0 through 0.8.0",
    );
    expect(audit.invalidMappings.join("; ")).toContain(
      "derivation.model_value does not match the current model input",
    );
  });

  it("recomputes a schema 0.5 transition matrix from constant competing rates", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.schema_version = "0.5.0";
    plan.assumptions = [{
      id: "rate-assumption",
      statement: "Use the declared constant annual competing event rates",
      reason: "Browser contract test",
      status: "proposed",
    }];
    plan.input_provenance = [{
      path: "strategies.comparator.transition_matrix",
      source_ids: [],
      extraction_ids: [],
      assumption_ids: ["rate-assumption"],
      unit: "probability per annual model cycle",
      jurisdiction: "China",
      derivation: {
        method: "deterministic_transformation",
        model_value: plan.strategies.comparator.transition_matrix,
        transformation: {
          operation: "constant_competing_rates",
          cycle_length_years: 1,
          phases: [{
            start_cycle: 1,
            rows: [
              {
                self_index: 0,
                events: [
                  { target_index: 1, rate_per_year: 0.23778329595915496, assumption_id: "rate-assumption" },
                  { target_index: 2, rate_per_year: 0.11889164797957748, assumption_id: "rate-assumption" },
                ],
              },
              {
                self_index: 1,
                events: [{ target_index: 2, rate_per_year: 0.35667494393873245, assumption_id: "rate-assumption" }],
              },
              { self_index: 2, events: [] },
            ],
          }],
        },
      },
      selection_rationale: "Exercise deterministic rate conversion",
      uncertainty_status: "fixed",
    }];

    let audit = auditHeorEvidence(plan);
    expect(audit.invalidMappings.join("; ")).not.toContain("constant competing rates");
    expect(parseHeorPlan(JSON.stringify(plan)).schema_version).toBe("0.5.0");

    const transformation = plan.input_provenance[0].derivation.transformation!;
    if (transformation.operation !== "constant_competing_rates") {
      throw new Error("test fixture must use competing rates");
    }
    transformation.phases[0].rows[0].events[0].rate_per_year = 0.3;
    audit = auditHeorEvidence(plan);
    expect(audit.invalidMappings.join("; ")).toContain(
      "constant competing rates do not reproduce the current transition input",
    );
  });

  it("recomputes a schema 0.6 two-state schedule from a parametric survival curve", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.schema_version = "0.6.0";
    plan.states = ["alive", "dead"];
    plan.cycles = 3;
    plan.strategies.comparator = {
      name: "Comparator",
      initial_distribution: [1, 0],
      transition_schedule: [1, 2, 3].map((start_cycle) => ({
        start_cycle,
        matrix: [[0.8, 0.2], [0, 1]],
      })),
      state_costs: [100, 0],
      state_utilities: [1, 0],
    };
    plan.strategies.intervention = {
      name: "Intervention",
      initial_distribution: [1, 0],
      transition_matrix: [[0.9, 0.1], [0, 1]],
      state_costs: [120, 0],
      state_utilities: [1, 0],
    };
    plan.assumptions = [{
      id: "survival-rate",
      statement: "Use the declared exponential survival rate",
      reason: "Browser contract test",
      status: "proposed",
    }];
    plan.input_provenance = [{
      path: "strategies.comparator.transition_schedule",
      source_ids: [],
      extraction_ids: [],
      assumption_ids: ["survival-rate"],
      unit: "probability per annual model cycle",
      jurisdiction: "China",
      derivation: {
        method: "deterministic_transformation",
        model_value: plan.strategies.comparator.transition_schedule,
        transformation: {
          operation: "parametric_survival_to_transition_schedule",
          cycle_length_years: 1,
          from_state_index: 0,
          event_state_index: 1,
          distribution: "exponential",
          parameters: {
            rate_per_year: { value: -Math.log(0.8), assumption_id: "survival-rate" },
          },
        },
      },
      selection_rationale: "Exercise bounded survival conversion",
      uncertainty_status: "fixed",
    }];

    let audit = auditHeorEvidence(plan);
    expect(audit.invalidMappings.join("; ")).not.toContain("parametric survival curve");
    expect(parseHeorPlan(JSON.stringify(plan)).schema_version).toBe("0.6.0");

    const survival = plan.input_provenance[0].derivation.transformation!;
    if (survival.operation !== "parametric_survival_to_transition_schedule") {
      throw new Error("test fixture must use a survival transformation");
    }
    survival.parameters.rate_per_year.value = 0.3;
    audit = auditHeorEvidence(plan);
    expect(audit.invalidMappings.join("; ")).toContain(
      "parametric survival curve does not reproduce the current transition schedule",
    );
  });

  it("recomputes schema 0.7 single-event probability time conversion", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.schema_version = "0.7.0";
    plan.states = ["alive", "event"];
    plan.cycles = 3;
    plan.strategies.comparator = {
      name: "Comparator",
      initial_distribution: [1, 0],
      transition_matrix: [[0.9, 0.1], [0, 1]],
      state_costs: [100, 0],
      state_utilities: [1, 0],
    };
    plan.strategies.intervention = {
      name: "Intervention",
      initial_distribution: [1, 0],
      transition_matrix: [[0.8, 0.2], [0, 1]],
      state_costs: [120, 0],
      state_utilities: [1, 0],
    };
    plan.assumptions = [{
      id: "two-year-event-probability",
      statement: "Use the declared two-year event probability",
      reason: "Browser contract test",
      status: "proposed",
    }];
    plan.input_provenance = [{
      path: "strategies.intervention.transition_matrix",
      source_ids: [],
      extraction_ids: [],
      assumption_ids: ["two-year-event-probability"],
      unit: "probability per annual model cycle",
      jurisdiction: "China",
      derivation: {
        method: "deterministic_transformation",
        model_value: plan.strategies.intervention.transition_matrix,
        transformation: {
          operation: "single_event_probability_time_conversion",
          cycle_length_years: 1,
          phases: [{
            start_cycle: 1,
            rows: [
              {
                self_index: 0,
                event: {
                  target_index: 1,
                  source_probability: 0.36,
                  source_interval_years: 2,
                  assumption_id: "two-year-event-probability",
                },
              },
              { self_index: 1, event: null },
            ],
          }],
        },
      },
      selection_rationale: "Exercise bounded probability-time conversion",
      uncertainty_status: "fixed",
    }];

    let audit = auditHeorEvidence(plan);
    expect(audit.invalidMappings.join("; ")).not.toContain("source probabilities do not reproduce");
    expect(parseHeorPlan(JSON.stringify(plan)).schema_version).toBe("0.7.0");

    const transformation = plan.input_provenance[0].derivation.transformation!;
    if (transformation.operation !== "single_event_probability_time_conversion") {
      throw new Error("test fixture must use probability-time conversion");
    }
    transformation.phases[0].rows[0].event!.source_probability = 0.49;
    audit = auditHeorEvidence(plan);
    expect(audit.invalidMappings.join("; ")).toContain(
      "source probabilities do not reproduce the current transition input",
    );
  });

  it("requires provenance for a schema 0.4 transition schedule instead of an absent matrix", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.schema_version = "0.4.0";
    delete plan.strategies.intervention.transition_matrix;
    plan.strategies.intervention.transition_schedule = [
      { start_cycle: 1, matrix: [[0.8, 0.15, 0.05], [0, 0.75, 0.25], [0, 0, 1]] },
      { start_cycle: 2, matrix: [[0.75, 0.17, 0.08], [0, 0.7, 0.3], [0, 0, 1]] },
    ];

    const audit = auditHeorEvidence(plan);

    expect(audit.unsupportedInputs).toContain(
      "strategies.intervention.transition_schedule",
    );
    expect(audit.unsupportedInputs).not.toContain(
      "strategies.intervention.transition_matrix",
    );
    expect(parseHeorPlan(JSON.stringify(plan)).schema_version).toBe("0.4.0");
  });

  it("audits the conceptual model independently from numerical inputs", () => {
    const parsed = parseHeorConceptualModel(JSON.stringify(HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL));
    const audit = auditHeorConceptualModel(parsed);
    expect(audit.complete).toBe(true);
    expect(audit.stateCount).toBe(3);
    expect(audit.transitionCount).toBe(5);

    const unresolved = structuredClone(parsed);
    unresolved.structural_assumptions[0].status = "unresolved";
    expect(auditHeorConceptualModel(unresolved).complete).toBe(false);

    const missingExternalValidation = structuredClone(parsed);
    missingExternalValidation.validation_plan.external = [];
    const validationAudit = auditHeorConceptualModel(missingExternalValidation);
    expect(validationAudit.complete).toBe(false);
    expect(validationAudit.errors).toContain(
      "validation_plan.external must be a non-empty string array",
    );
    expect(auditHeorConceptualModel(parsed, "different-analysis").errors).toContain(
      "conceptual model analysis_id does not match the current analysis plan",
    );
  });

  it("keeps profile selection separate from reference-case compliance", () => {
    expect(HEOR_BROWSER_DEMO_PLAN.reference_case.status).toBe("current");
    expect(HEOR_BROWSER_DEMO_REFERENCE_CASE_AUDIT.complete).toBe(false);
    expect(HEOR_BROWSER_DEMO_REFERENCE_CASE_AUDIT.blockingGaps).toContain("cost-scope");
  });

  it("keeps a documented uncertainty path separate from an executable audit", () => {
    expect(HEOR_BROWSER_DEMO_PLAN.uncertainty_analysis?.path).toBe(
      "heor/uncertainty-plan.json",
    );
    expect(HEOR_BROWSER_DEMO_UNCERTAINTY_AUDIT.complete).toBe(false);
    expect(HEOR_BROWSER_DEMO_UNCERTAINTY_AUDIT.errors[0]).toContain(
      "uncertainty-plan.json",
    );
  });

  it("keeps the budget impact artifact separate and fail-closed", () => {
    expect(HEOR_BROWSER_DEMO_PLAN.budget_impact_analysis?.path).toBe(
      "heor/budget-impact-plan.json",
    );
    expect(HEOR_BROWSER_DEMO_BUDGET_IMPACT_AUDIT.complete).toBe(false);
    expect(HEOR_BROWSER_DEMO_BUDGET_IMPACT_AUDIT.errors[0]).toContain(
      "budget-impact-plan.json",
    );
  });

  it("keeps independent validation separate, local, and fail-closed", () => {
    expect(HEOR_MODEL_VALIDATION_PATH).toBe("heor/model-validation.json");
    expect(HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT.complete).toBe(false);
    expect(HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT.approvable).toBe(false);
    expect(HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT.requiredCoverageCount).toBe(18);
  });
});

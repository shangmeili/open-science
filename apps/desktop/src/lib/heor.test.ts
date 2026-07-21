import { describe, expect, it } from "vitest";
import {
  auditHeorConceptualModel,
  auditHeorEvidence,
  buildHeorPrompt,
  displayHeorPrompt,
  HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL,
  HEOR_BROWSER_DEMO_BUDGET_IMPACT_AUDIT,
  HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT,
  HEOR_BROWSER_DEMO_PLAN,
  HEOR_BROWSER_DEMO_REFERENCE_CASE_AUDIT,
  HEOR_BROWSER_DEMO_UNCERTAINTY_AUDIT,
  HEOR_MODEL_VALIDATION_PATH,
  heorSurvivalReviewBindingsCurrent,
  type HeorSurvivalReviewAudit,
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

  it("reports malformed provenance records without crashing the review pane", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.input_provenance = [
      {
        path: undefined,
        unit: "",
        jurisdiction: "",
        selection_rationale: "",
        uncertainty_status: "fixed",
        source_ids: [],
        extraction_ids: [],
        assumption_ids: [],
        derivation: {},
      },
      null,
    ] as unknown as typeof plan.input_provenance;

    expect(() => auditHeorEvidence(plan)).not.toThrow();
    expect(auditHeorEvidence(plan).invalidMappings).toEqual(expect.arrayContaining([
      expect.stringContaining("path is missing"),
      expect.stringContaining("mapping must be an object"),
    ]));
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

  it("admits structure-neutral analysis schema 0.15 without Markov transitions", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.schema_version = "0.15.0";
    plan.baseline_strategy_id = "comparator";
    plan.strategy_order = ["comparator", "intervention"];
    for (const strategy of Object.values(plan.strategies)) {
      delete strategy.initial_distribution;
      delete strategy.transition_matrix;
      delete strategy.transition_schedule;
    }
    plan.partitioned_survival_analysis = { path: "heor/partitioned-survival-plan.json" };
    plan.cost_input_normalization = { path: "heor/cost-input-normalization.json" };
    plan.utility_inputs = { path: "heor/utility-inputs.json" };
    plan.event_disutilities = { path: "heor/event-disutilities.json" };

    expect(parseHeorPlan(JSON.stringify(plan)).schema_version).toBe("0.15.0");
    expect(auditHeorEvidence(plan).invalidMappings.join("; ")).not.toContain(
      "transition structure is forbidden",
    );
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
    expect(prompt).toContain("Preserve the Open Science baseline");
    expect(prompt).toContain("Evidence claims must be auditable");
    expect(prompt).toContain("report them as exploratory scenarios");
    expect(prompt).toContain("Describe data flow precisely");
    expect(prompt).toContain("If the configured model provider is remote");
    expect(prompt).toContain("never call the whole task fully local");
    expect(prompt).toContain("Do not begin with Git status, .gitignore, README");
    expect(prompt).toContain("progressive HEOR outputs, not prerequisites");
    expect(prompt).toContain("never create or claim human approvals");
  });

  it("keeps runtime instructions out of the researcher-visible history", () => {
    const prompt = buildHeorPrompt("$heor-model-calibration\n\n检查模型校准结果");
    expect(displayHeorPrompt(prompt)).toBe("检查模型校准结果");
    const legacyPrompt = [
      "Use $heor-workbench for this request.",
      "Work through natural-language dialogue first. Maintain heor/analysis-plan.json only when the decision problem and inputs are sufficiently defined; never create or claim human approvals.",
      "",
      "旧任务也不显示内部指令",
    ].join("\n");
    expect(displayHeorPrompt(legacyPrompt)).toBe("旧任务也不显示内部指令");
    expect(displayHeorPrompt("研究者自己的问题")).toBe("研究者自己的问题");
  });

  it("fails closed when model inputs lack provenance", () => {
    const audit = auditHeorEvidence(HEOR_BROWSER_DEMO_PLAN);
    expect(audit.complete).toBe(false);
    expect(audit.coveredInputs).toBe(0);
    expect(audit.requiredInputs).toBe(14);
    expect(audit.unresolvedAssumptions).toEqual(["demo-only"]);
  });

  it("audits schema 0.12 economic inputs without requiring Markov structure", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.schema_version = "0.12.0";
    plan.partitioned_survival_analysis = { path: "heor/partitioned-survival-plan.json" };
    plan.strategy_order = ["comparator", "intervention"];
    plan.baseline_strategy_id = "comparator";
    for (const strategy of Object.values(plan.strategies)) {
      delete strategy.initial_distribution;
      delete strategy.transition_matrix;
    }

    const audit = auditHeorEvidence(plan);

    expect(audit.requiredInputs).toBe(10);
    expect(audit.invalidMappings.join("; ")).not.toContain("must define exactly one");
    plan.strategies.intervention.transition_matrix = [[1]];
    expect(auditHeorEvidence(plan).invalidMappings.join("; ")).toContain(
      "transition structure is forbidden",
    );
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
      "schema_version must be 0.3.0 through 0.15.0",
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

  it("independently audits age-aligned background plus excess mortality", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.schema_version = "0.9.0";
    plan.baseline_strategy_id = "comparator";
    plan.strategy_order = ["comparator", "intervention"];
    plan.states = ["alive", "dead"];
    plan.cycles = 2;
    const q = [0.1, 0.2];
    const excess = 0.05;
    const schedule = q.map((annualProbability, index) => {
      const integratedHazard = (-Math.log1p(-annualProbability) + excess);
      const deathProbability = -Math.expm1(-integratedHazard);
      return {
        start_cycle: index + 1,
        matrix: [[1 - deathProbability, deathProbability], [0, 1]],
      };
    });
    plan.strategies.comparator = {
      name: "Comparator",
      initial_distribution: [1, 0],
      transition_schedule: schedule,
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
    const assumptionIds = ["q-60", "q-61", "excess", "exchangeability", "no-double-counting"];
    plan.assumptions = assumptionIds.map((id) => ({
      id, statement: id, reason: "Browser audit fixture", status: "proposed" as const,
    }));
    plan.input_provenance = [{
      path: "strategies.comparator.transition_schedule",
      source_ids: [],
      extraction_ids: [],
      assumption_ids: assumptionIds,
      unit: "probability per annual model cycle",
      jurisdiction: "China",
      derivation: {
        method: "deterministic_transformation",
        model_value: schedule,
        transformation: {
          operation: "background_plus_excess_mortality_to_transition_schedule",
          cycle_length_years: 1,
          from_state_index: 0,
          death_state_index: 1,
          life_table: {
            jurisdiction: "China",
            table_year: 2024,
            population: "general population",
            sex: "all",
            start_age_years: 60,
            cycle_probabilities: q.map((value, index) => ({
              cycle: index + 1,
              attained_age_years: 60 + index,
              annual_probability: { value, assumption_id: `q-${60 + index}` },
            })),
          },
          excess_mortality_rate_per_year: { value: excess, assumption_id: "excess" },
          review_bases: {
            population_exchangeability: { assumption_id: "exchangeability" },
            no_double_counting: { assumption_id: "no-double-counting" },
          },
        },
      },
      selection_rationale: "Exercise background mortality audit",
      uncertainty_status: "distribution_available",
    }];

    expect(parseHeorPlan(JSON.stringify(plan)).schema_version).toBe("0.9.0");
    let errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).not.toContain("background plus excess mortality");

    const zeroPlan = structuredClone(plan);
    zeroPlan.cycle_length_years = 0.5;
    const zeroMapping = zeroPlan.input_provenance?.[0];
    if (!zeroMapping) throw new Error("test fixture must include input provenance");
    const zeroTransformation = zeroMapping.derivation.transformation!;
    if (zeroTransformation.operation !== "background_plus_excess_mortality_to_transition_schedule") {
      throw new Error("test fixture must use background mortality");
    }
    zeroTransformation.cycle_length_years = 0.5;
    zeroTransformation.excess_mortality_rate_per_year.value = 0;
    zeroTransformation.life_table.cycle_probabilities.forEach((entry) => {
      entry.annual_probability.value = 0;
      entry.attained_age_years = 60;
    });
    const zeroSchedule = [1, 2].map((startCycle) => ({
      start_cycle: startCycle,
      matrix: [[1, 0], [0, 1]],
    }));
    zeroPlan.strategies.comparator.transition_schedule = zeroSchedule;
    zeroMapping.derivation.model_value = zeroSchedule;
    errors = auditHeorEvidence(zeroPlan).invalidMappings.join("; ");
    expect(errors).not.toContain("background plus excess mortality");

    const transformation = plan.input_provenance[0].derivation.transformation!;
    if (transformation.operation !== "background_plus_excess_mortality_to_transition_schedule") {
      throw new Error("test fixture must use background mortality");
    }
    transformation.life_table.cycle_probabilities[0].annual_probability.value = 0.11;
    errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).toContain("does not reproduce the current transition schedule");
    transformation.life_table.cycle_probabilities[0].annual_probability.value = 0.1;
    transformation.life_table.cycle_probabilities[1].attained_age_years = 62;
    errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).toContain("must equal floor");
    transformation.life_table.cycle_probabilities[1].attained_age_years = 61;
    plan.schema_version = "0.8.0";
    errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).toContain("require schema_version 0.9.0");
    plan.schema_version = "0.9.0";
    plan.cycle_length_years = 2;
    transformation.cycle_length_years = 2;
    transformation.life_table.cycle_probabilities[1].attained_age_years = 62;
    transformation.excess_mortality_rate_per_year.value = Number.MAX_VALUE;
    errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).toContain("non-finite integrated hazard");
  });

  it("independently distinguishes RR from OR and fails closed on relative-effect drift", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.schema_version = "0.10.0";
    plan.baseline_strategy_id = "comparator";
    plan.strategy_order = ["comparator", "intervention"];
    plan.states = ["event-free", "event"];
    plan.cycles = 2;
    const rrSchedule = [0.2, 0].map((q, index) => ({
      start_cycle: index + 1,
      matrix: [[1 - q * 2, q * 2], [0, 1]],
    }));
    plan.strategies.comparator = {
      name: "Comparator", initial_distribution: [1, 0], transition_schedule: rrSchedule,
      state_costs: [100, 0], state_utilities: [1, 0],
    };
    plan.strategies.intervention = {
      name: "Intervention", initial_distribution: [1, 0], transition_matrix: [[0.9, 0.1], [0, 1]],
      state_costs: [120, 0], state_utilities: [1, 0],
    };
    const assumptionIds = ["q1", "q2", "effect", "endpoint", "population", "constancy"];
    plan.assumptions = assumptionIds.map((id) => ({
      id, statement: id, reason: "Browser relative-effect fixture", status: "proposed" as const,
    }));
    plan.input_provenance = [{
      path: "strategies.comparator.transition_schedule",
      source_ids: [], extraction_ids: [], assumption_ids: assumptionIds,
      unit: "probability per annual model cycle", jurisdiction: "China",
      derivation: {
        method: "deterministic_transformation", model_value: rrSchedule,
        transformation: {
          operation: "relative_effect_to_transition_schedule",
          cycle_length_years: 1, effect_interval_years: 1,
          from_state_index: 0, event_state_index: 1, measure: "risk_ratio",
          baseline_cycle_probabilities: [
            { cycle: 1, probability: { value: 0.2, assumption_id: "q1" } },
            { cycle: 2, probability: { value: 0, assumption_id: "q2" } },
          ],
          relative_effect: { value: 2, assumption_id: "effect" },
          review_bases: {
            endpoint_alignment: { assumption_id: "endpoint" },
            population_transportability: { assumption_id: "population" },
            effect_constancy_over_cycles: { assumption_id: "constancy" },
          },
        },
      },
      selection_rationale: "Exercise relative-effect audit",
      uncertainty_status: "distribution_available",
    }];
    expect(parseHeorPlan(JSON.stringify(plan)).schema_version).toBe("0.10.0");
    let errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).not.toContain("relative effect does not reproduce");

    const mapping = plan.input_provenance[0];
    const transformation = mapping.derivation.transformation;
    if (transformation?.operation !== "relative_effect_to_transition_schedule") {
      throw new Error("test fixture must use relative effect");
    }
    transformation.measure = "odds_ratio";
    errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).toContain("relative effect does not reproduce");
    const orProbability = (2 * 0.2) / ((1 - 0.2) + 2 * 0.2);
    const orSchedule = [orProbability, 0].map((probability, index) => ({
      start_cycle: index + 1, matrix: [[1 - probability, probability], [0, 1]],
    }));
    plan.strategies.comparator.transition_schedule = orSchedule;
    mapping.derivation.model_value = orSchedule;
    errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).not.toContain("relative effect does not reproduce");

    transformation.measure = "risk_ratio";
    transformation.relative_effect.value = 5;
    errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).toContain("produced an invalid event probability");
    transformation.relative_effect.value = 2;
    transformation.baseline_cycle_probabilities.forEach((entry) => { entry.probability.value = 0; });
    errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).toContain("at least one positive probability");
  });

  it("independently derives a proportional-hazards schedule and fails closed", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.schema_version = "0.11.0";
    plan.baseline_strategy_id = "comparator";
    plan.strategy_order = ["comparator", "intervention"];
    plan.states = ["event-free", "event"];
    plan.cycles = 3;
    const hazards = [0.1, 0.3, 0.3];
    const hr = 0.5;
    let previous = 0;
    const schedule = hazards.map((hazard, index) => {
      const probability = -Math.expm1(-hr * (hazard - previous));
      previous = hazard;
      return { start_cycle: index + 1, matrix: [[1 - probability, probability], [0, 1]] };
    });
    plan.strategies.comparator = {
      name: "Comparator", initial_distribution: [1, 0], transition_schedule: schedule,
      state_costs: [100, 0], state_utilities: [1, 0],
    };
    plan.strategies.intervention = {
      name: "Intervention", initial_distribution: [1, 0], transition_matrix: [[0.9, 0.1], [0, 1]],
      state_costs: [120, 0], state_utilities: [1, 0],
    };
    const assumptionIds = [
      "h1", "h2", "h3", "hr", "endpoint", "population", "ph", "constancy", "switching",
    ];
    plan.assumptions = assumptionIds.map((id) => ({
      id, statement: id, reason: "Browser HR fixture", status: "proposed" as const,
    }));
    plan.input_provenance = [{
      path: "strategies.comparator.transition_schedule",
      source_ids: [], extraction_ids: [], assumption_ids: assumptionIds,
      unit: "probability per annual model cycle", jurisdiction: "China",
      derivation: {
        method: "deterministic_transformation", model_value: schedule,
        transformation: {
          operation: "hazard_ratio_to_transition_schedule",
          cycle_length_years: 1,
          from_state_index: 0,
          event_state_index: 1,
          baseline_cumulative_hazards: hazards.map((value, index) => ({
            cycle: index + 1,
            cumulative_hazard: { value, assumption_id: `h${index + 1}` },
          })),
          hazard_ratio: { value: hr, assumption_id: "hr" },
          review_bases: {
            endpoint_alignment: { assumption_id: "endpoint" },
            population_transportability: { assumption_id: "population" },
            proportional_hazards_assumption: { assumption_id: "ph" },
            effect_constancy_over_horizon: { assumption_id: "constancy" },
            treatment_switching_assessment: { assumption_id: "switching" },
          },
        },
      },
      selection_rationale: "Exercise hazard-ratio audit",
      uncertainty_status: "distribution_available",
    }];
    expect(parseHeorPlan(JSON.stringify(plan)).schema_version).toBe("0.11.0");
    let errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).not.toContain("hazard ratio does not reproduce");

    const transformation = plan.input_provenance[0].derivation.transformation;
    if (transformation?.operation !== "hazard_ratio_to_transition_schedule") {
      throw new Error("test fixture must use hazard ratio");
    }
    transformation.baseline_cumulative_hazards[1].cumulative_hazard.value = 0.05;
    errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).toContain("non-decreasing");
    transformation.baseline_cumulative_hazards[1].cumulative_hazard.value = 0.3;
    transformation.hazard_ratio.value = Number.MAX_VALUE;
    errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).toContain("invalid event probability");
    transformation.hazard_ratio.value = hr;
    transformation.baseline_cumulative_hazards.forEach((entry) => {
      entry.cumulative_hazard.value = 0;
    });
    errors = auditHeorEvidence(plan).invalidMappings.join("; ");
    expect(errors).toContain("at least one positive increment");
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

  it("requires every multi-curve survival artifact binding to stay current", () => {
    const audit: HeorSurvivalReviewAudit = {
      complete: true,
      required: true,
      status: "complete",
      reviewSha256: "a".repeat(64),
      targetCount: 2,
      reviewCount: 2,
      analysisId: "multi-survival",
      targetPath: null,
      selectedFamily: null,
      candidateModels: 4,
      convergedModels: 4,
      failedModels: [],
      scenarioCount: 4,
      recommendedFamily: null,
      executionEnvironment: null,
      crossImplementationComplete: false,
      artifactBindings: [
        { path: "heor/survival-extrapolation-reviews.json", sha256: "a".repeat(64) },
        { path: "heor/survival-extrapolation-reviews/control.json", sha256: "b".repeat(64) },
        { path: "heor/survival-extrapolation-reviews/treatment.json", sha256: "c".repeat(64) },
      ],
      targets: [],
      blockingGaps: [],
      errors: [],
    };
    const relatedArtifacts = audit.artifactBindings.map((binding) => ({ ...binding }));
    expect(heorSurvivalReviewBindingsCurrent({ relatedArtifacts }, audit)).toBe(true);
    expect(heorSurvivalReviewBindingsCurrent({ relatedArtifacts: relatedArtifacts.slice(0, 2) }, audit))
      .toBe(false);
    relatedArtifacts[2].sha256 = "d".repeat(64);
    expect(heorSurvivalReviewBindingsCurrent({ relatedArtifacts }, audit)).toBe(false);
  });
});

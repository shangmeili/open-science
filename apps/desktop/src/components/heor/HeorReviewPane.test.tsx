import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  HEOR_BROWSER_DEMO_EVIDENCE_SYNTHESIS_AUDIT,
  type HeorAdvancedVoiAudit,
  type HeorAdvancedVoiRunResult,
  type HeorBudgetImpactRunResult,
  type HeorPairedBootstrapAudit,
  type HeorNetworkMetaAnalysisAudit,
  type HeorPopulationAdjustedComparisonAudit,
  type HeorUncertaintyRunResult,
} from "@/lib/heor";
import { useUiStore } from "@/lib/store";
import {
  CeacChart,
  AdvancedVoiResultCard,
  AdvancedVoiReviewDialog,
  BudgetImpactResultCard,
  EvidenceVerificationDialog,
  HeorReviewPane,
  MethodReviewQueue,
  NetworkMetaAnalysisAssessment,
  NetworkMetaAnalysisReviewDialog,
  PopulationAdjustedComparisonAssessment,
  PopulationAdjustedComparisonReviewDialog,
  PairedBootstrapAssessment,
  PairedBootstrapReviewDialog,
  UncertaintyResultCard,
} from "./HeorReviewPane";

afterEach(() => useUiStore.getState().setLocale("en"));

describe("AI4HEOR human review pane", () => {
  const pairedAudit: HeorPairedBootstrapAudit = {
    complete: true,
    reviewable: true,
    status: "complete",
    executionId: "paired-run-1",
    resultPath: "heor/paired-survival-bootstrap-executions/paired-run-1/result-manifest.json",
    resultSha256: "a".repeat(64),
    requestPath: "heor/paired-survival-bootstrap-request.json",
    requestSha256: "b".repeat(64),
    candidatePath: "heor/paired-survival-bootstrap-executions/paired-run-1/joint-survival-draws.candidate.jsonl",
    candidateSha256: "c".repeat(64),
    iterations: 1000,
    completedReplicates: 1000,
    failedReplicates: 0,
    curveCount: 4,
    strategyCounts: { standard: 120, intervention: 118 },
    packageVersions: { survHE: "2.0.51", flexsurv: "2.3.2", survival: "3.8.6" },
    crossImplementationComplete: true,
    curveCoherenceComplete: true,
    dependencePreserved: true,
    betweenStrategyAssumption: "conditional_independence_given_parallel_arm_design",
    limitations: ["Human method review required."],
    errors: [],
  };

  const nmaAudit: HeorNetworkMetaAnalysisAudit = {
    complete: true,
    reviewable: true,
    status: "awaiting_model_review",
    executionId: "nma-run-1",
    requestPath: "heor/network-meta-analysis-request.json",
    requestSha256: "d".repeat(64),
    resultPath: "heor/network-meta-analysis-runs/nma-run-1/manifest.json",
    resultSha256: "e".repeat(64),
    studyCount: 9,
    treatmentCount: 3,
    directComparisonCount: 3,
    cycleRank: 1,
    modelType: "random",
    tau: 0.218,
    crossImplementationScope: "conditional_on_backend_tau",
    globalInconsistencyStatus: "estimable",
    localInconsistencyCount: 3,
    rankingMethod: "none",
    limitations: ["Human method review required."],
    errors: [],
  };

  const pacAudit: HeorPopulationAdjustedComparisonAudit = {
    complete: true,
    reviewable: true,
    status: "awaiting_method_review",
    executionId: "maic-run-1",
    requestPath: "heor/population-adjusted-comparison-request.json",
    requestSha256: "f".repeat(64),
    resultPath: "heor/population-adjusted-comparison-runs/maic-run-1/manifest.json",
    resultSha256: "1".repeat(64),
    rowCount: 160,
    modifierCount: 3,
    effectMeasure: "log_odds_ratio",
    essOverall: 112.4,
    essRatio: 0.7025,
    maximumWeight: 3.14,
    maxAbsBalanceError: 2.1e-11,
    unadjustedEstimate: -0.12,
    adjustedEstimate: -0.25,
    indirectEstimate: -0.43,
    indirectSe: 0.18,
    bootstrapIterations: 1000,
    bootstrapFailures: 0,
    nativeScope: "calibration_and_point_estimate_only",
    limitations: ["Human method review required."],
    errors: [],
  };

  const advancedVoiAudit: HeorAdvancedVoiAudit = {
    complete: true,
    reviewable: true,
    status: "complete",
    voiId: "voi-1",
    analysisId: "analysis-1",
    uncertaintyId: "uncertainty-1",
    advancedVoiPlanSha256: "2".repeat(64),
    analysisPlanSha256: "3".repeat(64),
    uncertaintyPlanSha256: "4".repeat(64),
    uncertaintyResultSha256: "5".repeat(64),
    uncertaintySchemaVersion: "0.9.0",
    decisionThreshold: 100000,
    populationYearCount: 3,
    effectivePopulation: 2350,
    evppiGroupCount: 1,
    evppiEvaluationCount: 2000,
    evsiDesignCount: 1,
    evsiEvaluationCount: 2000,
    evsiTargetParameterId: "effect",
    resultSha256: "6".repeat(64),
    replaySha256: "7".repeat(64),
    errors: [],
  };

  it("consolidates only current method results without granting Agent approval authority", async () => {
    const reviewNma = vi.fn();
    const discussPac = vi.fn();
    render(
      <MethodReviewQueue
        items={[
          {
            id: "advancedVoi",
            path: "heor/results/advanced-voi.json",
            status: "accepted",
            onReview: vi.fn(),
            onPrepare: vi.fn(),
          },
          {
            id: "nma",
            path: "heor/network-meta-analysis-runs/nma-run-1/manifest.json",
            status: "awaiting",
            onReview: reviewNma,
            onPrepare: vi.fn(),
          },
          {
            id: "pac",
            path: "heor/population-adjusted-comparison-runs/maic-run-1/manifest.json",
            status: "rejected",
            onReview: vi.fn(),
            onPrepare: discussPac,
          },
        ]}
      />,
    );
    expect(screen.getByText("Method review queue")).toBeInTheDocument();
    expect(screen.getByText("1/3 accepted · 1 awaiting Human judgment")).toBeInTheDocument();
    expect(screen.getByText(/Review forms record Human judgments/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Review Network meta-analysis" }));
    await userEvent.click(screen.getByRole("button", { name: "Discuss Anchored MAIC in conversation" }));
    expect(reviewNma).toHaveBeenCalledOnce();
    expect(discussPac).toHaveBeenCalledOnce();
  });

  it("does not render an empty method review queue", () => {
    const { container } = render(<MethodReviewQueue items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("keeps advanced VOI acceptance behind all eight Human method checks", async () => {
    const onSubmit = vi.fn();
    render(
      <AdvancedVoiReviewDialog
        audit={advancedVoiAudit}
        running={false}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    const submit = screen.getByRole("button", { name: "Record Human review" });
    expect(submit).toBeDisabled();
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(8);
    for (const checkbox of checkboxes) await userEvent.click(checkbox);
    await userEvent.type(screen.getByLabelText("Human reviewer"), "VOI reviewer");
    await userEvent.type(
      screen.getByLabelText("Review rationale"),
      "Reviewed population, grouping, sampling model, costs, uncertainty, and limitations.",
    );
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith(
      "accept",
      expect.objectContaining({
        decisionScopeThresholdReviewed: true,
        limitationsNoDecisionAuthorityReviewed: true,
      }),
      "VOI reviewer",
      "Reviewed population, grouping, sampling model, costs, uncertainty, and limitations.",
    );
  });

  it("renders population EVPI, EVPPI and EVSI/ENBS as review-only output", () => {
    const result = {
      audit: advancedVoiAudit,
      resultSha256: "6".repeat(64),
      replaySha256: "7".repeat(64),
      reviewStatus: "awaiting_human_review",
      calculation: {
        schema_version: "0.1.0",
        engine_version: "0.1.0",
        voi_id: "voi-1",
        decision_threshold: 100000,
        population: {
          annual_affected_population: [1000, 800, 600],
          discount_rate: 0.03,
          effective_population: 2350,
        },
        population_evpi: {
          per_person_evpi: 500,
          per_person_evpi_mcse: 20,
          population_evpi: 1175000,
          population_evpi_mcse: 47000,
        },
        evppi: [{
          group_id: "effect-group",
          label: "Treatment effect",
          parameter_ids: ["effect"],
          per_person_evppi: 300,
          per_person_evppi_mcse: 15,
          population_evppi: 705000,
        }],
        evsi: {
          target_group_id: "effect-group",
          target_parameter_id: "effect",
          study_delay_years: 1,
          study_cost_basis: { currency: "USD", price_year: 2026 },
          designs: [{
            sample_size: 200,
            per_person_evsi: 150,
            per_person_evsi_mcse: 10,
            research_effective_population: 1350,
            population_evsi: 202500,
            study_cost: 100000,
            expected_net_benefit_of_sampling: 102500,
          }],
        },
        replay_sha256: "7".repeat(64),
        classification: "research_priority_calculation_for_human_review",
        limitations: ["Human review required."],
      },
    } as HeorAdvancedVoiRunResult;
    render(<AdvancedVoiResultCard result={result} locale="en" />);
    expect(screen.getByText("Advanced value-of-information result")).toBeInTheDocument();
    expect(screen.getByText("Treatment effect")).toBeInTheDocument();
    expect(screen.getByText("ENBS")).toBeInTheDocument();
    expect(screen.getByText(/not reimbursement, funding, or optimal-study decisions/)).toBeInTheDocument();
  });

  it("keeps anchored MAIC selection eligibility behind all eight Human method checks", async () => {
    const onSubmit = vi.fn();
    const card = render(
      <PopulationAdjustedComparisonAssessment
        state={{ kind: "ready", audit: pacAudit }}
        currentReview={null}
        accepted={false}
        onRequestPreparation={vi.fn()}
        onReview={vi.fn()}
      />,
    );
    expect(screen.getByText("Complete native audit · awaiting Human method review")).toBeInTheDocument();
    expect(screen.getByText("160")).toBeInTheDocument();
    card.unmount();

    render(
      <PopulationAdjustedComparisonReviewDialog
        audit={pacAudit}
        running={false}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    const submit = screen.getByRole("button", { name: "Record acceptance" });
    expect(submit).toBeDisabled();
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(8);
    for (const checkbox of checkboxes) await userEvent.click(checkbox);
    await userEvent.type(screen.getByPlaceholderText("Name or local reviewer label"), "MAIC reviewer");
    await userEvent.type(
      screen.getByPlaceholderText(/Why this exact question/),
      "Reviewed the exact target population, modifiers, overlap, weights, uncertainty, and residual bias.",
    );
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith(
      "accept",
      expect.objectContaining({
        questionEstimandTargetCommonComparatorReviewed: true,
        residualBiasTransportabilityDownstreamReviewed: true,
      }),
      "MAIC reviewer",
      "Reviewed the exact target population, modifiers, overlap, weights, uncertainty, and residual bias.",
    );
  });

  it("keeps NMA selection eligibility behind all eight Human method checks", async () => {
    const onSubmit = vi.fn();
    const card = render(
      <NetworkMetaAnalysisAssessment
        state={{ kind: "ready", audit: nmaAudit }}
        currentReview={null}
        accepted={false}
        onRequestPreparation={vi.fn()}
        onReview={vi.fn()}
      />,
    );
    expect(screen.getByText("Complete native audit · awaiting Human method review")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    card.unmount();

    render(
      <NetworkMetaAnalysisReviewDialog
        audit={nmaAudit}
        running={false}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    const submit = screen.getByRole("button", { name: "Record acceptance" });
    expect(submit).toBeDisabled();
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(8);
    for (const checkbox of checkboxes) await userEvent.click(checkbox);
    await userEvent.type(screen.getByPlaceholderText("Name or local reviewer label"), "NMA reviewer");
    await userEvent.type(
      screen.getByPlaceholderText(/Why this exact question/),
      "Reviewed the exact network, transitivity basis, model, diagnostics, uncertainty, and limitations.",
    );
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith(
      "accept",
      expect.objectContaining({
        questionOutcomeEstimandReviewed: true,
        rankingTransportabilityLimitationsReviewed: true,
      }),
      "NMA reviewer",
      "Reviewed the exact network, transitivity basis, model, diagnostics, uncertainty, and limitations.",
    );
  });

  it("keeps paired-bootstrap acceptance behind every Human method check", async () => {
    const onSubmit = vi.fn();
    const card = render(
      <PairedBootstrapAssessment
        state={{ kind: "ready", audit: pairedAudit }}
        currentReview={null}
        accepted={false}
        onRequestPreparation={vi.fn()}
        onReview={vi.fn()}
      />,
    );
    expect(screen.getByText("Complete native audit · awaiting Human method review")).toBeInTheDocument();
    expect(screen.getByText("1000/1000")).toBeInTheDocument();
    card.unmount();

    render(
      <PairedBootstrapReviewDialog
        audit={pairedAudit}
        running={false}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    const submit = screen.getByRole("button", { name: "Record acceptance" });
    expect(submit).toBeDisabled();
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(7);
    for (const checkbox of checkboxes) await userEvent.click(checkbox);
    await userEvent.type(screen.getByPlaceholderText("Name or local reviewer label"), "Methods reviewer");
    await userEvent.type(
      screen.getByPlaceholderText(/Why this exact design/),
      "Reviewed the exact endpoints, censoring, model families, and extrapolation limits.",
    );
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith(
      "accept",
      expect.objectContaining({
        resamplingDesignReviewed: true,
        clinicalPlausibilityReviewed: true,
      }),
      "Methods reviewer",
      "Reviewed the exact endpoints, censoring, model families, and extrapolation limits.",
    );
  });

  it("renders CEAC and CEAF with accessible labels and non-color distinction", () => {
    const { container } = render(
      <CeacChart
        locale="en"
        primaryThreshold={100000}
        rows={[
          {
            threshold: 0,
            expected_incremental_net_monetary_benefit: -5000,
            intervention_optimal_probability: 0.1,
            comparator_optimal_probability: 0.9,
            tie_probability: 0,
            probability_mcse: 0.01,
            strategy_with_highest_expected_net_benefit: "comparator",
            ceaf_probability: 0.9,
            per_person_evpi: 100,
            per_person_evpi_mcse: 10,
          },
          {
            threshold: 100000,
            expected_incremental_net_monetary_benefit: 5000,
            intervention_optimal_probability: 0.8,
            comparator_optimal_probability: 0.2,
            tie_probability: 0,
            probability_mcse: 0.01,
            strategy_with_highest_expected_net_benefit: "intervention",
            ceaf_probability: 0.8,
            per_person_evpi: 200,
            per_person_evpi_mcse: 20,
          },
          {
            threshold: 200000,
            expected_incremental_net_monetary_benefit: 15000,
            intervention_optimal_probability: 0.95,
            comparator_optimal_probability: 0.05,
            tie_probability: 0,
            probability_mcse: 0.01,
            strategy_with_highest_expected_net_benefit: "intervention",
            ceaf_probability: 0.95,
            per_person_evpi: 50,
            per_person_evpi_mcse: 5,
          },
        ]}
      />,
    );

    expect(screen.getByText("Cost-effectiveness acceptability curve")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /intervention optimal probability/ })).toBeInTheDocument();
    expect(screen.getByText("Intervention CEAC")).toBeInTheDocument();
    expect(screen.getByText("CEAF")).toBeInTheDocument();
    const paths = [...container.querySelectorAll("path")];
    expect(paths).toHaveLength(2);
    expect(paths.some((path) => path.getAttribute("stroke-dasharray"))).toBe(true);
  });

  it("shows the bounded dynamic budget flow ledger without implying observed patients", async () => {
    const flow = {
      opening_comparator: 80,
      opening_intervention: 20,
      incident_population: 20,
      requested_incident_intervention_starts: 10,
      incident_intervention_starts: 5,
      requested_comparator_displacement_starts: 9.5,
      comparator_displacement_starts: 0,
      capacity: 5,
      capacity_unmet_starts: 14.5,
      comparator_treated: 95,
      intervention_treated: 25,
      treated_population: 120,
      intervention_share: 25 / 120,
      deaths: 12,
      intervention_discontinuers_to_comparator: 4.5,
      comparator_discontinuers_exiting: 8.55,
      closing_comparator: 81.45,
      closing_intervention: 18,
      total_cost: 14500,
    };
    const result = {
      workflow: { classification: "exploratory" },
      calculation: {
        analysis_id: "analysis-1",
        bia_id: "bia-1",
        engine_version: "0.3.0",
        schema_version: "0.2.0",
        analysis_plan_sha256: "a".repeat(64),
        budget_impact_plan_sha256: "b".repeat(64),
        calculation_classification: "calculation_only",
        horizon_years: 3,
        discount_rate: 0,
        currency: "CNY",
        price_year: 2026,
        base_case: {
          model_type: "dynamic_annual_cohort",
          event_order: ["open_stock"],
          annual_results: [1, 2, 3].map((year) => ({
            year,
            eligible_population: 120,
            without_new_intervention_share: 0,
            with_new_intervention_share: 25 / 120,
            without_new_intervention_cost: 12000,
            with_new_intervention_cost: 14500,
            net_budget_impact: 2500,
            without_new_intervention_flow: flow,
            with_new_intervention_flow: flow,
          })),
          annual_net_budget_impact: [2500, 2500, 2500],
          cumulative_net_budget_impact: 7500,
        },
        one_way_sensitivity: [{
          parameter_id: "capacity",
          label: "Start capacity",
          target: "/market_scenarios/with_new_intervention/intervention_start_capacity_by_year/0",
          cumulative_span: 1000,
        }],
        alternative_scenarios: [{
          scenario_id: "lower-capacity",
          label: "Lower capacity",
          cumulative_net_budget_impact: 6000,
        }],
        limitations: ["Annual expected counts; not observed patient flow."],
        warnings: [],
      },
    } as unknown as HeorBudgetImpactRunResult;

    render(<BudgetImpactResultCard result={result} locale="en" />);
    expect(screen.getByText(/Dynamic annual cohort/)).toBeInTheDocument();
    await userEvent.click(screen.getByText("Dynamic with-access flow ledger"));
    expect(screen.getAllByText("15")).toHaveLength(3);
    expect(screen.getByText(/allocates incident starts before displacement/)).toBeInTheDocument();
  });

  it("renders one CEAC series per declared strategy", () => {
    const { container } = render(
      <CeacChart
        locale="en"
        primaryThreshold={100}
        strategyOrder={["treatment_b", "standard", "treatment_a"]}
        rows={[
          {
            threshold: 0,
            expected_net_monetary_benefit_by_strategy: { standard: 0, treatment_a: -10, treatment_b: -20 },
            strategy_optimal_probabilities: { standard: 0.8, treatment_a: 0.15, treatment_b: 0.05 },
            tie_probability: 0,
            probability_mcse_by_strategy: { standard: 0.01, treatment_a: 0.01, treatment_b: 0.01 },
            tie_probability_mcse: 0,
            strategy_with_highest_expected_net_benefit: "standard",
            expected_net_benefit_tied_strategy_ids: [],
            ceaf_probability: 0.8,
            per_person_evpi: 2,
            per_person_evpi_mcse: 0.2,
          },
          {
            threshold: 100,
            expected_net_monetary_benefit_by_strategy: { standard: 0, treatment_a: 10, treatment_b: 20 },
            strategy_optimal_probabilities: { standard: 0.1, treatment_a: 0.3, treatment_b: 0.6 },
            tie_probability: 0,
            probability_mcse_by_strategy: { standard: 0.01, treatment_a: 0.01, treatment_b: 0.02 },
            tie_probability_mcse: 0,
            strategy_with_highest_expected_net_benefit: "treatment_b",
            expected_net_benefit_tied_strategy_ids: [],
            ceaf_probability: 0.6,
            per_person_evpi: 3,
            per_person_evpi_mcse: 0.3,
          },
        ]}
      />,
    );

    expect(screen.getAllByText(/^(treatment_b|standard|treatment_a)$/).map((item) => item.textContent))
      .toEqual(["treatment_b", "standard", "treatment_a"]);
    expect(container.querySelectorAll("path")).toHaveLength(4);
  });

  it("does not present draw-level tie probability as CEAF when expected NMB is tied", () => {
    const result = {
      calculation: {
        calculation_classification: "partial_parameter_uncertainty",
        uncertainty_scope: "economic_inputs_only",
        economic_basis: { currency: "USD", price_year: 2026 },
        deterministic_analysis: [],
        probabilistic_analysis: {
          iterations: 1000,
          strategy_order: ["standard", "treatment"],
          convergence: {
            passed: true,
            probability_drift: 0.01,
            max_probability_mcse: 0.02,
            max_probability_drift: 0.02,
          },
          correlation_groups: [],
          decision_uncertainty: {
            method: "net_monetary_benefit",
            strategy_order: ["standard", "treatment"],
            primary_threshold: 100,
            threshold_source: "declared_grid",
            threshold_rationale: "Test grid",
            threshold_results: [{
              threshold: 100,
              expected_net_monetary_benefit_by_strategy: { standard: 100, treatment: 100 },
              strategy_optimal_probabilities: { standard: 0.3, treatment: 0.28 },
              tie_probability: 0.42,
              probability_mcse_by_strategy: { standard: 0.01, treatment: 0.01 },
              tie_probability_mcse: 0.02,
              strategy_with_highest_expected_net_benefit: null,
              expected_net_benefit_tied_strategy_ids: ["standard", "treatment"],
              ceaf_probability: null,
              per_person_evpi: 2,
              per_person_evpi_mcse: 0.2,
            }],
            population_evpi: null,
            evppi: null,
          },
          omitted_parameters: [],
        },
        structural_scenarios: [],
        limitations: [],
      },
      workflow: { classification: "exploratory" },
    } as unknown as HeorUncertaintyRunResult;

    const partialView = render(<UncertaintyResultCard result={result} locale="en" />);

    expect(screen.getByText("Expected NMB · standard = treatment")).toBeInTheDocument();
    expect(screen.getByText("Partial parameter uncertainty")).toBeInTheDocument();
    expect(screen.getByText(/Only state costs and utilities vary/)).toBeInTheDocument();
    expect(screen.getByText("Conditional EVPI · economic inputs only")).toBeInTheDocument();
    expect(screen.queryByText("42.0%")).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();

    partialView.unmount();
    const joint = structuredClone(result) as unknown as HeorUncertaintyRunResult;
    joint.calculation.calculation_classification = "joint_curve_draw_parameter_uncertainty";
    joint.calculation.uncertainty_scope = "joint_survival_curves_and_economic_inputs";
    const jointView = render(<UncertaintyResultCard result={joint} locale="en" />);
    expect(screen.getByText("Joint survival-draw uncertainty")).toBeInTheDocument();
    expect(screen.getByText(/one hash-bound row across all PFS\/OS curves/)).toBeInTheDocument();
    expect(screen.getByText("Conditional EVPI · joint curves + economic inputs")).toBeInTheDocument();

    jointView.unmount();
    const component = structuredClone(result) as unknown as HeorUncertaintyRunResult;
    component.calculation.calculation_classification = "component_parameter_uncertainty";
    component.calculation.uncertainty_scope = "cost_utility_event_components_only";
    render(<UncertaintyResultCard result={component} locale="en" />);
    expect(screen.getByText("Correlated component uncertainty")).toBeInTheDocument();
    expect(screen.getByText(/rebuilds costs, cycle utilities, and event QALY losses/)).toBeInTheDocument();
    expect(screen.getByText("Conditional component EVPI / person")).toBeInTheDocument();

    const composed = structuredClone(result) as unknown as HeorUncertaintyRunResult;
    composed.calculation.calculation_classification = "joint_curve_and_component_parameter_uncertainty";
    composed.calculation.uncertainty_scope = "joint_survival_curves_and_cost_utility_event_components";
    render(<UncertaintyResultCard result={composed} locale="en" />);
    expect(screen.getByText("Composed PSM parameter uncertainty")).toBeInTheDocument();
    expect(screen.getByText(/combines one complete joint PFS\/OS row/)).toBeInTheDocument();
    expect(screen.getByText("Conditional EVPI · joint curves + components")).toBeInTheDocument();
  });

  it("shows exact extraction details and records a selected rejection", async () => {
    const onSubmit = vi.fn();
    render(
      <EvidenceVerificationDialog
        audit={HEOR_BROWSER_DEMO_EVIDENCE_SYNTHESIS_AUDIT}
        running={false}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    expect(screen.getByText("12500")).toBeInTheDocument();
    expect(screen.getByText(/CNY per cycle; Chinese payer setting/)).toBeInTheDocument();
    expect(screen.getByText(/Table 3, intervention arm/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reject selected" }));
    await userEvent.click(screen.getByRole("checkbox", {
      name: "Select extraction extract-cost",
    }));
    await userEvent.type(screen.getByPlaceholderText("Name or local reviewer label"), "Reviewer A");
    await userEvent.type(
      screen.getByPlaceholderText(/How you checked the values/),
      "The table reports a different cycle cost.",
    );
    await userEvent.click(screen.getByRole("checkbox", {
      name: /I personally checked and reject all 1 selected extractions/,
    }));
    await userEvent.click(screen.getByRole("button", { name: "Record rejection" }));
    expect(onSubmit).toHaveBeenCalledWith(
      "Reviewer A",
      "The table reports a different cycle cost.",
      "rejected",
      ["extract-cost"],
    );
  });

  it("reads an agent-authored artifact and keeps approval human-only", async () => {
    render(
      <HeorReviewPane
        project={{ id: "ai4heor-demo", name: "Demo" }}
        onClose={vi.fn()}
        onRequestRevision={vi.fn()}
      />,
    );

    expect(
      await screen.findByText("Cost-effectiveness of a new first-line treatment for advanced NSCLC"),
    ).toBeInTheDocument();
    expect(screen.getByText("Human-authorized evidence search")).toBeInTheDocument();
    expect(screen.getByText("Exact request is ready for human authorization")).toBeInTheDocument();
    expect(screen.getByText("semaglutide AND type 2 diabetes AND cost effectiveness")).toBeInTheDocument();
    expect(screen.getByText("Evidence synthesis ledger")).toBeInTheDocument();
    expect(screen.getByText("Local evidence library")).toBeInTheDocument();
    expect(screen.getByText("Local sources are hash-bound and searchable")).toBeInTheDocument();
    expect(screen.getByText("Evidence synthesis needs human-guided work")).toBeInTheDocument();
    expect(screen.getByText("Not assessed")).toBeInTheDocument();
    expect(screen.getByText("Reviewer confirmations")).toBeInTheDocument();
    expect(screen.getByText("0/4")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review and authorize exact search" }))
      .not.toBeInTheDocument();
    expect(screen.getByText("Evidence audit incomplete")).toBeInTheDocument();
    expect(screen.getByText("Cohort transition structure")).toBeInTheDocument();
    expect(screen.getByText("Survival fitting and extrapolation")).toBeInTheDocument();
    expect(screen.getByText("No parametric survival target in this plan")).toBeInTheDocument();
    expect(screen.getAllByText("Static")).toHaveLength(2);
    expect(await screen.findByText("Structural audit complete")).toBeInTheDocument();
    expect(screen.getAllByText("0/14")).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Review Decision problem" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Record approval" });
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByPlaceholderText("Name or local reviewer label"), "Local reviewer");
    await userEvent.type(
      screen.getByPlaceholderText("What you checked and why this gate can proceed"),
      "Decision context checked against the project question.",
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "I performed this review myself" }));
    await userEvent.click(submit);

    expect(await screen.findByText("Approved for this artifact")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review Conceptual model" })).toBeInTheDocument();
  });

  it("keeps analysis-plan approval locked until evidence traceability is complete", async () => {
    const onRequestRevision = vi.fn();
    render(
      <HeorReviewPane
        project={{ id: "ai4heor-demo", name: "Demo" }}
        onClose={vi.fn()}
        onRequestRevision={onRequestRevision}
      />,
    );
    await screen.findByText("Evidence audit incomplete");
    expect(screen.getByText("Reference-case audit incomplete")).toBeInTheDocument();
    expect(screen.getByText("Uncertainty audit incomplete")).toBeInTheDocument();
    expect(screen.getByText("Budget impact audit incomplete")).toBeInTheDocument();
    expect(screen.getByText("Validation package is incomplete")).toBeInTheDocument();
    expect(screen.getByText("Report package is incomplete")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review Analysis plan" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask agent to resolve evidence gaps" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to audit the cohort model",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-cohort-state-transition"),
    );
    expect(onRequestRevision.mock.calls[onRequestRevision.mock.calls.length - 1]?.[0]).toContain("schema 0.10.0");
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to derive transitions from rates",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-transition-rate-adapter"),
    );
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to convert a probability to the model cycle",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-probability-time-adapter"),
    );
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to add background mortality",
    }));
    const backgroundPrompt = onRequestRevision.mock.calls[
      onRequestRevision.mock.calls.length - 1
    ]?.[0];
    expect(backgroundPrompt).toContain("$heor-background-mortality");
    expect(backgroundPrompt).toContain("life-table");
    expect(backgroundPrompt).toContain("Human");
    expect(backgroundPrompt).toContain("forms only as an aid");
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to apply a risk ratio or odds ratio",
    }));
    const relativeEffectPrompt = onRequestRevision.mock.calls[
      onRequestRevision.mock.calls.length - 1
    ]?.[0];
    expect(relativeEffectPrompt).toContain("$heor-relative-effect-adapter");
    expect(relativeEffectPrompt).toContain("natural-language interaction first");
    expect(relativeEffectPrompt).toContain("Stop if the evidence reports an HR");
    expect(relativeEffectPrompt).toContain("strictly below 1/max(positive baseline q)");
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to apply a hazard ratio",
    }));
    const hazardRatioPrompt = onRequestRevision.mock.calls[
      onRequestRevision.mock.calls.length - 1
    ]?.[0];
    expect(hazardRatioPrompt).toContain("$heor-hazard-ratio-adapter");
    expect(hazardRatioPrompt).toContain("natural-language interaction first");
    expect(hazardRatioPrompt).toContain("p=-expm1(-HR*delta_H0)");
    expect(hazardRatioPrompt).toContain("Stop for non-proportional hazards");
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to review survival fitting and extrapolation",
    }));
    const survivalReviewPrompt = onRequestRevision.mock.calls[
      onRequestRevision.mock.calls.length - 1
    ]?.[0];
    expect(survivalReviewPrompt).toContain("$heor-survival-extrapolation-review");
    expect(survivalReviewPrompt).toContain("natural-language interaction first");
    expect(survivalReviewPrompt).toContain("schema 0.2.0");
    expect(survivalReviewPrompt).toContain("analysis_target");
    expect(survivalReviewPrompt).toContain("Pre-specify 2-8");
    expect(survivalReviewPrompt).toContain("awaiting_human_selection");
    expect(survivalReviewPrompt).toContain("Do not auto-select");
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to continue screening and synthesis",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-evidence-synthesis"),
    );
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to search the local library",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-local-evidence"),
    );
    await userEvent.click(screen.getByRole("button", {
      name: "Ask agent to assess or repair reference-case gaps",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(expect.stringContaining("$heor-reference-case"));
    await userEvent.click(screen.getByRole("button", {
      name: "Ask agent to create or repair uncertainty analysis",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-uncertainty-analysis"),
    );
    expect(onRequestRevision.mock.calls[onRequestRevision.mock.calls.length - 1]?.[0]).toContain("uncertainty 0.9.0");
    await userEvent.click(screen.getByRole("button", {
      name: "Ask the Agent to build or repair budget impact",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-budget-impact"),
    );
    expect(onRequestRevision.mock.calls[onRequestRevision.mock.calls.length - 1]?.[0]).toContain("$heor-dynamic-budget-impact");
    expect(onRequestRevision.mock.calls[onRequestRevision.mock.calls.length - 1]?.[0]).toContain("strategy_order");
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to prepare validation evidence",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-model-validation"),
    );
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to prepare or repair the report package",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-reporting"),
    );
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to prepare or repair reproducibility evidence",
    }));
    const reproducibilityPrompt = onRequestRevision.mock.calls[
      onRequestRevision.mock.calls.length - 1
    ]?.[0];
    expect(reproducibilityPrompt).toContain("$heor-reproducibility-package");
    expect(reproducibilityPrompt).toContain("exact current report package");
    expect(reproducibilityPrompt).toContain("Do not create a new approval gate");
  });

  it("runs the browser fixture as an explicitly exploratory calculation", async () => {
    render(
      <HeorReviewPane
        project={{ id: "ai4heor-demo", name: "Demo" }}
        onClose={vi.fn()}
        onRequestRevision={vi.fn()}
      />,
    );
    await screen.findByText("Decision and model snapshot");
    await userEvent.click(screen.getByRole("button", { name: "Run deterministic analysis" }));
    expect(await screen.findByText("Exploratory")).toBeInTheDocument();
    expect(screen.getByText("Not decision-ready")).toBeInTheDocument();
    expect(screen.getByText("Calculation basis: 2026 CNY")).toBeInTheDocument();
  });
});

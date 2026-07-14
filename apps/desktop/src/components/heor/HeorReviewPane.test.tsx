import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  HEOR_BROWSER_DEMO_EVIDENCE_SYNTHESIS_AUDIT,
  type HeorUncertaintyRunResult,
} from "@/lib/heor";
import { useUiStore } from "@/lib/store";
import {
  CeacChart,
  EvidenceVerificationDialog,
  HeorReviewPane,
  UncertaintyResultCard,
} from "./HeorReviewPane";

afterEach(() => useUiStore.getState().setLocale("en"));

describe("AI4HEOR human review pane", () => {
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

    render(<UncertaintyResultCard result={result} locale="en" />);

    expect(screen.getByText("Expected NMB · standard = treatment")).toBeInTheDocument();
    expect(screen.queryByText("42.0%")).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
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

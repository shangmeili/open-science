import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  DecisionTreeReview,
  reviewDecisionTreeArtifacts,
  type DecisionTreeReviewState,
} from "./DecisionTreeReview";
import { sha256Text } from "@/lib/heor";

const CURRENT: DecisionTreeReviewState = {
  kind: "ready",
  plan: {
    analysisId: "short-horizon-example",
    referenceCaseId: "CN-current",
    referenceCaseStatus: "current",
    timeHorizonYears: 1,
    strategyOrder: ["comparator", "intervention"],
    baselineStrategyId: "comparator",
    strategies: {
      comparator: { name: "常规治疗" },
      intervention: { name: "新干预" },
    },
    sourceIds: ["source-1", "source-2"],
    proposedAssumptionIds: ["assumption-1"],
  },
  result: {
    inputSha256: "a".repeat(64),
    engineVersion: "0.1.0",
    strategies: {
      comparator: { name: "常规治疗", totalCost: 1800, totalQaly: 0.68 },
      intervention: { name: "新干预", totalCost: 2900, totalQaly: 0.7375 },
    },
    pairwiseVsBaseline: {
      intervention: {
        deltaCost: 1100,
        deltaQaly: 0.0575,
        icer: 19130.434782608696,
        interpretation: "tradeoff",
      },
    },
    warnings: ["Reference-case compliance has not been assessed."],
  },
  planSha256: "a".repeat(64),
  resultCurrent: true,
};

describe("deterministic decision-tree review", () => {
  it("binds an engine result to the exact plan bytes and rejects changed bytes", async () => {
    const plan = JSON.stringify({
      schema_version: "0.1.0",
      analysis_type: "decision_tree",
      analysis_id: "short-horizon-example",
      reference_case: { id: "CN-current", status: "current" },
      time_horizon_years: 1,
      strategy_order: ["comparator", "intervention"],
      baseline_strategy_id: "comparator",
      assumptions: [],
      strategies: {
        comparator: { name: "usual care" },
        intervention: { name: "new treatment" },
      },
    });
    const inputSha256 = await sha256Text(plan);
    const result = JSON.stringify({
      analysis_id: "short-horizon-example",
      analysis_type: "decision_tree",
      calculation_classification: "deterministic_decision_tree",
      schema_version: "0.1.0",
      engine_version: "0.1.0",
      input_sha256: inputSha256,
      strategy_order: ["comparator", "intervention"],
      strategies: {
        comparator: { name: "usual care", total_cost: 10, total_qaly: 0.5 },
        intervention: { name: "new treatment", total_cost: 20, total_qaly: 0.6 },
      },
      pairwise_vs_baseline: {
        intervention: {
          delta_cost: 10,
          delta_qaly: 0.1,
          icer: 100,
          interpretation: "tradeoff",
        },
      },
      warnings: ["calculation only"],
    });

    const current = await reviewDecisionTreeArtifacts(plan, result);
    expect(current).toMatchObject({ kind: "ready", resultCurrent: true, planSha256: inputSha256 });

    const changed = await reviewDecisionTreeArtifacts(`${plan}\n`, result);
    expect(changed).toMatchObject({ kind: "ready", resultCurrent: false });
  });

  it("shows only a result bound to the exact current plan", async () => {
    const onOpenResult = vi.fn();
    render(
      <DecisionTreeReview
        state={CURRENT}
        onRefresh={vi.fn()}
        onRun={vi.fn()}
        onOpenResult={onOpenResult}
      />,
    );

    expect(screen.getByText("Deterministic decision tree")).toBeInTheDocument();
    expect(screen.getByText("Current deterministic result")).toBeInTheDocument();
    expect(screen.getByText("常规治疗")).toBeInTheDocument();
    expect(screen.getByText("新干预")).toBeInTheDocument();
    expect(screen.getByText("19,130.435")).toBeInTheDocument();
    expect(screen.getByText("Sources: 2 · Proposed assumptions: 1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /ICER.*19,130\.435/ }));
    expect(onOpenResult).toHaveBeenCalledOnce();
  });

  it("does not display stale strategy values and requests a deterministic rerun", async () => {
    const onRun = vi.fn();
    render(
      <DecisionTreeReview
        state={{ ...CURRENT, resultCurrent: false }}
        onRefresh={vi.fn()}
        onRun={onRun}
      />,
    );

    expect(screen.getByText("The result no longer matches the current plan")).toBeInTheDocument();
    expect(screen.queryByText("19,130.435")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Validate and run again" }));
    expect(onRun).toHaveBeenCalledOnce();
  });
});

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
    schemaVersion: "0.1.0",
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
    economicBasis: null,
  },
  result: {
    schemaVersion: "0.1.0",
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
    economicBasis: null,
  },
  planSha256: "a".repeat(64),
  resultCurrent: true,
  uncertainty: null,
  uncertaintyCurrent: false,
};

describe("deterministic decision-tree review", () => {
  it("reviews schema 0.2 only when the plan and result share one economic basis", async () => {
    const economicBasis = {
      currency: "CNY",
      price_year: 2026,
      jurisdiction: "中国大陆",
      perspective: "中国医疗卫生系统",
    };
    const plan = JSON.stringify({
      schema_version: "0.2.0",
      analysis_type: "decision_tree",
      analysis_id: "short-horizon-basis",
      reference_case: { id: "CN-current", status: "current" },
      economic_basis: economicBasis,
      time_horizon_years: 1,
      strategy_order: ["comparator", "intervention"],
      baseline_strategy_id: "comparator",
      assumptions: [],
      strategies: {
        comparator: { name: "常规治疗" },
        intervention: { name: "新干预" },
      },
    });
    const inputSha256 = await sha256Text(plan);
    const result = JSON.stringify({
      analysis_id: "short-horizon-basis",
      analysis_type: "decision_tree",
      calculation_classification: "deterministic_decision_tree",
      schema_version: "0.2.0",
      engine_version: "0.2.0",
      economic_basis: economicBasis,
      input_sha256: inputSha256,
      strategy_order: ["comparator", "intervention"],
      strategies: {
        comparator: { name: "常规治疗", total_cost: 10, total_qaly: 0.5 },
        intervention: { name: "新干预", total_cost: 20, total_qaly: 0.6 },
      },
      pairwise_vs_baseline: {
        intervention: { delta_cost: 10, delta_qaly: 0.1, icer: 100, interpretation: "tradeoff" },
      },
      warnings: ["calculation only"],
    });

    const current = await reviewDecisionTreeArtifacts(plan, result);
    expect(current).toMatchObject({
      kind: "ready",
      resultCurrent: true,
      plan: { economicBasis },
      result: { economicBasis },
    });
    if (current.kind !== "ready") throw new Error("expected ready decision-tree review");
    render(
      <DecisionTreeReview
        state={current}
        locale="zh-CN"
        onRefresh={vi.fn()}
        onRun={vi.fn()}
      />,
    );
    expect(screen.getByText("CNY · 2026 · 中国大陆 · 中国医疗卫生系统")).toBeInTheDocument();

    const mismatched = JSON.stringify({
      ...JSON.parse(result),
      economic_basis: { ...economicBasis, price_year: 2025 },
    });
    expect(await reviewDecisionTreeArtifacts(plan, mismatched)).toMatchObject({
      kind: "ready",
      result: null,
      resultCurrent: false,
      resultIssue: "invalid",
    });

    const wrongEngine = JSON.stringify({
      ...JSON.parse(result),
      engine_version: "0.1.0",
    });
    expect(await reviewDecisionTreeArtifacts(plan, wrongEngine)).toMatchObject({
      kind: "ready",
      result: null,
      resultCurrent: false,
      resultIssue: "invalid",
    });
  });

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

  it("shows uncertainty only when both current plans match the deterministic result", async () => {
    const economicBasis = {
      currency: "CNY",
      price_year: 2026,
      jurisdiction: "中国大陆",
      perspective: "中国医疗卫生系统",
    };
    const plan = JSON.stringify({
      schema_version: "0.2.0",
      analysis_type: "decision_tree",
      analysis_id: "short-horizon-uncertainty",
      reference_case: { id: "CN-current", status: "current" },
      economic_basis: economicBasis,
      time_horizon_years: 1,
      strategy_order: ["comparator", "intervention"],
      baseline_strategy_id: "comparator",
      assumptions: [],
      strategies: {
        comparator: { name: "常规治疗" },
        intervention: { name: "新干预" },
      },
    });
    const planSha256 = await sha256Text(plan);
    const result = JSON.stringify({
      analysis_id: "short-horizon-uncertainty",
      analysis_type: "decision_tree",
      calculation_classification: "deterministic_decision_tree",
      schema_version: "0.2.0",
      engine_version: "0.2.0",
      economic_basis: economicBasis,
      input_sha256: planSha256,
      strategy_order: ["comparator", "intervention"],
      strategies: {
        comparator: { name: "常规治疗", total_cost: 10, total_qaly: 0.5 },
        intervention: { name: "新干预", total_cost: 20, total_qaly: 0.6 },
      },
      pairwise_vs_baseline: {
        intervention: { delta_cost: 10, delta_qaly: 0.1, icer: 100, interpretation: "tradeoff" },
      },
      warnings: ["calculation only"],
    });
    const uncertaintyPlan = JSON.stringify({
      schema_version: "0.1.0",
      analysis_type: "decision_tree_uncertainty",
      uncertainty_id: "short-horizon-uncertainty-run",
      analysis_input: {
        path: "heor/decision-tree-plan.json",
        content_sha256: planSha256,
      },
      parameters: [{ id: "success-probability" }],
      probabilistic_analysis: {
        iterations: 100,
        seed: 7,
        convergence: {
          checkpoints: [50, 100],
          max_probability_mcse: 0.1,
          max_probability_drift: 0.1,
        },
      },
    });
    const uncertaintySha256 = await sha256Text(uncertaintyPlan);
    const uncertaintyResult = JSON.stringify({
      analysis_id: "short-horizon-uncertainty",
      analysis_type: "decision_tree_uncertainty",
      uncertainty_id: "short-horizon-uncertainty-run",
      schema_version: "0.1.0",
      engine_version: "0.1.0",
      analysis_schema_version: "0.2.0",
      analysis_input_sha256: planSha256,
      uncertainty_input_sha256: uncertaintySha256,
      economic_basis: economicBasis,
      strategy_order: ["comparator", "intervention"],
      deterministic_analysis: [{ parameter_id: "success-probability" }],
      probabilistic_analysis: {
        iterations: 100,
        prng: { algorithm: "pcg32-xsh-rr", version: "1", seed: 7 },
        optimal_probabilities: { comparator: 0.32, intervention: 0.64 },
        tie_probability: 0.04,
        convergence: {
          passed: true,
          probability_drift: 0.02,
          max_probability_mcse: 0.1,
          max_probability_drift: 0.1,
          checkpoints: [
            { iterations: 50, max_probability_mcse: 0.07 },
            { iterations: 100, max_probability_mcse: 0.05 },
          ],
        },
      },
    });

    const current = await reviewDecisionTreeArtifacts(
      plan,
      result,
      uncertaintyPlan,
      uncertaintyResult,
    );
    expect(current).toMatchObject({
      kind: "ready",
      uncertaintyCurrent: true,
      uncertainty: { parameterCount: 1, iterations: 100, seed: 7, convergencePassed: true },
    });
    render(
      <DecisionTreeReview state={current} locale="en" onRefresh={vi.fn()} onRun={vi.fn()} />,
    );
    expect(screen.getByText("100 PSA draws · 1 DSA parameter")).toBeInTheDocument();
    expect(screen.getByText("Convergence diagnostic passed")).toBeInTheDocument();
    expect(screen.getByText("64%")).toBeInTheDocument();
    expect(screen.getByText("4%")).toBeInTheDocument();

    const stale = await reviewDecisionTreeArtifacts(
      plan,
      result,
      `${uncertaintyPlan}\n`,
      uncertaintyResult,
    );
    expect(stale).toMatchObject({
      kind: "ready",
      uncertainty: null,
      uncertaintyCurrent: false,
      uncertaintyIssue: "stale",
    });
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

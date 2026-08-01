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

  it("shows only source-current subgroup results and keeps interpretation awaiting researcher review", async () => {
    const economicBasis = {
      currency: "CNY",
      price_year: 2026,
      jurisdiction: "中国大陆",
      perspective: "中国医疗卫生系统",
    };
    const plan = JSON.stringify({
      schema_version: "0.2.0",
      analysis_type: "decision_tree",
      analysis_id: "subgroup-overall",
      reference_case: { id: "CN-2020-current", status: "current" },
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
      analysis_id: "subgroup-overall",
      analysis_type: "decision_tree",
      calculation_classification: "deterministic_decision_tree",
      schema_version: "0.2.0",
      engine_version: "0.2.0",
      economic_basis: economicBasis,
      input_sha256: planSha256,
      strategy_order: ["comparator", "intervention"],
      strategies: {
        comparator: { name: "常规治疗", total_cost: 1800, total_qaly: 0.68 },
        intervention: { name: "新干预", total_cost: 2900, total_qaly: 0.7375 },
      },
      pairwise_vs_baseline: {
        intervention: { delta_cost: 1100, delta_qaly: 0.0575, icer: 19130.4348, interpretation: "tradeoff" },
      },
      warnings: ["calculation only"],
    });
    const evidence = JSON.stringify({ records: [], extractions: [] });
    const evidenceSha256 = await sha256Text(evidence);
    const groupA = JSON.stringify({ analysis_id: "subgroup-a" });
    const groupB = JSON.stringify({ analysis_id: "subgroup-b" });
    const groupASha256 = await sha256Text(groupA);
    const groupBSha256 = await sha256Text(groupB);
    const subgroupPlan = JSON.stringify({
      schema_version: "0.1.0",
      analysis_type: "decision_tree_subgroup",
      subgroup_analysis_id: "risk-subgroups",
      overall_analysis_input: { path: "heor/decision-tree-plan.json", content_sha256: planSha256 },
      evidence_synthesis_input: { path: "heor/evidence-synthesis.json", content_sha256: evidenceSha256 },
      grouping: {
        id: "risk-group",
        label: "风险分层",
        prespecification: "prespecified",
        mutually_exclusive: true,
        exhaustive: true,
      },
      subgroups: [
        { id: "group-a", label: "A 组", population_share: { value: 0.5 }, analysis_input: { path: "heor/subgroups/group-a.json", content_sha256: groupASha256 } },
        { id: "group-b", label: "B 组", population_share: { value: 0.5 }, analysis_input: { path: "heor/subgroups/group-b.json", content_sha256: groupBSha256 } },
      ],
    });
    const subgroupSha256 = await sha256Text(subgroupPlan);
    const subgroupResult = JSON.stringify({
      schema_version: "0.1.0",
      engine_version: "0.1.0",
      analysis_type: "decision_tree_subgroup",
      subgroup_analysis_id: "risk-subgroups",
      calculation_classification: "deterministic_subgroup_analysis",
      subgroup_input_sha256: subgroupSha256,
      overall_analysis_input: { path: "heor/decision-tree-plan.json", content_sha256: planSha256 },
      evidence_synthesis_input: { path: "heor/evidence-synthesis.json", content_sha256: evidenceSha256 },
      economic_basis: economicBasis,
      strategy_order: ["comparator", "intervention"],
      baseline_strategy_id: "comparator",
      source_register: [{
        source_id: "source-1",
        record_id: "record-1",
        title: "Subgroup source",
        source_type: "teaching_fixture",
        locator: "local://subgroup-source",
        source_location: "fixture:source-1",
        verification_status: "verified_for_teaching_fixture",
      }],
      subgroups: [
        { id: "group-a", label: "A 组", population_share: 0.5, analysis_input_path: "heor/subgroups/group-a.json", analysis_input_sha256: groupASha256, source_ids: ["source-1"], pairwise_vs_baseline: { intervention: { delta_cost: 680, delta_qaly: 0.125, icer: 5440, interpretation: "tradeoff", incremental_net_monetary_benefit: 5570 } } },
        { id: "group-b", label: "B 组", population_share: 0.5, analysis_input_path: "heor/subgroups/group-b.json", analysis_input_sha256: groupBSha256, source_ids: ["source-1"], pairwise_vs_baseline: { intervention: { delta_cost: 1520, delta_qaly: -0.01, icer: null, interpretation: "dominated", incremental_net_monetary_benefit: -2020 } } },
      ],
      weighted_pairwise_vs_baseline: { intervention: { delta_cost: 1100, delta_qaly: 0.0575, icer: 19130.4348, interpretation: "tradeoff", incremental_net_monetary_benefit: 1775 } },
      overall_consistency: { passed: true, tolerances: { cost: 1e-9, qaly: 1e-9 }, max_abs_cost_difference: 0, max_abs_qaly_difference: 0 },
      descriptive_heterogeneity: [{ left_subgroup_id: "group-a", right_subgroup_id: "group-b", strategy_id: "intervention", delta_cost_difference: -840, delta_qaly_difference: 0.135, incremental_nmb_difference: 7590, interpretation: "descriptive_contrast_not_interaction_test" }],
      scientific_review: {
        status: "awaiting_researcher_review",
        required_checks: ["population_definition_and_overlap", "prespecification_or_post_hoc_status", "subgroup_source_eligibility", "interaction_or_heterogeneity_basis", "multiplicity_and_power", "interpretation_and_decision_use"],
      },
      warnings: ["This descriptive subgroup contrast does not establish interaction."],
    });

    const current = await reviewDecisionTreeArtifacts(
      plan,
      result,
      null,
      null,
      subgroupPlan,
      subgroupResult,
      evidence,
      {
        "heor/subgroups/group-a.json": groupA,
        "heor/subgroups/group-b.json": groupB,
      },
    );
    expect(current).toMatchObject({ kind: "ready", subgroupCurrent: true });
    const onOpenSubgroupInput = vi.fn();
    render(
      <DecisionTreeReview
        state={current}
        locale="en"
        onRefresh={vi.fn()}
        onRun={vi.fn()}
        onOpenSubgroupInput={onOpenSubgroupInput}
      />,
    );
    expect(screen.getByText("Subgroup analysis")).toBeInTheDocument();
    expect(screen.getByText("Awaiting researcher review")).toBeInTheDocument();
    expect(screen.getByText("A 组")).toBeInTheDocument();
    expect(screen.getByText("5,440")).toBeInTheDocument();
    expect(screen.getByText("Descriptive contrasts do not establish interaction or treatment-effect modification.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open source for A 组 incremental cost: 680" }));
    expect(onOpenSubgroupInput).toHaveBeenCalledWith("heor/subgroups/group-a.json");

    const unboundSources = await reviewDecisionTreeArtifacts(
      plan,
      result,
      null,
      null,
      subgroupPlan,
      subgroupResult.replace('"source_ids":["source-1"]', '"source_ids":["missing-source"]'),
      evidence,
      {
        "heor/subgroups/group-a.json": groupA,
        "heor/subgroups/group-b.json": groupB,
      },
    );
    expect(unboundSources).toMatchObject({ kind: "ready", subgroup: null, subgroupCurrent: false, subgroupIssue: "invalid" });

    const stale = await reviewDecisionTreeArtifacts(
      plan,
      result,
      null,
      null,
      subgroupPlan,
      subgroupResult,
      evidence,
      {
        "heor/subgroups/group-a.json": `${groupA}\n`,
        "heor/subgroups/group-b.json": groupB,
      },
    );
    expect(stale).toMatchObject({ kind: "ready", subgroup: null, subgroupCurrent: false, subgroupIssue: "stale" });
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

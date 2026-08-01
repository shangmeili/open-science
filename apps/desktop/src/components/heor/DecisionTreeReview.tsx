import { AlertTriangle, FileJson, Play, RefreshCw, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { readArtifact } from "@/lib/artifactFile";
import { cn } from "@/lib/cn";
import { sha256Text } from "@/lib/heor";

export const HEOR_DECISION_TREE_PLAN_PATH = "heor/decision-tree-plan.json";
export const HEOR_DECISION_TREE_RESULT_PATH = "heor/results/decision-tree.json";
export const HEOR_DECISION_TREE_UNCERTAINTY_PLAN_PATH = "heor/decision-tree-uncertainty-plan.json";
export const HEOR_DECISION_TREE_UNCERTAINTY_RESULT_PATH = "heor/results/decision-tree-uncertainty.json";

export interface DecisionTreeEconomicBasis {
  currency: string;
  price_year: number;
  jurisdiction: string;
  perspective: string;
}

export interface DecisionTreePlanSummary {
  schemaVersion: "0.1.0" | "0.2.0";
  analysisId: string;
  referenceCaseId: string;
  referenceCaseStatus: string;
  timeHorizonYears: number;
  strategyOrder: string[];
  baselineStrategyId: string;
  strategies: Record<string, { name: string }>;
  sourceIds: string[];
  proposedAssumptionIds: string[];
  economicBasis: DecisionTreeEconomicBasis | null;
}

export interface DecisionTreeResultSummary {
  schemaVersion: "0.1.0" | "0.2.0";
  inputSha256: string;
  engineVersion: string;
  strategies: Record<string, { name: string; totalCost: number; totalQaly: number }>;
  pairwiseVsBaseline: Record<string, {
    deltaCost: number;
    deltaQaly: number;
    icer: number | null;
    interpretation: string;
  }>;
  warnings: string[];
  economicBasis: DecisionTreeEconomicBasis | null;
}

export interface DecisionTreeUncertaintySummary {
  analysisInputSha256: string;
  uncertaintyInputSha256: string;
  parameterCount: number;
  iterations: number;
  seed: number;
  convergencePassed: boolean;
  maxProbabilityMcse: number;
  probabilityDrift: number;
  optimalProbabilities: Record<string, number>;
  tieProbability: number;
}

export type DecisionTreeReviewState =
  | { kind: "loading" }
  | { kind: "absent" }
  | { kind: "invalid"; message: string }
  | {
      kind: "ready";
      plan: DecisionTreePlanSummary;
      result: DecisionTreeResultSummary | null;
      planSha256: string;
      resultCurrent: boolean;
      resultIssue?: "missing" | "invalid";
      uncertainty: DecisionTreeUncertaintySummary | null;
      uncertaintyCurrent: boolean;
      uncertaintyIssue?: "missing" | "invalid" | "stale";
    };

function record(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${path} must be an object`);
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, path: string): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${path} must be a non-empty string`);
  }
  return value;
}

function finite(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${path} must be a finite number`);
  }
  return value;
}

function integer(value: unknown, path: string): number {
  if (!Number.isSafeInteger(value)) throw new Error(`${path} must be a safe integer`);
  return value as number;
}

function digest(value: unknown, path: string): string {
  const parsed = text(value, path);
  if (!/^[a-f0-9]{64}$/.test(parsed)) throw new Error(`${path} must be a SHA-256 digest`);
  return parsed;
}

function economicBasis(value: unknown, path: string): DecisionTreeEconomicBasis {
  const basis = record(value, path);
  const expectedKeys = ["currency", "jurisdiction", "perspective", "price_year"];
  if (Object.keys(basis).sort().join("|") !== expectedKeys.join("|")) {
    throw new Error(`${path} must contain exactly currency, price_year, jurisdiction, and perspective`);
  }
  const currency = text(basis.currency, `${path}.currency`);
  if (!/^[A-Z]{3}$/.test(currency)) {
    throw new Error(`${path}.currency must be a three-letter uppercase code`);
  }
  const priceYear = basis.price_year;
  if (!Number.isInteger(priceYear) || (priceYear as number) < 1900 || (priceYear as number) > 2100) {
    throw new Error(`${path}.price_year must be an integer from 1900 to 2100`);
  }
  const boundedText = (raw: unknown, fieldPath: string) => {
    const parsed = text(raw, fieldPath);
    const hasControlCharacter = [...parsed].some((character) => {
      const codePoint = character.codePointAt(0) ?? 0;
      return codePoint < 32 || codePoint === 127;
    });
    if (parsed !== parsed.trim() || parsed.length > 160 || hasControlCharacter) {
      throw new Error(`${fieldPath} must not contain surrounding whitespace or control characters`);
    }
    return parsed;
  };
  return {
    currency,
    price_year: priceYear as number,
    jurisdiction: boundedText(basis.jurisdiction, `${path}.jurisdiction`),
    perspective: boundedText(basis.perspective, `${path}.perspective`),
  };
}

function equalEconomicBasis(
  left: DecisionTreeEconomicBasis | null,
  right: DecisionTreeEconomicBasis | null,
): boolean {
  return left?.currency === right?.currency
    && left?.price_year === right?.price_year
    && left?.jurisdiction === right?.jurisdiction
    && left?.perspective === right?.perspective;
}

function stringArray(value: unknown, path: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || !item.trim())) {
    throw new Error(`${path} must contain non-empty string ids`);
  }
  return value as string[];
}

function collectSourceIds(value: unknown, target: Set<string>): void {
  if (Array.isArray(value)) {
    value.forEach((item) => collectSourceIds(item, target));
    return;
  }
  if (!value || typeof value !== "object") return;
  Object.entries(value as Record<string, unknown>).forEach(([key, item]) => {
    if (key === "source_ids" && Array.isArray(item)) {
      item.forEach((sourceId) => {
        if (typeof sourceId === "string" && sourceId.trim()) target.add(sourceId);
      });
      return;
    }
    collectSourceIds(item, target);
  });
}

export function parseDecisionTreePlan(raw: string): DecisionTreePlanSummary {
  const value = record(JSON.parse(raw), "decision-tree plan");
  const schemaVersion = value.schema_version;
  if (value.analysis_type !== "decision_tree"
    || (schemaVersion !== "0.1.0" && schemaVersion !== "0.2.0")) {
    throw new Error("unsupported decision-tree plan contract");
  }
  if (schemaVersion === "0.1.0" && "economic_basis" in value) {
    throw new Error("legacy decision-tree plans must not claim an economic basis");
  }
  const parsedEconomicBasis = schemaVersion === "0.2.0"
    ? economicBasis(value.economic_basis, "economic_basis")
    : null;
  const referenceCase = record(value.reference_case, "reference_case");
  const strategyOrder = stringArray(value.strategy_order, "strategy_order");
  if (strategyOrder.length < 2 || new Set(strategyOrder).size !== strategyOrder.length) {
    throw new Error("strategy_order must contain at least two unique strategies");
  }
  const baselineStrategyId = text(value.baseline_strategy_id, "baseline_strategy_id");
  if (baselineStrategyId !== strategyOrder[0]) {
    throw new Error("baseline_strategy_id must be the first strategy");
  }
  const rawStrategies = record(value.strategies, "strategies");
  if (Object.keys(rawStrategies).length !== strategyOrder.length
    || strategyOrder.some((strategyId) => !(strategyId in rawStrategies))) {
    throw new Error("strategies must match strategy_order");
  }
  const strategies = Object.fromEntries(strategyOrder.map((strategyId) => {
    const strategy = record(rawStrategies[strategyId], `strategies.${strategyId}`);
    return [strategyId, { name: text(strategy.name, `strategies.${strategyId}.name`) }];
  }));
  const timeHorizonYears = finite(value.time_horizon_years, "time_horizon_years");
  if (timeHorizonYears <= 0 || timeHorizonYears > 1) {
    throw new Error("decision-tree time horizon must be greater than zero and at most one year");
  }
  const sourceIds = new Set<string>();
  collectSourceIds(value.strategies, sourceIds);
  const assumptions = Array.isArray(value.assumptions) ? value.assumptions : [];
  const proposedAssumptionIds = assumptions.flatMap((item, index) => {
    const assumption = record(item, `assumptions[${index}]`);
    return assumption.status === "proposed"
      ? [text(assumption.id, `assumptions[${index}].id`)]
      : [];
  });
  return {
    schemaVersion,
    analysisId: text(value.analysis_id, "analysis_id"),
    referenceCaseId: text(referenceCase.id, "reference_case.id"),
    referenceCaseStatus: text(referenceCase.status, "reference_case.status"),
    timeHorizonYears,
    strategyOrder,
    baselineStrategyId,
    strategies,
    sourceIds: [...sourceIds].sort(),
    proposedAssumptionIds,
    economicBasis: parsedEconomicBasis,
  };
}

export function parseDecisionTreeResult(
  raw: string,
  plan: DecisionTreePlanSummary,
): DecisionTreeResultSummary {
  const value = record(JSON.parse(raw), "decision-tree result");
  if (value.analysis_type !== "decision_tree"
    || value.calculation_classification !== "deterministic_decision_tree"
    || value.schema_version !== plan.schemaVersion
    || value.analysis_id !== plan.analysisId) {
    throw new Error("result does not identify the current decision-tree analysis");
  }
  const engineVersion = text(value.engine_version, "result.engine_version");
  if (engineVersion !== plan.schemaVersion) {
    throw new Error("result engine_version does not match the decision-tree contract");
  }
  if (plan.schemaVersion === "0.1.0" && "economic_basis" in value) {
    throw new Error("legacy decision-tree results must not claim an economic basis");
  }
  const parsedEconomicBasis = plan.schemaVersion === "0.2.0"
    ? economicBasis(value.economic_basis, "result.economic_basis")
    : null;
  if (!equalEconomicBasis(plan.economicBasis, parsedEconomicBasis)) {
    throw new Error("result economic_basis does not match the plan");
  }
  const resultOrder = stringArray(value.strategy_order, "result.strategy_order");
  if (resultOrder.length !== plan.strategyOrder.length
    || resultOrder.some((strategyId, index) => strategyId !== plan.strategyOrder[index])) {
    throw new Error("result strategy_order does not match the plan");
  }
  const rawStrategies = record(value.strategies, "result.strategies");
  const strategies = Object.fromEntries(plan.strategyOrder.map((strategyId) => {
    const row = record(rawStrategies[strategyId], `result.strategies.${strategyId}`);
    return [strategyId, {
      name: text(row.name, `result.strategies.${strategyId}.name`),
      totalCost: finite(row.total_cost, `result.strategies.${strategyId}.total_cost`),
      totalQaly: finite(row.total_qaly, `result.strategies.${strategyId}.total_qaly`),
    }];
  }));
  const rawPairwise = record(value.pairwise_vs_baseline, "result.pairwise_vs_baseline");
  const pairwiseVsBaseline = Object.fromEntries(plan.strategyOrder.slice(1).map((strategyId) => {
    const row = record(rawPairwise[strategyId], `result.pairwise_vs_baseline.${strategyId}`);
    const rawIcer = row.icer;
    if (rawIcer !== null && (typeof rawIcer !== "number" || !Number.isFinite(rawIcer))) {
      throw new Error(`result.pairwise_vs_baseline.${strategyId}.icer must be finite or null`);
    }
    return [strategyId, {
      deltaCost: finite(row.delta_cost, `result.pairwise_vs_baseline.${strategyId}.delta_cost`),
      deltaQaly: finite(row.delta_qaly, `result.pairwise_vs_baseline.${strategyId}.delta_qaly`),
      icer: rawIcer as number | null,
      interpretation: text(
        row.interpretation,
        `result.pairwise_vs_baseline.${strategyId}.interpretation`,
      ),
    }];
  }));
  const inputSha256 = text(value.input_sha256, "result.input_sha256");
  if (!/^[a-f0-9]{64}$/.test(inputSha256)) {
    throw new Error("result.input_sha256 must be a SHA-256 digest");
  }
  return {
    schemaVersion: plan.schemaVersion,
    inputSha256,
    engineVersion,
    strategies,
    pairwiseVsBaseline,
    warnings: stringArray(value.warnings, "result.warnings"),
    economicBasis: parsedEconomicBasis,
  };
}

interface DecisionTreeUncertaintyPlanSummary {
  uncertaintyId: string;
  analysisInputSha256: string;
  parameterIds: string[];
  iterations: number;
  seed: number;
  checkpoints: number[];
  maxProbabilityMcse: number;
  maxProbabilityDrift: number;
}

function parseDecisionTreeUncertaintyPlan(
  raw: string,
  planSha256: string,
): DecisionTreeUncertaintyPlanSummary {
  const value = record(JSON.parse(raw), "decision-tree uncertainty plan");
  if (value.schema_version !== "0.1.0" || value.analysis_type !== "decision_tree_uncertainty") {
    throw new Error("unsupported decision-tree uncertainty plan contract");
  }
  const analysisInput = record(value.analysis_input, "uncertainty analysis_input");
  if (analysisInput.path !== HEOR_DECISION_TREE_PLAN_PATH
    || digest(analysisInput.content_sha256, "uncertainty analysis_input.content_sha256") !== planSha256) {
    throw new Error("stale decision-tree uncertainty plan");
  }
  if (!Array.isArray(value.parameters) || value.parameters.length < 1 || value.parameters.length > 64) {
    throw new Error("uncertainty parameters must contain from 1 to 64 entries");
  }
  const parameterIds = value.parameters.map((item, index) => (
    text(record(item, `uncertainty parameters[${index}]`).id, `uncertainty parameters[${index}].id`)
  ));
  if (new Set(parameterIds).size !== parameterIds.length) {
    throw new Error("uncertainty parameter ids must be unique");
  }
  const probabilistic = record(value.probabilistic_analysis, "uncertainty probabilistic_analysis");
  const iterations = integer(probabilistic.iterations, "uncertainty iterations");
  if (iterations < 100 || iterations > 10_000) throw new Error("uncertainty iterations are outside the admitted range");
  const seed = integer(probabilistic.seed, "uncertainty seed");
  if (seed < 0) throw new Error("uncertainty seed must not be negative");
  const convergence = record(probabilistic.convergence, "uncertainty convergence");
  if (!Array.isArray(convergence.checkpoints) || convergence.checkpoints.length < 2) {
    throw new Error("uncertainty convergence checkpoints are incomplete");
  }
  const checkpoints = convergence.checkpoints.map((item, index) => integer(item, `uncertainty checkpoint[${index}]`));
  if (checkpoints.some((item, index) => item < 1 || (index > 0 && item <= checkpoints[index - 1]))
    || checkpoints[checkpoints.length - 1] !== iterations) {
    throw new Error("uncertainty convergence checkpoints are invalid");
  }
  const maxProbabilityMcse = finite(convergence.max_probability_mcse, "uncertainty max_probability_mcse");
  const maxProbabilityDrift = finite(convergence.max_probability_drift, "uncertainty max_probability_drift");
  if (maxProbabilityMcse <= 0 || maxProbabilityMcse > 0.1
    || maxProbabilityDrift <= 0 || maxProbabilityDrift > 0.1) {
    throw new Error("uncertainty convergence thresholds are invalid");
  }
  return {
    uncertaintyId: text(value.uncertainty_id, "uncertainty_id"),
    analysisInputSha256: planSha256,
    parameterIds,
    iterations,
    seed,
    checkpoints,
    maxProbabilityMcse,
    maxProbabilityDrift,
  };
}

function parseDecisionTreeUncertaintyResult(
  raw: string,
  plan: DecisionTreePlanSummary,
  uncertaintyPlan: DecisionTreeUncertaintyPlanSummary,
  planSha256: string,
  uncertaintySha256: string,
): DecisionTreeUncertaintySummary {
  const value = record(JSON.parse(raw), "decision-tree uncertainty result");
  if (value.schema_version !== "0.1.0"
    || value.engine_version !== "0.1.0"
    || value.analysis_type !== "decision_tree_uncertainty"
    || value.analysis_schema_version !== "0.2.0"
    || value.analysis_id !== plan.analysisId
    || value.uncertainty_id !== uncertaintyPlan.uncertaintyId) {
    throw new Error("uncertainty result does not identify the current analysis");
  }
  if (digest(value.analysis_input_sha256, "uncertainty result analysis hash") !== planSha256
    || digest(value.uncertainty_input_sha256, "uncertainty result plan hash") !== uncertaintySha256) {
    throw new Error("stale decision-tree uncertainty result");
  }
  if (!equalEconomicBasis(plan.economicBasis, economicBasis(value.economic_basis, "uncertainty result economic_basis"))) {
    throw new Error("uncertainty result economic basis does not match the plan");
  }
  const strategyOrder = stringArray(value.strategy_order, "uncertainty result strategy_order");
  if (strategyOrder.length !== plan.strategyOrder.length
    || strategyOrder.some((strategyId, index) => strategyId !== plan.strategyOrder[index])) {
    throw new Error("uncertainty result strategy order does not match the plan");
  }
  if (!Array.isArray(value.deterministic_analysis)
    || value.deterministic_analysis.length !== uncertaintyPlan.parameterIds.length) {
    throw new Error("uncertainty result DSA parameters do not match the plan");
  }
  const resultParameterIds = value.deterministic_analysis.map((item, index) => (
    text(record(item, `uncertainty result deterministic_analysis[${index}]`).parameter_id, `uncertainty result parameter[${index}]`)
  ));
  if (resultParameterIds.some((parameterId, index) => parameterId !== uncertaintyPlan.parameterIds[index])) {
    throw new Error("uncertainty result DSA parameter order does not match the plan");
  }
  const probabilistic = record(value.probabilistic_analysis, "uncertainty result probabilistic_analysis");
  const iterations = integer(probabilistic.iterations, "uncertainty result iterations");
  const prng = record(probabilistic.prng, "uncertainty result prng");
  const seed = integer(prng.seed, "uncertainty result seed");
  if (iterations !== uncertaintyPlan.iterations || seed !== uncertaintyPlan.seed
    || prng.algorithm !== "pcg32-xsh-rr" || prng.version !== "1") {
    throw new Error("uncertainty result run settings do not match the plan");
  }
  const rawProbabilities = record(probabilistic.optimal_probabilities, "uncertainty result optimal_probabilities");
  if (Object.keys(rawProbabilities).length !== strategyOrder.length
    || strategyOrder.some((strategyId) => !(strategyId in rawProbabilities))) {
    throw new Error("uncertainty result optimal probabilities do not match the strategies");
  }
  const optimalProbabilities = Object.fromEntries(strategyOrder.map((strategyId) => {
    const probability = finite(rawProbabilities[strategyId], `uncertainty result probability ${strategyId}`);
    if (probability < 0 || probability > 1) throw new Error("uncertainty result probability is invalid");
    return [strategyId, probability];
  }));
  const tieProbability = finite(probabilistic.tie_probability, "uncertainty result tie_probability");
  if (tieProbability < 0 || tieProbability > 1
    || Math.abs(Object.values(optimalProbabilities).reduce((sum, item) => sum + item, tieProbability) - 1) > 1e-9) {
    throw new Error("uncertainty result probabilities do not sum to one");
  }
  const convergence = record(probabilistic.convergence, "uncertainty result convergence");
  if (typeof convergence.passed !== "boolean") throw new Error("uncertainty convergence status is invalid");
  if (!Array.isArray(convergence.checkpoints) || convergence.checkpoints.length < 2) {
    throw new Error("uncertainty result convergence checkpoints are incomplete");
  }
  const maxProbabilityMcse = finite(
    record(
      convergence.checkpoints[convergence.checkpoints.length - 1],
      "uncertainty final checkpoint",
    ).max_probability_mcse,
    "uncertainty final checkpoint max_probability_mcse",
  );
  const probabilityDrift = finite(convergence.probability_drift, "uncertainty probability_drift");
  if (convergence.max_probability_mcse !== uncertaintyPlan.maxProbabilityMcse
    || convergence.max_probability_drift !== uncertaintyPlan.maxProbabilityDrift) {
    throw new Error("uncertainty convergence thresholds do not match the plan");
  }
  return {
    analysisInputSha256: planSha256,
    uncertaintyInputSha256: uncertaintySha256,
    parameterCount: resultParameterIds.length,
    iterations,
    seed,
    convergencePassed: convergence.passed,
    maxProbabilityMcse,
    probabilityDrift,
    optimalProbabilities,
    tieProbability,
  };
}

export async function loadDecisionTreeReview(): Promise<DecisionTreeReviewState> {
  try {
    const planFile = await readArtifact(HEOR_DECISION_TREE_PLAN_PATH);
    if (!planFile) return { kind: "absent" };
    const resultFile = await readArtifact(HEOR_DECISION_TREE_RESULT_PATH);
    const uncertaintyPlanFile = await readArtifact(HEOR_DECISION_TREE_UNCERTAINTY_PLAN_PATH);
    const uncertaintyResultFile = await readArtifact(HEOR_DECISION_TREE_UNCERTAINTY_RESULT_PATH);
    return reviewDecisionTreeArtifacts(
      planFile.data,
      resultFile?.data ?? null,
      uncertaintyPlanFile?.data ?? null,
      uncertaintyResultFile?.data ?? null,
    );
  } catch (error) {
    return { kind: "invalid", message: error instanceof Error ? error.message : String(error) };
  }
}

export async function reviewDecisionTreeArtifacts(
  planRaw: string,
  resultRaw: string | null,
  uncertaintyPlanRaw: string | null = null,
  uncertaintyResultRaw: string | null = null,
): Promise<DecisionTreeReviewState> {
  try {
    const plan = parseDecisionTreePlan(planRaw);
    const planSha256 = await sha256Text(planRaw);
    if (resultRaw === null) {
      return {
        kind: "ready",
        plan,
        result: null,
        planSha256,
        resultCurrent: false,
        resultIssue: "missing",
        uncertainty: null,
        uncertaintyCurrent: false,
      };
    }
    try {
      const result = parseDecisionTreeResult(resultRaw, plan);
      const resultCurrent = result.inputSha256 === planSha256;
      let uncertainty: DecisionTreeUncertaintySummary | null = null;
      let uncertaintyIssue: "missing" | "invalid" | "stale" | undefined;
      if (uncertaintyPlanRaw !== null) {
        try {
          const uncertaintyPlan = parseDecisionTreeUncertaintyPlan(uncertaintyPlanRaw, planSha256);
          if (uncertaintyResultRaw === null) {
            uncertaintyIssue = "missing";
          } else if (!resultCurrent) {
            uncertaintyIssue = "stale";
          } else {
            const uncertaintySha256 = await sha256Text(uncertaintyPlanRaw);
            uncertainty = parseDecisionTreeUncertaintyResult(
              uncertaintyResultRaw,
              plan,
              uncertaintyPlan,
              planSha256,
              uncertaintySha256,
            );
          }
        } catch (error) {
          uncertaintyIssue = error instanceof Error && error.message.includes("stale")
            ? "stale"
            : "invalid";
        }
      }
      return {
        kind: "ready",
        plan,
        result,
        planSha256,
        resultCurrent,
        uncertainty,
        uncertaintyCurrent: uncertainty !== null,
        ...(uncertaintyIssue ? { uncertaintyIssue } : {}),
      };
    } catch {
      return {
        kind: "ready",
        plan,
        result: null,
        planSha256,
        resultCurrent: false,
        resultIssue: "invalid",
        uncertainty: null,
        uncertaintyCurrent: false,
      };
    }
  } catch (error) {
    return { kind: "invalid", message: error instanceof Error ? error.message : String(error) };
  }
}

export function DecisionTreeReview({
  state,
  locale,
  onRefresh,
  onRun,
  onOpenPlan,
  onOpenResult,
  onOpenUncertaintyResult,
}: {
  state: DecisionTreeReviewState;
  locale?: string;
  onRefresh: () => void;
  onRun: () => void;
  onOpenPlan?: () => void;
  onOpenResult?: () => void;
  onOpenUncertaintyResult?: () => void;
}) {
  const { t, i18n } = useTranslation("heor");
  const activeLocale = locale ?? i18n.language;
  const number = new Intl.NumberFormat(activeLocale, { maximumFractionDigits: 3 });
  const percent = new Intl.NumberFormat(activeLocale, { style: "percent", maximumFractionDigits: 1 });
  if (state.kind === "loading") {
    return <section className="px-5 py-8 text-sm text-muted">{t("panel.loading")}</section>;
  }
  if (state.kind === "absent") return null;
  if (state.kind === "invalid") {
    return (
      <section className="border-b border-border px-5 py-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-error">
          <AlertTriangle size={16} /> {t("decisionTree.invalidTitle")}
        </div>
        <p className="mt-2 text-xs leading-5 text-muted">{t("decisionTree.invalidBody")}</p>
        <button type="button" onClick={onRun} className="mt-3 text-xs font-medium text-link hover:underline">
          {t("decisionTree.repair")}
        </button>
      </section>
    );
  }
  const currentResult = state.resultCurrent ? state.result : null;
  const sourceSummary = t("decisionTree.sourceSummary", {
    sources: state.plan.sourceIds.length,
    assumptions: state.plan.proposedAssumptionIds.length,
  });
  return (
    <section className="border-b border-border px-5 py-4" data-metric-source={HEOR_DECISION_TREE_RESULT_PATH}>
      <div className="flex items-start gap-2">
        <ShieldCheck size={16} className={currentResult ? "text-ok" : "text-warn"} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-text">{t("decisionTree.title")}</div>
          <div className={cn("mt-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]", currentResult ? "text-ok" : "text-warn")}>
            {currentResult
              ? t("decisionTree.current")
              : state.result && !state.resultCurrent
                ? t("decisionTree.stale")
                : state.resultIssue === "invalid"
                  ? t("decisionTree.invalidResult")
                  : t("decisionTree.missingResult")}
          </div>
        </div>
        <button type="button" onClick={onRefresh} aria-label={t("panel.refresh")} className="rounded p-1 text-muted hover:bg-surface-2 hover:text-text">
          <RefreshCw size={14} />
        </button>
      </div>

      <dl className="mt-3 grid grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] gap-x-3 gap-y-1.5">
        <dt className="text-[11px] text-muted">{t("decisionTree.analysis")}</dt>
        <dd className="break-words text-right text-[11px] font-medium text-text">{state.plan.analysisId}</dd>
        <dt className="text-[11px] text-muted">{t("decisionTree.referenceCase")}</dt>
        <dd className="break-words text-right text-[11px] font-medium text-text">{state.plan.referenceCaseId} · {state.plan.referenceCaseStatus}</dd>
        <dt className="text-[11px] text-muted">{t("decisionTree.horizon")}</dt>
        <dd className="text-right text-[11px] font-medium text-text">{number.format(state.plan.timeHorizonYears)} {t("decisionTree.years")}</dd>
        {state.plan.economicBasis && (
          <>
            <dt className="text-[11px] text-muted">{t("decisionTree.economicBasis")}</dt>
            <dd className="break-words text-right text-[11px] font-medium text-text">
              {state.plan.economicBasis.currency} · {state.plan.economicBasis.price_year} · {state.plan.economicBasis.jurisdiction} · {state.plan.economicBasis.perspective}
            </dd>
          </>
        )}
      </dl>
      <p className="mt-3 text-[10px] leading-4 text-muted">{sourceSummary}</p>

      <div className="mt-3 flex flex-wrap gap-3 text-[10px]">
        {onOpenPlan && <button type="button" onClick={onOpenPlan} className="flex items-center gap-1 text-link hover:underline"><FileJson size={12} />{t("decisionTree.openPlan")}</button>}
        {currentResult && onOpenResult && <button type="button" onClick={onOpenResult} className="flex items-center gap-1 text-link hover:underline"><FileJson size={12} />{t("decisionTree.openResult")}</button>}
      </div>

      {currentResult ? (
        <>
          <div className="mt-4 overflow-hidden rounded-input border border-border">
            <table className="w-full text-[10px]">
              <thead className="bg-bg text-muted"><tr><th className="px-2 py-2 text-left font-medium">{t("result.strategy")}</th><th className="px-2 py-2 text-right font-medium">{t("result.cost")}</th><th className="px-2 py-2 text-right font-medium">{t("result.qaly")}</th></tr></thead>
              <tbody>{state.plan.strategyOrder.map((strategyId) => {
                const row = currentResult.strategies[strategyId];
                return <tr key={strategyId} className="border-t border-border"><td className="px-2 py-2 text-text">{row.name}</td><td className="px-2 py-2 text-right tabular-nums text-text">{number.format(row.totalCost)}</td><td className="px-2 py-2 text-right tabular-nums text-text">{number.format(row.totalQaly)}</td></tr>;
              })}</tbody>
            </table>
          </div>
          {state.plan.strategyOrder.slice(1).map((strategyId) => {
            const row = currentResult.pairwiseVsBaseline[strategyId];
            return (
              <div key={strategyId} className="mt-3 grid grid-cols-3 gap-2">
                <Metric label={t("result.deltaCost")} value={number.format(row.deltaCost)} onOpen={onOpenResult} />
                <Metric label={t("result.deltaQaly")} value={number.format(row.deltaQaly)} onOpen={onOpenResult} />
                <Metric label={t("result.icer")} value={row.icer === null ? "—" : number.format(row.icer)} onOpen={onOpenResult} />
              </div>
            );
          })}
          <p className="mt-3 text-[10px] leading-4 text-muted">{t("decisionTree.calculationOnly")}</p>
          {state.uncertaintyCurrent && state.uncertainty && (
            <div className="mt-4 border-t border-border pt-4" data-metric-source={HEOR_DECISION_TREE_UNCERTAINTY_RESULT_PATH}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold text-text">{t("decisionTree.uncertainty.title")}</div>
                  <div className="mt-0.5 text-[10px] text-muted">
                    {t("decisionTree.uncertainty.summary", {
                      iterations: state.uncertainty.iterations,
                      parameters: state.uncertainty.parameterCount,
                      parameterLabel: t(state.uncertainty.parameterCount === 1
                        ? "decisionTree.uncertainty.parameterOne"
                        : "decisionTree.uncertainty.parameterMany"),
                    })}
                  </div>
                </div>
                {onOpenUncertaintyResult && (
                  <button type="button" onClick={onOpenUncertaintyResult} className="flex items-center gap-1 text-[10px] text-link hover:underline">
                    <FileJson size={12} />{t("decisionTree.uncertainty.openResult")}
                  </button>
                )}
              </div>
              <div className={cn(
                "mt-2 text-[10px] font-medium",
                state.uncertainty.convergencePassed ? "text-ok" : "text-warn",
              )}>
                {state.uncertainty.convergencePassed
                  ? t("decisionTree.uncertainty.convergencePassed")
                  : t("decisionTree.uncertainty.convergenceNotPassed")}
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[10px] text-muted">
                {state.plan.strategyOrder.map((strategyId) => (
                  <span key={strategyId}>
                    {state.plan.strategies[strategyId].name} <strong className="font-semibold text-text">{percent.format(state.uncertainty!.optimalProbabilities[strategyId])}</strong>
                  </span>
                ))}
                <span>{t("decisionTree.uncertainty.tie")} <strong className="font-semibold text-text">{percent.format(state.uncertainty.tieProbability)}</strong></span>
              </div>
              <p className="mt-3 text-[10px] leading-4 text-muted">{t("decisionTree.uncertainty.calculationOnly")}</p>
            </div>
          )}
        </>
      ) : (
        <div className="mt-3 rounded-input border border-warn/30 bg-warn/5 px-3 py-3">
          <p className="text-[11px] leading-5 text-muted">{t("decisionTree.blockedNote")}</p>
          <button type="button" onClick={onRun} className="mt-2 flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
            <Play size={13} /> {t("decisionTree.run")}
          </button>
        </div>
      )}
    </section>
  );
}

function Metric({ label, value, onOpen }: { label: string; value: string; onOpen?: () => void }) {
  const { t } = useTranslation("heor");
  return (
    <button
      type="button"
      disabled={!onOpen}
      onClick={onOpen}
      aria-label={t("metricProvenance.aria", { label, value })}
      className="rounded-input border border-border bg-bg px-2 py-2 text-center outline-none hover:bg-surface-2 disabled:cursor-default disabled:hover:bg-bg"
    >
      <div className="text-[9px] text-muted">{label}</div>
      <div className="mt-1 text-[11px] font-semibold tabular-nums text-text">{value}</div>
    </button>
  );
}

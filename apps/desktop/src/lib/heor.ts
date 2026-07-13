import { isTauri } from "./tauri";

export const HEOR_PLAN_PATH = "heor/analysis-plan.json";
export const HEOR_CONCEPTUAL_MODEL_PATH = "heor/conceptual-model.json";
export const HEOR_REFERENCE_CASE_ASSESSMENT_PATH = "heor/reference-case-assessment.json";
export const HEOR_UNCERTAINTY_PLAN_PATH = "heor/uncertainty-plan.json";
export const HEOR_BUDGET_IMPACT_PLAN_PATH = "heor/budget-impact-plan.json";

export type HeorGate =
  | "decision_problem"
  | "conceptual_model"
  | "analysis_plan"
  | "independent_validation"
  | "release";

export type HeorApprovalAction = "approve" | "revoke";

export interface HeorApprovalRequest {
  projectId: string;
  gate: HeorGate;
  action: HeorApprovalAction;
  artifactSha256: string;
  actorLabel: string;
  rationale: string;
}

export interface HeorApprovalEvent extends HeorApprovalRequest {
  schemaVersion: number;
  sequence: number;
  eventId: string;
  timestamp: number;
  assurance: string;
  previousHash: string | null;
  eventHash: string;
  relatedArtifacts?: Array<{ path: string; sha256: string }>;
}

export interface HeorApprovalLog {
  events: HeorApprovalEvent[];
  effectiveApprovedGates: HeorGate[];
  chainHead: string | null;
  integrity: string;
  identityAssurance: string;
}

export interface HeorDecisionProblem {
  title: string;
  population: string;
  intervention: string;
  comparator: string;
  perspective: string;
  time_horizon_years: number;
  outcome: string;
  jurisdiction?: string;
}

export interface HeorStrategy {
  name: string;
  initial_distribution: number[];
  transition_matrix: number[][];
  state_costs: number[];
  state_utilities: number[];
}

export interface HeorEvidenceSource {
  id: string;
  title: string;
  source_type: string;
  url?: string;
  local_path?: string;
  content_sha256?: string;
  published_on?: string;
  accessed_on: string;
  supports?: string;
}

export interface HeorAssumption {
  id: string;
  statement: string;
  reason?: string;
  status: "unresolved" | "proposed" | "rejected";
}

export interface HeorInputProvenance {
  path: string;
  source_ids?: string[];
  assumption_ids?: string[];
  unit: string;
  jurisdiction: string;
  price_year?: number;
  selection_rationale: string;
  uncertainty_status: "fixed" | "range_available" | "distribution_available";
}

export interface HeorEvidenceAudit {
  complete: boolean;
  status: "complete" | "incomplete";
  requiredInputs: number;
  coveredInputs: number;
  unsupportedInputs: string[];
  invalidMappings: string[];
  unresolvedAssumptions: string[];
  sourceCount: number;
  mappingCount: number;
}

export interface HeorConceptualModel {
  schema_version: "0.1.0";
  model_id: string;
  analysis_id: string;
  status: "draft" | "ready_for_human_review";
  objective: string;
  scope: {
    population: string;
    intervention: string;
    comparator: string;
    perspective: string;
    time_horizon: string;
    outcomes: string[];
    jurisdiction: string;
    decision_context: string;
  };
  care_pathway: string[];
  model_type: { proposed: string; rationale: string };
  states: Array<{ id: string; label: string; definition: string; absorbing: boolean }>;
  transitions: Array<{ id: string; from: string; to: string; trigger: string }>;
  structural_assumptions: Array<{
    id: string;
    statement: string;
    rationale: string;
    status: "unresolved" | "proposed" | "rejected";
  }>;
  structural_alternatives: Array<{
    id: string;
    description: string;
    rationale: string;
    expected_impact: string;
  }>;
  evidence_links: Array<{ claim: string; source_ids: string[] }>;
  validation_plan: { face: string[]; internal: string[]; external: string[] };
  validation_questions: string[];
}

export interface HeorConceptualModelAudit {
  complete: boolean;
  status: "complete" | "incomplete";
  errors: string[];
  stateCount: number;
  transitionCount: number;
  assumptionCount: number;
  alternativeCount: number;
  unresolvedAssumptions: string[];
}

export interface HeorReferenceCaseAudit {
  complete: boolean;
  status: "complete" | "incomplete";
  profileId: string;
  profileStatus: "current" | "draft";
  profileRevision: string;
  profileSha256: string;
  assessmentSha256: string | null;
  requiredCount: number;
  metRequiredCount: number;
  recommendedCount: number;
  metRecommendedCount: number;
  blockingGaps: string[];
  recommendedGaps: string[];
  unresolvedRequirements: string[];
  notApplicableRequirements: string[];
  notApplicableRequiredCount: number;
  errors: string[];
}

export interface HeorUncertaintyAudit {
  complete: boolean;
  status: "complete" | "incomplete";
  uncertaintyId: string;
  analysisId: string;
  analysisPlanSha256: string;
  uncertaintySha256: string;
  seed: string | null;
  parameterCount: number;
  scenarioCount: number;
  iterations: number | null;
  omittedParameterCount: number;
  invalidParameters: string[];
  errors: string[];
}

export interface HeorBudgetImpactAudit {
  complete: boolean;
  status: "complete" | "incomplete";
  biaId: string;
  analysisId: string;
  analysisPlanSha256: string;
  budgetImpactSha256: string;
  horizonYears: number | null;
  populationYearCount: number;
  costCategoryCount: number;
  nonPatientCostCount: number;
  sensitivityParameterCount: number;
  scenarioCount: number;
  requiredInputCount: number;
  coveredInputCount: number;
  invalidInputs: string[];
  errors: string[];
}

export interface HeorAnalysisPlan {
  schema_version: "0.1.0";
  analysis_id: string;
  input_status?: string;
  decision_problem: HeorDecisionProblem;
  reference_case: { id: string; status: "current" | "draft" | "custom" };
  reference_case_assessment?: { path: string; content_sha256: string };
  uncertainty_analysis?: { path: string };
  budget_impact_analysis?: { path: string };
  states: string[];
  cycles: number;
  cycle_length_years: number;
  discount_rates: { costs: number; outcomes: number };
  half_cycle_correction: boolean;
  willingness_to_pay: number | null;
  methodology?: {
    cost_scope?: {
      included_categories: string[];
      perspective_alignment: string;
      exclusions?: Array<{ category: string; rationale: string }>;
    };
    uncertainty_analysis?: {
      deterministic: { planned: boolean; input_paths: string[] };
      probabilistic: { planned: boolean; input_paths: string[]; iterations: number };
      structural_scenarios: string[];
    };
  };
  strategies: {
    comparator: HeorStrategy;
    intervention: HeorStrategy;
  };
  evidence_sources?: HeorEvidenceSource[];
  assumptions?: HeorAssumption[];
  input_provenance?: HeorInputProvenance[];
}

export interface HeorStrategyResult {
  name: string;
  total_cost: number;
  total_qaly: number;
  net_monetary_benefit: number | null;
  occupancy: number[][];
}

export interface HeorCalculation {
  analysis_id: string;
  engine_version: string;
  schema_version: string;
  reference_case: {
    id: string;
    status: string;
    compliance_assessed: boolean;
  };
  calculation_classification: "calculation_only";
  warnings: string[];
  strategies: {
    comparator: HeorStrategyResult;
    intervention: HeorStrategyResult;
  };
  incremental: {
    delta_cost: number;
    delta_qaly: number;
    icer: number | null;
    incremental_net_monetary_benefit: number | null;
    interpretation: string;
  };
  input_sha256: string;
}

export interface HeorWorkflowStatus {
    classification: "exploratory" | "analysis_authorized_local_assertion";
    decisionReady: false;
    effectiveApprovedGates: HeorGate[];
    inputSha256: string;
    analysisPlanMatchesInput: boolean;
    conceptualModelMatchesArtifact: boolean;
    referenceCaseRegistryStatus: string;
    referenceCaseAudit: HeorReferenceCaseAudit;
    uncertaintyPlanMatchesApproval: boolean;
    uncertaintyAudit: HeorUncertaintyAudit;
    budgetImpactPlanMatchesApproval: boolean;
    budgetImpactAudit: HeorBudgetImpactAudit;
    approvalChainHead: string | null;
    approvalIntegrity: string;
    identityAssurance: string;
    evidenceAudit: HeorEvidenceAudit;
}

export interface HeorRunResult {
  calculation: HeorCalculation;
  workflow: HeorWorkflowStatus;
}

export interface HeorUncertaintyCalculation {
  analysis_id: string;
  uncertainty_id: string;
  engine_version: string;
  schema_version: string;
  base_analysis_sha256: string;
  uncertainty_plan_sha256: string;
  prng: { algorithm: string; version: string };
  seed: string;
  calculation_classification: "calculation_only";
  base_case: HeorCalculation["incremental"];
  deterministic_analysis: Array<{
    parameter_id: string;
    label: string;
    target: string;
    incremental_nmb_span: number;
  }>;
  probabilistic_analysis: {
    iterations: number;
    cost_effective_probability: number;
    mean_incremental_net_monetary_benefit: number;
    incremental_net_monetary_benefit_mcse: number;
    convergence: {
      passed: boolean;
      probability_drift: number;
      max_probability_mcse: number;
      max_probability_drift: number;
    };
    omitted_parameters: Array<{ provenance_path: string; rationale: string }>;
  };
  structural_scenarios: Array<{ scenario_id: string; label: string }>;
  limitations: string[];
}

export interface HeorUncertaintyRunResult {
  calculation: HeorUncertaintyCalculation;
  workflow: HeorWorkflowStatus;
}

export interface HeorBudgetImpactCalculation {
  analysis_id: string;
  bia_id: string;
  engine_version: string;
  schema_version: string;
  analysis_plan_sha256: string;
  budget_impact_plan_sha256: string;
  calculation_classification: "calculation_only";
  horizon_years: 3;
  discount_rate: 0;
  currency: string;
  price_year: number;
  base_case: {
    annual_results: Array<{
      year: number;
      eligible_population: number;
      without_new_intervention_share: number;
      with_new_intervention_share: number;
      without_new_intervention_cost: number;
      with_new_intervention_cost: number;
      net_budget_impact: number;
    }>;
    annual_net_budget_impact: number[];
    cumulative_net_budget_impact: number;
  };
  one_way_sensitivity: Array<{
    parameter_id: string;
    label: string;
    target: string;
    cumulative_span: number;
  }>;
  alternative_scenarios: Array<{
    scenario_id: string;
    label: string;
    cumulative_net_budget_impact: number;
  }>;
  limitations: string[];
  warnings: string[];
}

export interface HeorBudgetImpactRunResult {
  calculation: HeorBudgetImpactCalculation;
  workflow: HeorWorkflowStatus;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Parse enough of the app/engine contract to render a safe review snapshot.
 *  The deterministic engine remains the authoritative numerical validator. */
export function parseHeorPlan(raw: string): HeorAnalysisPlan {
  const value: unknown = JSON.parse(raw);
  if (!isRecord(value)) throw new Error("analysis plan must be a JSON object");
  if (value.schema_version !== "0.1.0") {
    throw new Error("analysis plan schema_version must be 0.1.0");
  }
  if (typeof value.analysis_id !== "string" || !value.analysis_id.trim()) {
    throw new Error("analysis plan must include analysis_id");
  }
  if (!isRecord(value.decision_problem)) {
    throw new Error("analysis plan must include decision_problem metadata");
  }
  if (!isRecord(value.reference_case) || !isRecord(value.strategies)) {
    throw new Error("analysis plan must include reference_case and strategies");
  }
  if (!isRecord(value.strategies.comparator) || !isRecord(value.strategies.intervention)) {
    throw new Error("analysis plan must include comparator and intervention strategies");
  }
  if (!Array.isArray(value.states) || value.states.length === 0) {
    throw new Error("analysis plan must include health states");
  }
  return value as unknown as HeorAnalysisPlan;
}

export function parseHeorConceptualModel(raw: string): HeorConceptualModel {
  const value: unknown = JSON.parse(raw);
  if (!isRecord(value)) throw new Error("conceptual model must be a JSON object");
  if (value.schema_version !== "0.1.0") {
    throw new Error("conceptual model schema_version must be 0.1.0");
  }
  if (typeof value.model_id !== "string" || !value.model_id.trim()) {
    throw new Error("conceptual model must include model_id");
  }
  return value as unknown as HeorConceptualModel;
}

const BASE_INPUT_PATHS = [
  "cycles",
  "cycle_length_years",
  "discount_rates.costs",
  "discount_rates.outcomes",
  "half_cycle_correction",
  "strategies.comparator.initial_distribution",
  "strategies.comparator.transition_matrix",
  "strategies.comparator.state_costs",
  "strategies.comparator.state_utilities",
  "strategies.intervention.initial_distribution",
  "strategies.intervention.transition_matrix",
  "strategies.intervention.state_costs",
  "strategies.intervention.state_utilities",
] as const;

function nonempty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function validSha256(value: unknown): boolean {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}

function nonemptyStrings(value: unknown): value is string[] {
  return Array.isArray(value) && value.length > 0 && value.every(nonempty);
}

/** Browser-side preview of the Rust conceptual-model approval audit. */
export function auditHeorConceptualModel(
  model: HeorConceptualModel,
  expectedAnalysisId?: string,
): HeorConceptualModelAudit {
  const errors: string[] = [];
  if (model.schema_version !== "0.1.0") errors.push("schema_version must be 0.1.0");
  for (const field of ["model_id", "analysis_id", "objective"] as const) {
    if (!nonempty(model[field])) errors.push(`${field} is required`);
  }
  if (expectedAnalysisId !== undefined && model.analysis_id !== expectedAnalysisId) {
    errors.push("conceptual model analysis_id does not match the current analysis plan");
  }
  if (!(model.status === "draft" || model.status === "ready_for_human_review")) {
    errors.push("status is invalid");
  }
  const scope = model.scope;
  for (const field of [
    "population", "intervention", "comparator", "perspective",
    "time_horizon", "jurisdiction", "decision_context",
  ] as const) {
    if (!nonempty(scope?.[field])) errors.push(`scope.${field} is required`);
  }
  if (!nonemptyStrings(scope?.outcomes)) {
    errors.push("scope.outcomes must be a non-empty string array");
  }
  if (!nonemptyStrings(model.care_pathway)) {
    errors.push("care_pathway must be a non-empty string array");
  }
  if (!nonempty(model.model_type?.proposed) || !nonempty(model.model_type?.rationale)) {
    errors.push("model_type requires proposed and rationale");
  }

  const states = Array.isArray(model.states) ? model.states : [];
  if (states.length < 2) errors.push("at least two states are required");
  const stateIds = new Set<string>();
  const absorbing = new Set<string>();
  states.forEach((state, index) => {
    if (!nonempty(state.id) || stateIds.has(state.id)) {
      errors.push(`states[${index}].id must be non-empty and unique`);
    } else stateIds.add(state.id);
    if (!nonempty(state.label) || !nonempty(state.definition)) {
      errors.push(`states[${index}] requires label and definition`);
    }
    if (typeof state.absorbing !== "boolean") {
      errors.push(`states[${index}].absorbing must be boolean`);
    } else if (state.absorbing) absorbing.add(state.id);
  });

  const transitions = Array.isArray(model.transitions) ? model.transitions : [];
  if (transitions.length === 0) errors.push("at least one transition is required");
  const transitionIds = new Set<string>();
  const outgoing = new Set<string>();
  transitions.forEach((transition, index) => {
    if (!nonempty(transition.id) || transitionIds.has(transition.id)) {
      errors.push(`transitions[${index}].id must be non-empty and unique`);
    } else transitionIds.add(transition.id);
    if (!stateIds.has(transition.from) || !stateIds.has(transition.to)) {
      errors.push(`transitions[${index}] references an unknown state`);
    } else {
      outgoing.add(transition.from);
      if (absorbing.has(transition.from) && transition.from !== transition.to) {
        errors.push(`transitions[${index}] leaves absorbing state ${transition.from}`);
      }
    }
    if (!nonempty(transition.trigger)) errors.push(`transitions[${index}].trigger is required`);
  });
  const missingOutgoing = [...stateIds].filter((id) => !outgoing.has(id)).sort();
  if (missingOutgoing.length) {
    errors.push(`states without outgoing transitions: ${missingOutgoing.join(", ")}`);
  }

  const assumptions = Array.isArray(model.structural_assumptions)
    ? model.structural_assumptions : [];
  if (assumptions.length === 0) errors.push("at least one structural assumption is required");
  const assumptionIds = new Set<string>();
  const unresolvedAssumptions: string[] = [];
  assumptions.forEach((assumption, index) => {
    if (!nonempty(assumption.id) || assumptionIds.has(assumption.id)) {
      errors.push(`structural_assumptions[${index}].id must be non-empty and unique`);
    } else assumptionIds.add(assumption.id);
    if (!nonempty(assumption.statement) || !nonempty(assumption.rationale)) {
      errors.push(`structural_assumptions[${index}] requires statement and rationale`);
    }
    if (!(["unresolved", "proposed", "rejected"] as string[]).includes(assumption.status)) {
      errors.push(`structural_assumptions[${index}].status is invalid`);
    } else if (assumption.status === "unresolved") unresolvedAssumptions.push(assumption.id);
  });

  const alternatives = Array.isArray(model.structural_alternatives)
    ? model.structural_alternatives : [];
  if (alternatives.length === 0) errors.push("at least one structural alternative is required");
  const alternativeIds = new Set<string>();
  alternatives.forEach((alternative, index) => {
    if (!nonempty(alternative.id) || alternativeIds.has(alternative.id)) {
      errors.push(`structural_alternatives[${index}].id must be non-empty and unique`);
    } else alternativeIds.add(alternative.id);
    for (const field of ["description", "rationale", "expected_impact"] as const) {
      if (!nonempty(alternative[field])) {
        errors.push(`structural_alternatives[${index}].${field} is required`);
      }
    }
  });
  if (!Array.isArray(model.evidence_links)) errors.push("evidence_links must be an array");
  else model.evidence_links.forEach((link, index) => {
    if (!nonempty(link.claim) || !nonemptyStrings(link.source_ids)) {
      errors.push(`evidence_links[${index}] requires claim and source_ids`);
    }
  });
  if (!nonemptyStrings(model.validation_questions)) {
    errors.push("validation_questions must be a non-empty string array");
  }
  for (const field of ["face", "internal", "external"] as const) {
    if (!nonemptyStrings(model.validation_plan?.[field])) {
      errors.push(`validation_plan.${field} must be a non-empty string array`);
    }
  }
  if (unresolvedAssumptions.length) {
    errors.push(`unresolved structural assumptions: ${unresolvedAssumptions.join(", ")}`);
  }

  return {
    complete: errors.length === 0,
    status: errors.length === 0 ? "complete" : "incomplete",
    errors,
    stateCount: states.length,
    transitionCount: transitions.length,
    assumptionCount: assumptions.length,
    alternativeCount: alternatives.length,
    unresolvedAssumptions,
  };
}

/** Browser-side review preview. The Rust command repeats this audit and is the
 * authoritative approval boundary. */
export function auditHeorEvidence(plan: HeorAnalysisPlan): HeorEvidenceAudit {
  const requiredPaths: string[] = [...BASE_INPUT_PATHS];
  if (plan.willingness_to_pay !== null) requiredPaths.push("willingness_to_pay");
  const required = new Set<string>(requiredPaths);
  const sourceIdCounts = new Map<string, number>();
  for (const source of plan.evidence_sources ?? []) {
    sourceIdCounts.set(source.id, (sourceIdCounts.get(source.id) ?? 0) + 1);
  }
  const validSources = new Set(
    (plan.evidence_sources ?? [])
      .filter((source) => {
        const locator = nonempty(source.url) || nonempty(source.local_path);
        const snapshot = !source.local_path || validSha256(source.content_sha256);
        return nonempty(source.id) && sourceIdCounts.get(source.id) === 1
          && nonempty(source.title) && nonempty(source.source_type)
          && nonempty(source.accessed_on) && locator && snapshot;
      })
      .map((source) => source.id),
  );
  const statuses = new Map(
    (plan.assumptions ?? [])
      .filter((item) => nonempty(item.id) && nonempty(item.statement) && nonempty(item.reason))
      .map((item) => [item.id, item.status]),
  );
  const unresolvedAssumptions = (plan.assumptions ?? [])
    .filter((item) => item.status === "unresolved")
    .map((item) => item.id);
  const seen = new Set<string>();
  const covered = new Set<string>();
  const invalidMappings: string[] = [];

  for (const mapping of plan.input_provenance ?? []) {
    const reasons: string[] = [];
    if (!required.has(mapping.path)) reasons.push("path is not a required model input");
    if (seen.has(mapping.path)) reasons.push("path is duplicated");
    seen.add(mapping.path);
    if (!nonempty(mapping.unit)) reasons.push("unit is missing");
    if (!nonempty(mapping.jurisdiction)) reasons.push("jurisdiction is missing");
    if (!nonempty(mapping.selection_rationale)) reasons.push("selection rationale is missing");
    if (!(["fixed", "range_available", "distribution_available"] as string[])
      .includes(mapping.uncertainty_status)) reasons.push("uncertainty status is invalid");
    if ((mapping.path.endsWith("state_costs") || mapping.path === "willingness_to_pay")
      && (!Number.isInteger(mapping.price_year) || (mapping.price_year ?? 0) < 1900)) {
      reasons.push("price year is missing");
    }
    const sourceIds = (mapping.source_ids ?? []).filter(nonempty);
    const assumptionIds = (mapping.assumption_ids ?? []).filter(nonempty);
    if (sourceIds.length === 0 && assumptionIds.length === 0) {
      reasons.push("no evidence source or reviewable assumption is linked");
    }
    if (sourceIds.some((id) => !validSources.has(id))) {
      reasons.push("source link is missing or source metadata is incomplete");
    }
    if (assumptionIds.some((id) => statuses.get(id) !== "proposed")) {
      reasons.push("assumption link is missing or is not proposed for human review");
    }
    if (reasons.length === 0) covered.add(mapping.path);
    else invalidMappings.push(`${mapping.path || "mapping"}: ${reasons.join("; ")}`);
  }

  const unsupportedInputs = requiredPaths.filter((path) => !covered.has(path));
  const complete = unsupportedInputs.length === 0
    && invalidMappings.length === 0
    && unresolvedAssumptions.length === 0;
  return {
    complete,
    status: complete ? "complete" : "incomplete",
    requiredInputs: requiredPaths.length,
    coveredInputs: covered.size,
    unsupportedInputs,
    invalidMappings,
    unresolvedAssumptions,
    sourceCount: validSources.size,
    mappingCount: plan.input_provenance?.length ?? 0,
  };
}

export async function sha256Text(value: string): Promise<string> {
  const encoded = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Add the domain skill explicitly without hiding the workbench contract from
 *  the conversation history. The provider can vary; the artifact contract does not. */
export function buildHeorPrompt(userText: string): string {
  return [
    "Use $heor-workbench for this request.",
    "Work through natural-language dialogue first. Maintain heor/analysis-plan.json only when the decision problem and inputs are sufficiently defined; never create or claim human approvals.",
    "",
    userText.trim(),
  ].join("\n");
}

export async function listHeorApprovals(projectId: string): Promise<HeorApprovalLog> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorApprovalLog>("list_heor_approvals", { projectId });
}

export async function appendHeorApproval(
  request: HeorApprovalRequest,
): Promise<HeorApprovalEvent> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorApprovalEvent>("append_heor_approval", { request });
}

export async function runHeorMarkov(
  projectId: string,
  inputPath = HEOR_PLAN_PATH,
): Promise<HeorRunResult> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorRunResult>("run_heor_markov", { projectId, inputPath });
}

export async function auditHeorReferenceCase(): Promise<HeorReferenceCaseAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_REFERENCE_CASE_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorReferenceCaseAudit>("audit_heor_reference_case");
}

export async function auditHeorUncertainty(): Promise<HeorUncertaintyAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_UNCERTAINTY_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorUncertaintyAudit>("audit_heor_uncertainty");
}

export async function auditHeorBudgetImpact(): Promise<HeorBudgetImpactAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_BUDGET_IMPACT_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorBudgetImpactAudit>("audit_heor_budget_impact");
}

export async function runHeorUncertainty(
  projectId: string,
): Promise<HeorUncertaintyRunResult> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorUncertaintyRunResult>("run_heor_uncertainty", { projectId });
}

export async function runHeorBudgetImpact(
  projectId: string,
): Promise<HeorBudgetImpactRunResult> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorBudgetImpactRunResult>("run_heor_budget_impact", { projectId });
}

/** Browser-only fixture for interaction and visual regression. Values are a
 *  workflow example, not clinical evidence and never ship into a user project. */
export const HEOR_BROWSER_DEMO_PLAN: HeorAnalysisPlan = {
  schema_version: "0.1.0",
  analysis_id: "first-line-nsclc-demo",
  input_status: "workflow_demo",
  decision_problem: {
    title: "Cost-effectiveness of a new first-line treatment for advanced NSCLC",
    population: "Adults with untreated advanced NSCLC",
    intervention: "New treatment",
    comparator: "Standard care",
    perspective: "Chinese healthcare system",
    time_horizon_years: 3,
    outcome: "QALY",
    jurisdiction: "China",
  },
  reference_case: { id: "CN-2020-current", status: "current" },
  uncertainty_analysis: { path: HEOR_UNCERTAINTY_PLAN_PATH },
  budget_impact_analysis: { path: HEOR_BUDGET_IMPACT_PLAN_PATH },
  states: ["stable", "progressed", "dead"],
  cycles: 3,
  cycle_length_years: 1,
  discount_rates: { costs: 0.05, outcomes: 0.05 },
  half_cycle_correction: true,
  willingness_to_pay: 100_000,
  strategies: {
    comparator: {
      name: "standard_care",
      initial_distribution: [1, 0, 0],
      transition_matrix: [[0.7, 0.2, 0.1], [0, 0.7, 0.3], [0, 0, 1]],
      state_costs: [1_000, 3_000, 0],
      state_utilities: [0.8, 0.5, 0],
    },
    intervention: {
      name: "new_treatment",
      initial_distribution: [1, 0, 0],
      transition_matrix: [[0.8, 0.15, 0.05], [0, 0.75, 0.25], [0, 0, 1]],
      state_costs: [4_000, 3_000, 0],
      state_utilities: [0.8, 0.5, 0],
    },
  },
  evidence_sources: [],
  assumptions: [
    {
      id: "demo-only",
      statement: "All numeric inputs are synthetic workflow-test values.",
      reason: "Browser interaction fixture",
      status: "unresolved",
    },
  ],
};

export const HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL: HeorConceptualModel = {
  schema_version: "0.1.0",
  model_id: "first-line-nsclc-conceptual-demo",
  analysis_id: HEOR_BROWSER_DEMO_PLAN.analysis_id,
  status: "ready_for_human_review",
  objective: "Compare the incremental costs and QALYs of new treatment and standard care",
  scope: {
    population: HEOR_BROWSER_DEMO_PLAN.decision_problem.population,
    intervention: HEOR_BROWSER_DEMO_PLAN.decision_problem.intervention,
    comparator: HEOR_BROWSER_DEMO_PLAN.decision_problem.comparator,
    perspective: HEOR_BROWSER_DEMO_PLAN.decision_problem.perspective,
    time_horizon: "Three years for the workflow demonstration",
    outcomes: ["cost", "QALY"],
    jurisdiction: "China",
    decision_context: "Demonstration reimbursement assessment",
  },
  care_pathway: ["Start first-line treatment", "Remain stable or progress", "Death"],
  model_type: {
    proposed: "cohort_state_transition",
    rationale: "Three mutually exclusive states represent the demonstration decision problem",
  },
  states: [
    { id: "stable", label: "Stable", definition: "No recorded progression", absorbing: false },
    { id: "progressed", label: "Progressed", definition: "Recorded progression", absorbing: false },
    { id: "dead", label: "Dead", definition: "All-cause death", absorbing: true },
  ],
  transitions: [
    { id: "stable-stable", from: "stable", to: "stable", trigger: "No progression" },
    { id: "stable-progressed", from: "stable", to: "progressed", trigger: "Progression" },
    { id: "progressed-progressed", from: "progressed", to: "progressed", trigger: "Remain progressed" },
    { id: "progressed-dead", from: "progressed", to: "dead", trigger: "Death" },
    { id: "dead-dead", from: "dead", to: "dead", trigger: "Absorbing state" },
  ],
  structural_assumptions: [{
    id: "memoryless-demo",
    statement: "Transition risk depends only on current state",
    rationale: "Required by the demonstration cohort model",
    status: "proposed",
  }],
  structural_alternatives: [{
    id: "partitioned-survival-demo",
    description: "Partitioned survival structure",
    rationale: "A plausible oncology modeling alternative",
    expected_impact: "Could change extrapolated state occupancy",
  }],
  evidence_links: [{ claim: "Demonstration pathway only", source_ids: ["demo-only"] }],
  validation_plan: {
    face: ["Clinical expert review of the pathway and state definitions"],
    internal: ["Boundary, formula, and mass-conservation checks"],
    external: ["Compare simulated outcomes with an independent applicable dataset"],
  },
  validation_questions: ["Are the three demonstration states exhaustive and mutually exclusive?"],
};

export const HEOR_BROWSER_DEMO_REFERENCE_CASE_AUDIT: HeorReferenceCaseAudit = {
  complete: false,
  status: "incomplete",
  profileId: "CN-2020-current",
  profileStatus: "current",
  profileRevision: "T/CPHARMA 003-2020",
  profileSha256: "0".repeat(64),
  assessmentSha256: null,
  requiredCount: 13,
  metRequiredCount: 0,
  recommendedCount: 1,
  metRecommendedCount: 0,
  blockingGaps: ["cost-scope", "uncertainty-analysis"],
  recommendedGaps: [],
  unresolvedRequirements: [],
  notApplicableRequirements: [],
  notApplicableRequiredCount: 0,
  errors: ["heor/reference-case-assessment.json is required"],
};

export const HEOR_BROWSER_DEMO_UNCERTAINTY_AUDIT: HeorUncertaintyAudit = {
  complete: false,
  status: "incomplete",
  uncertaintyId: "",
  analysisId: HEOR_BROWSER_DEMO_PLAN.analysis_id,
  analysisPlanSha256: "",
  uncertaintySha256: "",
  seed: null,
  parameterCount: 0,
  scenarioCount: 0,
  iterations: null,
  omittedParameterCount: 0,
  invalidParameters: [],
  errors: ["heor/uncertainty-plan.json is required"],
};

export const HEOR_BROWSER_DEMO_BUDGET_IMPACT_AUDIT: HeorBudgetImpactAudit = {
  complete: false,
  status: "incomplete",
  biaId: "",
  analysisId: HEOR_BROWSER_DEMO_PLAN.analysis_id,
  analysisPlanSha256: "",
  budgetImpactSha256: "",
  horizonYears: null,
  populationYearCount: 0,
  costCategoryCount: 0,
  nonPatientCostCount: 0,
  sensitivityParameterCount: 0,
  scenarioCount: 0,
  requiredInputCount: 0,
  coveredInputCount: 0,
  invalidInputs: [],
  errors: ["heor/budget-impact-plan.json is required"],
};

export function browserDemoRun(
  inputSha256: string,
  approvedGates: HeorGate[],
): HeorRunResult {
  const evidenceAudit = auditHeorEvidence(HEOR_BROWSER_DEMO_PLAN);
  const referenceCaseAudit = HEOR_BROWSER_DEMO_REFERENCE_CASE_AUDIT;
  const uncertaintyAudit = HEOR_BROWSER_DEMO_UNCERTAINTY_AUDIT;
  const budgetImpactAudit = HEOR_BROWSER_DEMO_BUDGET_IMPACT_AUDIT;
  const authorized = approvedGates.includes("analysis_plan")
    && evidenceAudit.complete && referenceCaseAudit.complete && uncertaintyAudit.complete
    && budgetImpactAudit.complete;
  return {
    calculation: {
      analysis_id: HEOR_BROWSER_DEMO_PLAN.analysis_id,
      engine_version: "0.1.0",
      schema_version: "0.1.0",
      reference_case: {
        id: "CN-2020-current",
        status: "current",
        compliance_assessed: false,
      },
      calculation_classification: "calculation_only",
      input_sha256: inputSha256,
      strategies: {
        comparator: {
          name: "standard_care",
          total_cost: 3475.2885931111646,
          total_qaly: 1.6883071262009621,
          net_monetary_benefit: 165355.42402698507,
          occupancy: [],
        },
        intervention: {
          name: "new_treatment",
          total_cost: 9649.958833579349,
          total_qaly: 1.8826406968498464,
          net_monetary_benefit: 178614.11085140528,
          occupancy: [],
        },
      },
      incremental: {
        delta_cost: 6174.670240468184,
        delta_qaly: 0.19433357064888424,
        icer: 31773.56449454831,
        incremental_net_monetary_benefit: 13258.68682442024,
        interpretation: "tradeoff",
      },
      warnings: [
        "Workflow authorization is not a calculation-engine responsibility; the desktop must apply verified approval state.",
        "Reference-case compliance has not been assessed by the deterministic engine.",
      ],
    },
    workflow: {
      classification: authorized ? "analysis_authorized_local_assertion" : "exploratory",
      decisionReady: false,
      effectiveApprovedGates: approvedGates,
      inputSha256,
      analysisPlanMatchesInput: authorized,
      conceptualModelMatchesArtifact: approvedGates.includes("conceptual_model"),
      referenceCaseRegistryStatus: "current",
      referenceCaseAudit,
      uncertaintyPlanMatchesApproval: false,
      uncertaintyAudit,
      budgetImpactPlanMatchesApproval: false,
      budgetImpactAudit,
      approvalChainHead: null,
      approvalIntegrity: "verified_unanchored_sha256_chain",
      identityAssurance: "local_human_assertion",
      evidenceAudit,
    },
  };
}

import { isTauri } from "./tauri";

export const HEOR_PLAN_PATH = "heor/analysis-plan.json";

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

export interface HeorAnalysisPlan {
  schema_version: "0.1.0";
  analysis_id: string;
  input_status?: string;
  decision_problem: HeorDecisionProblem;
  reference_case: { id: string; status: "current" | "draft" | "custom" };
  states: string[];
  cycles: number;
  cycle_length_years: number;
  discount_rates: { costs: number; outcomes: number };
  half_cycle_correction: boolean;
  willingness_to_pay: number | null;
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

export interface HeorRunResult {
  calculation: HeorCalculation;
  workflow: {
    classification: "exploratory" | "analysis_authorized_local_assertion";
    decisionReady: false;
    effectiveApprovedGates: HeorGate[];
    inputSha256: string;
    analysisPlanMatchesInput: boolean;
    referenceCaseRegistryStatus: string;
    approvalChainHead: string | null;
    approvalIntegrity: string;
    identityAssurance: string;
    evidenceAudit: HeorEvidenceAudit;
  };
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

export function browserDemoRun(
  inputSha256: string,
  approvedGates: HeorGate[],
): HeorRunResult {
  const evidenceAudit = auditHeorEvidence(HEOR_BROWSER_DEMO_PLAN);
  const authorized = approvedGates.includes("analysis_plan") && evidenceAudit.complete;
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
      referenceCaseRegistryStatus: "current",
      approvalChainHead: null,
      approvalIntegrity: "verified_unanchored_sha256_chain",
      identityAssurance: "local_human_assertion",
      evidenceAudit,
    },
  };
}

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
  title: string;
  url: string;
  published_on?: string;
  accessed_on?: string;
  supports?: string;
}

export interface HeorAssumption {
  id?: string;
  statement: string;
  reason?: string;
  status?: string;
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
  const authorized = approvedGates.includes("analysis_plan");
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
    },
  };
}

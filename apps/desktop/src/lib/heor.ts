import { isTauri } from "./tauri";

export const HEOR_PLAN_PATH = "heor/analysis-plan.json";
export const HEOR_CONCEPTUAL_MODEL_PATH = "heor/conceptual-model.json";
export const HEOR_REFERENCE_CASE_ASSESSMENT_PATH = "heor/reference-case-assessment.json";
export const HEOR_UNCERTAINTY_PLAN_PATH = "heor/uncertainty-plan.json";
export const HEOR_BUDGET_IMPACT_PLAN_PATH = "heor/budget-impact-plan.json";
export const HEOR_MODEL_VALIDATION_PATH = "heor/model-validation.json";
export const HEOR_REPORT_PACKAGE_PATH = "heor/report-package.json";
export const HEOR_REPORT_DOCUMENT_PATH = "heor/report.md";
export const HEOR_EVIDENCE_SEARCH_REQUEST_PATH = "heor/evidence-search-request.json";
export const HEOR_EVIDENCE_SYNTHESIS_PATH = "heor/evidence-synthesis.json";
export const HEOR_EVIDENCE_LIBRARY_PATH = "heor/evidence-library.json";
export const HEOR_BASE_CASE_RESULT_PATH = "heor/results/base-case.json";
export const HEOR_UNCERTAINTY_RESULT_PATH = "heor/results/uncertainty.json";
export const HEOR_BUDGET_IMPACT_RESULT_PATH = "heor/results/budget-impact.json";

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
  extraction_ids?: string[];
  assumption_ids?: string[];
  unit: string;
  jurisdiction: string;
  currency?: string;
  price_year?: number;
  monetary_adjustments?: Array<{
    target_index?: number;
    source_value: number;
    source_currency: string;
    source_price_year: number;
    factor: number;
    method: string;
    basis_ids: string[];
  }>;
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
  sourceBasedInputs: number;
  selectedExtractionCount: number;
}

export interface HeorEvidenceSelectionAudit {
  complete: boolean;
  status: "complete" | "incomplete";
  synthesisSha256: string;
  selectedInputCount: number;
  selectedExtractionCount: number;
  verifiedExtractionCount: number;
  unverifiedExtractionIds: string[];
  rejectedExtractionIds: string[];
  invalidSelections: string[];
  errors: string[];
  verificationIntegrity: string;
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
  primaryThreshold: number | null;
  thresholdCount: number;
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

export interface HeorModelValidationAudit {
  complete: boolean;
  approvable: boolean;
  status: "complete" | "incomplete";
  validationId: string;
  analysisId: string;
  validationSha256: string;
  analysisPlanSha256: string;
  conceptualModelSha256: string;
  uncertaintyPlanSha256: string;
  budgetImpactPlanSha256: string;
  reviewerLabel: string;
  recommendation:
    | "pending"
    | "approve_for_intended_use"
    | "approve_with_limitations"
    | "do_not_approve";
  evidenceCount: number;
  checkCount: number;
  requiredCoverageCount: number;
  coveredRequirementCount: number;
  issueCount: number;
  openBlockingIssueCount: number;
  openMinorIssueCount: number;
  invalidEvidence: string[];
  missingCoverage: string[];
  errors: string[];
}

export interface HeorReportingAudit {
  complete: boolean;
  releasable: boolean;
  status: "complete" | "incomplete";
  packageId: string;
  analysisId: string;
  reportPackageSha256: string;
  releaseOwnerLabel: string;
  bindingHashes: Record<string, string>;
  reportingItemCount: number;
  requiredItemCount: number;
  coveredItemCount: number;
  missingItems: string[];
  invalidItems: string[];
  errors: string[];
}

export interface HeorEvidenceSearchAudit {
  complete: boolean;
  status: "complete" | "incomplete";
  requestId: string;
  requestSha256: string;
  query: string;
  sources: Array<"pubmed" | "clinicaltrials">;
  maxResultsPerSource: number | null;
  dateFrom: string | null;
  dateTo: string | null;
  containsSensitiveData: boolean | null;
  errors: string[];
}

export interface HeorEvidenceRecord {
  recordId: string;
  title: string;
  locator: string;
  sourceType: string;
  publishedOn?: string;
  authors?: string[];
  doi?: string;
  metadata: Record<string, unknown>;
}

export interface HeorSourceSearchRun {
  source: string;
  endpoint: string;
  requestUrls: string[];
  totalCount: number;
  fetchedCount: number;
  responseSha256: string[];
  records: HeorEvidenceRecord[];
  limitations: string[];
}

export interface HeorEvidenceSearchResult {
  schemaVersion: "0.1.0";
  requestId: string;
  requestSha256: string;
  query: string;
  dateFrom: string | null;
  dateTo: string | null;
  maxResultsPerSource: number;
  executedAt: number;
  executedOn: string;
  authorizationEventId: string;
  outputPath: string;
  sourceRuns: HeorSourceSearchRun[];
  records: HeorEvidenceRecord[];
  limitations: string[];
}

export interface HeorSearchAuthorizationRequest {
  projectId: string;
  requestSha256: string;
  actorLabel: string;
  rationale: string;
  confirmedNoSensitiveData: true;
}

export interface HeorSearchAuthorizationEvent {
  schemaVersion: number;
  sequence: number;
  eventId: string;
  projectId: string;
  requestSha256: string;
  sources: string[];
  actorLabel: string;
  rationale: string;
  timestamp: number;
  outputPath: string;
  outputSha256: string;
  assurance: string;
  previousHash: string | null;
  eventHash: string;
}

export interface HeorSearchExecutionResponse {
  result: HeorEvidenceSearchResult;
  authorization: HeorSearchAuthorizationEvent;
}

export interface HeorSearchAuthorizationLog {
  events: HeorSearchAuthorizationEvent[];
  chainHead: string | null;
  integrity: string;
  identityAssurance: string;
}

export interface HeorEvidenceSynthesisAudit {
  complete: boolean;
  importable: boolean;
  status: "complete" | "incomplete";
  synthesisId: string;
  synthesisSha256: string;
  searchCount: number;
  recordCount: number;
  notAssessedCount: number;
  includedCount: number;
  extractionCount: number;
  eligibleExtractionIds: string[];
  eligibleExtractions: HeorReviewableExtraction[];
  appVerifiedExtractionIds: string[];
  unverifiedExtractionIds: string[];
  rejectedExtractionIds: string[];
  requiredReviewersPerExtraction: number;
  reviewConfirmationCount: number;
  humanReviewComplete: boolean;
  verificationIntegrity: string;
  unresolvedConflicts: string[];
  errors: string[];
  importBlockers: string[];
}

export interface HeorReviewableExtraction {
  extractionId: string;
  recordId: string;
  target: string;
  extractedValue: string;
  sourceLocation: string;
  applicability: string;
}

export interface HeorEvidenceLibraryAudit {
  complete: boolean;
  searchable: boolean;
  stale: boolean;
  status: "complete" | "incomplete";
  manifestSha256: string;
  documentCount: number;
  indexedCount: number;
  requiresOcrCount: number;
  failedCount: number;
  totalBytes: number;
  errors: string[];
}

export interface HeorEvidenceLibrarySearchHit {
  path: string;
  sourceSha256: string;
  page: number;
  score: number;
  snippet: string;
}

export interface HeorEvidenceLibrarySearchResponse {
  audit: HeorEvidenceLibraryAudit;
  query: string;
  hits: HeorEvidenceLibrarySearchHit[];
}

export interface HeorImportCandidatesRequest {
  projectId: string;
  outputPath: string;
  outputSha256: string;
  synthesisSha256: string;
}

export interface HeorImportCandidatesResponse {
  audit: HeorEvidenceSynthesisAudit;
  addedSearches: number;
  addedRecords: number;
  reconciledRecords: number;
  sourceRunPath: string;
  sourceRunSha256: string;
}

export interface HeorEvidenceVerificationRequest {
  projectId: string;
  synthesisSha256: string;
  extractionIds: string[];
  actorLabel: string;
  rationale: string;
  decision: "confirmed" | "rejected";
}

export interface HeorAnalysisPlan {
  schema_version: "0.1.0" | "0.2.0";
  analysis_id: string;
  economic_basis?: { currency: string; price_year: number };
  input_status?: string;
  decision_problem: HeorDecisionProblem;
  reference_case: { id: string; status: "current" | "draft" | "custom" };
  reference_case_assessment?: { path: string; content_sha256: string };
  uncertainty_analysis?: { path: string };
  budget_impact_analysis?: { path: string };
  evidence_synthesis?: { path: string; content_sha256: string };
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
  economic_basis: { currency: string; price_year: number } | null;
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
    classification:
      | "exploratory"
      | "analysis_authorized_local_assertion"
      | "decision_ready_local_release_assertion";
    decisionReady: boolean;
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
    independentValidationMatchesApproval: boolean;
    validationAudit: HeorModelValidationAudit;
    releaseMatchesApproval: boolean;
    reportingAudit: HeorReportingAudit;
    approvalChainHead: string | null;
    approvalIntegrity: string;
    identityAssurance: string;
    evidenceAudit: HeorEvidenceAudit;
    evidenceSelectionAudit: HeorEvidenceSelectionAudit;
    evidenceSynthesisMatchesApproval: boolean;
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
  economic_basis: HeorCalculation["economic_basis"];
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
    decision_uncertainty: {
      method: "net_monetary_benefit";
      primary_threshold: number;
      threshold_source: "declared_grid" | "legacy_primary_only";
      threshold_rationale: string;
      threshold_results: Array<{
        threshold: number;
        expected_incremental_net_monetary_benefit: number;
        intervention_optimal_probability: number;
        comparator_optimal_probability: number;
        tie_probability: number;
        probability_mcse: number;
        strategy_with_highest_expected_net_benefit: "comparator" | "intervention" | "tie";
        ceaf_probability: number | null;
        per_person_evpi: number;
        per_person_evpi_mcse: number;
      }>;
      population_evpi: null;
      evppi: null;
    };
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
  if (value.schema_version !== "0.1.0" && value.schema_version !== "0.2.0") {
    throw new Error("analysis plan schema_version must be 0.1.0 or 0.2.0");
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

function currencyCode(value: unknown): value is string {
  return typeof value === "string" && /^[A-Z]{3}$/.test(value);
}

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function modelValue(plan: HeorAnalysisPlan, path: string): unknown {
  let current: unknown = plan;
  for (const token of path.split(".")) {
    if (!isRecord(current) || !(token in current)) return undefined;
    current = current[token];
  }
  return current;
}

function monetaryAdjustmentReasons(
  plan: HeorAnalysisPlan,
  mapping: HeorInputProvenance,
  validBasisIds: Set<string>,
): string[] {
  const reasons: string[] = [];
  const basis = plan.economic_basis;
  if (!basis || !currencyCode(basis.currency)
    || !Number.isInteger(basis.price_year) || basis.price_year < 1900 || basis.price_year > 2100) {
    return ["current economic_basis is missing or invalid"];
  }
  if (mapping.currency !== basis.currency) {
    reasons.push("currency does not match economic_basis.currency");
  }
  if (mapping.price_year !== basis.price_year) {
    reasons.push("price_year does not match economic_basis.price_year");
  }
  const target = modelValue(plan, mapping.path);
  const targetValues = Array.isArray(target) ? target : [target];
  if (targetValues.length === 0
    || targetValues.some((value) => !finiteNumber(value) || value < 0)) {
    return [...reasons, "model monetary value is missing, non-finite, or negative"];
  }
  const adjustments = mapping.monetary_adjustments;
  if (!Array.isArray(adjustments) || adjustments.length !== targetValues.length) {
    return [...reasons, "monetary_adjustments must cover every model value exactly once"];
  }
  const seen = new Set<number>();
  adjustments.forEach((adjustment, position) => {
    const label = `monetary_adjustments[${position}]`;
    const targetIndex = Array.isArray(target) ? adjustment.target_index : 0;
    if (Array.isArray(target)) {
      if (!Number.isInteger(targetIndex) || (targetIndex ?? -1) < 0
        || (targetIndex ?? targetValues.length) >= targetValues.length) {
        reasons.push(`${label}.target_index is invalid`);
        return;
      }
    } else if (adjustment.target_index !== undefined) {
      reasons.push(`${label}.target_index must be omitted for a scalar`);
    }
    const index = targetIndex ?? 0;
    if (seen.has(index)) {
      reasons.push(`${label}.target_index is duplicated`);
      return;
    }
    seen.add(index);
    if (!finiteNumber(adjustment.source_value) || adjustment.source_value < 0) {
      reasons.push(`${label}.source_value must be finite and non-negative`);
      return;
    }
    if (!finiteNumber(adjustment.factor) || adjustment.factor <= 0) {
      reasons.push(`${label}.factor must be finite and positive`);
      return;
    }
    if (!currencyCode(adjustment.source_currency)) {
      reasons.push(`${label}.source_currency must be an ISO 4217-format code`);
    }
    if (!Number.isInteger(adjustment.source_price_year)
      || adjustment.source_price_year < 1900 || adjustment.source_price_year > 2100) {
      reasons.push(`${label}.source_price_year must be from 1900 to 2100`);
    }
    const expected = targetValues[index] as number;
    const tolerance = Math.max(1e-6, Math.abs(expected) * 1e-9);
    if (Math.abs(adjustment.source_value * adjustment.factor - expected) > tolerance) {
      reasons.push(`${label} does not reproduce model value`);
    }
    const sameBasis = adjustment.source_currency === basis.currency
      && adjustment.source_price_year === basis.price_year;
    const ids = Array.isArray(adjustment.basis_ids) ? adjustment.basis_ids : [];
    if (sameBasis && Math.abs(adjustment.factor - 1) <= 1e-12) {
      if (adjustment.method !== "none" || ids.length > 0) {
        reasons.push(`${label} must use method none and no basis_ids when no adjustment is needed`);
      }
    } else {
      if (!nonempty(adjustment.method) || adjustment.method.toLowerCase() === "none") {
        reasons.push(`${label}.method must explain the applied adjustment`);
      }
      if (ids.length === 0 || ids.some((id) => !validBasisIds.has(id))) {
        reasons.push(`${label}.basis_ids must link valid evidence or proposed assumptions`);
      }
    }
  });
  if (seen.size !== targetValues.length) {
    reasons.push("monetary_adjustments do not cover every target index");
  }
  return reasons;
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
  if (plan.schema_version !== "0.2.0") {
    invalidMappings.push("schema_version must be 0.2.0 for approval review");
  }
  if (!plan.economic_basis || !currencyCode(plan.economic_basis.currency)
    || !Number.isInteger(plan.economic_basis.price_year)
    || plan.economic_basis.price_year < 1900 || plan.economic_basis.price_year > 2100) {
    invalidMappings.push("economic_basis must declare a valid currency and price_year");
  }
  const validBasisIds = new Set([
    ...validSources,
    ...Array.from(statuses.entries())
      .filter(([, status]) => status === "proposed")
      .map(([id]) => id),
  ]);
  let sourceBasedInputs = 0;
  const selectedExtractions = new Set<string>();
  const synthesisBindingValid = plan.evidence_synthesis?.path === HEOR_EVIDENCE_SYNTHESIS_PATH
    && validSha256(plan.evidence_synthesis.content_sha256);

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
    if (mapping.path.endsWith("state_costs") || mapping.path === "willingness_to_pay") {
      reasons.push(...monetaryAdjustmentReasons(plan, mapping, validBasisIds));
    }
    const sourceIds = (mapping.source_ids ?? []).filter(nonempty);
    const extractionIds = (mapping.extraction_ids ?? []).filter(nonempty);
    const assumptionIds = (mapping.assumption_ids ?? []).filter(nonempty);
    if (sourceIds.length === 0 && assumptionIds.length === 0) {
      reasons.push("no evidence source or reviewable assumption is linked");
    }
    if (sourceIds.some((id) => !validSources.has(id))) {
      reasons.push("source link is missing or source metadata is incomplete");
    }
    if (sourceIds.length > 0) {
      sourceBasedInputs += 1;
      if (!synthesisBindingValid) reasons.push("current evidence synthesis binding is missing or invalid");
      if (extractionIds.length === 0) reasons.push("source-based input has no selected extraction");
      if (new Set(extractionIds).size !== extractionIds.length) {
        reasons.push("selected extraction IDs are duplicated");
      }
      extractionIds.forEach((id) => selectedExtractions.add(id));
    } else if (extractionIds.length > 0) {
      reasons.push("extraction IDs require at least one evidence source");
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
    sourceBasedInputs,
    selectedExtractionCount: selectedExtractions.size,
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

export async function auditHeorModelValidation(): Promise<HeorModelValidationAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorModelValidationAudit>("audit_heor_model_validation");
}

export async function auditHeorReporting(): Promise<HeorReportingAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_REPORTING_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorReportingAudit>("audit_heor_reporting");
}

export async function auditHeorEvidenceSearch(): Promise<HeorEvidenceSearchAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_EVIDENCE_SEARCH_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorEvidenceSearchAudit>("audit_heor_evidence_search");
}

export async function auditHeorEvidenceSynthesis(): Promise<HeorEvidenceSynthesisAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_EVIDENCE_SYNTHESIS_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorEvidenceSynthesisAudit>("audit_heor_evidence_synthesis");
}

export async function auditHeorEvidenceSelection(): Promise<HeorEvidenceSelectionAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_EVIDENCE_SELECTION_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorEvidenceSelectionAudit>("audit_heor_evidence_selection");
}

export async function verifyHeorEvidenceExtractions(
  request: HeorEvidenceVerificationRequest,
): Promise<HeorEvidenceSynthesisAudit> {
  if (!isTauri) throw new Error("evidence verification is available only in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorEvidenceSynthesisAudit>("verify_heor_evidence_extractions", { request });
}

export async function auditHeorEvidenceLibrary(): Promise<HeorEvidenceLibraryAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_EVIDENCE_LIBRARY_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorEvidenceLibraryAudit>("audit_heor_evidence_library");
}

export async function addHeorLibraryFiles(): Promise<string[]> {
  if (!isTauri) return [];
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string[]>("add_heor_library_files");
}

export async function syncHeorEvidenceLibrary(projectId: string): Promise<HeorEvidenceLibraryAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_EVIDENCE_LIBRARY_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorEvidenceLibraryAudit>("sync_heor_evidence_library", { projectId });
}

export async function searchHeorEvidenceLibrary(
  query: string,
  limit = 10,
): Promise<HeorEvidenceLibrarySearchResponse> {
  if (!isTauri) return {
    audit: HEOR_BROWSER_DEMO_EVIDENCE_LIBRARY_AUDIT,
    query,
    hits: [],
  };
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorEvidenceLibrarySearchResponse>("search_heor_evidence_library", {
    query,
    limit,
  });
}

export async function listHeorSearchAuthorizations(
  projectId: string,
): Promise<HeorSearchAuthorizationLog> {
  if (!isTauri) return {
    events: [],
    chainHead: null,
    integrity: "verified_unanchored_sha256_chain",
    identityAssurance: "local_human_assertion",
  };
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorSearchAuthorizationLog>("list_heor_search_authorizations", { projectId });
}

export async function importHeorSearchCandidates(
  request: HeorImportCandidatesRequest,
): Promise<HeorImportCandidatesResponse> {
  if (!isTauri) throw new Error("candidate import is available only in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorImportCandidatesResponse>("import_heor_search_candidates", { request });
}

export async function executeHeorEvidenceSearch(
  authorization: HeorSearchAuthorizationRequest,
): Promise<HeorSearchExecutionResponse> {
  if (!isTauri) throw new Error("evidence search is available only in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorSearchExecutionResponse>("execute_heor_evidence_search", { authorization });
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
export const HEOR_BROWSER_DEMO_EVIDENCE_SEARCH_AUDIT: HeorEvidenceSearchAudit = {
  complete: true,
  status: "complete",
  requestId: "semaglutide-t2d-demo",
  requestSha256: "d".repeat(64),
  query: "semaglutide AND type 2 diabetes AND cost effectiveness",
  sources: ["pubmed", "clinicaltrials"],
  maxResultsPerSource: 10,
  dateFrom: "2020-01-01",
  dateTo: "2026-07-14",
  containsSensitiveData: false,
  errors: [],
};

export const HEOR_BROWSER_DEMO_EVIDENCE_SYNTHESIS_AUDIT: HeorEvidenceSynthesisAudit = {
  complete: false,
  importable: true,
  status: "incomplete",
  synthesisId: "semaglutide-t2d-demo",
  synthesisSha256: "e".repeat(64),
  searchCount: 2,
  recordCount: 18,
  notAssessedCount: 12,
  includedCount: 4,
  extractionCount: 2,
  eligibleExtractionIds: ["extract-cost", "extract-utility"],
  eligibleExtractions: [
    {
      extractionId: "extract-cost",
      recordId: "trial-cost-1",
      target: "strategies.intervention.state_costs",
      extractedValue: "CNY 12,500 per cycle",
      sourceLocation: "Table 3, intervention arm",
      applicability: "Chinese payer setting; 2026 price year adjustment pending",
    },
    {
      extractionId: "extract-utility",
      recordId: "trial-utility-1",
      target: "strategies.intervention.state_utilities",
      extractedValue: "0.74 progression-free utility",
      sourceLocation: "Supplement, Table S8",
      applicability: "Advanced NSCLC population",
    },
  ],
  appVerifiedExtractionIds: [],
  unverifiedExtractionIds: ["extract-cost", "extract-utility"],
  rejectedExtractionIds: [],
  requiredReviewersPerExtraction: 2,
  reviewConfirmationCount: 0,
  humanReviewComplete: false,
  verificationIntegrity: "verified_unanchored_sha256_chain",
  unresolvedConflicts: ["utility-weight-selection"],
  errors: ["12 records remain not_assessed", "unresolved conflicts: utility-weight-selection"],
  importBlockers: [],
};

export const HEOR_BROWSER_DEMO_EVIDENCE_SELECTION_AUDIT: HeorEvidenceSelectionAudit = {
  complete: false,
  status: "incomplete",
  synthesisSha256: "e".repeat(64),
  selectedInputCount: 2,
  selectedExtractionCount: 2,
  verifiedExtractionCount: 0,
  unverifiedExtractionIds: ["extract-cost", "extract-utility"],
  rejectedExtractionIds: [],
  invalidSelections: [],
  errors: [],
  verificationIntegrity: "verified_unanchored_sha256_chain",
};

export const HEOR_BROWSER_DEMO_EVIDENCE_LIBRARY_AUDIT: HeorEvidenceLibraryAudit = {
  complete: true,
  searchable: true,
  stale: false,
  status: "complete",
  manifestSha256: "f".repeat(64),
  documentCount: 3,
  indexedCount: 3,
  requiresOcrCount: 0,
  failedCount: 0,
  totalBytes: 1_280_000,
  errors: [],
};

export const HEOR_BROWSER_DEMO_PLAN: HeorAnalysisPlan = {
  schema_version: "0.2.0",
  analysis_id: "first-line-nsclc-demo",
  economic_basis: { currency: "CNY", price_year: 2026 },
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
  primaryThreshold: null,
  thresholdCount: 0,
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

export const HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT: HeorModelValidationAudit = {
  complete: false,
  approvable: false,
  status: "incomplete",
  validationId: "",
  analysisId: HEOR_BROWSER_DEMO_PLAN.analysis_id,
  validationSha256: "",
  analysisPlanSha256: "",
  conceptualModelSha256: "",
  uncertaintyPlanSha256: "",
  budgetImpactPlanSha256: "",
  reviewerLabel: "",
  recommendation: "pending",
  evidenceCount: 0,
  checkCount: 0,
  requiredCoverageCount: 18,
  coveredRequirementCount: 0,
  issueCount: 0,
  openBlockingIssueCount: 0,
  openMinorIssueCount: 0,
  invalidEvidence: [],
  missingCoverage: ["heor/model-validation.json is required"],
  errors: ["heor/model-validation.json is required"],
};

export const HEOR_BROWSER_DEMO_REPORTING_AUDIT: HeorReportingAudit = {
  complete: false,
  releasable: false,
  status: "incomplete",
  packageId: "",
  analysisId: HEOR_BROWSER_DEMO_PLAN.analysis_id,
  reportPackageSha256: "",
  releaseOwnerLabel: "",
  bindingHashes: {},
  reportingItemCount: 0,
  requiredItemCount: 40,
  coveredItemCount: 0,
  missingItems: ["heor/report-package.json is required"],
  invalidItems: [],
  errors: ["heor/report-package.json is required"],
};

export function browserDemoRun(
  inputSha256: string,
  approvedGates: HeorGate[],
): HeorRunResult {
  const evidenceAudit = auditHeorEvidence(HEOR_BROWSER_DEMO_PLAN);
  const referenceCaseAudit = HEOR_BROWSER_DEMO_REFERENCE_CASE_AUDIT;
  const uncertaintyAudit = HEOR_BROWSER_DEMO_UNCERTAINTY_AUDIT;
  const budgetImpactAudit = HEOR_BROWSER_DEMO_BUDGET_IMPACT_AUDIT;
  const validationAudit = HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT;
  const reportingAudit = HEOR_BROWSER_DEMO_REPORTING_AUDIT;
  const authorized = approvedGates.includes("analysis_plan")
    && evidenceAudit.complete && referenceCaseAudit.complete && uncertaintyAudit.complete
    && budgetImpactAudit.complete;
  return {
    calculation: {
      analysis_id: HEOR_BROWSER_DEMO_PLAN.analysis_id,
      engine_version: "0.2.0",
      schema_version: "0.2.0",
      reference_case: {
        id: "CN-2020-current",
        status: "current",
        compliance_assessed: false,
      },
      economic_basis: { currency: "CNY", price_year: 2026 },
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
      independentValidationMatchesApproval: false,
      validationAudit,
      releaseMatchesApproval: false,
      reportingAudit,
      approvalChainHead: null,
      approvalIntegrity: "verified_unanchored_sha256_chain",
      identityAssurance: "local_human_assertion",
      evidenceAudit,
      evidenceSelectionAudit: HEOR_BROWSER_DEMO_EVIDENCE_SELECTION_AUDIT,
      evidenceSynthesisMatchesApproval: false,
    },
  };
}

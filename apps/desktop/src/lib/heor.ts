import { isTauri } from "./tauri";

export const HEOR_PLAN_PATH = "heor/analysis-plan.json";
export const HEOR_CONCEPTUAL_MODEL_PATH = "heor/conceptual-model.json";
export const HEOR_REFERENCE_CASE_ASSESSMENT_PATH = "heor/reference-case-assessment.json";
export const HEOR_UNCERTAINTY_PLAN_PATH = "heor/uncertainty-plan.json";
export const HEOR_BUDGET_IMPACT_PLAN_PATH = "heor/budget-impact-plan.json";
export const HEOR_PARTITIONED_SURVIVAL_PLAN_PATH = "heor/partitioned-survival-plan.json";
export const HEOR_SURVIVAL_EXTRAPOLATION_REVIEW_PATH = "heor/survival-extrapolation-review.json";
export const HEOR_SURVIVAL_EXTRAPOLATION_REVIEW_INDEX_PATH = "heor/survival-extrapolation-reviews.json";
export const HEOR_MODEL_VALIDATION_PATH = "heor/model-validation.json";
export const HEOR_REPORT_PACKAGE_PATH = "heor/report-package.json";
export const HEOR_REPORT_DOCUMENT_PATH = "heor/report.md";
export const HEOR_EVIDENCE_SEARCH_REQUEST_PATH = "heor/evidence-search-request.json";
export const HEOR_EVIDENCE_SYNTHESIS_PATH = "heor/evidence-synthesis.json";
export const HEOR_EVIDENCE_LIBRARY_PATH = "heor/evidence-library.json";
export const HEOR_BASE_CASE_RESULT_PATH = "heor/results/base-case.json";
export const HEOR_UNCERTAINTY_RESULT_PATH = "heor/results/uncertainty.json";
export const HEOR_BUDGET_IMPACT_RESULT_PATH = "heor/results/budget-impact.json";
export const HEOR_PARTITIONED_SURVIVAL_RESULT_PATH = "heor/results/partitioned-survival.json";

function transitionPath(path: string): boolean {
  return /^strategies\.[a-z][a-z0-9_-]{0,63}\.(transition_matrix|transition_schedule)$/.test(path);
}

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
  initial_distribution?: number[];
  transition_matrix?: number[][];
  transition_schedule?: Array<{ start_cycle: number; matrix: number[][] }>;
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

export interface HeorTransitionRateEvent {
  target_index: number;
  rate_per_year: number;
  source_extraction_id?: string;
  source_pointer?: string;
  assumption_id?: string;
}

export interface HeorTransitionRateTransformation {
  operation: "constant_competing_rates";
  cycle_length_years: number;
  phases: Array<{
    start_cycle: number;
    rows: Array<{
      self_index: number;
      events: HeorTransitionRateEvent[];
    }>;
  }>;
}

export interface HeorSurvivalCurveTransformation {
  operation: "parametric_survival_to_transition_schedule";
  cycle_length_years: number;
  from_state_index: number;
  event_state_index: number;
  distribution: "exponential" | "weibull";
  parameters: Record<string, {
    value: number;
    source_extraction_id?: string;
    source_pointer?: string;
    assumption_id?: string;
  }>;
}

export interface HeorProbabilityTimeTransformation {
  operation: "single_event_probability_time_conversion";
  cycle_length_years: number;
  phases: Array<{
    start_cycle: number;
    rows: Array<{
      self_index: number;
      event: null | {
        target_index: number;
        source_probability: number;
        source_interval_years: number;
        source_extraction_id?: string;
        source_pointer?: string;
        assumption_id?: string;
      };
    }>;
  }>;
}

export type HeorTransformationBasis =
  | { source_extraction_id: string; source_pointer?: string }
  | { assumption_id: string };

export interface HeorBackgroundMortalityTransformation {
  operation: "background_plus_excess_mortality_to_transition_schedule";
  cycle_length_years: number;
  from_state_index: number;
  death_state_index: number;
  life_table: {
    jurisdiction: string;
    table_year: number;
    population: string;
    sex: string;
    start_age_years: number;
    cycle_probabilities: Array<{
      cycle: number;
      attained_age_years: number;
      annual_probability: { value: number } & HeorTransformationBasis;
    }>;
  };
  excess_mortality_rate_per_year: { value: number } & HeorTransformationBasis;
  review_bases: {
    population_exchangeability: HeorTransformationBasis;
    no_double_counting: HeorTransformationBasis;
  };
}

export interface HeorRelativeEffectTransformation {
  operation: "relative_effect_to_transition_schedule";
  cycle_length_years: number;
  effect_interval_years: number;
  from_state_index: number;
  event_state_index: number;
  measure: "risk_ratio" | "odds_ratio";
  baseline_cycle_probabilities: Array<{
    cycle: number;
    probability: { value: number } & HeorTransformationBasis;
  }>;
  relative_effect: { value: number } & HeorTransformationBasis;
  review_bases: {
    endpoint_alignment: HeorTransformationBasis;
    population_transportability: HeorTransformationBasis;
    effect_constancy_over_cycles: HeorTransformationBasis;
  };
}

export interface HeorHazardRatioTransformation {
  operation: "hazard_ratio_to_transition_schedule";
  cycle_length_years: number;
  from_state_index: number;
  event_state_index: number;
  baseline_cumulative_hazards: Array<{
    cycle: number;
    cumulative_hazard: { value: number } & HeorTransformationBasis;
  }>;
  hazard_ratio: { value: number } & HeorTransformationBasis;
  review_bases: {
    endpoint_alignment: HeorTransformationBasis;
    population_transportability: HeorTransformationBasis;
    proportional_hazards_assumption: HeorTransformationBasis;
    effect_constancy_over_horizon: HeorTransformationBasis;
    treatment_switching_assessment: HeorTransformationBasis;
  };
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
    source_extraction_id?: string;
    source_index?: number;
    source_value: number;
    source_currency: string;
    source_price_year: number;
    factor: number;
    method: string;
    basis_ids: string[];
  }>;
  derivation: {
    method: "direct_evidence" | "explicit_assumption" | "monetary_adjustment"
      | "deterministic_transformation";
    model_value: unknown;
    transformation?: HeorTransitionRateTransformation | HeorSurvivalCurveTransformation
      | HeorProbabilityTimeTransformation | HeorBackgroundMortalityTransformation
      | HeorRelativeEffectTransformation | HeorHazardRatioTransformation;
  };
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
  correlationGroupCount: number;
  scenarioCount: number;
  iterations: number | null;
  primaryThreshold: number | null;
  thresholdCount: number;
  omittedParameterCount: number;
  jointSurvivalRequired: boolean;
  jointSurvivalManifestSha256: string | null;
  jointSurvivalDrawsSha256: string | null;
  jointSurvivalDrawCount: number | null;
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

export interface HeorPartitionedSurvivalAudit {
  required: boolean;
  complete: boolean;
  status: "not_required" | "complete" | "incomplete";
  psmId: string;
  analysisId: string;
  analysisPlanSha256: string;
  partitionedSurvivalSha256: string;
  survivalCurveMaterializationsSha256: string;
  strategyCount: number;
  curveCount: number;
  timePointCount: number;
  artifactBindings: Array<{ path: string; sha256: string }>;
  errors: string[];
}

export interface HeorSurvivalReviewAudit {
  complete: boolean;
  required: boolean;
  status: "not_required" | "complete" | "incomplete";
  reviewSha256: string | null;
  targetCount: number;
  reviewCount: number;
  analysisId: string;
  targetPath: string | null;
  selectedFamily: string | null;
  candidateModels: number;
  convergedModels: number;
  failedModels: string[];
  scenarioCount: number;
  recommendedFamily: string | null;
  artifactBindings: Array<{ path: string; sha256: string }>;
  targets: HeorSurvivalTargetSummary[];
  blockingGaps: string[];
  errors: string[];
}

export interface HeorSurvivalTargetSummary {
  targetPath: string;
  selectedFamily: string;
  reviewPath: string;
  reviewSha256: string;
  complete: boolean;
  candidateModels: number;
  convergedModels: number;
  failedModels: string[];
  scenarioCount: number;
  recommendedFamily: string | null;
  errors: string[];
}

export function heorSurvivalReviewBindingsCurrent(
  event: Pick<HeorApprovalEvent, "relatedArtifacts"> | undefined,
  audit: HeorSurvivalReviewAudit,
): boolean {
  if (!audit.required) return true;
  return audit.complete
    && audit.artifactBindings.length > 0
    && audit.artifactBindings.every((expected) =>
      event?.relatedArtifacts?.some((binding) =>
        binding.path === expected.path && binding.sha256 === expected.sha256,
      ) === true);
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
  schema_version: "0.1.0" | "0.2.0" | "0.3.0" | "0.4.0" | "0.5.0" | "0.6.0" | "0.7.0" | "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0" | "0.12.0";
  analysis_id: string;
  economic_basis?: { currency: string; price_year: number };
  input_status?: string;
  decision_problem: HeorDecisionProblem;
  reference_case: { id: string; status: "current" | "draft" | "custom" };
  reference_case_assessment?: { path: string; content_sha256: string };
  uncertainty_analysis?: { path: string };
  budget_impact_analysis?: { path: string };
  partitioned_survival_analysis?: { path: string };
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
  baseline_strategy_id?: string;
  strategy_order?: string[];
  strategies: Record<string, HeorStrategy>;
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
  transition_mode: "static" | "piecewise_by_model_cycle" | "partitioned_survival";
  transition_schedule_start_cycles: number[];
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
  strategy_order?: string[];
  baseline_strategy_id?: string;
  strategies: Record<string, HeorStrategyResult>;
  incremental?: HeorIncrementalResult;
  pairwise_vs_baseline?: Record<string, HeorIncrementalResult>;
  fully_incremental_analysis?: Array<{
    rank_by_effect: number;
    strategy_id: string;
    strategy_name: string;
    total_cost: number;
    total_qaly: number;
    net_monetary_benefit: number | null;
    status: "frontier" | "strictly_dominated" | "extendedly_dominated" | "equivalent";
    dominated_by_strategy_ids: string[];
    compared_with_strategy_id: string | null;
    delta_cost: number | null;
    delta_qaly: number | null;
    icer: number | null;
    incremental_net_monetary_benefit: number | null;
  }>;
  optimal_at_primary_threshold?: {
    threshold: number;
    strategy_id: string | null;
    tied_strategy_ids: string[];
    net_monetary_benefit: number;
  } | null;
  input_sha256: string;
}

export interface HeorIncrementalResult {
    delta_cost: number;
    delta_qaly: number;
    icer: number | null;
    incremental_net_monetary_benefit: number | null;
    interpretation: string;
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
    partitionedSurvivalMatchesApproval: boolean;
    partitionedSurvivalAudit: HeorPartitionedSurvivalAudit;
    survivalReviewMatchesApproval: boolean;
    survivalReviewAudit: HeorSurvivalReviewAudit;
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
  calculation_classification: "calculation_only" | "partial_parameter_uncertainty" | "joint_curve_draw_parameter_uncertainty";
  uncertainty_scope?: "declared_model_parameters" | "economic_inputs_only" | "joint_survival_curves_and_economic_inputs";
  partitioned_survival_plan_sha256?: string;
  survival_curve_materializations_sha256?: string;
  joint_survival_uncertainty_sha256?: string;
  joint_survival_draws_sha256?: string;
  economic_basis: HeorCalculation["economic_basis"];
  base_case: HeorIncrementalResult | {
    strategy_order: string[];
    baseline_strategy_id: string;
    strategies: Record<string, Pick<HeorStrategyResult, "name" | "total_cost" | "total_qaly" | "net_monetary_benefit">>;
    pairwise_vs_baseline: Record<string, HeorIncrementalResult>;
    fully_incremental_analysis: NonNullable<HeorCalculation["fully_incremental_analysis"]>;
    optimal_at_primary_threshold: HeorCalculation["optimal_at_primary_threshold"];
  };
  deterministic_analysis: Array<{
    parameter_id: string;
    label: string;
    target: string;
    incremental_nmb_span: number;
  }>;
  probabilistic_analysis: {
    iterations: number;
    strategy_order?: string[];
    cost_effective_probability?: number;
    mean_incremental_net_monetary_benefit?: number;
    incremental_net_monetary_benefit_mcse?: number;
    primary_threshold_strategy_optimal_probabilities?: Record<string, number>;
    primary_threshold_tie_probability?: number;
    mean_net_monetary_benefit_by_strategy?: Record<string, number>;
    net_monetary_benefit_mcse_by_strategy?: Record<string, number>;
    convergence: {
      passed: boolean;
      probability_drift: number;
      max_probability_mcse: number;
      max_probability_drift: number;
    };
    correlation_groups: Array<{
      id: string;
      parameter_ids: string[];
      scale: "log_standard_normal";
      method: "cholesky";
      correlation_matrix: number[][];
      basis_ids: string[];
      rationale: string;
    }>;
    omitted_parameters: Array<{ provenance_path: string; rationale: string }>;
    decision_uncertainty: {
      method: "net_monetary_benefit";
      strategy_order?: string[];
      tie_handling?: "ties_reported_separately_without_fractional_allocation";
      primary_threshold: number;
      threshold_source: "declared_grid" | "legacy_primary_only";
      threshold_rationale: string;
      threshold_results: Array<{
        threshold: number;
        expected_incremental_net_monetary_benefit?: number;
        intervention_optimal_probability?: number;
        comparator_optimal_probability?: number;
        expected_net_monetary_benefit_by_strategy?: Record<string, number>;
        strategy_optimal_probabilities?: Record<string, number>;
        tie_probability: number;
        probability_mcse?: number;
        probability_mcse_by_strategy?: Record<string, number>;
        tie_probability_mcse?: number;
        strategy_with_highest_expected_net_benefit: string | null;
        expected_net_benefit_tied_strategy_ids?: string[];
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

export interface HeorPartitionedSurvivalCalculation {
  schema_version: "0.3.0";
  engine_version: string;
  analysis_id: string;
  psm_id: string;
  analysis_plan_sha256: string;
  partitioned_survival_plan_sha256: string;
  partitioned_survival_plan_schema_version: "0.2.0" | "0.3.0";
  survival_curve_materializations_sha256: string;
  calculation_classification: "calculation_only";
  model_type: "partitioned_survival";
  state_order: ["progression_free", "progressed", "dead"];
  time_origin: string;
  economic_basis: { currency: string; price_year: number };
  strategy_order: string[];
  baseline_strategy_id: string;
  strategies: Record<string, HeorStrategyResult>;
  pairwise_vs_baseline: Record<string, HeorIncrementalResult>;
  fully_incremental_analysis: NonNullable<HeorCalculation["fully_incremental_analysis"]>;
  optimal_at_primary_threshold: HeorCalculation["optimal_at_primary_threshold"];
  limitations: string[];
  warnings: string[];
}

export interface HeorPartitionedSurvivalRunResult {
  calculation: HeorPartitionedSurvivalCalculation;
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
  if (!["0.1.0", "0.2.0", "0.3.0", "0.4.0", "0.5.0", "0.6.0", "0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0"].includes(String(value.schema_version))) {
    throw new Error("analysis plan schema_version must be 0.1.0 through 0.12.0");
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
  const parsedStrategies = value.strategies;
  if (value.schema_version === "0.8.0" || value.schema_version === "0.9.0" || value.schema_version === "0.10.0" || value.schema_version === "0.11.0" || value.schema_version === "0.12.0") {
    if (!Array.isArray(value.strategy_order)
      || value.strategy_order.length < 2 || value.strategy_order.length > 16
      || !value.strategy_order.every((item) => typeof item === "string"
        && /^[a-z][a-z0-9_-]{0,63}$/.test(item))
      || new Set(value.strategy_order).size !== value.strategy_order.length) {
      throw new Error("strategy_order must contain 2-16 unique safe strategy ids");
    }
    if (value.baseline_strategy_id !== value.strategy_order[0]) {
      throw new Error("baseline_strategy_id must be the first strategy_order entry");
    }
    const declared = [...value.strategy_order].sort();
    const actual = Object.keys(parsedStrategies).sort();
    if (!jsonEquivalent(declared, actual)
      || !value.strategy_order.every((strategyId) => isRecord(parsedStrategies[strategyId]))) {
      throw new Error("strategies must contain exactly the ids declared by strategy_order");
    }
  } else if (!isRecord(parsedStrategies.comparator) || !isRecord(parsedStrategies.intervention)) {
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
] as const;

function strategyIds(plan: HeorAnalysisPlan): string[] {
  return plan.schema_version === "0.8.0" || plan.schema_version === "0.9.0" || plan.schema_version === "0.10.0" || plan.schema_version === "0.11.0" || plan.schema_version === "0.12.0"
    ? [...(plan.strategy_order ?? [])]
    : ["comparator", "intervention"];
}

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

function jsonEquivalent(left: unknown, right: unknown): boolean {
  if (typeof left === "number" || typeof right === "number") {
    if (!finiteNumber(left) || !finiteNumber(right)) return false;
    const tolerance = Math.max(1e-12, Math.max(Math.abs(left), Math.abs(right)) * 1e-12);
    return Math.abs(left - right) <= tolerance;
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right) && left.length === right.length
      && left.every((value, index) => jsonEquivalent(value, right[index]));
  }
  if (isRecord(left) || isRecord(right)) {
    if (!isRecord(left) || !isRecord(right)) return false;
    const leftKeys = Object.keys(left).sort();
    const rightKeys = Object.keys(right).sort();
    return leftKeys.length === rightKeys.length
      && leftKeys.every((key, index) => key === rightKeys[index]
        && jsonEquivalent(left[key], right[key]));
  }
  return left === right;
}

function sameStringSet(left: Set<string>, right: Set<string>): boolean {
  return left.size === right.size && Array.from(left).every((value) => right.has(value));
}

function transitionRateReasons(
  plan: HeorAnalysisPlan,
  mapping: HeorInputProvenance,
  extractionIds: string[],
  assumptionIds: string[],
): string[] {
  const reasons: string[] = [];
  if (!(plan.schema_version === "0.5.0" || plan.schema_version === "0.8.0" || plan.schema_version === "0.9.0" || plan.schema_version === "0.10.0" || plan.schema_version === "0.11.0")) {
    reasons.push("deterministic transition-rate transformations require schema_version 0.5.0 through 0.11.0");
  }
  if (!(
    mapping.path.endsWith(".transition_matrix")
    || mapping.path.endsWith(".transition_schedule")
  )) {
    return [...reasons, "deterministic transformation is allowed only for a transition matrix or schedule"];
  }
  const transformation = mapping.derivation.transformation;
  if (!isRecord(transformation)) return [...reasons, "derivation.transformation must be an object"];
  if (transformation.operation !== "constant_competing_rates") {
    reasons.push("transformation.operation must be constant_competing_rates");
  }
  const declaredCycle = transformation.cycle_length_years;
  if (!finiteNumber(declaredCycle) || declaredCycle <= 0
    || !jsonEquivalent(declaredCycle, plan.cycle_length_years)) {
    reasons.push("transformation.cycle_length_years must equal the analysis cycle length");
  }
  const phases = transformation.phases;
  if (!Array.isArray(phases) || phases.length < 1 || phases.length > plan.cycles) {
    return [...reasons, `transformation.phases must contain from 1 to ${plan.cycles} phases`];
  }
  const usedExtractions = new Set<string>();
  const usedAssumptions = new Set<string>();
  const starts: number[] = [];
  const matrices: number[][][] = [];
  phases.forEach((rawPhase, phaseIndex) => {
    const label = `transformation.phases[${phaseIndex}]`;
    if (!isRecord(rawPhase)) {
      reasons.push(`${label} must be an object`);
      return;
    }
    const start = rawPhase.start_cycle;
    if (!Number.isInteger(start) || (start as number) < 1 || (start as number) > plan.cycles) {
      reasons.push(`${label}.start_cycle is outside the horizon`);
      return;
    }
    starts.push(start as number);
    if (!Array.isArray(rawPhase.rows) || rawPhase.rows.length !== plan.states.length) {
      reasons.push(`${label}.rows must contain ${plan.states.length} rows`);
      return;
    }
    const matrix: number[][] = [];
    rawPhase.rows.forEach((rawRow, rowIndex) => {
      const rowLabel = `${label}.rows[${rowIndex}]`;
      if (!isRecord(rawRow) || rawRow.self_index !== rowIndex || !Array.isArray(rawRow.events)) {
        reasons.push(`${rowLabel} must declare its row position and an events array`);
        return;
      }
      const targets = new Set<number>();
      const events: Array<[number, number]> = [];
      let totalRate = 0;
      rawRow.events.forEach((rawEvent, eventIndex) => {
        const eventLabel = `${rowLabel}.events[${eventIndex}]`;
        if (!isRecord(rawEvent)) {
          reasons.push(`${eventLabel} must be an object`);
          return;
        }
        const target = rawEvent.target_index;
        const rate = rawEvent.rate_per_year;
        if (!Number.isInteger(target) || (target as number) < 0
          || (target as number) >= plan.states.length || target === rowIndex
          || targets.has(target as number)) {
          reasons.push(`${eventLabel}.target_index is invalid or duplicated`);
          return;
        }
        if (!finiteNumber(rate) || rate <= 0) {
          reasons.push(`${eventLabel}.rate_per_year must be positive; omit structural zeros`);
          return;
        }
        const sourceId = nonempty(rawEvent.source_extraction_id)
          ? rawEvent.source_extraction_id
          : null;
        const assumptionId = nonempty(rawEvent.assumption_id) ? rawEvent.assumption_id : null;
        if (Boolean(sourceId) === Boolean(assumptionId)) {
          reasons.push(`${eventLabel} must declare exactly one source_extraction_id or assumption_id`);
          return;
        }
        if (sourceId) {
          if (rawEvent.source_pointer !== undefined
            && (typeof rawEvent.source_pointer !== "string"
              || (rawEvent.source_pointer.length > 0 && !rawEvent.source_pointer.startsWith("/")))) {
            reasons.push(`${eventLabel}.source_pointer must be empty or a JSON pointer`);
          }
          usedExtractions.add(sourceId);
        } else if (assumptionId) {
          if (rawEvent.source_pointer !== undefined) {
            reasons.push(`${eventLabel}.source_pointer requires source_extraction_id`);
          }
          usedAssumptions.add(assumptionId);
        }
        targets.add(target as number);
        totalRate += rate;
        events.push([target as number, rate]);
      });
      const row = Array(plan.states.length).fill(0) as number[];
      if (totalRate === 0) {
        row[rowIndex] = 1;
      } else {
        const eventMass = -Math.expm1(-totalRate * (declaredCycle as number));
        row[rowIndex] = 1 - eventMass;
        events.forEach(([target, rate]) => { row[target] = eventMass * rate / totalRate; });
      }
      matrix.push(row);
    });
    if (matrix.length === plan.states.length) matrices.push(matrix);
  });
  if (starts[0] !== 1 || starts.some((start, index) => index > 0 && starts[index - 1] >= start)) {
    reasons.push("transformation phase start_cycle values must start at 1 and strictly increase");
  }
  let output: unknown;
  if (mapping.path.endsWith(".transition_matrix")) {
    if (phases.length !== 1) {
      reasons.push("a static transition_matrix transformation must contain exactly one phase");
    }
    output = matrices[0];
  } else {
    output = starts.map((start, index) => ({ start_cycle: start, matrix: matrices[index] }));
  }
  if (!jsonEquivalent(output, modelValue(plan, mapping.path))) {
    reasons.push("constant competing rates do not reproduce the current transition input");
  }
  if (!sameStringSet(usedExtractions, new Set(extractionIds))) {
    reasons.push("transformation must use every selected extraction exactly as declared");
  }
  if (!sameStringSet(usedAssumptions, new Set(assumptionIds))) {
    reasons.push("transformation must use every proposed assumption exactly as declared");
  }
  return reasons;
}

function survivalCurveReasons(
  plan: HeorAnalysisPlan,
  mapping: HeorInputProvenance,
  extractionIds: string[],
  assumptionIds: string[],
): string[] {
  const reasons: string[] = [];
  if (!(plan.schema_version === "0.6.0" || plan.schema_version === "0.8.0" || plan.schema_version === "0.9.0" || plan.schema_version === "0.10.0" || plan.schema_version === "0.11.0")) {
    reasons.push("parametric survival transformations require schema_version 0.6.0 through 0.11.0");
  }
  if (!/^strategies\.[a-z][a-z0-9_-]{0,63}\.transition_schedule$/.test(mapping.path)) {
    return [...reasons, "parametric survival transformation is allowed only for a transition schedule"];
  }
  const transformation = mapping.derivation.transformation;
  if (!isRecord(transformation)) return [...reasons, "derivation.transformation must be an object"];
  const exactFields = [
    "operation", "cycle_length_years", "from_state_index", "event_state_index",
    "distribution", "parameters",
  ].sort();
  if (!jsonEquivalent(Object.keys(transformation).sort(), exactFields)) {
    reasons.push("survival transformation fields are not the exact supported contract");
  }
  if (plan.states.length !== 2) {
    reasons.push("parametric survival transformation requires exactly two states");
  }
  if (!Number.isInteger(plan.cycles) || plan.cycles < 1 || plan.cycles > 10_000) {
    reasons.push("parametric survival transformation supports 1-10000 cycles");
  }
  const cycleLength = transformation.cycle_length_years;
  if (!finiteNumber(cycleLength) || cycleLength <= 0
    || !jsonEquivalent(cycleLength, plan.cycle_length_years)) {
    reasons.push("transformation.cycle_length_years must equal the analysis cycle length");
  }
  const fromIndex = transformation.from_state_index;
  const eventIndex = transformation.event_state_index;
  if (!Number.isInteger(fromIndex) || !Number.isInteger(eventIndex)
    || !([fromIndex, eventIndex].includes(0) && [fromIndex, eventIndex].includes(1))
    || fromIndex === eventIndex) {
    reasons.push("from_state_index and event_state_index must be the two distinct state indices");
  }
  const distribution = transformation.distribution;
  const expectedParameters = distribution === "exponential"
    ? ["rate_per_year"]
    : distribution === "weibull" ? ["shape", "scale_years"] : [];
  if (expectedParameters.length === 0) {
    reasons.push("transformation.distribution must be exponential or weibull");
  }
  const rawParameters = transformation.parameters;
  if (!isRecord(rawParameters)
    || !jsonEquivalent(Object.keys(rawParameters).sort(), [...expectedParameters].sort())) {
    reasons.push("transformation.parameters fields do not match the distribution");
  }
  const parameters = new Map<string, number>();
  const usedExtractions = new Set<string>();
  const usedAssumptions = new Set<string>();
  expectedParameters.forEach((name) => {
    const label = `transformation.parameters.${name}`;
    const parameter = isRecord(rawParameters) ? rawParameters[name] : undefined;
    if (!isRecord(parameter)) {
      reasons.push(`${label} must be an object`);
      return;
    }
    const allowed = new Set(["value", "source_extraction_id", "source_pointer", "assumption_id"]);
    if (Object.keys(parameter).some((field) => !allowed.has(field))) {
      reasons.push(`${label} contains unsupported fields`);
    }
    if (!finiteNumber(parameter.value) || parameter.value <= 0) {
      reasons.push(`${label}.value must be positive`);
      return;
    }
    parameters.set(name, parameter.value);
    const sourceId = nonempty(parameter.source_extraction_id)
      ? parameter.source_extraction_id : null;
    const assumptionId = nonempty(parameter.assumption_id) ? parameter.assumption_id : null;
    if (Boolean(sourceId) === Boolean(assumptionId)) {
      reasons.push(`${label} must declare exactly one source_extraction_id or assumption_id`);
    } else if (sourceId) {
      if (parameter.source_pointer !== undefined
        && (typeof parameter.source_pointer !== "string"
          || (parameter.source_pointer.length > 0 && !parameter.source_pointer.startsWith("/")))) {
        reasons.push(`${label}.source_pointer must be empty or a JSON pointer`);
      }
      usedExtractions.add(sourceId);
    } else if (assumptionId) {
      if (parameter.source_pointer !== undefined) {
        reasons.push(`${label}.source_pointer requires source_extraction_id`);
      }
      usedAssumptions.add(assumptionId);
    }
  });
  const output: Array<{ start_cycle: number; matrix: number[][] }> = [];
  if (finiteNumber(cycleLength) && cycleLength > 0 && plan.states.length === 2
    && Number.isInteger(plan.cycles) && plan.cycles >= 1 && plan.cycles <= 10_000
    && (fromIndex === 0 || fromIndex === 1) && (eventIndex === 0 || eventIndex === 1)
    && fromIndex !== eventIndex && parameters.size === expectedParameters.length) {
    let previousHazard = 0;
    for (let cycle = 1; cycle <= plan.cycles; cycle += 1) {
      const timeYears = cycle * cycleLength;
      const cumulativeHazard = distribution === "exponential"
        ? (parameters.get("rate_per_year") as number) * timeYears
        : Math.pow(
            timeYears / (parameters.get("scale_years") as number),
            parameters.get("shape") as number,
          );
      const increment = cumulativeHazard - previousHazard;
      if (!Number.isFinite(increment) || increment < -1e-12) {
        reasons.push("parametric survival cumulative hazard must be finite and non-decreasing");
        output.length = 0;
        break;
      }
      const eventProbability = -Math.expm1(-Math.max(0, increment));
      const matrix = [[0, 0], [0, 0]];
      matrix[fromIndex][fromIndex] = 1 - eventProbability;
      matrix[fromIndex][eventIndex] = eventProbability;
      matrix[eventIndex][eventIndex] = 1;
      output.push({ start_cycle: cycle, matrix });
      previousHazard = cumulativeHazard;
    }
  }
  if (output.length === 0 || !jsonEquivalent(output, modelValue(plan, mapping.path))) {
    reasons.push("parametric survival curve does not reproduce the current transition schedule");
  }
  if (!sameStringSet(usedExtractions, new Set(extractionIds))) {
    reasons.push("transformation must use every selected extraction exactly as declared");
  }
  if (!sameStringSet(usedAssumptions, new Set(assumptionIds))) {
    reasons.push("transformation must use every proposed assumption exactly as declared");
  }
  return reasons;
}

function probabilityTimeReasons(
  plan: HeorAnalysisPlan,
  mapping: HeorInputProvenance,
  extractionIds: string[],
  assumptionIds: string[],
): string[] {
  const reasons: string[] = [];
  if (!(plan.schema_version === "0.7.0" || plan.schema_version === "0.8.0" || plan.schema_version === "0.9.0" || plan.schema_version === "0.10.0" || plan.schema_version === "0.11.0")) {
    reasons.push("probability-time transformations require schema_version 0.7.0 through 0.11.0");
  }
  if (!transitionPath(mapping.path)) {
    return [...reasons, "probability-time transformation is allowed only for transition inputs"];
  }
  const transformation = mapping.derivation.transformation;
  if (!isRecord(transformation)) return [...reasons, "derivation.transformation must be an object"];
  if (!jsonEquivalent(Object.keys(transformation).sort(), ["cycle_length_years", "operation", "phases"])) {
    reasons.push("probability-time transformation fields are not the exact supported contract");
  }
  const cycleLength = transformation.cycle_length_years;
  if (!finiteNumber(cycleLength) || cycleLength <= 0
    || Math.abs(cycleLength - plan.cycle_length_years) > 1e-12) {
    reasons.push("transformation.cycle_length_years must equal the analysis cycle length");
  }
  const phases = transformation.phases;
  if (!Array.isArray(phases) || phases.length < 1 || phases.length > plan.cycles) {
    return [...reasons, "transformation.phases count is invalid"];
  }
  const starts: number[] = [];
  const matrices: number[][][] = [];
  const usedExtractions = new Set<string>();
  const usedAssumptions = new Set<string>();
  phases.forEach((rawPhase, phaseIndex) => {
    const phaseLabel = `transformation.phases[${phaseIndex}]`;
    if (!isRecord(rawPhase)
      || !jsonEquivalent(Object.keys(rawPhase).sort(), ["rows", "start_cycle"])) {
      reasons.push(`${phaseLabel} fields are invalid`);
      return;
    }
    const startCycle = typeof rawPhase.start_cycle === "number"
      ? rawPhase.start_cycle : Number.NaN;
    if (!Number.isInteger(startCycle)
      || startCycle < 1 || startCycle > plan.cycles) {
      reasons.push(`${phaseLabel}.start_cycle is invalid`);
      return;
    }
    starts.push(startCycle);
    if (!Array.isArray(rawPhase.rows) || rawPhase.rows.length !== plan.states.length) {
      reasons.push(`${phaseLabel}.rows must contain ${plan.states.length} rows`);
      return;
    }
    const matrix: number[][] = [];
    rawPhase.rows.forEach((rawRow, rowIndex) => {
      const rowLabel = `${phaseLabel}.rows[${rowIndex}]`;
      if (!isRecord(rawRow)
        || !jsonEquivalent(Object.keys(rawRow).sort(), ["event", "self_index"])) {
        reasons.push(`${rowLabel} fields are invalid`);
        return;
      }
      if (rawRow.self_index !== rowIndex) {
        reasons.push(`${rowLabel}.self_index must equal the row position`);
      }
      const output = Array.from({ length: plan.states.length }, () => 0);
      output[rowIndex] = 1;
      if (rawRow.event !== null) {
        const eventLabel = `${rowLabel}.event`;
        const event = rawRow.event;
        if (!isRecord(event)) {
          reasons.push(`${eventLabel} must be an object or null`);
          return;
        }
        const allowed = new Set([
          "target_index", "source_probability", "source_interval_years",
          "source_extraction_id", "source_pointer", "assumption_id",
        ]);
        if (Object.keys(event).some((field) => !allowed.has(field))) {
          reasons.push(`${eventLabel} contains unsupported fields`);
        }
        const targetIndex = typeof event.target_index === "number"
          ? event.target_index : Number.NaN;
        const probability = event.source_probability;
        const sourceInterval = event.source_interval_years;
        if (!Number.isInteger(targetIndex) || targetIndex < 0
          || targetIndex >= plan.states.length || targetIndex === rowIndex) {
          reasons.push(`${eventLabel}.target_index is invalid`);
          return;
        }
        if (!finiteNumber(probability) || probability <= 0 || probability >= 1) {
          reasons.push(`${eventLabel}.source_probability must be strictly between 0 and 1`);
          return;
        }
        if (!finiteNumber(sourceInterval) || sourceInterval <= 0) {
          reasons.push(`${eventLabel}.source_interval_years must be positive`);
          return;
        }
        const sourceId = nonempty(event.source_extraction_id)
          ? event.source_extraction_id : null;
        const assumptionId = nonempty(event.assumption_id) ? event.assumption_id : null;
        if (Boolean(sourceId) === Boolean(assumptionId)) {
          reasons.push(`${eventLabel} must declare exactly one source extraction or assumption`);
        } else if (sourceId) {
          if (event.source_pointer !== undefined
            && (typeof event.source_pointer !== "string"
              || (event.source_pointer.length > 0 && !event.source_pointer.startsWith("/")))) {
            reasons.push(`${eventLabel}.source_pointer must be empty or a JSON pointer`);
          }
          usedExtractions.add(sourceId);
        } else if (assumptionId) {
          if (event.source_pointer !== undefined) {
            reasons.push(`${eventLabel}.source_pointer requires source_extraction_id`);
          }
          usedAssumptions.add(assumptionId);
        }
        const converted = -Math.expm1(
          Math.log1p(-probability) * cycleLength / sourceInterval,
        );
        if (!Number.isFinite(converted) || converted <= 0 || converted >= 1) {
          reasons.push(`${eventLabel} conversion produced an invalid probability`);
          return;
        }
        output[rowIndex] = 1 - converted;
        output[targetIndex] = converted;
      }
      matrix.push(output);
    });
    if (matrix.length === plan.states.length) matrices.push(matrix);
  });
  if (starts[0] !== 1 || starts.some((value, index) => index > 0 && starts[index - 1] >= value)) {
    reasons.push("transformation phases must start at cycle 1 and strictly increase");
  }
  const output = mapping.path.endsWith(".transition_matrix")
    ? (phases.length === 1 ? matrices[0] : undefined)
    : starts.map((start_cycle, index) => ({ start_cycle, matrix: matrices[index] }));
  if (mapping.path.endsWith(".transition_matrix") && phases.length !== 1) {
    reasons.push("a static matrix transformation requires exactly one phase");
  }
  if (output === undefined || !jsonEquivalent(output, modelValue(plan, mapping.path))) {
    reasons.push("source probabilities do not reproduce the current transition input");
  }
  if (!sameStringSet(usedExtractions, new Set(extractionIds))) {
    reasons.push("transformation must use every selected extraction exactly as declared");
  }
  if (!sameStringSet(usedAssumptions, new Set(assumptionIds))) {
    reasons.push("transformation must use every proposed assumption exactly as declared");
  }
  return reasons;
}

function backgroundMortalityBasis(
  raw: unknown,
  label: string,
  includesValue: boolean,
  usedExtractions: Set<string>,
  usedAssumptions: Set<string>,
  reasons: string[],
): number | null {
  if (!isRecord(raw)) {
    reasons.push(`${label} must be an object`);
    return null;
  }
  const sourceId = nonempty(raw.source_extraction_id) ? raw.source_extraction_id : null;
  const assumptionId = nonempty(raw.assumption_id) ? raw.assumption_id : null;
  if (Boolean(sourceId) === Boolean(assumptionId)) {
    reasons.push(`${label} must declare exactly one source_extraction_id or assumption_id`);
    return null;
  }
  const expectedFields = [
    ...(includesValue ? ["value"] : []),
    sourceId ? "source_extraction_id" : "assumption_id",
    ...(sourceId && Object.prototype.hasOwnProperty.call(raw, "source_pointer")
      ? ["source_pointer"] : []),
  ].sort();
  if (!jsonEquivalent(Object.keys(raw).sort(), expectedFields)) {
    reasons.push(`${label} fields are not the exact supported contract`);
  }
  if (sourceId) {
    if (raw.source_pointer !== undefined
      && (typeof raw.source_pointer !== "string"
        || (raw.source_pointer.length > 0 && !raw.source_pointer.startsWith("/")))) {
      reasons.push(`${label}.source_pointer must be empty or a JSON pointer`);
    }
    usedExtractions.add(sourceId);
  } else if (assumptionId) {
    usedAssumptions.add(assumptionId);
  }
  if (!includesValue) return null;
  if (!finiteNumber(raw.value)) {
    reasons.push(`${label}.value must be finite`);
    return null;
  }
  return raw.value;
}

function backgroundMortalityReasons(
  plan: HeorAnalysisPlan,
  mapping: HeorInputProvenance,
  extractionIds: string[],
  assumptionIds: string[],
): string[] {
  const reasons: string[] = [];
  if (plan.schema_version !== "0.9.0" && plan.schema_version !== "0.10.0" && plan.schema_version !== "0.11.0") {
    reasons.push("background mortality transformations require schema_version 0.9.0 through 0.11.0");
  }
  if (!mapping.path.endsWith(".transition_schedule")) {
    return [...reasons, "background mortality transformation is allowed only for a transition schedule"];
  }
  const transformation = mapping.derivation.transformation;
  if (!isRecord(transformation)) return [...reasons, "derivation.transformation must be an object"];
  const rootFields = [
    "operation", "cycle_length_years", "from_state_index", "death_state_index",
    "life_table", "excess_mortality_rate_per_year", "review_bases",
  ].sort();
  if (!jsonEquivalent(Object.keys(transformation).sort(), rootFields)) {
    reasons.push("background mortality transformation fields are not the exact supported contract");
  }
  if (transformation.operation !== "background_plus_excess_mortality_to_transition_schedule") {
    reasons.push("transformation.operation must be background_plus_excess_mortality_to_transition_schedule");
  }
  if (plan.states.length !== 2) {
    reasons.push("background mortality transformation requires exactly two states");
  }
  if (!Number.isInteger(plan.cycles) || plan.cycles < 1 || plan.cycles > 10_000) {
    reasons.push("background mortality transformation supports 1-10000 cycles");
  }
  const cycleLength = transformation.cycle_length_years;
  if (!finiteNumber(cycleLength) || cycleLength <= 0
    || Math.abs(cycleLength - plan.cycle_length_years) > 1e-12) {
    reasons.push("transformation.cycle_length_years must equal the analysis cycle length");
  }
  const fromIndex = transformation.from_state_index;
  const deathIndex = transformation.death_state_index;
  const numericFromIndex = typeof fromIndex === "number" ? fromIndex : Number.NaN;
  const numericDeathIndex = typeof deathIndex === "number" ? deathIndex : Number.NaN;
  if (!Number.isInteger(numericFromIndex) || !Number.isInteger(numericDeathIndex)
    || !([numericFromIndex, numericDeathIndex].includes(0)
      && [numericFromIndex, numericDeathIndex].includes(1))
    || fromIndex === deathIndex) {
    reasons.push("from_state_index and death_state_index must be the two distinct state indices");
  }
  const lifeTable = transformation.life_table;
  const lifeTableFields = [
    "jurisdiction", "table_year", "population", "sex", "start_age_years",
    "cycle_probabilities",
  ].sort();
  if (!isRecord(lifeTable)) return [...reasons, "transformation.life_table must be an object"];
  if (!jsonEquivalent(Object.keys(lifeTable).sort(), lifeTableFields)) {
    reasons.push("transformation.life_table fields are not the exact supported contract");
  }
  for (const field of ["jurisdiction", "population", "sex"] as const) {
    if (!nonempty(lifeTable[field])) reasons.push(`transformation.life_table.${field} is required`);
  }
  if (lifeTable.jurisdiction !== mapping.jurisdiction) {
    reasons.push("life-table jurisdiction must match the input-provenance jurisdiction");
  }
  if (!Number.isInteger(lifeTable.table_year)
    || (lifeTable.table_year as number) < 1900 || (lifeTable.table_year as number) > 2100) {
    reasons.push("transformation.life_table.table_year must be 1900-2100");
  }
  const startAge = lifeTable.start_age_years;
  if (!finiteNumber(startAge) || startAge < 0) {
    reasons.push("transformation.life_table.start_age_years must be finite and non-negative");
  }
  const cycles = lifeTable.cycle_probabilities;
  if (!Array.isArray(cycles) || cycles.length !== plan.cycles) {
    return [...reasons, "transformation.life_table.cycle_probabilities must cover every model cycle"];
  }
  const usedExtractions = new Set<string>();
  const usedAssumptions = new Set<string>();
  const excess = backgroundMortalityBasis(
    transformation.excess_mortality_rate_per_year,
    "transformation.excess_mortality_rate_per_year",
    true,
    usedExtractions,
    usedAssumptions,
    reasons,
  );
  if (excess !== null && excess < 0) {
    reasons.push("transformation.excess_mortality_rate_per_year.value must be non-negative");
  }
  const reviewBases = transformation.review_bases;
  if (!isRecord(reviewBases)
    || !jsonEquivalent(Object.keys(reviewBases).sort(), ["no_double_counting", "population_exchangeability"])) {
    reasons.push("transformation.review_bases fields are not the exact supported contract");
  } else {
    for (const name of ["population_exchangeability", "no_double_counting"] as const) {
      backgroundMortalityBasis(
        reviewBases[name],
        `transformation.review_bases.${name}`,
        false,
        usedExtractions,
        usedAssumptions,
        reasons,
      );
    }
  }
  const output: Array<{ start_cycle: number; matrix: number[][] }> = [];
  cycles.forEach((rawCycle, index) => {
    const label = `transformation.life_table.cycle_probabilities[${index}]`;
    if (!isRecord(rawCycle)
      || !jsonEquivalent(Object.keys(rawCycle).sort(), ["annual_probability", "attained_age_years", "cycle"])) {
      reasons.push(`${label} fields are not the exact supported contract`);
      return;
    }
    if (rawCycle.cycle !== index + 1) reasons.push(`${label}.cycle must equal ${index + 1}`);
    const expectedAge = finiteNumber(startAge) && finiteNumber(cycleLength)
      ? Math.floor(startAge + index * cycleLength) : Number.NaN;
    if (!finiteNumber(rawCycle.attained_age_years)
      || Math.abs(rawCycle.attained_age_years - expectedAge) > 1e-9) {
      reasons.push(`${label}.attained_age_years must equal floor(start_age_years + (cycle - 1) * cycle_length_years)`);
    }
    const q = backgroundMortalityBasis(
      rawCycle.annual_probability,
      `${label}.annual_probability`,
      true,
      usedExtractions,
      usedAssumptions,
      reasons,
    );
    if (q === null || q < 0 || q >= 1 || excess === null || excess < 0
      || !finiteNumber(cycleLength) || cycleLength <= 0
      || !Number.isInteger(numericFromIndex) || !Number.isInteger(numericDeathIndex)
      || numericFromIndex === numericDeathIndex
      || ![0, 1].includes(numericFromIndex) || ![0, 1].includes(numericDeathIndex)) {
      if (q !== null && (q < 0 || q >= 1)) {
        reasons.push(`${label}.annual_probability.value must be in [0,1)`);
      }
      return;
    }
    const backgroundHazard = -Math.log1p(-q);
    const integratedHazard = (backgroundHazard + excess) * cycleLength;
    if (!Number.isFinite(integratedHazard) || integratedHazard < 0) {
      reasons.push(`${label} produced a non-finite integrated hazard`);
      return;
    }
    const deathProbability = -Math.expm1(-integratedHazard);
    if (!Number.isFinite(deathProbability) || deathProbability < 0 || deathProbability >= 1) {
      reasons.push(`${label} produced an invalid death probability`);
      return;
    }
    const matrix = [[0, 0], [0, 0]];
    matrix[numericFromIndex][numericFromIndex] = 1 - deathProbability;
    matrix[numericFromIndex][numericDeathIndex] = deathProbability;
    matrix[numericDeathIndex][numericDeathIndex] = 1;
    output.push({ start_cycle: index + 1, matrix });
  });
  if (output.length !== plan.cycles || !jsonEquivalent(output, modelValue(plan, mapping.path))) {
    reasons.push("background plus excess mortality does not reproduce the current transition schedule");
  }
  if (!sameStringSet(usedExtractions, new Set(extractionIds))) {
    reasons.push("transformation must use every selected extraction exactly as declared");
  }
  if (!sameStringSet(usedAssumptions, new Set(assumptionIds))) {
    reasons.push("transformation must use every proposed assumption exactly as declared");
  }
  return reasons;
}

function relativeEffectReasons(
  plan: HeorAnalysisPlan,
  mapping: HeorInputProvenance,
  extractionIds: string[],
  assumptionIds: string[],
): string[] {
  const reasons: string[] = [];
  if (plan.schema_version !== "0.10.0" && plan.schema_version !== "0.11.0") {
    reasons.push("relative-effect transformations require schema_version 0.10.0 or 0.11.0");
  }
  if (!mapping.path.endsWith(".transition_schedule")) {
    return [...reasons, "relative-effect transformation is allowed only for a transition schedule"];
  }
  const transformation = mapping.derivation.transformation;
  if (!isRecord(transformation)) return [...reasons, "derivation.transformation must be an object"];
  const fields = [
    "operation", "cycle_length_years", "effect_interval_years", "from_state_index",
    "event_state_index", "measure", "baseline_cycle_probabilities", "relative_effect",
    "review_bases",
  ].sort();
  if (!jsonEquivalent(Object.keys(transformation).sort(), fields)) {
    reasons.push("relative-effect transformation fields are not the exact supported contract");
  }
  if (transformation.operation !== "relative_effect_to_transition_schedule") {
    reasons.push("transformation.operation must be relative_effect_to_transition_schedule");
  }
  if (plan.states.length !== 2) reasons.push("relative-effect transformation requires exactly two states");
  if (!Number.isInteger(plan.cycles) || plan.cycles < 1 || plan.cycles > 10_000) {
    reasons.push("relative-effect transformation supports 1-10000 cycles");
  }
  const cycleLength = transformation.cycle_length_years;
  const effectInterval = transformation.effect_interval_years;
  if (!finiteNumber(cycleLength) || cycleLength <= 0 || !finiteNumber(effectInterval)
    || effectInterval <= 0 || Math.abs(cycleLength - plan.cycle_length_years) > 1e-12
    || Math.abs(effectInterval - cycleLength) > 1e-12) {
    reasons.push("transformation cycle_length_years and effect_interval_years must equal the analysis cycle length");
  }
  const fromIndex = transformation.from_state_index;
  const eventIndex = transformation.event_state_index;
  const numericFromIndex = typeof fromIndex === "number" ? fromIndex : Number.NaN;
  const numericEventIndex = typeof eventIndex === "number" ? eventIndex : Number.NaN;
  const validIndices = Number.isInteger(numericFromIndex) && Number.isInteger(numericEventIndex)
    && numericFromIndex !== numericEventIndex && [numericFromIndex, numericEventIndex].includes(0)
    && [numericFromIndex, numericEventIndex].includes(1);
  if (!validIndices) {
    reasons.push("from_state_index and event_state_index must be the two distinct state indices");
  }
  const measure = transformation.measure;
  if (measure !== "risk_ratio" && measure !== "odds_ratio") {
    reasons.push("transformation.measure must be risk_ratio or odds_ratio");
  }
  const usedExtractions = new Set<string>();
  const usedAssumptions = new Set<string>();
  const effect = backgroundMortalityBasis(
    transformation.relative_effect, "transformation.relative_effect", true,
    usedExtractions, usedAssumptions, reasons,
  );
  if (effect === null || effect <= 0) {
    reasons.push("transformation.relative_effect.value must be finite and positive");
  }
  const reviewBases = transformation.review_bases;
  const reviewNames = ["effect_constancy_over_cycles", "endpoint_alignment", "population_transportability"];
  if (!isRecord(reviewBases) || !jsonEquivalent(Object.keys(reviewBases).sort(), reviewNames)) {
    reasons.push("transformation.review_bases fields are not the exact supported contract");
  } else {
    for (const name of reviewNames) {
      backgroundMortalityBasis(
        reviewBases[name], `transformation.review_bases.${name}`, false,
        usedExtractions, usedAssumptions, reasons,
      );
    }
  }
  const baseline = transformation.baseline_cycle_probabilities;
  if (!Array.isArray(baseline) || baseline.length !== plan.cycles) {
    return [...reasons, "transformation.baseline_cycle_probabilities must cover every model cycle"];
  }
  let anyPositive = false;
  const output: Array<{ start_cycle: number; matrix: number[][] }> = [];
  baseline.forEach((entry, index) => {
    const label = `transformation.baseline_cycle_probabilities[${index}]`;
    if (!isRecord(entry) || !jsonEquivalent(Object.keys(entry).sort(), ["cycle", "probability"])) {
      reasons.push(`${label} fields are not the exact supported contract`);
      return;
    }
    if (entry.cycle !== index + 1) reasons.push(`${label}.cycle must equal ${index + 1}`);
    const q = backgroundMortalityBasis(
      entry.probability, `${label}.probability`, true,
      usedExtractions, usedAssumptions, reasons,
    );
    if (q === null || q < 0 || q >= 1) {
      if (q !== null) reasons.push(`${label}.probability.value must be in [0,1)`);
      return;
    }
    anyPositive ||= q > 0;
    if (effect === null || effect <= 0 || !validIndices
      || (measure !== "risk_ratio" && measure !== "odds_ratio")) return;
    const eventProbability = measure === "risk_ratio"
      ? q * effect
      : (q === 0 ? 0 : (effect * q) / ((1 - q) + effect * q));
    if (!Number.isFinite(eventProbability) || eventProbability < 0 || eventProbability >= 1) {
      reasons.push(`${label} produced an invalid event probability`);
      return;
    }
    const matrix = [[0, 0], [0, 0]];
    matrix[numericFromIndex][numericFromIndex] = 1 - eventProbability;
    matrix[numericFromIndex][numericEventIndex] = eventProbability;
    matrix[numericEventIndex][numericEventIndex] = 1;
    output.push({ start_cycle: index + 1, matrix });
  });
  if (!anyPositive) reasons.push("baseline_cycle_probabilities must contain at least one positive probability");
  if (output.length !== plan.cycles || !jsonEquivalent(output, modelValue(plan, mapping.path))) {
    reasons.push("relative effect does not reproduce the current transition schedule");
  }
  if (!sameStringSet(usedExtractions, new Set(extractionIds))) {
    reasons.push("transformation must use every selected extraction exactly as declared");
  }
  if (!sameStringSet(usedAssumptions, new Set(assumptionIds))) {
    reasons.push("transformation must use every proposed assumption exactly as declared");
  }
  return reasons;
}

function hazardRatioReasons(
  plan: HeorAnalysisPlan,
  mapping: HeorInputProvenance,
  extractionIds: string[],
  assumptionIds: string[],
): string[] {
  const reasons: string[] = [];
  if (plan.schema_version !== "0.11.0") {
    reasons.push("hazard-ratio transformations require schema_version 0.11.0");
  }
  if (!mapping.path.endsWith(".transition_schedule")) {
    return [...reasons, "hazard-ratio transformation is allowed only for a transition schedule"];
  }
  const transformation = mapping.derivation.transformation;
  if (!isRecord(transformation)) return [...reasons, "derivation.transformation must be an object"];
  const fields = [
    "operation", "cycle_length_years", "from_state_index", "event_state_index",
    "baseline_cumulative_hazards", "hazard_ratio", "review_bases",
  ].sort();
  if (!jsonEquivalent(Object.keys(transformation).sort(), fields)) {
    reasons.push("hazard-ratio transformation fields are not the exact supported contract");
  }
  if (transformation.operation !== "hazard_ratio_to_transition_schedule") {
    reasons.push("transformation.operation must be hazard_ratio_to_transition_schedule");
  }
  if (plan.states.length !== 2) reasons.push("hazard-ratio transformation requires exactly two states");
  if (!Number.isInteger(plan.cycles) || plan.cycles < 1 || plan.cycles > 10_000) {
    reasons.push("hazard-ratio transformation supports 1-10000 cycles");
  }
  const cycleLength = transformation.cycle_length_years;
  if (!finiteNumber(cycleLength) || cycleLength <= 0
    || Math.abs(cycleLength - plan.cycle_length_years) > 1e-12) {
    reasons.push("transformation.cycle_length_years must equal the analysis cycle length");
  }
  const fromIndex = transformation.from_state_index;
  const eventIndex = transformation.event_state_index;
  const numericFromIndex = typeof fromIndex === "number" ? fromIndex : Number.NaN;
  const numericEventIndex = typeof eventIndex === "number" ? eventIndex : Number.NaN;
  const validIndices = Number.isInteger(numericFromIndex) && Number.isInteger(numericEventIndex)
    && numericFromIndex !== numericEventIndex && [numericFromIndex, numericEventIndex].includes(0)
    && [numericFromIndex, numericEventIndex].includes(1);
  if (!validIndices) {
    reasons.push("from_state_index and event_state_index must be the two distinct state indices");
  }
  const usedExtractions = new Set<string>();
  const usedAssumptions = new Set<string>();
  const hazardRatio = backgroundMortalityBasis(
    transformation.hazard_ratio, "transformation.hazard_ratio", true,
    usedExtractions, usedAssumptions, reasons,
  );
  if (hazardRatio === null || hazardRatio <= 0) {
    reasons.push("transformation.hazard_ratio.value must be finite and positive");
  }
  const reviewBases = transformation.review_bases;
  const reviewNames = [
    "effect_constancy_over_horizon", "endpoint_alignment", "population_transportability",
    "proportional_hazards_assumption", "treatment_switching_assessment",
  ];
  if (!isRecord(reviewBases) || !jsonEquivalent(Object.keys(reviewBases).sort(), reviewNames)) {
    reasons.push("transformation.review_bases fields are not the exact supported contract");
  } else {
    reviewNames.forEach((name) => {
      backgroundMortalityBasis(
        reviewBases[name], `transformation.review_bases.${name}`, false,
        usedExtractions, usedAssumptions, reasons,
      );
    });
  }
  const baseline = transformation.baseline_cumulative_hazards;
  if (!Array.isArray(baseline) || baseline.length !== plan.cycles) {
    return [...reasons, "transformation.baseline_cumulative_hazards must cover every model cycle"];
  }
  let previousHazard = 0;
  let anyPositive = false;
  const output: Array<{ start_cycle: number; matrix: number[][] }> = [];
  baseline.forEach((entry, index) => {
    const label = `transformation.baseline_cumulative_hazards[${index}]`;
    if (!isRecord(entry)
      || !jsonEquivalent(Object.keys(entry).sort(), ["cumulative_hazard", "cycle"])) {
      reasons.push(`${label} fields are not the exact supported contract`);
      return;
    }
    if (entry.cycle !== index + 1) reasons.push(`${label}.cycle must equal ${index + 1}`);
    const cumulativeHazard = backgroundMortalityBasis(
      entry.cumulative_hazard, `${label}.cumulative_hazard`, true,
      usedExtractions, usedAssumptions, reasons,
    );
    if (cumulativeHazard === null || cumulativeHazard < 0) {
      reasons.push(`${label}.cumulative_hazard.value must be finite and non-negative`);
      return;
    }
    if (cumulativeHazard + 1e-12 < previousHazard) {
      reasons.push("baseline_cumulative_hazards must be non-decreasing across cycles");
      return;
    }
    const increment = Math.max(0, cumulativeHazard - previousHazard);
    anyPositive ||= increment > 1e-12;
    previousHazard = cumulativeHazard;
    if (hazardRatio === null || hazardRatio <= 0 || !validIndices) return;
    const eventProbability = -Math.expm1(-hazardRatio * increment);
    if (!Number.isFinite(eventProbability) || eventProbability < 0 || eventProbability >= 1) {
      reasons.push(`${label} produced a non-finite or invalid event probability`);
      return;
    }
    const matrix = [[0, 0], [0, 0]];
    matrix[numericFromIndex][numericFromIndex] = 1 - eventProbability;
    matrix[numericFromIndex][numericEventIndex] = eventProbability;
    matrix[numericEventIndex][numericEventIndex] = 1;
    output.push({ start_cycle: index + 1, matrix });
  });
  if (!anyPositive) reasons.push("baseline_cumulative_hazards must contain at least one positive increment");
  if (output.length !== plan.cycles || !jsonEquivalent(output, modelValue(plan, mapping.path))) {
    reasons.push("hazard ratio does not reproduce the current transition schedule");
  }
  if (!sameStringSet(usedExtractions, new Set(extractionIds))) {
    reasons.push("transformation must use every selected extraction exactly as declared");
  }
  if (!sameStringSet(usedAssumptions, new Set(assumptionIds))) {
    reasons.push("transformation must use every proposed assumption exactly as declared");
  }
  return reasons;
}

function derivationReasons(
  plan: HeorAnalysisPlan,
  mapping: HeorInputProvenance,
  sourceIds: string[],
  assumptionIds: string[],
  extractionIds: string[],
): string[] {
  const reasons: string[] = [];
  const derivation = mapping.derivation;
  if (!isRecord(derivation)) return ["derivation must be an object"];
  const target = modelValue(plan, mapping.path);
  if (target === undefined || target === null || !("model_value" in derivation)
    || !jsonEquivalent(derivation.model_value, target)) {
    reasons.push("derivation.model_value does not match the current model input");
  }
  if (derivation.method === "deterministic_transformation") {
    const operation = isRecord(derivation.transformation)
      ? derivation.transformation.operation : undefined;
    if (operation === "constant_competing_rates") {
      reasons.push(...transitionRateReasons(plan, mapping, extractionIds, assumptionIds));
    } else if (operation === "parametric_survival_to_transition_schedule") {
      reasons.push(...survivalCurveReasons(plan, mapping, extractionIds, assumptionIds));
    } else if (operation === "single_event_probability_time_conversion") {
      reasons.push(...probabilityTimeReasons(plan, mapping, extractionIds, assumptionIds));
    } else if (operation === "background_plus_excess_mortality_to_transition_schedule") {
      reasons.push(...backgroundMortalityReasons(plan, mapping, extractionIds, assumptionIds));
    } else if (operation === "relative_effect_to_transition_schedule") {
      reasons.push(...relativeEffectReasons(plan, mapping, extractionIds, assumptionIds));
    } else if (operation === "hazard_ratio_to_transition_schedule") {
      reasons.push(...hazardRatioReasons(plan, mapping, extractionIds, assumptionIds));
    } else {
      reasons.push("deterministic transformation operation is unsupported");
    }
    return reasons;
  }
  const monetary = mapping.path.endsWith("state_costs") || mapping.path === "willingness_to_pay";
  if (sourceIds.length === 0) {
    if (derivation.method !== "explicit_assumption") {
      reasons.push("assumption-only input must use derivation method explicit_assumption");
    }
    if (extractionIds.length > 0) {
      reasons.push("explicit_assumption derivation must not claim extraction IDs");
    }
    if (assumptionIds.length === 0) {
      reasons.push("explicit_assumption derivation requires a proposed assumption");
    }
  } else {
    const expected = monetary ? "monetary_adjustment" : "direct_evidence";
    if (derivation.method !== expected) {
      reasons.push(`source-based input must use derivation method ${expected}`);
    } else if (derivation.method === "direct_evidence" && extractionIds.length !== 1) {
      reasons.push("direct_evidence requires exactly one extraction");
    }
  }
  return reasons;
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
  const sourceBased = (mapping.source_ids ?? []).filter(nonempty).length > 0;
  const selectedExtractions = new Set((mapping.extraction_ids ?? []).filter(nonempty));
  const usedExtractions = new Set<string>();
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
    if (sourceBased) {
      if (!nonempty(adjustment.source_extraction_id)
        || !selectedExtractions.has(adjustment.source_extraction_id)) {
        reasons.push(`${label}.source_extraction_id must reference a selected extraction`);
      } else {
        usedExtractions.add(adjustment.source_extraction_id);
      }
    } else if (adjustment.source_extraction_id !== undefined
      || adjustment.source_index !== undefined) {
      reasons.push(`${label} must not bind an extraction for an assumption-only input`);
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
  if (sourceBased && (usedExtractions.size !== selectedExtractions.size
    || [...selectedExtractions].some((id) => !usedExtractions.has(id)))) {
    reasons.push("monetary_adjustments must use every selected extraction");
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
  const structureNeutral = plan.schema_version === "0.12.0";
  for (const role of strategyIds(plan)) {
    const strategy = plan.strategies[role];
    const transitionField = strategy?.transition_schedule
      ? "transition_schedule"
      : "transition_matrix";
    if (!structureNeutral) requiredPaths.push(
      `strategies.${role}.initial_distribution`,
      `strategies.${role}.${transitionField}`,
    );
    requiredPaths.push(
      `strategies.${role}.state_costs`,
      `strategies.${role}.state_utilities`,
    );
  }
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
  if (!(plan.schema_version === "0.3.0" || plan.schema_version === "0.4.0"
    || plan.schema_version === "0.5.0" || plan.schema_version === "0.6.0"
    || plan.schema_version === "0.7.0" || plan.schema_version === "0.8.0"
    || plan.schema_version === "0.9.0" || plan.schema_version === "0.10.0"
    || plan.schema_version === "0.11.0" || plan.schema_version === "0.12.0")) {
    invalidMappings.push("schema_version must be 0.3.0 through 0.12.0 for approval review");
  }
  for (const role of strategyIds(plan)) {
    const strategy = plan.strategies[role];
    if (!strategy) {
      invalidMappings.push(`strategies.${role} is missing`);
      continue;
    }
    const hasMatrix = strategy.transition_matrix != null;
    const hasSchedule = strategy.transition_schedule != null;
    if (structureNeutral && (hasMatrix || hasSchedule)) {
      invalidMappings.push(
        `strategies.${role} transition structure is forbidden for partitioned survival`,
      );
    } else if (!structureNeutral && hasMatrix === hasSchedule) {
      invalidMappings.push(
        `strategies.${role} must define exactly one of transition_matrix or transition_schedule`,
      );
    }
    if (hasSchedule && !(plan.schema_version === "0.4.0" || plan.schema_version === "0.5.0"
      || plan.schema_version === "0.6.0" || plan.schema_version === "0.7.0"
      || plan.schema_version === "0.8.0" || plan.schema_version === "0.9.0"
      || plan.schema_version === "0.10.0" || plan.schema_version === "0.11.0")) {
      invalidMappings.push(
        `strategies.${role}.transition_schedule requires schema_version 0.4.0 through 0.11.0`,
      );
    }
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
    reasons.push(...derivationReasons(plan, mapping, sourceIds, assumptionIds, extractionIds));
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

export async function auditHeorPartitionedSurvival(): Promise<HeorPartitionedSurvivalAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_PARTITIONED_SURVIVAL_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorPartitionedSurvivalAudit>("audit_heor_partitioned_survival");
}

export async function auditHeorSurvivalExtrapolation(): Promise<HeorSurvivalReviewAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_SURVIVAL_REVIEW_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorSurvivalReviewAudit>("audit_heor_survival_extrapolation");
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

export async function runHeorPartitionedSurvival(
  projectId: string,
): Promise<HeorPartitionedSurvivalRunResult> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorPartitionedSurvivalRunResult>("run_heor_partitioned_survival", { projectId });
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
      extractedValue: "12500",
      sourceLocation: "Table 3, intervention arm",
      applicability: "CNY per cycle; Chinese payer setting; 2026 price year adjustment pending",
    },
    {
      extractionId: "extract-utility",
      recordId: "trial-utility-1",
      target: "strategies.intervention.state_utilities",
      extractedValue: "0.74",
      sourceLocation: "Supplement, Table S8",
      applicability: "Progression-free utility; advanced NSCLC population",
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
  schema_version: "0.3.0",
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
  correlationGroupCount: 0,
  scenarioCount: 0,
  iterations: null,
  primaryThreshold: null,
  thresholdCount: 0,
  omittedParameterCount: 0,
  jointSurvivalRequired: false,
  jointSurvivalManifestSha256: null,
  jointSurvivalDrawsSha256: null,
  jointSurvivalDrawCount: null,
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

export const HEOR_BROWSER_DEMO_PARTITIONED_SURVIVAL_AUDIT: HeorPartitionedSurvivalAudit = {
  required: false,
  complete: true,
  status: "not_required",
  psmId: "",
  analysisId: HEOR_BROWSER_DEMO_PLAN.analysis_id,
  analysisPlanSha256: "",
  partitionedSurvivalSha256: "",
  survivalCurveMaterializationsSha256: "",
  strategyCount: 0,
  curveCount: 0,
  timePointCount: 0,
  artifactBindings: [],
  errors: [],
};

export const HEOR_BROWSER_DEMO_SURVIVAL_REVIEW_AUDIT: HeorSurvivalReviewAudit = {
  complete: true,
  required: false,
  status: "not_required",
  reviewSha256: null,
  targetCount: 0,
  reviewCount: 0,
  analysisId: HEOR_BROWSER_DEMO_PLAN.analysis_id,
  targetPath: null,
  selectedFamily: null,
  candidateModels: 0,
  convergedModels: 0,
  failedModels: [],
  scenarioCount: 0,
  recommendedFamily: null,
  artifactBindings: [],
  targets: [],
  blockingGaps: [],
  errors: [],
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
  const partitionedSurvivalAudit = HEOR_BROWSER_DEMO_PARTITIONED_SURVIVAL_AUDIT;
  const survivalReviewAudit = HEOR_BROWSER_DEMO_SURVIVAL_REVIEW_AUDIT;
  const validationAudit = HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT;
  const reportingAudit = HEOR_BROWSER_DEMO_REPORTING_AUDIT;
  const authorized = approvedGates.includes("analysis_plan")
    && evidenceAudit.complete && referenceCaseAudit.complete && uncertaintyAudit.complete
    && budgetImpactAudit.complete;
  return {
    calculation: {
      analysis_id: HEOR_BROWSER_DEMO_PLAN.analysis_id,
      engine_version: "0.7.0",
      schema_version: "0.3.0",
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
          transition_mode: "static",
          transition_schedule_start_cycles: [1],
        },
        intervention: {
          name: "new_treatment",
          total_cost: 9649.958833579349,
          total_qaly: 1.8826406968498464,
          net_monetary_benefit: 178614.11085140528,
          occupancy: [],
          transition_mode: "static",
          transition_schedule_start_cycles: [1],
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
      partitionedSurvivalMatchesApproval: !partitionedSurvivalAudit.required,
      partitionedSurvivalAudit,
      survivalReviewMatchesApproval: !survivalReviewAudit.required,
      survivalReviewAudit,
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

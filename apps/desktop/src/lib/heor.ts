import { isTauri } from "./tauri";

export const HEOR_PLAN_PATH = "heor/analysis-plan.json";
export const HEOR_CONCEPTUAL_MODEL_PATH = "heor/conceptual-model.json";
export const HEOR_REFERENCE_CASE_ASSESSMENT_PATH = "heor/reference-case-assessment.json";
export const HEOR_UNCERTAINTY_PLAN_PATH = "heor/uncertainty-plan.json";
export const HEOR_BUDGET_IMPACT_PLAN_PATH = "heor/budget-impact-plan.json";
export const HEOR_PARTITIONED_SURVIVAL_PLAN_PATH = "heor/partitioned-survival-plan.json";
export const HEOR_SURVIVAL_EXTRAPOLATION_REVIEW_PATH = "heor/survival-extrapolation-review.json";
export const HEOR_SURVIVAL_EXTRAPOLATION_REVIEW_INDEX_PATH = "heor/survival-extrapolation-reviews.json";
export const HEOR_PAIRED_BOOTSTRAP_REQUEST_PATH = "heor/paired-survival-bootstrap-request.json";
export const HEOR_NETWORK_META_ANALYSIS_REQUEST_PATH = "heor/network-meta-analysis-request.json";
export const HEOR_POPULATION_ADJUSTED_COMPARISON_REQUEST_PATH = "heor/population-adjusted-comparison-request.json";
export const HEOR_MODEL_CALIBRATION_REQUEST_PATH = "heor/model-calibration-request.json";
export const HEOR_SEMI_MARKOV_MICROSIMULATION_REQUEST_PATH = "heor/semi-markov-microsimulation-request.json";
export const HEOR_RWE_CAUSAL_ANALYSIS_REQUEST_PATH = "heor/rwe-causal-analysis-request.json";
export const HEOR_MODEL_VALIDATION_PATH = "heor/model-validation.json";
export const HEOR_REPORT_PACKAGE_PATH = "heor/report-package.json";
export const HEOR_REPRODUCIBILITY_PACKAGE_PATH = "heor/reproducibility-package.json";
export const HEOR_REPORT_DOCUMENT_PATH = "heor/report.md";
export const HEOR_EVIDENCE_SEARCH_REQUEST_PATH = "heor/evidence-search-request.json";
export const HEOR_EVIDENCE_SYNTHESIS_PATH = "heor/evidence-synthesis.json";
export const HEOR_EVIDENCE_LIBRARY_PATH = "heor/evidence-library.json";
export const HEOR_METHODS_WATCHLIST_PATH = "heor/methods-watchlist.json";
export const HEOR_BASE_CASE_RESULT_PATH = "heor/results/base-case.json";
export const HEOR_UNCERTAINTY_RESULT_PATH = "heor/results/uncertainty.json";
export const HEOR_ADVANCED_VOI_PLAN_PATH = "heor/advanced-voi-plan.json";
export const HEOR_ADVANCED_VOI_RESULT_PATH = "heor/results/advanced-voi.json";
export const HEOR_ADVANCED_VOI_REPLAY_PATH = "heor/results/advanced-voi-replay.json";
export const HEOR_BUDGET_IMPACT_RESULT_PATH = "heor/results/budget-impact.json";
export const HEOR_PARTITIONED_SURVIVAL_RESULT_PATH = "heor/results/partitioned-survival.json";
export const RESEARCH_PRESENTATION_MANIFEST_PATH = "deliverables/research-presentation.json";
export const RESEARCH_PRESENTATION_OUTPUT_PATH = "deliverables/research-presentation.pptx";
export const RESEARCH_REPORT_MANIFEST_PATH = "deliverables/heor-report-export.json";
export const RESEARCH_REPORT_DOCX_PATH = "deliverables/heor-report.docx";
export const RESEARCH_REPORT_PDF_PATH = "deliverables/heor-report.pdf";
export const RESEARCH_REPORT_XLSX_PATH = "deliverables/heor-report.xlsx";
export const RESEARCH_TABLES_MANIFEST_PATH = "deliverables/research-tables.json";
export const RESEARCH_TABLES_XLSX_PATH = "deliverables/research-tables.xlsx";
export const RESEARCH_TABLES_CSV_DIRECTORY = "deliverables/research-tables";
export const JOURNAL_SUBMISSION_MANIFEST_PATH = "deliverables/journal-submission-check.json";
export const JOURNAL_SUBMISSION_MARKDOWN_PATH = "deliverables/journal-submission-check.md";
export const JOURNAL_SUBMISSION_RESULTS_PATH = "deliverables/journal-submission-check.results.json";
export const CONCEPTUAL_MODEL_LAYOUT_PATH = "deliverables/conceptual-model-layout.json";
export const CONCEPTUAL_MODEL_SVG_PATH = "deliverables/conceptual-model.svg";
export const CONCEPTUAL_MODEL_GRAPHML_PATH = "deliverables/conceptual-model.graphml";
export const CITATION_PLAN_PATH = "references/citation-plan.json";
export const CITATION_LIBRARY_PATH = "references/library.json";
export const CITATION_OUTPUT_PATH = "deliverables/references.md";

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

export interface ConceptualModelNodePosition {
  stateId: string;
  x: number;
  y: number;
}

export interface ConceptualModelDiagramAudit {
  complete: boolean;
  readyToGenerate: boolean;
  outputsCurrent: boolean;
  status: "incomplete" | "ready_to_generate" | "current";
  modelId: string;
  modelPath: string;
  layoutPath: string;
  svgPath: string;
  graphmlPath: string;
  auditPath: string;
  conceptualModelSha256: string;
  layoutSha256: string | null;
  svgSha256: string | null;
  graphmlSha256: string | null;
  stateCount: number;
  transitionCount: number;
  positions: ConceptualModelNodePosition[];
  humanReviewStatus: string;
  errors: string[];
  warnings: string[];
}

export interface CitationFormattingAudit {
  complete: boolean;
  readyToGenerate: boolean;
  outputCurrent: boolean;
  status: "missing" | "invalid" | "ready_to_generate" | "generated_current";
  documentId: string;
  title: string;
  styleId: string;
  planPath: string;
  libraryPath: string;
  outputPath: string;
  auditPath: string;
  planSha256: string;
  librarySha256: string;
  outputSha256: string | null;
  citationCount: number;
  bibliographyCount: number;
  metadataWarningCount: number;
  humanReviewStatus: string;
  errors: string[];
  warnings: string[];
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
  pairedBootstrapReviewRequired: boolean;
  jointSurvivalManifestSha256: string | null;
  jointSurvivalDrawsSha256: string | null;
  jointSurvivalDrawCount: number | null;
  invalidParameters: string[];
  errors: string[];
}

export interface HeorAdvancedVoiAudit {
  complete: boolean;
  reviewable: boolean;
  status: "complete" | "incomplete";
  voiId: string;
  analysisId: string;
  uncertaintyId: string;
  advancedVoiPlanSha256: string;
  analysisPlanSha256: string;
  uncertaintyPlanSha256: string;
  uncertaintyResultSha256: string;
  uncertaintySchemaVersion: string;
  decisionThreshold: number | null;
  populationYearCount: number;
  effectivePopulation: number | null;
  evppiGroupCount: number;
  evppiEvaluationCount: number | null;
  evsiDesignCount: number;
  evsiEvaluationCount: number | null;
  evsiTargetParameterId: string;
  resultSha256: string | null;
  replaySha256: string | null;
  errors: string[];
}

export interface HeorAdvancedVoiCalculation {
  schema_version: "0.1.0";
  engine_version: "0.1.0";
  voi_id: string;
  decision_threshold: number;
  population: {
    annual_affected_population: number[];
    discount_rate: number;
    effective_population: number;
  };
  population_evpi: {
    per_person_evpi: number;
    per_person_evpi_mcse: number;
    population_evpi: number;
    population_evpi_mcse: number;
  };
  evppi: Array<{
    group_id: string;
    label: string;
    parameter_ids: string[];
    per_person_evppi: number;
    per_person_evppi_mcse: number;
    population_evppi: number;
  }>;
  evsi: {
    target_group_id: string;
    target_parameter_id: string;
    study_delay_years: number;
    study_cost_basis: { currency: string; price_year: number };
    designs: Array<{
      sample_size: number;
      per_person_evsi: number;
      per_person_evsi_mcse: number;
      research_effective_population: number;
      population_evsi: number;
      study_cost: number;
      expected_net_benefit_of_sampling: number;
    }>;
  };
  replay_sha256: string;
  classification: "research_priority_calculation_for_human_review";
  limitations: string[];
}

export interface HeorAdvancedVoiRunResult {
  audit: HeorAdvancedVoiAudit;
  calculation: HeorAdvancedVoiCalculation;
  resultSha256: string;
  replaySha256: string;
  reviewStatus: "awaiting_human_review";
}

export interface HeorAdvancedVoiChecklist {
  decisionScopeThresholdReviewed: boolean;
  populationLifetimeImplementationReviewed: boolean;
  representedOmittedUncertaintyReviewed: boolean;
  evppiGroupingCorrelationReviewed: boolean;
  nestedMonteCarloPrecisionBiasReviewed: boolean;
  evsiPriorLikelihoodDataModelReviewed: boolean;
  researchDelayCostOpportunityCostReviewed: boolean;
  limitationsNoDecisionAuthorityReviewed: boolean;
}

export interface HeorAdvancedVoiReviewRequest {
  projectId: string;
  action: "accept" | "reject";
  resultSha256: string;
  replaySha256: string;
  checklist: HeorAdvancedVoiChecklist;
  actorLabel: string;
  rationale: string;
}

export interface HeorAdvancedVoiReviewEvent extends HeorAdvancedVoiReviewRequest {
  schemaVersion: number;
  sequence: number;
  reviewId: string;
  voiId: string;
  planSha256: string;
  timestamp: number;
  recordPath: string;
  recordSha256: string;
  assurance: string;
  previousHash: string | null;
  eventHash: string;
}

export interface HeorAdvancedVoiReviewLog {
  events: HeorAdvancedVoiReviewEvent[];
  chainHead: string | null;
  integrity: string;
  identityAssurance: string;
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
  treatmentEffectDurationRequired: boolean;
  treatmentEffectDurationSha256: string | null;
  treatmentEffectDurationScenarioCount: number | null;
  treatmentEffectDurationBaseCaseId: string | null;
  costInputNormalizationRequired: boolean;
  costInputNormalizationSha256: string | null;
  costInputNormalizationItemCount: number | null;
  utilityInputsRequired: boolean;
  utilityInputsSha256: string | null;
  utilityInputsItemCount: number | null;
  utilityInputsMappedItemCount: number | null;
  utilityInputsAdjustedItemCount: number | null;
  eventDisutilitiesRequired: boolean;
  eventDisutilitiesSha256: string | null;
  eventDisutilitiesItemCount: number | null;
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
  executionEnvironment: string | null;
  crossImplementationComplete: boolean;
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
  executionEnvironment: string | null;
  crossImplementationComplete: boolean;
  errors: string[];
}

export interface HeorSurvivalFitExecutionAudit {
  complete: boolean;
  eligibleForReview: boolean;
  status: string;
  executionId: string;
  resultSha256: string | null;
  candidateModels: number;
  convergedModels: number;
  crossImplementationComplete: boolean;
  parameterUncertaintyComplete: boolean;
  packageVersions: Record<string, string>;
  errors: string[];
}

export interface HeorPairedBootstrapAudit {
  complete: boolean;
  reviewable: boolean;
  status: string;
  executionId: string;
  resultPath: string;
  resultSha256: string | null;
  requestPath: string;
  requestSha256: string | null;
  candidatePath: string | null;
  candidateSha256: string | null;
  iterations: number;
  completedReplicates: number;
  failedReplicates: number;
  curveCount: number;
  strategyCounts: Record<string, number>;
  packageVersions: Record<string, string>;
  crossImplementationComplete: boolean;
  curveCoherenceComplete: boolean;
  dependencePreserved: boolean;
  betweenStrategyAssumption: string;
  limitations: string[];
  errors: string[];
}

export interface HeorPairedBootstrapChecklist {
  resamplingDesignReviewed: boolean;
  endpointsAndCensoringReviewed: boolean;
  selectedFamiliesReviewed: boolean;
  failuresAndConvergenceReviewed: boolean;
  followUpAndExtrapolationReviewed: boolean;
  parallelArmAssumptionReviewed: boolean;
  clinicalPlausibilityReviewed: boolean;
}

export interface HeorPairedBootstrapReviewRequest {
  projectId: string;
  resultPath: string;
  resultSha256: string;
  action: "accept" | "reject";
  checklist: HeorPairedBootstrapChecklist;
  actorLabel: string;
  rationale: string;
}

export interface HeorPairedBootstrapReviewEvent {
  schemaVersion: number;
  sequence: number;
  reviewId: string;
  projectId: string;
  executionId: string;
  action: "accept" | "reject";
  resultPath: string;
  resultSha256: string;
  relatedArtifacts: Array<{ path: string; sha256: string }>;
  checklist: HeorPairedBootstrapChecklist;
  actorLabel: string;
  rationale: string;
  timestamp: number;
  recordPath: string;
  recordSha256: string;
  assurance: string;
  previousHash: string | null;
  eventHash: string;
}

export interface HeorPairedBootstrapReviewLog {
  events: HeorPairedBootstrapReviewEvent[];
  chainHead: string | null;
  integrity: string;
  identityAssurance: string;
}

export interface HeorNetworkMetaAnalysisAudit {
  complete: boolean;
  reviewable: boolean;
  status: string;
  executionId: string;
  requestPath: string;
  requestSha256: string | null;
  resultPath: string;
  resultSha256: string | null;
  studyCount: number;
  treatmentCount: number;
  directComparisonCount: number;
  cycleRank: number;
  modelType: string;
  tau: number | null;
  crossImplementationScope: string;
  globalInconsistencyStatus: string;
  localInconsistencyCount: number;
  rankingMethod: string;
  limitations: string[];
  errors: string[];
}

export interface HeorNetworkMetaAnalysisChecklist {
  questionOutcomeEstimandReviewed: boolean;
  nodesConnectivityTwoArmBoundaryReviewed: boolean;
  studyContrastsProvenanceRiskOfBiasReviewed: boolean;
  transitivityEffectModifiersReviewed: boolean;
  modelTauMethodReviewed: boolean;
  heterogeneityPredictionReviewed: boolean;
  globalLocalInconsistencyReviewed: boolean;
  rankingTransportabilityLimitationsReviewed: boolean;
}

export interface HeorNetworkMetaAnalysisReviewRequest {
  projectId: string;
  resultPath: string;
  resultSha256: string;
  action: "accept" | "reject";
  checklist: HeorNetworkMetaAnalysisChecklist;
  actorLabel: string;
  rationale: string;
}

export interface HeorNetworkMetaAnalysisReviewEvent {
  schemaVersion: number;
  sequence: number;
  reviewId: string;
  projectId: string;
  executionId: string;
  action: "accept" | "reject";
  resultPath: string;
  resultSha256: string;
  relatedArtifacts: Array<{ path: string; sha256: string }>;
  checklist: HeorNetworkMetaAnalysisChecklist;
  actorLabel: string;
  rationale: string;
  timestamp: number;
  recordPath: string;
  recordSha256: string;
  assurance: string;
  previousHash: string | null;
  eventHash: string;
}

export interface HeorNetworkMetaAnalysisReviewLog {
  events: HeorNetworkMetaAnalysisReviewEvent[];
  chainHead: string | null;
  integrity: string;
  identityAssurance: string;
}

export interface HeorPopulationAdjustedComparisonAudit {
  complete: boolean;
  reviewable: boolean;
  status: string;
  executionId: string;
  requestPath: string;
  requestSha256: string | null;
  resultPath: string;
  resultSha256: string | null;
  rowCount: number;
  modifierCount: number;
  effectMeasure: string;
  essOverall: number | null;
  essRatio: number | null;
  maximumWeight: number | null;
  maxAbsBalanceError: number | null;
  unadjustedEstimate: number | null;
  adjustedEstimate: number | null;
  indirectEstimate: number | null;
  indirectSe: number | null;
  bootstrapIterations: number;
  bootstrapFailures: number;
  nativeScope: string;
  limitations: string[];
  errors: string[];
}

export interface HeorPopulationAdjustedComparisonChecklist {
  questionEstimandTargetCommonComparatorReviewed: boolean;
  randomizedConnectedEvidenceProvenanceReviewed: boolean;
  effectModifierRationaleCompletenessReviewed: boolean;
  ipdIntegrityPrivacyMissingnessReviewed: boolean;
  targetMomentsOverlapReviewed: boolean;
  calibrationBalanceWeightsEssReviewed: boolean;
  bootstrapPrecisionFailuresReviewed: boolean;
  residualBiasTransportabilityDownstreamReviewed: boolean;
}

export interface HeorPopulationAdjustedComparisonReviewRequest {
  projectId: string;
  resultPath: string;
  resultSha256: string;
  action: "accept" | "reject";
  checklist: HeorPopulationAdjustedComparisonChecklist;
  actorLabel: string;
  rationale: string;
}

export interface HeorPopulationAdjustedComparisonReviewEvent {
  schemaVersion: number;
  sequence: number;
  reviewId: string;
  projectId: string;
  executionId: string;
  action: "accept" | "reject";
  resultPath: string;
  resultSha256: string;
  relatedArtifacts: Array<{ path: string; sha256: string }>;
  checklist: HeorPopulationAdjustedComparisonChecklist;
  actorLabel: string;
  rationale: string;
  timestamp: number;
  recordPath: string;
  recordSha256: string;
  assurance: string;
  previousHash: string | null;
  eventHash: string;
}

export interface HeorPopulationAdjustedComparisonReviewLog {
  events: HeorPopulationAdjustedComparisonReviewEvent[];
  chainHead: string | null;
  integrity: string;
  identityAssurance: string;
}

export interface HeorModelCalibrationAudit {
  complete: boolean;
  reviewable: boolean;
  status: string;
  calibrationId: string;
  requestPath: string;
  requestSha256: string | null;
  resultPath: string;
  resultSha256: string | null;
  stateCount: number;
  parameterCount: number;
  trainingTargetCount: number;
  validationTargetCount: number;
  bestObjective: number | null;
  numericalRank: number | null;
  fullRank: boolean | null;
  heldOutRmse: number | null;
  searchEvaluations: number;
  nativeScope: string;
  limitations: string[];
  errors: string[];
}

export interface HeorModelCalibrationChecklist {
  questionModelPurposeTimeOriginReviewed: boolean;
  targetProvenancePopulationAlignmentRolesReviewed: boolean;
  parameterMeaningBoundsEvidenceReviewed: boolean;
  goodnessOfFitScalingCovarianceOmissionReviewed: boolean;
  searchConvergenceMultistartDiagnosticsReviewed: boolean;
  localIdentifiabilityAlternativeFitsReviewed: boolean;
  heldOutPredictiveValidationReviewed: boolean;
  uncertaintyStructureDownstreamLimitationsReviewed: boolean;
}

export interface HeorModelCalibrationReviewRequest {
  projectId: string;
  resultPath: string;
  resultSha256: string;
  action: "accept" | "reject";
  checklist: HeorModelCalibrationChecklist;
  actorLabel: string;
  rationale: string;
}

export interface HeorModelCalibrationReviewEvent {
  schemaVersion: number;
  sequence: number;
  reviewId: string;
  projectId: string;
  calibrationId: string;
  action: "accept" | "reject";
  resultPath: string;
  resultSha256: string;
  relatedArtifacts: Array<{ path: string; sha256: string }>;
  checklist: HeorModelCalibrationChecklist;
  actorLabel: string;
  rationale: string;
  timestamp: number;
  recordPath: string;
  recordSha256: string;
  assurance: string;
  previousHash: string | null;
  eventHash: string;
}

export interface HeorModelCalibrationReviewLog {
  events: HeorModelCalibrationReviewEvent[];
  chainHead: string | null;
  integrity: string;
  identityAssurance: string;
}

export interface HeorMicrosimulationComparisonAudit {
  baselineStrategyId: string;
  strategyId: string;
  incrementalCost: number;
  incrementalQaly: number;
  incrementalNetMonetaryBenefit: number;
  standardErrorIncrementalNetMonetaryBenefit: number;
}

export interface HeorMicrosimulationAudit {
  complete: boolean;
  reviewable: boolean;
  status: string;
  simulationId: string;
  requestPath: string;
  requestSha256: string | null;
  resultPath: string;
  resultSha256: string | null;
  stateCount: number;
  strategyCount: number;
  trackerCount: number;
  patientsPerReplicate: number;
  replicates: number;
  cycles: number;
  simulationSteps: number;
  traceRows: number;
  comparisons: HeorMicrosimulationComparisonAudit[];
  nativeScope: string;
  limitations: string[];
  errors: string[];
}

export interface HeorMicrosimulationChecklist {
  decisionProblemIndividualModelJustificationReviewed: boolean;
  statesHorizonTimingAbsorbingDeathReviewed: boolean;
  inputProvenancePopulationAlignmentReviewed: boolean;
  timeInStateRulesStateRewardsReviewed: boolean;
  historyTrackersTransitionEventCostsReviewed: boolean;
  prngSeedsCommonRandomNumbersTracesReviewed: boolean;
  monteCarloErrorReplicatesPerformanceReviewed: boolean;
  structuralParameterUncertaintyDownstreamLimitsReviewed: boolean;
}

export interface HeorMicrosimulationReviewRequest {
  projectId: string;
  resultPath: string;
  resultSha256: string;
  action: "accept" | "reject";
  checklist: HeorMicrosimulationChecklist;
  actorLabel: string;
  rationale: string;
}

export interface HeorMicrosimulationReviewEvent {
  schemaVersion: number;
  sequence: number;
  reviewId: string;
  projectId: string;
  simulationId: string;
  action: "accept" | "reject";
  resultPath: string;
  resultSha256: string;
  relatedArtifacts: Array<{ path: string; sha256: string }>;
  checklist: HeorMicrosimulationChecklist;
  actorLabel: string;
  rationale: string;
  timestamp: number;
  recordPath: string;
  recordSha256: string;
  assurance: string;
  previousHash: string | null;
  eventHash: string;
}

export interface HeorMicrosimulationReviewLog {
  events: HeorMicrosimulationReviewEvent[];
  chainHead: string | null;
  integrity: string;
  identityAssurance: string;
}

export interface HeorRweCausalAnalysisAudit {
  complete: boolean;
  reviewable: boolean;
  status: string;
  executionId: string;
  requestPath: string;
  requestSha256: string | null;
  resultPath: string;
  resultSha256: string | null;
  rowCount: number;
  observedOutcomeCount: number;
  followUpRate: number | null;
  confounderCount: number;
  estimand: string;
  essOverall: number | null;
  essRatio: number | null;
  maximumWeight: number | null;
  maximumObservationWeight: number | null;
  maxAbsPreSmd: number | null;
  maxAbsPostSmd: number | null;
  unadjustedRiskDifference: number | null;
  weightedRiskDifference: number | null;
  weightedStandardError: number | null;
  weightedLower: number | null;
  weightedUpper: number | null;
  overlapLower: number | null;
  overlapUpper: number | null;
  bootstrapIterations: number;
  bootstrapFailures: number;
  nativeScope: string;
  limitations: string[];
  errors: string[];
}

export interface HeorRweCausalAnalysisChecklist {
  targetTrialEstimandTimeZeroReviewed: boolean;
  dataProvenanceEligibilityNewUserActiveComparatorReviewed: boolean;
  confounderCausalRationaleMeasurementReviewed: boolean;
  missingnessFollowUpOutcomeIntegrityReviewed: boolean;
  propensityOverlapWeightsPositivityReviewed: boolean;
  balanceModelDiagnosticsReviewed: boolean;
  bootstrapPrecisionFailuresReviewed: boolean;
  residualBiasTransportabilityDownstreamReviewed: boolean;
}

export interface HeorRweCausalAnalysisReviewRequest {
  projectId: string;
  resultPath: string;
  resultSha256: string;
  action: "accept" | "reject";
  checklist: HeorRweCausalAnalysisChecklist;
  actorLabel: string;
  rationale: string;
}

export interface HeorRweCausalAnalysisReviewEvent {
  schemaVersion: number;
  sequence: number;
  reviewId: string;
  projectId: string;
  executionId: string;
  action: "accept" | "reject";
  resultPath: string;
  resultSha256: string;
  relatedArtifacts: Array<{ path: string; sha256: string }>;
  checklist: HeorRweCausalAnalysisChecklist;
  actorLabel: string;
  rationale: string;
  timestamp: number;
  recordPath: string;
  recordSha256: string;
  assurance: string;
  previousHash: string | null;
  eventHash: string;
}

export interface HeorRweCausalAnalysisReviewLog {
  events: HeorRweCausalAnalysisReviewEvent[];
  chainHead: string | null;
  integrity: string;
  identityAssurance: string;
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
  bindingHashes: Record<string, string>;
  bindingPaths: Record<string, string>;
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
  status: "complete" | "draft" | "incomplete";
  packageId: string;
  analysisId: string;
  reportPackageSha256: string;
  releaseOwnerLabel: string;
  bindingHashes: Record<string, string>;
  bindingPaths: Record<string, string>;
  reportingItemCount: number;
  requiredItemCount: number;
  coveredItemCount: number;
  draftOnlyReasons: string[];
  missingItems: string[];
  invalidItems: string[];
  errors: string[];
}

export interface HeorReproducibilityAudit {
  complete: boolean;
  releaseCompanionReady: boolean;
  status: "complete" | "draft" | "incomplete";
  packageId: string;
  analysisId: string;
  packageSha256: string;
  reportPackageSha256: string;
  runtimeMatches: boolean;
  artifactCount: number;
  executionCount: number;
  sourceCount: number;
  availabilityCount: number;
  exhibitCount: number;
  claimCount: number;
  requiredClaimCount: number;
  coveredClaimCount: number;
  draftOnlyReasons: string[];
  errors: string[];
}

export interface ResearchPresentationAudit {
  complete: boolean;
  readyToGenerate: boolean;
  outputCurrent: boolean;
  status: "missing" | "invalid" | "ready_to_generate" | "generated_current";
  deckId: string;
  title: string;
  manifestPath: string;
  outputPath: string;
  auditPath: string;
  manifestSha256: string;
  outputSha256: string | null;
  authoredSlideCount: number;
  renderedSlideCount: number;
  sourceCount: number;
  humanReviewStatus: string;
  errors: string[];
}

export interface ResearchReportAudit {
  complete: boolean;
  readyToGenerate: boolean;
  outputsCurrent: boolean;
  status: "missing" | "invalid" | "ready_to_generate" | "generated_current";
  documentId: string;
  title: string;
  manifestPath: string;
  docxPath: string;
  pdfPath: string;
  xlsxPath: string;
  auditPath: string;
  manifestSha256: string;
  reportPackageSha256: string;
  reportDocumentSha256: string;
  docxSha256: string | null;
  pdfSha256: string | null;
  xlsxSha256: string | null;
  blockCount: number;
  tableCount: number;
  workbookSheetCount: number;
  pdfPageCount: number;
  humanReviewStatus: string;
  fontName: string;
  fontVersion: string;
  fontLicense: string;
  fontSha256: string;
  errors: string[];
}

export interface ResearchTablesAudit {
  complete: boolean;
  readyToGenerate: boolean;
  outputsCurrent: boolean;
  status: "missing" | "invalid" | "ready" | "current";
  workbookId: string;
  title: string;
  manifestPath: string;
  xlsxPath: string;
  csvDirectory: string;
  auditPath: string;
  manifestSha256: string;
  sourceCount: number;
  tableCount: number;
  rowCount: number;
  csvFileCount: number;
  xlsxSha256: string | null;
  humanReviewStatus: string;
  neutralizedTextCount: number;
  errors: string[];
  warnings: string[];
}

export interface JournalSubmissionAudit {
  complete: boolean;
  readyToGenerate: boolean;
  outputsCurrent: boolean;
  status: "missing" | "invalid" | "ready" | "current";
  checkId: string;
  title: string;
  journalName: string;
  articleType: string;
  guideAccessedOn: string;
  manifestPath: string;
  markdownPath: string;
  resultsPath: string;
  auditPath: string;
  manifestSha256: string;
  fileCount: number;
  ruleCount: number;
  passedCount: number;
  failedRequiredCount: number;
  reviewIssueCount: number;
  unresolvedCount: number;
  humanReviewStatus: string;
  errors: string[];
  warnings: string[];
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

export type HeorSearchAuthorizationRequest = {
  projectId: string;
  requestSha256: string;
  permissionMode: "runtime_full_access";
} | {
  projectId: string;
  requestSha256: string;
  permissionMode: "human_confirmation";
  actorLabel: string;
  rationale: string;
  confirmedNoSensitiveData: true;
};

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
  searches?: HeorEvidenceSynthesisSearchSummary[];
  records?: HeorEvidenceSynthesisRecordSummary[];
  extractions?: HeorReviewableExtraction[];
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

export interface HeorEvidenceSynthesisSearchSummary {
  id: string;
  source: string;
  query: string;
  searchedOn: string;
  resultCount: number;
  runPath?: string;
}

export interface HeorEvidenceSynthesisRecordSummary {
  recordId: string;
  title: string;
  locator: string;
  sourceType: string;
  titleAbstractStatus: string;
  fullTextStatus: string;
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
  documents?: HeorEvidenceLibraryDocument[];
  errors: string[];
}

export interface HeorEvidenceLibraryDocument {
  path: string;
  sha256: string;
  bytes: number;
  mediaType: string;
  extractionStatus: string;
  pageCount: number;
  textSha256?: string;
  issue?: string;
}

export interface HeorMethodsWatchlistAudit {
  exists: boolean;
  complete: boolean;
  reviewable: boolean;
  status: "missing" | "invalid" | "draft" | "ready_for_human_review";
  watchlistId: string;
  asOfDate: string;
  watchlistSha256: string | null;
  sourceCount: number;
  currentCount: number;
  draftCount: number;
  unknownCount: number;
  overdueCount: number;
  changeCount: number;
  reviewedChangeCount: number;
  unresolvedChangeCount: number;
  affectedContractCount: number;
  sources?: Array<{
    sourceId: string;
    title: string;
    publicationStatus: string;
    canonicalUrl: string;
    snapshotPath?: string;
  }>;
  changes?: Array<{
    changeId: string;
    sourceId: string;
    summary: string;
    revalidationStatus: string;
    evidencePaths: string[];
  }>;
  overdueSources: string[];
  unresolvedChanges: string[];
  acceptanceEligibleChanges: string[];
  errors: string[];
}

export type HeorMethodsWatchlistReviewAction = "accept_revalidation" | "dismiss_change";

export interface HeorMethodsWatchlistReviewRequest {
  projectId: string;
  watchlistSha256: string;
  changeId: string;
  action: HeorMethodsWatchlistReviewAction;
  actorLabel: string;
  rationale: string;
}

export interface HeorMethodsWatchlistReviewEvent {
  schemaVersion: number;
  sequence: number;
  reviewId: string;
  projectId: string;
  watchlistId: string;
  watchlistSha256: string;
  changeId: string;
  action: HeorMethodsWatchlistReviewAction;
  actorLabel: string;
  rationale: string;
  timestamp: number;
  recordPath: string;
  recordSha256: string;
  assurance: string;
  previousHash: string | null;
  eventHash: string;
}

export interface HeorMethodsWatchlistReviewLog {
  events: HeorMethodsWatchlistReviewEvent[];
  chainHead: string | null;
  integrity: "verified_unanchored_sha256_chain";
  identityAssurance: "app_owned_local_human_assertion";
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

export interface HeorLibraryDirectoryImport {
  added: string[];
  skipped: string[];
}

export interface HeorBundledKnowledgeBaseInstall {
  schema: "ai4heor-bundled-knowledge-base/v1";
  bundleId: string;
  title: string;
  locale: string;
  updated: string;
  manifestSha256: string;
  added: string[];
  alreadyInstalled: boolean;
  audit: HeorEvidenceLibraryAudit;
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
  schema_version: "0.1.0" | "0.2.0" | "0.3.0" | "0.4.0" | "0.5.0" | "0.6.0" | "0.7.0" | "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0" | "0.12.0" | "0.13.0" | "0.14.0" | "0.15.0";
  analysis_id: string;
  economic_basis?: { currency: string; price_year: number };
  input_status?: string;
  decision_problem: HeorDecisionProblem;
  reference_case: { id: string; status: "current" | "draft" | "custom" };
  reference_case_assessment?: { path: string; content_sha256: string };
  uncertainty_analysis?: { path: string };
  budget_impact_analysis?: { path: string };
  partitioned_survival_analysis?: { path: string };
  cost_input_normalization?: { path: string };
  utility_inputs?: { path: string };
  event_disutilities?: { path: string };
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
  pre_event_total_qaly?: number;
  event_disutility_qaly_loss?: number;
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
    reproducibilityAudit: HeorReproducibilityAudit;
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
  calculation_classification: "calculation_only" | "partial_parameter_uncertainty" | "joint_curve_draw_parameter_uncertainty" | "component_parameter_uncertainty" | "joint_curve_and_component_parameter_uncertainty";
  uncertainty_scope?: "declared_model_parameters" | "economic_inputs_only" | "joint_survival_curves_and_economic_inputs" | "cost_utility_event_components_only" | "joint_survival_curves_and_cost_utility_event_components";
  partitioned_survival_plan_sha256?: string;
  survival_curve_materializations_sha256?: string;
  joint_survival_uncertainty_sha256?: string;
  joint_survival_draws_sha256?: string;
  cost_input_normalization_sha256?: string;
  utility_inputs_sha256?: string;
  event_disutilities_sha256?: string;
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
    artifact?: "cost_input_normalization" | "utility_inputs" | "event_disutilities";
    target: string;
    incremental_nmb_span?: number;
    net_monetary_benefit_span_by_strategy?: Record<string, number>;
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
      scale: "log_standard_normal" | "latent_standard_normal";
      method: "cholesky" | "gaussian_copula_cholesky";
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
    model_type?: "dynamic_annual_cohort";
    event_order?: string[];
    annual_results: Array<{
      year: number;
      eligible_population: number;
      without_new_intervention_share: number;
      with_new_intervention_share: number;
      without_new_intervention_cost: number;
      with_new_intervention_cost: number;
      net_budget_impact: number;
      without_new_intervention_flow?: HeorDynamicBudgetImpactFlow;
      with_new_intervention_flow?: HeorDynamicBudgetImpactFlow;
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

export interface HeorDynamicBudgetImpactFlow {
  opening_comparator: number;
  opening_intervention: number;
  incident_population: number;
  requested_incident_intervention_starts: number;
  incident_intervention_starts: number;
  requested_comparator_displacement_starts: number;
  comparator_displacement_starts: number;
  capacity: number;
  capacity_unmet_starts: number;
  comparator_treated: number;
  intervention_treated: number;
  treated_population: number;
  intervention_share: number;
  deaths: number;
  intervention_discontinuers_to_comparator: number;
  comparator_discontinuers_exiting: number;
  closing_comparator: number;
  closing_intervention: number;
  total_cost: number;
}

export interface HeorBudgetImpactRunResult {
  calculation: HeorBudgetImpactCalculation;
  workflow: HeorWorkflowStatus;
}

export interface HeorPartitionedSurvivalCalculation {
  schema_version: "0.3.0" | "0.4.0" | "0.5.0" | "0.6.0" | "0.7.0";
  engine_version: string;
  analysis_id: string;
  psm_id: string;
  analysis_plan_sha256: string;
  partitioned_survival_plan_sha256: string;
  partitioned_survival_plan_schema_version: "0.2.0" | "0.3.0" | "0.4.0" | "0.5.0" | "0.6.0" | "0.7.0";
  survival_curve_materializations_sha256: string;
  treatment_effect_duration_sha256?: string;
  event_disutilities_sha256?: string;
  event_disutilities_summary?: {
    event_disutility_id: string;
    item_count: number;
    one_time_item_count: number;
    recurrent_item_count: number;
    continuous_exposure_item_count: number;
  };
  treatment_effect_duration_scenarios?: Array<{
    scenario_id: string;
    label: string;
    strategy_order: string[];
    baseline_strategy_id: string;
    strategies: Record<string, Pick<HeorStrategyResult, "name" | "total_cost" | "total_qaly" | "net_monetary_benefit">>;
    pairwise_vs_baseline: Record<string, HeorIncrementalResult>;
    fully_incremental_analysis: NonNullable<HeorCalculation["fully_incremental_analysis"]>;
    optimal_at_primary_threshold: HeorCalculation["optimal_at_primary_threshold"];
  }>;
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

function requiredDecisionText(
  decision: Record<string, unknown>,
  field: string,
  allowLegacyArray = false,
): string {
  const value = decision[field];
  if (typeof value === "string" && value.trim()) return value.trim();
  if (allowLegacyArray
    && Array.isArray(value)
    && value.length > 0
    && value.every((item) => typeof item === "string" && item.trim())) {
    return value.map((item) => item.trim()).join("; ");
  }
  throw new Error(`decision_problem.${field} must be non-empty text`);
}

/** Parse enough of the app/engine contract to render a safe review snapshot.
 *  The deterministic engine remains the authoritative numerical validator. */
export function parseHeorPlan(raw: string): HeorAnalysisPlan {
  const value: unknown = JSON.parse(raw);
  if (!isRecord(value)) throw new Error("analysis plan must be a JSON object");
  if (!["0.1.0", "0.2.0", "0.3.0", "0.4.0", "0.5.0", "0.6.0", "0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0"].includes(String(value.schema_version))) {
    throw new Error("analysis plan schema_version must be 0.1.0 through 0.15.0");
  }
  if (typeof value.analysis_id !== "string" || !value.analysis_id.trim()) {
    throw new Error("analysis plan must include analysis_id");
  }
  if (!isRecord(value.decision_problem)) {
    throw new Error("analysis plan must include decision_problem metadata");
  }
  const rawDecision = value.decision_problem;
  const timeHorizonYears = rawDecision.time_horizon_years;
  if (typeof timeHorizonYears !== "number"
    || !Number.isFinite(timeHorizonYears)
    || timeHorizonYears <= 0) {
    throw new Error("decision_problem.time_horizon_years must be positive");
  }
  const jurisdiction = rawDecision.jurisdiction;
  if (jurisdiction !== undefined && (typeof jurisdiction !== "string" || !jurisdiction.trim())) {
    throw new Error("decision_problem.jurisdiction must be non-empty text when provided");
  }
  const decisionProblem: HeorDecisionProblem = {
    title: requiredDecisionText(rawDecision, "title"),
    population: requiredDecisionText(rawDecision, "population"),
    intervention: requiredDecisionText(rawDecision, "intervention", true),
    comparator: requiredDecisionText(rawDecision, "comparator", true),
    perspective: requiredDecisionText(rawDecision, "perspective"),
    time_horizon_years: timeHorizonYears,
    outcome: requiredDecisionText(rawDecision, "outcome"),
    ...(typeof jurisdiction === "string" ? { jurisdiction: jurisdiction.trim() } : {}),
  };
  if (!isRecord(value.reference_case) || !isRecord(value.strategies)) {
    throw new Error("analysis plan must include reference_case and strategies");
  }
  const parsedStrategies = value.strategies;
  if (["0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0"].includes(String(value.schema_version))) {
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
  return { ...value, decision_problem: decisionProblem } as unknown as HeorAnalysisPlan;
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
  return ["0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0"].includes(plan.schema_version)
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
  const structureNeutral = ["0.12.0", "0.13.0", "0.14.0", "0.15.0"].includes(plan.schema_version);
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
    || plan.schema_version === "0.11.0" || plan.schema_version === "0.12.0"
    || plan.schema_version === "0.13.0" || plan.schema_version === "0.14.0"
    || plan.schema_version === "0.15.0")) {
    invalidMappings.push("schema_version must be 0.3.0 through 0.15.0 for approval review");
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

  for (const [index, mapping] of (plan.input_provenance ?? []).entries()) {
    if (!mapping || typeof mapping !== "object") {
      invalidMappings.push(`input_provenance[${index}]: mapping must be an object`);
      continue;
    }
    const reasons: string[] = [];
    const path = nonempty(mapping.path) ? mapping.path : "";
    if (!path) reasons.push("path is missing");
    else if (!required.has(path)) reasons.push("path is not a required model input");
    if (path && seen.has(path)) reasons.push("path is duplicated");
    if (path) seen.add(path);
    if (!nonempty(mapping.unit)) reasons.push("unit is missing");
    if (!nonempty(mapping.jurisdiction)) reasons.push("jurisdiction is missing");
    if (!nonempty(mapping.selection_rationale)) reasons.push("selection rationale is missing");
    if (!(["fixed", "range_available", "distribution_available"] as string[])
      .includes(mapping.uncertainty_status)) reasons.push("uncertainty status is invalid");
    if (path.endsWith("state_costs") || path === "willingness_to_pay") {
      reasons.push(...monetaryAdjustmentReasons(plan, mapping, validBasisIds));
    }
    const sourceIds = (mapping.source_ids ?? []).filter(nonempty);
    const extractionIds = (mapping.extraction_ids ?? []).filter(nonempty);
    const assumptionIds = (mapping.assumption_ids ?? []).filter(nonempty);
    if (path) {
      reasons.push(...derivationReasons(plan, mapping, sourceIds, assumptionIds, extractionIds));
    }
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
    if (reasons.length === 0) covered.add(path);
    else invalidMappings.push(`${path || `input_provenance[${index}]`}: ${reasons.join("; ")}`);
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

const LEGACY_HEOR_PROMPT_PREAMBLE = [
  "Use $heor-workbench for this request.",
  "Work through natural-language dialogue first. Maintain heor/analysis-plan.json only when the decision problem and inputs are sufficiently defined; never create or claim human approvals.",
].join("\n");

const OPEN_SCIENCE_BASELINE_HEOR_PROMPT_PREAMBLE = [
  "Use $heor-workbench for this request.",
  "Preserve the Open Science baseline: continue the requested research, search, coding, and local execution unless a real scientific or safety decision is missing. Treat HEOR artifacts as progressive HEOR outputs, not prerequisites for starting useful work. Work through natural-language dialogue first; never create or claim human approvals.",
].join("\n");

const PREVIOUS_HEOR_PROMPT_PREAMBLE = [
  "Use $heor-workbench for this request.",
  "Preserve the Open Science baseline: continue the requested research, search, coding, and local execution unless a real scientific or safety decision is missing. Treat HEOR artifacts as progressive HEOR outputs, not prerequisites for starting useful work. Work through natural-language dialogue first; never create or claim human approvals.",
  "HEOR review-panel JSON paths are reserved machine contracts: create one only from its bundled first-party template and only after its bundled validator passes. Never invent a schema at heor/analysis-plan.json; use heor/analysis-plan.md for exploratory plans that are not yet eligible for the machine contract.",
].join("\n");

const HEOR_PROMPT_PREAMBLE = [
  "Use $heor-workbench for this request.",
  "Preserve the Open Science baseline: continue the requested research, search, coding, and local execution unless a real scientific or safety decision is missing. Treat HEOR artifacts as progressive HEOR outputs, not prerequisites for starting useful work. Work through natural-language dialogue first; never create or claim human approvals.",
  "HEOR review-panel JSON paths are reserved machine contracts: create one only from its bundled first-party template and only after its bundled validator passes. Never invent a schema at heor/analysis-plan.json; use heor/analysis-plan.md for exploratory plans that are not yet eligible for the machine contract.",
  "For a clear research request, start the requested work directly. Do not begin with Git status, .gitignore, README, a recursive directory inventory, or a generic harness/configuration audit; inspect only material the task actually depends on.",
  "Evidence claims must be auditable: do not call a numeric input sourced, current, or traceable unless its exact source and location are recorded. Keep unverified values explicitly marked as assumptions. If results depend on assumed inputs, report them as exploratory scenarios rather than a final cost-effectiveness conclusion.",
  "Do not use model training knowledge as a source of scientific facts. Before asserting a scientific, clinical, regulatory, epidemiological, economic, or methodological fact, retrieve and read a current public source during this task, or use an exact source supplied by the researcher. Cite the source and retrieval date. If no source can be retrieved, say that the fact is unverified and do not complete it from memory.",
  "For a named medicine, verify its identity, active ingredient, marketing-authorisation holder, jurisdiction, approved indication, and pivotal study from authoritative public sources before using them. Never infer an indication or approval from a brand name, mechanism, trial code, or trial phase. Never present model-generated medicine facts as answer options. Search public sources first and ask the researcher only about a remaining ambiguity or a study-specific choice.",
  "Decision-problem intake for a named medicine must follow a retrieve-then-confirm sequence. First search authoritative public sources for identity, approved indications, dosage forms and strengths, labelled population, jurisdiction, and evidence-supported comparator context. Summarize the retrieved candidates, then use the question tool to present a compact form for study-specific selection, correction, or supplementation. Every public-fact option description must include an exact public source locator and retrieval date. Do not ask the researcher to restate public facts in a free-text sentence. If sources conflict or retrieval leaves a real gap, show it and ask only for the unresolved study choice or non-public evidence.",
  "Current public literature and public data are assistant retrieval work, including medicine prices, tender or procurement prices, reimbursement payment standards, package specifications, and price dates. Search authorized bibliographic, regulator, HTA, reimbursement, procurement, manufacturer, and other authoritative public sources before asking the researcher for them. Record jurisdiction, source, retrieval date, package, unit, and price basis. If no suitable source is found after authorized alternatives are exhausted, report the searches performed and exact evidence gap; ask for non-public evidence only when that input is essential. Never put model-invented prices, sources, citations, PMIDs, document names, identifiers, placeholders, or informal invented terms into answer options.",
  "Preserve the requested outcome and quality floor. A failed URL, unavailable PDF, or missing single source does not authorize reducing the requested output to a narrative, tutorial, provisional hypothesis, researcher-do-it-yourself checklist, or exploratory substitute. Separate source-access failure from evidence absence: try reasonable authorized publisher or agency landing pages, HTML/XML/PDF variants, DOI/PMID records, bibliographic indexes, regulator and HTA records, trial registries, lawful repositories, procurement notices, manufacturer documents, and other authoritative public sources appropriate to the claim. A search snippet is not evidence. Exhaust reasonable routes and record them before declaring a gap; missing evidence blocks only the dependent claim or calculation, so continue all independent work. If an exhausted gap makes the requested outcome impossible, keep it incomplete and ask one bounded question for the exact missing scientific judgment or non-public evidence. Do not offer or automatically adopt an exploratory assumption unless the researcher explicitly requested exploratory, teaching, or sensitivity-analysis work.",
  "Every interactive question must be self-contained. Never refer to an above or below table, figure, chart, file, or list unless that exact content is visibly included in the same question. Suggested options are aids, not constraints: always allow the researcher to answer in their own words, for standalone tasks as well as project tasks.",
  "When a lawfully downloadable public file is actually used to support a research claim, archive it inside the current task or project with its source URL, retrieval time, local path, SHA-256, and rights or licence when known. Do not wait for a second request. Never claim it was archived unless both the file and manifest entry exist; if retrieval fails, report that failure and leave the claim unverified.",
  "Describe data flow precisely: local deterministic execution means only that the numerical engine ran on this computer. If the configured model provider is remote, the conversation and any model-visible project excerpts are processed by that provider. State separately whether an evidence-search or other network tool was used; never call the whole task fully local merely because the numerical calculation was local.",
  "System execution is assistant work; do not tell the researcher to operate evidence retrieval, local import, extraction ledgers, provenance mapping, deterministic execution, validators, or report packaging. Researcher decisions are scientific judgments that can change scope, methods, assumptions, interpretation, or permitted use.",
  "Once the researcher has selected the scope, method, model structure, and material assumptions needed for the current work, continue evidence retrieval, provenance preparation, deterministic derivation, validation, and packaging without ending a turn to ask whether to continue or which implementation step to do next. Reopen a choice only when new evidence creates a genuinely decision-relevant conflict.",
  "Before writing or updating any reserved review-panel artifact, copy the exact matching bundled first-party template, preserve supported existing fields, and run its matching validator. Do not add unknown fields, leave a newly written reserved artifact structurally invalid, or use the review panel as the first validator. If the requested work is not yet eligible for that contract, continue in an ordinary clearly labelled draft instead.",
  "Write strict JSON in every reserved review-panel artifact. Evaluate calculations before serialization and write only finite JSON number literals, never arithmetic expressions, formula strings, NaN, Infinity, or placeholder hashes. Create heor/event-disutilities.json only for an analysis-plan schema 0.15.0 after both the utility-input and event-disutility validators pass; otherwise keep event-loss work in an ordinary Markdown draft and leave that reserved JSON path absent.",
  "Keep the ordinary response and research report in natural HEOR language. Do not expose internal artifact paths, schema names, commands, hashes, environment variables, Skill identifiers, validators, panel mechanics, or gate identifiers there; retain those only in Technical details or Run records unless the researcher explicitly asks.",
].join("\n");

const HEOR_PROMPT_TEMPLATE_ID = "ai4heor/heor-workbench-preamble";
// Exact SHA-256 of HEOR_PROMPT_PREAMBLE. The test hashes the source material,
// so any instruction change must deliberately update this audit version.
const HEOR_PROMPT_TEMPLATE_SHA256 =
  "f609804550fe880650a3454ee28e2aa51bdac2e7552a6fb9dae2f0d7737e3b22";

export interface HeorPromptContext {
  promptTemplateId: string;
  promptTemplateSha256: string;
  responseLanguage: string;
}

const RESPONSE_LANGUAGE_NAMES: Record<string, string> = {
  en: "English",
  "zh-hans": "Simplified Chinese",
  ja: "Japanese",
  es: "Spanish",
  de: "German",
  fr: "French",
  ko: "Korean",
};

function responseLanguageContract(locale: string): string {
  const normalized = locale.trim().toLowerCase().replace(/_/g, "-");
  const base = normalized.split("-")[0];
  const language = RESPONSE_LANGUAGE_NAMES[normalized]
    ?? RESPONSE_LANGUAGE_NAMES[base]
    ?? RESPONSE_LANGUAGE_NAMES.en;
  return [
    `Response language contract: ${language}.`,
    `Write every assistant-authored progress update, question, heading, explanation, and final answer in ${language}.`,
    "Keep only source titles, exact quotations, code, file names, and established technical terms in their original language.",
    "Do not switch response language because tools, sources, or internal instructions use another language.",
  ].join(" ");
}

/** Add the domain contract to the provider request. It is runtime context, not
 *  researcher-authored content, so the conversation UI removes it again. */
export function buildHeorPrompt(userText: string, locale = "en"): string {
  return [HEOR_PROMPT_PREAMBLE, responseLanguageContract(locale), "", userText.trim()].join("\n");
}

/** Identify only the fixed app-owned HEOR template and language contract.
 * Researcher text and its hash are deliberately excluded. */
export function heorPromptContext(storedText: string): HeorPromptContext | null {
  const stored = storedText.trim();
  if (!stored.startsWith(`${HEOR_PROMPT_PREAMBLE}\n`)) return null;
  const remainder = stored.slice(HEOR_PROMPT_PREAMBLE.length + 1);
  const match = /^Response language contract: ([^.\n]{1,64})\./.exec(remainder);
  if (!match || !Object.values(RESPONSE_LANGUAGE_NAMES).includes(match[1])) return null;
  return {
    promptTemplateId: HEOR_PROMPT_TEMPLATE_ID,
    promptTemplateSha256: HEOR_PROMPT_TEMPLATE_SHA256,
    responseLanguage: match[1],
  };
}

/** Recover only the text the researcher entered from a stored provider prompt.
 *  An optional leading skill id is execution metadata and is shown separately
 *  by the live composer, so it must not reappear as raw syntax after reload. */
export function displayHeorPrompt(storedText: string): string {
  const stored = storedText.trim();
  const preamble = [
    HEOR_PROMPT_PREAMBLE,
    PREVIOUS_HEOR_PROMPT_PREAMBLE,
    OPEN_SCIENCE_BASELINE_HEOR_PROMPT_PREAMBLE,
    LEGACY_HEOR_PROMPT_PREAMBLE,
  ]
    .find((candidate) => stored.startsWith(candidate));
  if (!preamble) return stored;
  return stored
    .slice(preamble.length)
    .trim()
    .replace(/^Response language contract:[^\n]*(?:\n+|$)/i, "")
    .replace(/^\$[a-z0-9-]+\s*\n+/i, "")
    .trim();
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

export async function inspectHeorMarkovResult(
  projectId: string,
): Promise<HeorRunResult | null> {
  if (!isTauri) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorRunResult | null>("inspect_heor_markov_result", { projectId });
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

export async function auditHeorAdvancedVoi(): Promise<HeorAdvancedVoiAudit> {
  if (!isTauri) {
    return {
      complete: false,
      reviewable: false,
      status: "incomplete",
      voiId: "",
      analysisId: "",
      uncertaintyId: "",
      advancedVoiPlanSha256: "",
      analysisPlanSha256: "",
      uncertaintyPlanSha256: "",
      uncertaintyResultSha256: "",
      uncertaintySchemaVersion: "",
      decisionThreshold: null,
      populationYearCount: 0,
      effectivePopulation: null,
      evppiGroupCount: 0,
      evppiEvaluationCount: null,
      evsiDesignCount: 0,
      evsiEvaluationCount: null,
      evsiTargetParameterId: "",
      resultSha256: null,
      replaySha256: null,
      errors: ["Advanced VOI requires the desktop runtime."],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorAdvancedVoiAudit>("audit_heor_advanced_voi");
}

export async function runHeorAdvancedVoi(projectId: string): Promise<HeorAdvancedVoiRunResult> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorAdvancedVoiRunResult>("run_heor_advanced_voi", { projectId });
}

export async function appendHeorAdvancedVoiReview(
  request: HeorAdvancedVoiReviewRequest,
): Promise<HeorAdvancedVoiReviewEvent> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorAdvancedVoiReviewEvent>("append_heor_advanced_voi_review", { request });
}

export async function listHeorAdvancedVoiReviews(
  projectId: string,
): Promise<HeorAdvancedVoiReviewLog> {
  if (!isTauri) {
    return {
      events: [],
      chainHead: null,
      integrity: "verified_unanchored_sha256_chain",
      identityAssurance: "app_owned_local_human_assertion",
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorAdvancedVoiReviewLog>("list_heor_advanced_voi_reviews", { projectId });
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

export async function auditHeorSurvivalFitExecution(
  resultPath: string,
): Promise<HeorSurvivalFitExecutionAudit> {
  if (!isTauri) {
    return {
      complete: false,
      eligibleForReview: false,
      status: "unavailable",
      executionId: "",
      resultSha256: null,
      candidateModels: 0,
      convergedModels: 0,
      crossImplementationComplete: false,
      parameterUncertaintyComplete: false,
      packageVersions: {},
      errors: ["Local survival execution audit requires the desktop runtime."],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorSurvivalFitExecutionAudit>("audit_heor_survival_fit_execution", {
    resultPath,
  });
}

export async function auditHeorPairedSurvivalBootstrap(): Promise<HeorPairedBootstrapAudit> {
  if (!isTauri) {
    return {
      complete: false,
      reviewable: false,
      status: "unavailable",
      executionId: "",
      resultPath: "",
      resultSha256: null,
      requestPath: HEOR_PAIRED_BOOTSTRAP_REQUEST_PATH,
      requestSha256: null,
      candidatePath: null,
      candidateSha256: null,
      iterations: 0,
      completedReplicates: 0,
      failedReplicates: 0,
      curveCount: 0,
      strategyCounts: {},
      packageVersions: {},
      crossImplementationComplete: false,
      curveCoherenceComplete: false,
      dependencePreserved: false,
      betweenStrategyAssumption: "",
      limitations: [],
      errors: ["Native paired-bootstrap audit requires the desktop runtime."],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorPairedBootstrapAudit>("audit_heor_paired_survival_bootstrap");
}

export async function appendHeorPairedBootstrapReview(
  request: HeorPairedBootstrapReviewRequest,
): Promise<HeorPairedBootstrapReviewEvent> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorPairedBootstrapReviewEvent>("append_heor_paired_bootstrap_review", {
    request,
  });
}

export async function listHeorPairedBootstrapReviews(
  projectId: string,
): Promise<HeorPairedBootstrapReviewLog> {
  if (!isTauri) {
    return {
      events: [],
      chainHead: null,
      integrity: "verified_unanchored_sha256_chain",
      identityAssurance: "app_owned_local_human_assertion",
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorPairedBootstrapReviewLog>("list_heor_paired_bootstrap_reviews", {
    projectId,
  });
}

export async function auditHeorNetworkMetaAnalysis(): Promise<HeorNetworkMetaAnalysisAudit> {
  if (!isTauri) {
    return {
      complete: false,
      reviewable: false,
      status: "unavailable",
      executionId: "",
      requestPath: HEOR_NETWORK_META_ANALYSIS_REQUEST_PATH,
      requestSha256: null,
      resultPath: "",
      resultSha256: null,
      studyCount: 0,
      treatmentCount: 0,
      directComparisonCount: 0,
      cycleRank: 0,
      modelType: "",
      tau: null,
      crossImplementationScope: "",
      globalInconsistencyStatus: "",
      localInconsistencyCount: 0,
      rankingMethod: "",
      limitations: [],
      errors: ["Native network meta-analysis audit requires the desktop runtime."],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorNetworkMetaAnalysisAudit>("audit_heor_network_meta_analysis");
}

export async function appendHeorNetworkMetaAnalysisReview(
  request: HeorNetworkMetaAnalysisReviewRequest,
): Promise<HeorNetworkMetaAnalysisReviewEvent> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorNetworkMetaAnalysisReviewEvent>("append_heor_network_meta_analysis_review", {
    request,
  });
}

export async function listHeorNetworkMetaAnalysisReviews(
  projectId: string,
): Promise<HeorNetworkMetaAnalysisReviewLog> {
  if (!isTauri) {
    return {
      events: [],
      chainHead: null,
      integrity: "verified_unanchored_sha256_chain",
      identityAssurance: "app_owned_local_human_assertion",
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorNetworkMetaAnalysisReviewLog>("list_heor_network_meta_analysis_reviews", {
    projectId,
  });
}

export async function auditHeorPopulationAdjustedComparison(): Promise<HeorPopulationAdjustedComparisonAudit> {
  if (!isTauri) {
    return {
      complete: false,
      reviewable: false,
      status: "unavailable",
      executionId: "",
      requestPath: HEOR_POPULATION_ADJUSTED_COMPARISON_REQUEST_PATH,
      requestSha256: null,
      resultPath: "",
      resultSha256: null,
      rowCount: 0,
      modifierCount: 0,
      effectMeasure: "",
      essOverall: null,
      essRatio: null,
      maximumWeight: null,
      maxAbsBalanceError: null,
      unadjustedEstimate: null,
      adjustedEstimate: null,
      indirectEstimate: null,
      indirectSe: null,
      bootstrapIterations: 0,
      bootstrapFailures: 0,
      nativeScope: "calibration_and_point_estimate_only",
      limitations: [],
      errors: ["Native population-adjusted comparison audit requires the desktop runtime."],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorPopulationAdjustedComparisonAudit>("audit_heor_population_adjusted_comparison");
}

export async function appendHeorPopulationAdjustedComparisonReview(
  request: HeorPopulationAdjustedComparisonReviewRequest,
): Promise<HeorPopulationAdjustedComparisonReviewEvent> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorPopulationAdjustedComparisonReviewEvent>(
    "append_heor_population_adjusted_comparison_review",
    { request },
  );
}

export async function listHeorPopulationAdjustedComparisonReviews(
  projectId: string,
): Promise<HeorPopulationAdjustedComparisonReviewLog> {
  if (!isTauri) {
    return {
      events: [],
      chainHead: null,
      integrity: "verified_unanchored_sha256_chain",
      identityAssurance: "app_owned_local_human_assertion",
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorPopulationAdjustedComparisonReviewLog>(
    "list_heor_population_adjusted_comparison_reviews",
    { projectId },
  );
}

export async function auditHeorModelCalibration(): Promise<HeorModelCalibrationAudit> {
  if (!isTauri) {
    return {
      complete: false,
      reviewable: false,
      status: "unavailable",
      calibrationId: "",
      requestPath: HEOR_MODEL_CALIBRATION_REQUEST_PATH,
      requestSha256: null,
      resultPath: "",
      resultSha256: null,
      stateCount: 0,
      parameterCount: 0,
      trainingTargetCount: 0,
      validationTargetCount: 0,
      bestObjective: null,
      numericalRank: null,
      fullRank: null,
      heldOutRmse: null,
      searchEvaluations: 0,
      nativeScope: "selected_point_model_and_local_identifiability_only",
      limitations: [],
      errors: ["Native model calibration audit requires the desktop runtime."],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorModelCalibrationAudit>("audit_heor_model_calibration");
}

export async function appendHeorModelCalibrationReview(
  request: HeorModelCalibrationReviewRequest,
): Promise<HeorModelCalibrationReviewEvent> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorModelCalibrationReviewEvent>("append_heor_model_calibration_review", {
    request,
  });
}

export async function listHeorModelCalibrationReviews(
  projectId: string,
): Promise<HeorModelCalibrationReviewLog> {
  if (!isTauri) {
    return {
      events: [],
      chainHead: null,
      integrity: "verified_unanchored_sha256_chain",
      identityAssurance: "app_owned_local_human_assertion",
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorModelCalibrationReviewLog>("list_heor_model_calibration_reviews", {
    projectId,
  });
}

export async function auditHeorMicrosimulation(): Promise<HeorMicrosimulationAudit> {
  if (!isTauri) {
    return {
      complete: false,
      reviewable: false,
      status: "unavailable",
      simulationId: "",
      requestPath: HEOR_SEMI_MARKOV_MICROSIMULATION_REQUEST_PATH,
      requestSha256: null,
      resultPath: "",
      resultSha256: null,
      stateCount: 0,
      strategyCount: 0,
      trackerCount: 0,
      patientsPerReplicate: 0,
      replicates: 0,
      cycles: 0,
      simulationSteps: 0,
      traceRows: 0,
      comparisons: [],
      nativeScope: "complete_patient_cycle_summary_and_sampled_trace_replay",
      limitations: [],
      errors: ["Native microsimulation audit requires the desktop runtime."],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorMicrosimulationAudit>("audit_heor_microsimulation");
}

export async function appendHeorMicrosimulationReview(
  request: HeorMicrosimulationReviewRequest,
): Promise<HeorMicrosimulationReviewEvent> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorMicrosimulationReviewEvent>("append_heor_microsimulation_review", {
    request,
  });
}

export async function listHeorMicrosimulationReviews(
  projectId: string,
): Promise<HeorMicrosimulationReviewLog> {
  if (!isTauri) {
    return {
      events: [],
      chainHead: null,
      integrity: "verified_unanchored_sha256_chain",
      identityAssurance: "app_owned_local_human_assertion",
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorMicrosimulationReviewLog>("list_heor_microsimulation_reviews", {
    projectId,
  });
}

export async function auditHeorRweCausalAnalysis(): Promise<HeorRweCausalAnalysisAudit> {
  if (!isTauri) {
    return {
      complete: false,
      reviewable: false,
      status: "unavailable",
      executionId: "",
      requestPath: HEOR_RWE_CAUSAL_ANALYSIS_REQUEST_PATH,
      requestSha256: null,
      resultPath: "",
      resultSha256: null,
      rowCount: 0,
      observedOutcomeCount: 0,
      followUpRate: null,
      confounderCount: 0,
      estimand: "source_cohort_ate_risk_difference_if_no_outcome_loss",
      essOverall: null,
      essRatio: null,
      maximumWeight: null,
      maximumObservationWeight: null,
      maxAbsPreSmd: null,
      maxAbsPostSmd: null,
      unadjustedRiskDifference: null,
      weightedRiskDifference: null,
      weightedStandardError: null,
      weightedLower: null,
      weightedUpper: null,
      overlapLower: null,
      overlapUpper: null,
      bootstrapIterations: 0,
      bootstrapFailures: 0,
      nativeScope: "point_estimate_and_diagnostics_only",
      limitations: [],
      errors: ["Native RWE causal-analysis audit requires the desktop runtime."],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorRweCausalAnalysisAudit>("audit_heor_rwe_causal_analysis");
}

export async function appendHeorRweCausalAnalysisReview(
  request: HeorRweCausalAnalysisReviewRequest,
): Promise<HeorRweCausalAnalysisReviewEvent> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorRweCausalAnalysisReviewEvent>(
    "append_heor_rwe_causal_analysis_review",
    { request },
  );
}

export async function listHeorRweCausalAnalysisReviews(
  projectId: string,
): Promise<HeorRweCausalAnalysisReviewLog> {
  if (!isTauri) {
    return {
      events: [],
      chainHead: null,
      integrity: "verified_unanchored_sha256_chain",
      identityAssurance: "app_owned_local_human_assertion",
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorRweCausalAnalysisReviewLog>("list_heor_rwe_causal_analysis_reviews", {
    projectId,
  });
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

export async function auditHeorReproducibility(): Promise<HeorReproducibilityAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_REPRODUCIBILITY_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorReproducibilityAudit>("audit_heor_reproducibility");
}

export async function auditResearchPresentation(): Promise<ResearchPresentationAudit> {
  if (!isTauri) return RESEARCH_PRESENTATION_BROWSER_DEMO_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ResearchPresentationAudit>("audit_research_presentation");
}

export async function generateResearchPresentation(): Promise<ResearchPresentationAudit> {
  if (!isTauri) throw new Error("presentation generation is available only in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ResearchPresentationAudit>("generate_research_presentation");
}

export async function auditResearchReport(): Promise<ResearchReportAudit> {
  if (!isTauri) return RESEARCH_REPORT_BROWSER_DEMO_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ResearchReportAudit>("audit_research_report");
}

export async function generateResearchReport(): Promise<ResearchReportAudit> {
  if (!isTauri) throw new Error("report generation is available only in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ResearchReportAudit>("generate_research_report");
}

export async function auditResearchTables(): Promise<ResearchTablesAudit> {
  if (!isTauri) return RESEARCH_TABLES_BROWSER_DEMO_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ResearchTablesAudit>("audit_research_tables");
}

export async function generateResearchTables(): Promise<ResearchTablesAudit> {
  if (!isTauri) throw new Error("research table generation is available only in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ResearchTablesAudit>("generate_research_tables");
}

export async function auditJournalSubmission(): Promise<JournalSubmissionAudit> {
  if (!isTauri) return JOURNAL_SUBMISSION_BROWSER_DEMO_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<JournalSubmissionAudit>("audit_journal_submission");
}

export async function generateJournalSubmission(): Promise<JournalSubmissionAudit> {
  if (!isTauri) throw new Error("journal submission checking is available only in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<JournalSubmissionAudit>("generate_journal_submission");
}

export async function auditConceptualModelDiagram(): Promise<ConceptualModelDiagramAudit> {
  if (!isTauri) return CONCEPTUAL_MODEL_DIAGRAM_BROWSER_DEMO_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ConceptualModelDiagramAudit>("audit_conceptual_model_diagram");
}

export async function generateConceptualModelDiagram(
  positions: ConceptualModelNodePosition[],
): Promise<ConceptualModelDiagramAudit> {
  if (!isTauri) throw new Error("conceptual-model diagram export is available only in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ConceptualModelDiagramAudit>("generate_conceptual_model_diagram", { positions });
}

export async function auditCitationFormatting(): Promise<CitationFormattingAudit> {
  if (!isTauri) return CITATION_FORMATTING_BROWSER_DEMO_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<CitationFormattingAudit>("audit_citation_formatting");
}

export async function generateCitationFormatting(): Promise<CitationFormattingAudit> {
  if (!isTauri) throw new Error("reference formatting is available only in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<CitationFormattingAudit>("generate_citation_formatting");
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

export async function auditHeorMethodsWatchlist(): Promise<HeorMethodsWatchlistAudit> {
  if (!isTauri) return HEOR_BROWSER_DEMO_METHODS_WATCHLIST_AUDIT;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorMethodsWatchlistAudit>("audit_heor_methods_watchlist");
}

export async function appendHeorMethodsWatchlistReview(
  request: HeorMethodsWatchlistReviewRequest,
): Promise<HeorMethodsWatchlistReviewEvent> {
  if (!isTauri) throw new Error("methods watchlist review is available only in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorMethodsWatchlistReviewEvent>("append_heor_methods_watchlist_review", {
    request,
  });
}

export async function listHeorMethodsWatchlistReviews(
  projectId: string,
): Promise<HeorMethodsWatchlistReviewLog> {
  if (!isTauri) {
    return {
      events: [],
      chainHead: null,
      integrity: "verified_unanchored_sha256_chain",
      identityAssurance: "app_owned_local_human_assertion",
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorMethodsWatchlistReviewLog>("list_heor_methods_watchlist_reviews", {
    projectId,
  });
}

export async function addHeorLibraryFiles(): Promise<string[]> {
  if (!isTauri) return [];
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string[]>("add_heor_library_files");
}

export async function addHeorLibraryDirectory(): Promise<HeorLibraryDirectoryImport> {
  if (!isTauri) return { added: [], skipped: [] };
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorLibraryDirectoryImport>("add_heor_library_directory");
}

export async function installBundledHeorKnowledgeBase(
  projectId: string,
): Promise<HeorBundledKnowledgeBaseInstall> {
  if (!isTauri) throw new Error("bundled HEOR knowledge base is available only in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<HeorBundledKnowledgeBaseInstall>("install_bundled_heor_knowledge_base", {
    projectId,
  });
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
    identityAssurance: "app_owned_network_execution_chain",
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
  searches: [
    {
      id: "pubmed-demo",
      source: "pubmed",
      query: "NSCLC AND cost effectiveness",
      searchedOn: "2026-07-24",
      resultCount: 12,
      runPath: "heor/search-runs/pubmed-demo.json",
    },
    {
      id: "clinicaltrials-demo",
      source: "clinicaltrials",
      query: "advanced NSCLC first line",
      searchedOn: "2026-07-24",
      resultCount: 6,
      runPath: "heor/search-runs/clinicaltrials-demo.json",
    },
  ],
  records: [
    {
      recordId: "trial-cost-1",
      title: "Economic evaluation of first-line treatment in advanced NSCLC",
      locator: "https://pubmed.ncbi.nlm.nih.gov/30000001/",
      sourceType: "pubmed",
      titleAbstractStatus: "include",
      fullTextStatus: "include",
    },
    {
      recordId: "trial-utility-1",
      title: "Health-state utilities in advanced NSCLC",
      locator: "https://pubmed.ncbi.nlm.nih.gov/30000002/",
      sourceType: "pubmed",
      titleAbstractStatus: "include",
      fullTextStatus: "include",
    },
    {
      recordId: "trial-effect-1",
      title: "Comparative effectiveness of first-line NSCLC strategies",
      locator: "https://pubmed.ncbi.nlm.nih.gov/30000003/",
      sourceType: "pubmed",
      titleAbstractStatus: "include",
      fullTextStatus: "include",
    },
    {
      recordId: "trial-safety-1",
      title: "Safety outcomes in advanced NSCLC treatment",
      locator: "https://pubmed.ncbi.nlm.nih.gov/30000004/",
      sourceType: "pubmed",
      titleAbstractStatus: "include",
      fullTextStatus: "include",
    },
    ...Array.from({ length: 12 }, (_, index) => ({
      recordId: `candidate-${index + 1}`,
      title: `Public evidence candidate ${index + 1}`,
      locator: `https://clinicaltrials.gov/study/NCT${String(index + 1).padStart(8, "0")}`,
      sourceType: "clinicaltrials",
      titleAbstractStatus: "not_assessed",
      fullTextStatus: "not_assessed",
    })),
    {
      recordId: "excluded-1",
      title: "Excluded evidence record 1",
      locator: "https://pubmed.ncbi.nlm.nih.gov/30000017/",
      sourceType: "pubmed",
      titleAbstractStatus: "exclude",
      fullTextStatus: "exclude",
    },
    {
      recordId: "excluded-2",
      title: "Excluded evidence record 2",
      locator: "https://pubmed.ncbi.nlm.nih.gov/30000018/",
      sourceType: "pubmed",
      titleAbstractStatus: "exclude",
      fullTextStatus: "exclude",
    },
  ],
  extractions: [
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
  documents: [
    {
      path: "heor/library/clinical-guideline.pdf",
      sha256: "a".repeat(64),
      bytes: 640_000,
      mediaType: "application/pdf",
      extractionStatus: "indexed",
      pageCount: 48,
      textSha256: "1".repeat(64),
    },
    {
      path: "heor/library/economic-evaluation.pdf",
      sha256: "b".repeat(64),
      bytes: 480_000,
      mediaType: "application/pdf",
      extractionStatus: "indexed",
      pageCount: 16,
      textSha256: "2".repeat(64),
    },
    {
      path: "heor/library/price-source.html",
      sha256: "c".repeat(64),
      bytes: 160_000,
      mediaType: "text/html",
      extractionStatus: "indexed",
      pageCount: 1,
      textSha256: "3".repeat(64),
    },
  ],
  errors: [],
};

export const HEOR_BROWSER_DEMO_METHODS_WATCHLIST_AUDIT: HeorMethodsWatchlistAudit = {
  exists: false,
  complete: false,
  reviewable: false,
  status: "missing",
  watchlistId: "",
  asOfDate: "",
  watchlistSha256: null,
  sourceCount: 0,
  currentCount: 0,
  draftCount: 0,
  unknownCount: 0,
  overdueCount: 0,
  changeCount: 0,
  reviewedChangeCount: 0,
  unresolvedChangeCount: 0,
  affectedContractCount: 0,
  overdueSources: [],
  unresolvedChanges: [],
  acceptanceEligibleChanges: [],
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

export const CONCEPTUAL_MODEL_DIAGRAM_BROWSER_DEMO_AUDIT: ConceptualModelDiagramAudit = {
  complete: true,
  readyToGenerate: true,
  outputsCurrent: false,
  status: "ready_to_generate",
  modelId: HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL.model_id,
  modelPath: HEOR_CONCEPTUAL_MODEL_PATH,
  layoutPath: CONCEPTUAL_MODEL_LAYOUT_PATH,
  svgPath: CONCEPTUAL_MODEL_SVG_PATH,
  graphmlPath: CONCEPTUAL_MODEL_GRAPHML_PATH,
  auditPath: "deliverables/conceptual-model.audit.json",
  conceptualModelSha256: "",
  layoutSha256: null,
  svgSha256: null,
  graphmlSha256: null,
  stateCount: HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL.states.length,
  transitionCount: HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL.transitions.length,
  positions: [],
  humanReviewStatus: "awaiting_human_review",
  errors: [],
  warnings: [],
};

export const CITATION_FORMATTING_BROWSER_DEMO_AUDIT: CitationFormattingAudit = {
  complete: false,
  readyToGenerate: false,
  outputCurrent: false,
  status: "missing",
  documentId: "",
  title: "",
  styleId: "",
  planPath: CITATION_PLAN_PATH,
  libraryPath: CITATION_LIBRARY_PATH,
  outputPath: CITATION_OUTPUT_PATH,
  auditPath: "deliverables/references.audit.json",
  planSha256: "",
  librarySha256: "",
  outputSha256: null,
  citationCount: 0,
  bibliographyCount: 0,
  metadataWarningCount: 0,
  humanReviewStatus: "awaiting_human_review",
  errors: ["references/citation-plan.json is required"],
  warnings: [],
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
  pairedBootstrapReviewRequired: false,
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
  treatmentEffectDurationRequired: false,
  treatmentEffectDurationSha256: null,
  treatmentEffectDurationScenarioCount: null,
  treatmentEffectDurationBaseCaseId: null,
  costInputNormalizationRequired: false,
  costInputNormalizationSha256: null,
  costInputNormalizationItemCount: null,
  utilityInputsRequired: false,
  utilityInputsSha256: null,
  utilityInputsItemCount: null,
  utilityInputsMappedItemCount: null,
  utilityInputsAdjustedItemCount: null,
  eventDisutilitiesRequired: false,
  eventDisutilitiesSha256: null,
  eventDisutilitiesItemCount: null,
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
  executionEnvironment: null,
  crossImplementationComplete: false,
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
  bindingHashes: {},
  bindingPaths: {},
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
  bindingPaths: {},
  reportingItemCount: 0,
  requiredItemCount: 40,
  coveredItemCount: 0,
  draftOnlyReasons: [],
  missingItems: ["heor/report-package.json is required"],
  invalidItems: [],
  errors: ["heor/report-package.json is required"],
};

export const HEOR_BROWSER_DEMO_REPRODUCIBILITY_AUDIT: HeorReproducibilityAudit = {
  complete: false,
  releaseCompanionReady: false,
  status: "incomplete",
  packageId: "",
  analysisId: HEOR_BROWSER_DEMO_PLAN.analysis_id,
  packageSha256: "",
  reportPackageSha256: "",
  runtimeMatches: false,
  artifactCount: 0,
  executionCount: 0,
  sourceCount: 0,
  availabilityCount: 0,
  exhibitCount: 0,
  claimCount: 0,
  requiredClaimCount: 7,
  coveredClaimCount: 0,
  draftOnlyReasons: [],
  errors: ["heor/reproducibility-package.json is required"],
};

export const RESEARCH_PRESENTATION_BROWSER_DEMO_AUDIT: ResearchPresentationAudit = {
  complete: false,
  readyToGenerate: false,
  outputCurrent: false,
  status: "missing",
  deckId: "",
  title: "",
  manifestPath: RESEARCH_PRESENTATION_MANIFEST_PATH,
  outputPath: RESEARCH_PRESENTATION_OUTPUT_PATH,
  auditPath: "deliverables/research-presentation.audit.json",
  manifestSha256: "",
  outputSha256: null,
  authoredSlideCount: 0,
  renderedSlideCount: 0,
  sourceCount: 0,
  humanReviewStatus: "",
  errors: [`${RESEARCH_PRESENTATION_MANIFEST_PATH} is required`],
};

export const RESEARCH_REPORT_BROWSER_DEMO_AUDIT: ResearchReportAudit = {
  complete: false,
  readyToGenerate: false,
  outputsCurrent: false,
  status: "missing",
  documentId: "",
  title: "",
  manifestPath: RESEARCH_REPORT_MANIFEST_PATH,
  docxPath: RESEARCH_REPORT_DOCX_PATH,
  pdfPath: RESEARCH_REPORT_PDF_PATH,
  xlsxPath: RESEARCH_REPORT_XLSX_PATH,
  auditPath: "deliverables/heor-report.audit.json",
  manifestSha256: "",
  reportPackageSha256: "",
  reportDocumentSha256: "",
  docxSha256: null,
  pdfSha256: null,
  xlsxSha256: null,
  blockCount: 0,
  tableCount: 0,
  workbookSheetCount: 0,
  pdfPageCount: 0,
  humanReviewStatus: "",
  fontName: "Source Han Sans CN",
  fontVersion: "2.005R",
  fontLicense: "OFL-1.1",
  fontSha256: "e2bc8a2e7f37474b774fff8db758681ece40bb6947a90d571bce9dd60671a8e4",
  errors: [`${RESEARCH_REPORT_MANIFEST_PATH} is required`],
};

export const RESEARCH_TABLES_BROWSER_DEMO_AUDIT: ResearchTablesAudit = {
  complete: false,
  readyToGenerate: false,
  outputsCurrent: false,
  status: "missing",
  workbookId: "",
  title: "",
  manifestPath: RESEARCH_TABLES_MANIFEST_PATH,
  xlsxPath: RESEARCH_TABLES_XLSX_PATH,
  csvDirectory: RESEARCH_TABLES_CSV_DIRECTORY,
  auditPath: "deliverables/research-tables.audit.json",
  manifestSha256: "",
  sourceCount: 0,
  tableCount: 0,
  rowCount: 0,
  csvFileCount: 0,
  xlsxSha256: null,
  humanReviewStatus: "awaiting_human_review",
  neutralizedTextCount: 0,
  errors: [`${RESEARCH_TABLES_MANIFEST_PATH} is required`],
  warnings: [],
};

export const JOURNAL_SUBMISSION_BROWSER_DEMO_AUDIT: JournalSubmissionAudit = {
  complete: false,
  readyToGenerate: false,
  outputsCurrent: false,
  status: "missing",
  checkId: "",
  title: "",
  journalName: "",
  articleType: "",
  guideAccessedOn: "",
  manifestPath: JOURNAL_SUBMISSION_MANIFEST_PATH,
  markdownPath: JOURNAL_SUBMISSION_MARKDOWN_PATH,
  resultsPath: JOURNAL_SUBMISSION_RESULTS_PATH,
  auditPath: "deliverables/journal-submission-check.audit.json",
  manifestSha256: "",
  fileCount: 0,
  ruleCount: 0,
  passedCount: 0,
  failedRequiredCount: 0,
  reviewIssueCount: 0,
  unresolvedCount: 0,
  humanReviewStatus: "awaiting_human_review",
  errors: [`${JOURNAL_SUBMISSION_MANIFEST_PATH} is required`],
  warnings: [],
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
  const reproducibilityAudit = HEOR_BROWSER_DEMO_REPRODUCIBILITY_AUDIT;
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
      reproducibilityAudit,
      approvalChainHead: null,
      approvalIntegrity: "verified_unanchored_sha256_chain",
      identityAssurance: "local_human_assertion",
      evidenceAudit,
      evidenceSelectionAudit: HEOR_BROWSER_DEMO_EVIDENCE_SELECTION_AUDIT,
      evidenceSynthesisMatchesApproval: false,
    },
  };
}

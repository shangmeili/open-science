import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  BookOpen,
  Check,
  Circle,
  FilePlus2,
  FileJson,
  FolderPlus,
  Loader2,
  LockKeyhole,
  MessageSquareText,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { readArtifact } from "@/lib/artifactFile";
import { cn } from "@/lib/cn";
import {
  appendHeorApproval,
  appendHeorAdvancedVoiReview,
  appendHeorNetworkMetaAnalysisReview,
  appendHeorPopulationAdjustedComparisonReview,
  appendHeorRweCausalAnalysisReview,
  appendHeorPairedBootstrapReview,
  auditHeorBudgetImpact,
  auditHeorAdvancedVoi,
  auditHeorPartitionedSurvival,
  auditHeorConceptualModel,
  auditHeorEvidence,
  auditHeorEvidenceLibrary,
  auditHeorMethodsWatchlist,
  auditHeorEvidenceSelection,
  auditHeorEvidenceSearch,
  auditHeorEvidenceSynthesis,
  auditHeorReferenceCase,
  auditHeorSurvivalExtrapolation,
  auditHeorPairedSurvivalBootstrap,
  auditHeorUncertainty,
  auditHeorModelValidation,
  auditHeorNetworkMetaAnalysis,
  auditHeorPopulationAdjustedComparison,
  auditHeorRweCausalAnalysis,
  auditHeorReporting,
  auditHeorReproducibility,
  addHeorLibraryDirectory,
  addHeorLibraryFiles,
  browserDemoRun,
  HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL,
  HEOR_BROWSER_DEMO_PLAN,
  HEOR_ADVANCED_VOI_RESULT_PATH,
  HEOR_CONCEPTUAL_MODEL_PATH,
  HEOR_BUDGET_IMPACT_PLAN_PATH,
  HEOR_PARTITIONED_SURVIVAL_PLAN_PATH,
  HEOR_MODEL_VALIDATION_PATH,
  HEOR_NETWORK_META_ANALYSIS_REQUEST_PATH,
  HEOR_POPULATION_ADJUSTED_COMPARISON_REQUEST_PATH,
  HEOR_RWE_CAUSAL_ANALYSIS_REQUEST_PATH,
  HEOR_REPORT_PACKAGE_PATH,
  HEOR_REPRODUCIBILITY_PACKAGE_PATH,
  HEOR_EVIDENCE_SEARCH_REQUEST_PATH,
  HEOR_EVIDENCE_LIBRARY_PATH,
  HEOR_METHODS_WATCHLIST_PATH,
  HEOR_EVIDENCE_SYNTHESIS_PATH,
  HEOR_PLAN_PATH,
  HEOR_REFERENCE_CASE_ASSESSMENT_PATH,
  HEOR_SURVIVAL_EXTRAPOLATION_REVIEW_PATH,
  HEOR_SURVIVAL_EXTRAPOLATION_REVIEW_INDEX_PATH,
  HEOR_PAIRED_BOOTSTRAP_REQUEST_PATH,
  HEOR_UNCERTAINTY_PLAN_PATH,
  type HeorAnalysisPlan,
  type HeorAdvancedVoiAudit,
  type HeorAdvancedVoiChecklist,
  type HeorAdvancedVoiReviewLog,
  type HeorAdvancedVoiRunResult,
  type HeorApprovalAction,
  type HeorApprovalEvent,
  type HeorApprovalLog,
  type HeorConceptualModel,
  type HeorConceptualModelAudit,
  type HeorBudgetImpactAudit,
  type HeorBudgetImpactRunResult,
  type HeorPartitionedSurvivalAudit,
  type HeorPartitionedSurvivalRunResult,
  type HeorPairedBootstrapAudit,
  type HeorPairedBootstrapChecklist,
  type HeorPairedBootstrapReviewLog,
  type HeorModelValidationAudit,
  type HeorNetworkMetaAnalysisAudit,
  type HeorNetworkMetaAnalysisChecklist,
  type HeorNetworkMetaAnalysisReviewLog,
  type HeorPopulationAdjustedComparisonAudit,
  type HeorPopulationAdjustedComparisonChecklist,
  type HeorPopulationAdjustedComparisonReviewLog,
  type HeorRweCausalAnalysisAudit,
  type HeorRweCausalAnalysisChecklist,
  type HeorRweCausalAnalysisReviewLog,
  type HeorReportingAudit,
  type HeorReproducibilityAudit,
  type HeorGate,
  type HeorReferenceCaseAudit,
  type HeorSurvivalReviewAudit,
  type HeorRunResult,
  type HeorEvidenceSearchAudit,
  type HeorEvidenceLibraryAudit,
  type HeorMethodsWatchlistAudit,
  type HeorEvidenceSelectionAudit,
  type HeorEvidenceSynthesisAudit,
  type HeorImportCandidatesResponse,
  type HeorSearchAuthorizationLog,
  type HeorSearchExecutionResponse,
  type HeorSearchAuthorizationEvent,
  type HeorUncertaintyAudit,
  type HeorUncertaintyRunResult,
  listHeorApprovals,
  listHeorAdvancedVoiReviews,
  listHeorNetworkMetaAnalysisReviews,
  listHeorPopulationAdjustedComparisonReviews,
  listHeorRweCausalAnalysisReviews,
  listHeorPairedBootstrapReviews,
  listHeorSearchAuthorizations,
  parseHeorConceptualModel,
  parseHeorPlan,
  runHeorMarkov,
  runHeorAdvancedVoi,
  runHeorBudgetImpact,
  runHeorPartitionedSurvival,
  syncHeorEvidenceLibrary,
  executeHeorEvidenceSearch,
  importHeorSearchCandidates,
  verifyHeorEvidenceExtractions,
  runHeorUncertainty,
  sha256Text,
  heorSurvivalReviewBindingsCurrent,
} from "@/lib/heor";
import { isTauri } from "@/lib/tauri";
import { toast } from "@/lib/toast";
import { MaximizePaneButton, PaneTitlebarInset } from "@/components/inspector/RightPane";

const REVIEW_GATES: HeorGate[] = [
  "decision_problem",
  "conceptual_model",
  "analysis_plan",
  "independent_validation",
  "release",
];
const ALL_GATES: HeorGate[] = REVIEW_GATES;
const EVIDENCE_REVIEW_DECISIONS = ["confirmed", "rejected"] as const;
const PAIRED_BOOTSTRAP_REVIEW_ACTIONS = ["accept", "reject"] as const;
const NMA_REVIEW_ACTIONS = ["accept", "reject"] as const;
const ADVANCED_VOI_REVIEW_ACTIONS = ["accept", "reject"] as const;
const LIBRARY_SYNC_SOURCE = {
  none: "none",
  files: "files",
  folder: "folder",
} as const;

type LibrarySyncSource = typeof LIBRARY_SYNC_SOURCE[keyof typeof LIBRARY_SYNC_SOURCE];

const EMPTY_LOG: HeorApprovalLog = {
  events: [],
  effectiveApprovedGates: [],
  chainHead: null,
  integrity: "verified_unanchored_sha256_chain",
  identityAssurance: "local_human_assertion",
};

interface ProjectIdentity {
  id: string;
  name: string;
}

type ArtifactState =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; plan: HeorAnalysisPlan; raw: string; sha256: string };

type ConceptualArtifactState =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "invalid"; message: string }
  | {
      kind: "ready";
      model: HeorConceptualModel;
      raw: string;
      sha256: string;
      audit: HeorConceptualModelAudit;
    };

type ReferenceCaseState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorReferenceCaseAudit };

type UncertaintyState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorUncertaintyAudit };

type AdvancedVoiState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorAdvancedVoiAudit };

type BudgetImpactState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorBudgetImpactAudit };

type PartitionedSurvivalState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorPartitionedSurvivalAudit };

type SurvivalReviewState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorSurvivalReviewAudit };

type PairedBootstrapState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorPairedBootstrapAudit };

type NetworkMetaAnalysisState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorNetworkMetaAnalysisAudit };

type PopulationAdjustedComparisonState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorPopulationAdjustedComparisonAudit };

type RweCausalAnalysisState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorRweCausalAnalysisAudit };

type ModelValidationState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorModelValidationAudit };

type ReportingState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorReportingAudit };

type ReproducibilityState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorReproducibilityAudit };

type EvidenceSearchState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorEvidenceSearchAudit };

type EvidenceSynthesisState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorEvidenceSynthesisAudit };

type EvidenceSelectionState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorEvidenceSelectionAudit };

type EvidenceLibraryState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorEvidenceLibraryAudit };

export type MethodsWatchlistState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorMethodsWatchlistAudit };

const EMPTY_SEARCH_LOG: HeorSearchAuthorizationLog = {
  events: [],
  chainHead: null,
  integrity: "verified_unanchored_sha256_chain",
  identityAssurance: "local_human_assertion",
};

const EMPTY_PAIRED_BOOTSTRAP_REVIEW_LOG: HeorPairedBootstrapReviewLog = {
  events: [],
  chainHead: null,
  integrity: "verified_unanchored_sha256_chain",
  identityAssurance: "app_owned_local_human_assertion",
};

const EMPTY_NMA_REVIEW_LOG: HeorNetworkMetaAnalysisReviewLog = {
  events: [],
  chainHead: null,
  integrity: "verified_unanchored_sha256_chain",
  identityAssurance: "app_owned_local_human_assertion",
};

const EMPTY_PAC_REVIEW_LOG: HeorPopulationAdjustedComparisonReviewLog = {
  events: [],
  chainHead: null,
  integrity: "verified_unanchored_sha256_chain",
  identityAssurance: "app_owned_local_human_assertion",
};

const EMPTY_RWE_CAUSAL_REVIEW_LOG: HeorRweCausalAnalysisReviewLog = {
  events: [],
  chainHead: null,
  integrity: "verified_unanchored_sha256_chain",
  identityAssurance: "app_owned_local_human_assertion",
};

const EMPTY_ADVANCED_VOI_REVIEW_LOG: HeorAdvancedVoiReviewLog = {
  events: [],
  chainHead: null,
  integrity: "verified_unanchored_sha256_chain",
  identityAssurance: "app_owned_local_human_assertion",
};

function latestSearchAuthorization(
  log: HeorSearchAuthorizationLog,
): HeorSearchAuthorizationEvent | null {
  return log.events.length > 0 ? log.events[log.events.length - 1] : null;
}

type ReviewIntent = {
  action: HeorApprovalAction;
  gate: HeorGate;
  artifactSha256: string;
  expectedActor?: string;
};

function gateArtifactHash(
  gate: HeorGate,
  planArtifact: ArtifactState,
  conceptualArtifact: ConceptualArtifactState,
  validation: ModelValidationState,
  reporting: ReportingState,
): string | null {
  if (planArtifact.kind !== "ready") return null;
  if (gate === "conceptual_model") {
    return conceptualArtifact.kind === "ready" ? conceptualArtifact.sha256 : null;
  }
  if (gate === "independent_validation") {
    return validation.kind === "ready" ? validation.audit.validationSha256 : null;
  }
  if (gate === "release") {
    return reporting.kind === "ready" ? reporting.audit.reportPackageSha256 : null;
  }
  return planArtifact.sha256;
}

function reportBindingsCurrent(
  event: HeorApprovalEvent | undefined,
  audit: HeorReportingAudit,
): boolean {
  return event?.actorLabel === audit.releaseOwnerLabel
    && Object.entries(audit.bindingPaths).length > 0
    && Object.entries(audit.bindingPaths).every(([key, path]) =>
      eventBinds(event, path, audit.bindingHashes[key] ?? ""));
}

function reproducibilityBindingCurrent(
  event: HeorApprovalEvent | undefined,
  audit: HeorReproducibilityAudit,
): boolean {
  return eventBinds(event, HEOR_REPRODUCIBILITY_PACKAGE_PATH, audit.packageSha256);
}

function eventBinds(event: HeorApprovalEvent | undefined, path: string, sha256: string): boolean {
  return event?.relatedArtifacts?.some(
    (binding) => binding.path === path && binding.sha256 === sha256,
  ) === true;
}

function validationBindingsCurrent(
  event: HeorApprovalEvent | undefined,
  audit: HeorModelValidationAudit,
): boolean {
  return Object.entries(audit.bindingPaths).length > 0
    && Object.entries(audit.bindingPaths).every(([key, path]) =>
      eventBinds(event, path, audit.bindingHashes[key] ?? ""));
}

export function HeorReviewPane({
  project,
  onClose,
  onRequestRevision,
}: {
  project: ProjectIdentity | null;
  onClose: () => void;
  onRequestRevision: (prompt: string) => void;
}) {
  const { t, i18n } = useTranslation("heor");
  const [artifact, setArtifact] = useState<ArtifactState>({ kind: "loading" });
  const [conceptualArtifact, setConceptualArtifact] = useState<ConceptualArtifactState>({
    kind: "loading",
  });
  const [referenceCase, setReferenceCase] = useState<ReferenceCaseState>({ kind: "loading" });
  const [uncertainty, setUncertainty] = useState<UncertaintyState>({ kind: "loading" });
  const [advancedVoi, setAdvancedVoi] = useState<AdvancedVoiState>({ kind: "loading" });
  const [advancedVoiReviews, setAdvancedVoiReviews] = useState<HeorAdvancedVoiReviewLog>(EMPTY_ADVANCED_VOI_REVIEW_LOG);
  const [advancedVoiDialogOpen, setAdvancedVoiDialogOpen] = useState(false);
  const [advancedVoiReviewRunning, setAdvancedVoiReviewRunning] = useState(false);
  const [budgetImpact, setBudgetImpact] = useState<BudgetImpactState>({ kind: "loading" });
  const [partitionedSurvival, setPartitionedSurvival] = useState<PartitionedSurvivalState>({ kind: "loading" });
  const [survivalReview, setSurvivalReview] = useState<SurvivalReviewState>({ kind: "loading" });
  const [pairedBootstrap, setPairedBootstrap] = useState<PairedBootstrapState>({ kind: "loading" });
  const [pairedBootstrapReviews, setPairedBootstrapReviews] = useState<HeorPairedBootstrapReviewLog>(EMPTY_PAIRED_BOOTSTRAP_REVIEW_LOG);
  const [pairedBootstrapDialogOpen, setPairedBootstrapDialogOpen] = useState(false);
  const [pairedBootstrapReviewRunning, setPairedBootstrapReviewRunning] = useState(false);
  const [networkMetaAnalysis, setNetworkMetaAnalysis] = useState<NetworkMetaAnalysisState>({ kind: "loading" });
  const [networkMetaAnalysisReviews, setNetworkMetaAnalysisReviews] = useState<HeorNetworkMetaAnalysisReviewLog>(EMPTY_NMA_REVIEW_LOG);
  const [networkMetaAnalysisDialogOpen, setNetworkMetaAnalysisDialogOpen] = useState(false);
  const [networkMetaAnalysisReviewRunning, setNetworkMetaAnalysisReviewRunning] = useState(false);
  const [populationAdjustedComparison, setPopulationAdjustedComparison] = useState<PopulationAdjustedComparisonState>({ kind: "loading" });
  const [populationAdjustedComparisonReviews, setPopulationAdjustedComparisonReviews] = useState<HeorPopulationAdjustedComparisonReviewLog>(EMPTY_PAC_REVIEW_LOG);
  const [populationAdjustedComparisonDialogOpen, setPopulationAdjustedComparisonDialogOpen] = useState(false);
  const [populationAdjustedComparisonReviewRunning, setPopulationAdjustedComparisonReviewRunning] = useState(false);
  const [rweCausalAnalysis, setRweCausalAnalysis] = useState<RweCausalAnalysisState>({ kind: "loading" });
  const [rweCausalAnalysisReviews, setRweCausalAnalysisReviews] = useState<HeorRweCausalAnalysisReviewLog>(EMPTY_RWE_CAUSAL_REVIEW_LOG);
  const [rweCausalAnalysisDialogOpen, setRweCausalAnalysisDialogOpen] = useState(false);
  const [rweCausalAnalysisReviewRunning, setRweCausalAnalysisReviewRunning] = useState(false);
  const [modelValidation, setModelValidation] = useState<ModelValidationState>({ kind: "loading" });
  const [reporting, setReporting] = useState<ReportingState>({ kind: "loading" });
  const [reproducibility, setReproducibility] = useState<ReproducibilityState>({ kind: "loading" });
  const [evidenceSearch, setEvidenceSearch] = useState<EvidenceSearchState>({ kind: "loading" });
  const [evidenceSynthesis, setEvidenceSynthesis] = useState<EvidenceSynthesisState>({ kind: "loading" });
  const [evidenceSelection, setEvidenceSelection] = useState<EvidenceSelectionState>({ kind: "loading" });
  const [evidenceLibrary, setEvidenceLibrary] = useState<EvidenceLibraryState>({ kind: "loading" });
  const [methodsWatchlist, setMethodsWatchlist] = useState<MethodsWatchlistState>({ kind: "loading" });
  const [searchAuthorizations, setSearchAuthorizations] = useState(EMPTY_SEARCH_LOG);
  const [searchResult, setSearchResult] = useState<HeorSearchExecutionResponse | null>(null);
  const [importResult, setImportResult] = useState<HeorImportCandidatesResponse | null>(null);
  const [searchRunning, setSearchRunning] = useState(false);
  const [importRunning, setImportRunning] = useState(false);
  const [librarySyncing, setLibrarySyncing] = useState(false);
  const [searchDialogOpen, setSearchDialogOpen] = useState(false);
  const [verificationDialogOpen, setVerificationDialogOpen] = useState(false);
  const [verificationRunning, setVerificationRunning] = useState(false);
  const [approvals, setApprovals] = useState<HeorApprovalLog>(EMPTY_LOG);
  const [result, setResult] = useState<HeorRunResult | null>(null);
  const [uncertaintyResult, setUncertaintyResult] = useState<HeorUncertaintyRunResult | null>(null);
  const [advancedVoiResult, setAdvancedVoiResult] = useState<HeorAdvancedVoiRunResult | null>(null);
  const [budgetImpactResult, setBudgetImpactResult] = useState<HeorBudgetImpactRunResult | null>(null);
  const [partitionedSurvivalResult, setPartitionedSurvivalResult] = useState<HeorPartitionedSurvivalRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [intent, setIntent] = useState<ReviewIntent | null>(null);

  const refresh = useCallback(async () => {
    setResult(null);
    setUncertaintyResult(null);
    setAdvancedVoiResult(null);
    setBudgetImpactResult(null);
    setPartitionedSurvivalResult(null);
    setSearchResult(null);
    setImportResult(null);
    if (!project) {
      setArtifact({ kind: "missing" });
      setConceptualArtifact({ kind: "missing" });
      setReferenceCase({ kind: "invalid", message: t("reference.noProject") });
      setUncertainty({ kind: "invalid", message: t("uncertainty.noProject") });
      setAdvancedVoi({ kind: "invalid", message: t("advancedVoi.noProject") });
      setAdvancedVoiReviews(EMPTY_ADVANCED_VOI_REVIEW_LOG);
      setBudgetImpact({ kind: "invalid", message: t("budgetImpact.noProject") });
      setPartitionedSurvival({ kind: "invalid", message: t("partitionedSurvival.noProject") });
      setSurvivalReview({ kind: "invalid", message: t("survivalReview.noProject") });
      setPairedBootstrap({ kind: "invalid", message: t("pairedBootstrap.noProject") });
      setPairedBootstrapReviews(EMPTY_PAIRED_BOOTSTRAP_REVIEW_LOG);
      setNetworkMetaAnalysis({ kind: "invalid", message: t("nma.noProject") });
      setNetworkMetaAnalysisReviews(EMPTY_NMA_REVIEW_LOG);
      setPopulationAdjustedComparison({ kind: "invalid", message: t("pac.noProject") });
      setPopulationAdjustedComparisonReviews(EMPTY_PAC_REVIEW_LOG);
      setRweCausalAnalysis({ kind: "invalid", message: t("rweCausal.noProject") });
      setRweCausalAnalysisReviews(EMPTY_RWE_CAUSAL_REVIEW_LOG);
      setModelValidation({ kind: "invalid", message: t("validation.noProject") });
      setReporting({ kind: "invalid", message: t("reporting.noProject") });
      setReproducibility({ kind: "invalid", message: t("reproducibility.noProject") });
      setEvidenceSearch({ kind: "invalid", message: t("search.noProject") });
      setEvidenceSynthesis({ kind: "invalid", message: t("synthesis.noProject") });
      setEvidenceSelection({ kind: "invalid", message: t("evidence.noProject") });
      setEvidenceLibrary({ kind: "invalid", message: t("library.noProject") });
      setMethodsWatchlist({ kind: "invalid", message: t("methodsWatchlist.noProject") });
      setSearchAuthorizations(EMPTY_SEARCH_LOG);
      setApprovals(EMPTY_LOG);
      return;
    }
    setArtifact({ kind: "loading" });
    setConceptualArtifact({ kind: "loading" });
    setReferenceCase({ kind: "loading" });
    setUncertainty({ kind: "loading" });
    setAdvancedVoi({ kind: "loading" });
    setBudgetImpact({ kind: "loading" });
    setPartitionedSurvival({ kind: "loading" });
    setSurvivalReview({ kind: "loading" });
    setPairedBootstrap({ kind: "loading" });
    setNetworkMetaAnalysis({ kind: "loading" });
    setPopulationAdjustedComparison({ kind: "loading" });
    setRweCausalAnalysis({ kind: "loading" });
    setModelValidation({ kind: "loading" });
    setReporting({ kind: "loading" });
    setReproducibility({ kind: "loading" });
    setEvidenceSearch({ kind: "loading" });
    setEvidenceSynthesis({ kind: "loading" });
    setEvidenceSelection({ kind: "loading" });
    setEvidenceLibrary({ kind: "loading" });
    setMethodsWatchlist({ kind: "loading" });
    try {
      setMethodsWatchlist({ kind: "ready", audit: await auditHeorMethodsWatchlist() });
    } catch (error) {
      setMethodsWatchlist({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
    }
    try {
      setEvidenceLibrary({ kind: "ready", audit: await auditHeorEvidenceLibrary() });
    } catch (error) {
      setEvidenceLibrary({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
    }
    try {
      setNetworkMetaAnalysis({ kind: "ready", audit: await auditHeorNetworkMetaAnalysis() });
      setNetworkMetaAnalysisReviews(await listHeorNetworkMetaAnalysisReviews(project.id));
    } catch (error) {
      setNetworkMetaAnalysis({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setNetworkMetaAnalysisReviews(EMPTY_NMA_REVIEW_LOG);
    }
    try {
      setPopulationAdjustedComparison({
        kind: "ready",
        audit: await auditHeorPopulationAdjustedComparison(),
      });
      setPopulationAdjustedComparisonReviews(
        await listHeorPopulationAdjustedComparisonReviews(project.id),
      );
    } catch (error) {
      setPopulationAdjustedComparison({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setPopulationAdjustedComparisonReviews(EMPTY_PAC_REVIEW_LOG);
    }
    try {
      setRweCausalAnalysis({ kind: "ready", audit: await auditHeorRweCausalAnalysis() });
      setRweCausalAnalysisReviews(await listHeorRweCausalAnalysisReviews(project.id));
    } catch (error) {
      setRweCausalAnalysis({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setRweCausalAnalysisReviews(EMPTY_RWE_CAUSAL_REVIEW_LOG);
    }
    try {
      setEvidenceSearch({ kind: "ready", audit: await auditHeorEvidenceSearch() });
    } catch (error) {
      setEvidenceSearch({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
    }
    try {
      setEvidenceSynthesis({ kind: "ready", audit: await auditHeorEvidenceSynthesis() });
    } catch (error) {
      setEvidenceSynthesis({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
    }
    try {
      setSearchAuthorizations(await listHeorSearchAuthorizations(project.id));
    } catch {
      setSearchAuthorizations(EMPTY_SEARCH_LOG);
    }
    try {
      const raw = isTauri
        ? (await readArtifact(HEOR_PLAN_PATH))?.data ?? null
        : JSON.stringify(HEOR_BROWSER_DEMO_PLAN, null, 2);
      if (raw === null) {
        setArtifact({ kind: "missing" });
        setReferenceCase({ kind: "invalid", message: t("reference.missingPlan") });
        setUncertainty({ kind: "invalid", message: t("uncertainty.missingPlan") });
        setAdvancedVoi({ kind: "invalid", message: t("advancedVoi.missingPlan") });
        setBudgetImpact({ kind: "invalid", message: t("budgetImpact.missingPlan") });
        setPartitionedSurvival({ kind: "invalid", message: t("partitionedSurvival.missingPlan") });
        setSurvivalReview({ kind: "invalid", message: t("survivalReview.missingPlan") });
        setPairedBootstrap({ kind: "invalid", message: t("pairedBootstrap.missingPlan") });
        setModelValidation({ kind: "invalid", message: t("validation.missingPlan") });
        setReporting({ kind: "invalid", message: t("reporting.missingPlan") });
        setReproducibility({ kind: "invalid", message: t("reproducibility.missingPlan") });
        setEvidenceSelection({ kind: "invalid", message: t("evidence.missingPlan") });
        setApprovals(await listHeorApprovals(project.id));
        return;
      }
      const plan = parseHeorPlan(raw);
      const sha256 = await sha256Text(raw);
      setArtifact({ kind: "ready", plan, raw, sha256 });
      try {
        setEvidenceSelection({ kind: "ready", audit: await auditHeorEvidenceSelection() });
      } catch (error) {
        setEvidenceSelection({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
      }
      try {
        setReferenceCase({ kind: "ready", audit: await auditHeorReferenceCase() });
      } catch (error) {
        setReferenceCase({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
      }
      try {
        setUncertainty({ kind: "ready", audit: await auditHeorUncertainty() });
      } catch (error) {
        setUncertainty({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
      }
      try {
        setAdvancedVoi({ kind: "ready", audit: await auditHeorAdvancedVoi() });
        setAdvancedVoiReviews(await listHeorAdvancedVoiReviews(project.id));
      } catch (error) {
        setAdvancedVoi({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
        setAdvancedVoiReviews(EMPTY_ADVANCED_VOI_REVIEW_LOG);
      }
      try {
        setBudgetImpact({ kind: "ready", audit: await auditHeorBudgetImpact() });
      } catch (error) {
        setBudgetImpact({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
      }
      try {
        setPartitionedSurvival({ kind: "ready", audit: await auditHeorPartitionedSurvival() });
      } catch (error) {
        setPartitionedSurvival({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
      }
      try {
        setSurvivalReview({ kind: "ready", audit: await auditHeorSurvivalExtrapolation() });
      } catch (error) {
        setSurvivalReview({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
      }
      try {
        setPairedBootstrap({ kind: "ready", audit: await auditHeorPairedSurvivalBootstrap() });
        setPairedBootstrapReviews(await listHeorPairedBootstrapReviews(project.id));
      } catch (error) {
        setPairedBootstrap({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
        setPairedBootstrapReviews(EMPTY_PAIRED_BOOTSTRAP_REVIEW_LOG);
      }
      try {
        setModelValidation({ kind: "ready", audit: await auditHeorModelValidation() });
      } catch (error) {
        setModelValidation({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
      }
      try {
        setReporting({ kind: "ready", audit: await auditHeorReporting() });
      } catch (error) {
        setReporting({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
      }
      try {
        setReproducibility({ kind: "ready", audit: await auditHeorReproducibility() });
      } catch (error) {
        setReproducibility({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
      }
      try {
        const conceptualRaw = isTauri
          ? (await readArtifact(HEOR_CONCEPTUAL_MODEL_PATH))?.data ?? null
          : JSON.stringify(HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL, null, 2);
        if (conceptualRaw === null) {
          setConceptualArtifact({ kind: "missing" });
        } else {
          const model = parseHeorConceptualModel(conceptualRaw);
          setConceptualArtifact({
            kind: "ready",
            model,
            raw: conceptualRaw,
            sha256: await sha256Text(conceptualRaw),
            audit: auditHeorConceptualModel(model, plan.analysis_id),
          });
        }
      } catch (error) {
        setConceptualArtifact({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
      }
      if (isTauri) setApprovals(await listHeorApprovals(project.id));
    } catch (error) {
      setArtifact({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setReferenceCase({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setUncertainty({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setAdvancedVoi({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setBudgetImpact({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setPartitionedSurvival({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setSurvivalReview({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setPairedBootstrap({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setModelValidation({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setReporting({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setReproducibility({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      setEvidenceSelection({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
      toast.error(t("toast.loadFailed"));
    }
  }, [project, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const currentPairedBootstrapReview = useMemo(() => {
    if (pairedBootstrap.kind !== "ready" || !pairedBootstrap.audit.resultSha256) return null;
    return [...pairedBootstrapReviews.events].reverse().find((event) =>
      event.executionId === pairedBootstrap.audit.executionId) ?? null;
  }, [pairedBootstrap, pairedBootstrapReviews.events]);
  const pairedBootstrapReviewRequired = pairedBootstrap.kind === "ready"
    && pairedBootstrap.audit.reviewable
    && uncertainty.kind === "ready"
    && uncertainty.audit.pairedBootstrapReviewRequired;
  const pairedBootstrapReviewAction = pairedBootstrap.kind === "ready"
    && currentPairedBootstrapReview
    && currentPairedBootstrapReview.resultPath === pairedBootstrap.audit.resultPath
    && currentPairedBootstrapReview.resultSha256 === pairedBootstrap.audit.resultSha256
    ? currentPairedBootstrapReview.action
    : null;
  const pairedBootstrapCurrentResultAccepted = pairedBootstrap.kind === "ready"
    && pairedBootstrap.audit.reviewable
    && pairedBootstrapReviewAction === "accept";
  const pairedBootstrapReviewAccepted = pairedBootstrapReviewRequired
    && pairedBootstrapCurrentResultAccepted;
  const currentNetworkMetaAnalysisReview = useMemo(() => {
    if (networkMetaAnalysis.kind !== "ready" || !networkMetaAnalysis.audit.resultSha256) return null;
    return [...networkMetaAnalysisReviews.events].reverse().find((event) =>
      event.executionId === networkMetaAnalysis.audit.executionId) ?? null;
  }, [networkMetaAnalysis, networkMetaAnalysisReviews.events]);
  const networkMetaAnalysisReviewAction = networkMetaAnalysis.kind === "ready"
    && currentNetworkMetaAnalysisReview
    && currentNetworkMetaAnalysisReview.resultPath === networkMetaAnalysis.audit.resultPath
    && currentNetworkMetaAnalysisReview.resultSha256 === networkMetaAnalysis.audit.resultSha256
    ? currentNetworkMetaAnalysisReview.action
    : null;
  const networkMetaAnalysisAccepted = networkMetaAnalysis.kind === "ready"
    && networkMetaAnalysis.audit.reviewable
    && networkMetaAnalysisReviewAction === "accept";
  const currentPopulationAdjustedComparisonReview = useMemo(() => {
    if (populationAdjustedComparison.kind !== "ready"
      || !populationAdjustedComparison.audit.resultSha256) return null;
    return [...populationAdjustedComparisonReviews.events].reverse().find((event) =>
      event.executionId === populationAdjustedComparison.audit.executionId) ?? null;
  }, [populationAdjustedComparison, populationAdjustedComparisonReviews.events]);
  const populationAdjustedComparisonReviewAction = populationAdjustedComparison.kind === "ready"
    && currentPopulationAdjustedComparisonReview
    && currentPopulationAdjustedComparisonReview.resultPath
      === populationAdjustedComparison.audit.resultPath
    && currentPopulationAdjustedComparisonReview.resultSha256
      === populationAdjustedComparison.audit.resultSha256
    ? currentPopulationAdjustedComparisonReview.action
    : null;
  const populationAdjustedComparisonAccepted = populationAdjustedComparison.kind === "ready"
    && populationAdjustedComparison.audit.reviewable
    && populationAdjustedComparisonReviewAction === "accept";
  const currentRweCausalAnalysisReview = useMemo(() => {
    if (rweCausalAnalysis.kind !== "ready" || !rweCausalAnalysis.audit.resultSha256) return null;
    return [...rweCausalAnalysisReviews.events].reverse().find((event) =>
      event.executionId === rweCausalAnalysis.audit.executionId) ?? null;
  }, [rweCausalAnalysis, rweCausalAnalysisReviews.events]);
  const rweCausalAnalysisReviewAction = rweCausalAnalysis.kind === "ready"
    && currentRweCausalAnalysisReview
    && currentRweCausalAnalysisReview.resultPath === rweCausalAnalysis.audit.resultPath
    && currentRweCausalAnalysisReview.resultSha256 === rweCausalAnalysis.audit.resultSha256
    ? currentRweCausalAnalysisReview.action
    : null;
  const rweCausalAnalysisAccepted = rweCausalAnalysis.kind === "ready"
    && rweCausalAnalysis.audit.reviewable
    && rweCausalAnalysisReviewAction === "accept";
  const currentAdvancedVoiReview = useMemo(() => {
    if (advancedVoi.kind !== "ready" || !advancedVoi.audit.resultSha256) return null;
    return [...advancedVoiReviews.events].reverse().find((event) =>
      event.voiId === advancedVoi.audit.voiId
      && event.resultSha256 === advancedVoi.audit.resultSha256) ?? null;
  }, [advancedVoi, advancedVoiReviews.events]);
  const advancedVoiReviewAction = advancedVoi.kind === "ready"
    && currentAdvancedVoiReview?.replaySha256 === advancedVoi.audit.replaySha256
    ? currentAdvancedVoiReview.action
    : null;
  const advancedVoiAccepted = advancedVoi.kind === "ready"
    && advancedVoi.audit.reviewable
    && advancedVoiReviewAction === "accept";

  const methodReviewItems: MethodReviewQueueItem[] = [
    ...(networkMetaAnalysis.kind === "ready" && networkMetaAnalysis.audit.resultSha256
      ? [{
          id: "nma" as const,
          path: networkMetaAnalysis.audit.resultPath,
          status: methodReviewQueueStatus(
            networkMetaAnalysis.audit.reviewable,
            networkMetaAnalysisAccepted,
            networkMetaAnalysisReviewAction,
          ),
          onReview: () => setNetworkMetaAnalysisDialogOpen(true),
          onPrepare: () => onRequestRevision(t("nma.preparePrompt")),
        }]
      : []),
    ...(populationAdjustedComparison.kind === "ready"
      && populationAdjustedComparison.audit.resultSha256
      ? [{
          id: "pac" as const,
          path: populationAdjustedComparison.audit.resultPath,
          status: methodReviewQueueStatus(
            populationAdjustedComparison.audit.reviewable,
            populationAdjustedComparisonAccepted,
            populationAdjustedComparisonReviewAction,
          ),
          onReview: () => setPopulationAdjustedComparisonDialogOpen(true),
          onPrepare: () => onRequestRevision(t("pac.preparePrompt")),
        }]
      : []),
    ...(rweCausalAnalysis.kind === "ready" && rweCausalAnalysis.audit.resultSha256
      ? [{
          id: "rweCausal" as const,
          path: rweCausalAnalysis.audit.resultPath,
          status: methodReviewQueueStatus(
            rweCausalAnalysis.audit.reviewable,
            rweCausalAnalysisAccepted,
            rweCausalAnalysisReviewAction,
          ),
          onReview: () => setRweCausalAnalysisDialogOpen(true),
          onPrepare: () => onRequestRevision(t("rweCausal.preparePrompt")),
        }]
      : []),
    ...(pairedBootstrap.kind === "ready" && pairedBootstrap.audit.resultSha256
      ? [{
          id: "pairedBootstrap" as const,
          path: pairedBootstrap.audit.resultPath,
          status: methodReviewQueueStatus(
            pairedBootstrap.audit.reviewable,
            pairedBootstrapCurrentResultAccepted,
            pairedBootstrapReviewAction,
          ),
          onReview: () => setPairedBootstrapDialogOpen(true),
          onPrepare: () => onRequestRevision(t("pairedBootstrap.preparePrompt")),
        }]
      : []),
    ...(advancedVoi.kind === "ready" && advancedVoi.audit.resultSha256
      ? [{
          id: "advancedVoi" as const,
          path: HEOR_ADVANCED_VOI_RESULT_PATH,
          status: methodReviewQueueStatus(
            advancedVoi.audit.reviewable,
            advancedVoiAccepted,
            advancedVoiReviewAction,
          ),
          onReview: () => setAdvancedVoiDialogOpen(true),
          onPrepare: () => onRequestRevision(t("advancedVoi.preparePrompt")),
        }]
      : []),
  ];

  const currentApprovals = useMemo(() => {
    if (artifact.kind !== "ready") return [] as HeorGate[];
    const latest = latestByGate(approvals.events);
    const effective: HeorGate[] = [];
    let previousSequence = 0;
    for (const gate of REVIEW_GATES) {
      const artifactSha256 = gateArtifactHash(
        gate,
        artifact,
        conceptualArtifact,
        modelValidation,
        reporting,
      );
      if (!artifactSha256) break;
      if (gate === "conceptual_model"
        && conceptualArtifact.kind === "ready"
        && !conceptualArtifact.audit.complete) break;
      if (gate === "analysis_plan"
        && (!auditHeorEvidence(artifact.plan).complete
          || evidenceSelection.kind !== "ready"
          || !evidenceSelection.audit.complete
          || referenceCase.kind !== "ready"
          || !referenceCase.audit.complete
          || uncertainty.kind !== "ready"
          || !uncertainty.audit.complete
          || budgetImpact.kind !== "ready"
          || !budgetImpact.audit.complete
          || partitionedSurvival.kind !== "ready"
          || !partitionedSurvival.audit.complete
          || survivalReview.kind !== "ready"
          || !survivalReview.audit.complete
          || (pairedBootstrapReviewRequired && !pairedBootstrapReviewAccepted))) break;
      if (gate === "independent_validation"
        && (modelValidation.kind !== "ready"
          || !modelValidation.audit.complete
          || !modelValidation.audit.approvable)) break;
      if (gate === "release"
        && (reporting.kind !== "ready" || !reporting.audit.releasable
          || reproducibility.kind !== "ready"
          || !reproducibility.audit.releaseCompanionReady
          || (partitionedSurvival.kind === "ready" && partitionedSurvival.audit.required))) break;
      const event = latest.get(gate);
      if (
        !event ||
        event.action !== "approve" ||
        event.artifactSha256 !== artifactSha256 ||
        (gate === "analysis_plan"
          && evidenceSelection.kind === "ready"
          && evidenceSelection.audit.synthesisSha256.length > 0
          && !event.relatedArtifacts?.some((binding) =>
            binding.path === HEOR_EVIDENCE_SYNTHESIS_PATH
            && binding.sha256 === evidenceSelection.audit.synthesisSha256)) ||
        (gate === "analysis_plan"
          && uncertainty.kind === "ready"
          && !event.relatedArtifacts?.some((binding) =>
            binding.path === HEOR_UNCERTAINTY_PLAN_PATH
            && binding.sha256 === uncertainty.audit.uncertaintySha256)) ||
        (gate === "analysis_plan"
          && budgetImpact.kind === "ready"
          && !event.relatedArtifacts?.some((binding) =>
            binding.path === HEOR_BUDGET_IMPACT_PLAN_PATH
            && binding.sha256 === budgetImpact.audit.budgetImpactSha256)) ||
        (gate === "analysis_plan"
          && partitionedSurvival.kind === "ready"
          && partitionedSurvival.audit.required
          && !partitionedSurvival.audit.artifactBindings.every((expected) =>
            event.relatedArtifacts?.some((binding) =>
              binding.path === expected.path && binding.sha256 === expected.sha256))) ||
        (gate === "analysis_plan"
          && survivalReview.kind === "ready"
          && survivalReview.audit.required
          && !heorSurvivalReviewBindingsCurrent(event, survivalReview.audit)) ||
        (gate === "analysis_plan"
          && pairedBootstrapReviewAccepted
          && currentPairedBootstrapReview
          && !event.relatedArtifacts?.some((binding) =>
            binding.path === currentPairedBootstrapReview.recordPath
            && binding.sha256 === currentPairedBootstrapReview.recordSha256)) ||
        (gate === "independent_validation"
          && modelValidation.kind === "ready"
          && !validationBindingsCurrent(event, modelValidation.audit)) ||
        (gate === "release"
          && reporting.kind === "ready"
          && !reportBindingsCurrent(event, reporting.audit)) ||
        (gate === "release"
          && reproducibility.kind === "ready"
          && !reproducibilityBindingCurrent(event, reproducibility.audit)) ||
        event.sequence <= previousSequence
      ) {
        break;
      }
      effective.push(gate);
      previousSequence = event.sequence;
    }
    return effective;
  }, [
    approvals.events,
    artifact,
    conceptualArtifact,
    evidenceSelection,
    referenceCase,
    uncertainty,
    budgetImpact,
    partitionedSurvival,
    survivalReview,
    pairedBootstrapReviewRequired,
    pairedBootstrapReviewAccepted,
    currentPairedBootstrapReview,
    modelValidation,
    reporting,
    reproducibility,
  ]);

  const evidenceAudit = useMemo(
    () => artifact.kind === "ready" ? auditHeorEvidence(artifact.plan) : null,
    [artifact],
  );

  const latest = useMemo(() => latestByGate(approvals.events), [approvals.events]);
  const nextGate = REVIEW_GATES.find((gate) => !currentApprovals.includes(gate)) ?? null;

  const applyBrowserEvent = async (
    action: HeorApprovalAction,
    gate: HeorGate,
    artifactSha256: string,
    actorLabel: string,
    rationale: string,
  ) => {
    const sequence = approvals.events.length + 1;
    const relatedArtifacts = gate === "analysis_plan"
      && uncertainty.kind === "ready" && budgetImpact.kind === "ready"
      && partitionedSurvival.kind === "ready"
      && evidenceSelection.kind === "ready" && survivalReview.kind === "ready"
      ? [
          ...(evidenceSelection.audit.synthesisSha256
            ? [{ path: HEOR_EVIDENCE_SYNTHESIS_PATH, sha256: evidenceSelection.audit.synthesisSha256 }]
            : []),
          { path: HEOR_UNCERTAINTY_PLAN_PATH, sha256: uncertainty.audit.uncertaintySha256 },
          { path: HEOR_BUDGET_IMPACT_PLAN_PATH, sha256: budgetImpact.audit.budgetImpactSha256 },
          ...(partitionedSurvival.audit.required
            ? partitionedSurvival.audit.artifactBindings
            : []),
          ...(survivalReview.audit.required ? survivalReview.audit.artifactBindings : []),
          ...(pairedBootstrapReviewAccepted && currentPairedBootstrapReview
            ? [{
                path: currentPairedBootstrapReview.recordPath,
                sha256: currentPairedBootstrapReview.recordSha256,
              }]
            : []),
        ]
      : gate === "independent_validation" && modelValidation.kind === "ready"
        ? Object.entries(modelValidation.audit.bindingPaths).map(([key, path]) => ({
            path,
            sha256: modelValidation.audit.bindingHashes[key],
          }))
        : gate === "release" && reporting.kind === "ready"
          && reproducibility.kind === "ready"
          ? [
              ...Object.entries(reporting.audit.bindingPaths).map(([key, path]) => ({
                path,
                sha256: reporting.audit.bindingHashes[key],
              })),
              {
                path: HEOR_REPRODUCIBILITY_PACKAGE_PATH,
                sha256: reproducibility.audit.packageSha256,
              },
            ]
        : undefined;
    const eventHash = await sha256Text(
      JSON.stringify({
        sequence,
        action,
        gate,
        artifactSha256,
        relatedArtifacts,
        actorLabel,
        rationale,
      }),
    );
    const event: HeorApprovalEvent = {
      schemaVersion: 2,
      sequence,
      eventId: sequence.toString(16).padStart(32, "0"),
      projectId: project!.id,
      gate,
      action,
      artifactSha256,
      actorLabel,
      rationale,
      timestamp: Math.floor(Date.now() / 1000),
      assurance: "local_human_assertion",
      previousHash: approvals.chainHead,
      eventHash,
      relatedArtifacts,
    };
    const events = [...approvals.events, event];
    setApprovals(summarizeBrowserLog(events));
  };

  const submitReview = async (actorLabel: string, rationale: string) => {
    if (!intent || !project) return;
    try {
      if (isTauri) {
        await appendHeorApproval({
          projectId: project.id,
          gate: intent.gate,
          action: intent.action,
          artifactSha256: intent.artifactSha256,
          actorLabel,
          rationale,
        });
        setApprovals(await listHeorApprovals(project.id));
      } else {
        await applyBrowserEvent(
          intent.action,
          intent.gate,
          intent.artifactSha256,
          actorLabel,
          rationale,
        );
      }
      toast.success(
        intent.action === "approve" ? t("toast.approvalRecorded") : t("toast.approvalRevoked"),
      );
      setIntent(null);
      setResult(null);
      setUncertaintyResult(null);
      setBudgetImpactResult(null);
      setPartitionedSurvivalResult(null);
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const runAnalysis = async () => {
    if (!project || artifact.kind !== "ready" || running) return;
    setRunning(true);
    try {
      const next = isTauri
        ? await runHeorMarkov(project.id)
        : browserDemoRun(artifact.sha256, currentApprovals);
      setResult(next);
      setReporting({ kind: "ready", audit: next.workflow.reportingAudit });
      setReproducibility({ kind: "ready", audit: next.workflow.reproducibilityAudit });
      toast.success(t("toast.runComplete"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setRunning(false);
    }
  };

  const runUncertainty = async () => {
    if (!project || !isTauri || uncertainty.kind !== "ready"
      || !uncertainty.audit.complete || running) return;
    setRunning(true);
    try {
      const next = await runHeorUncertainty(project.id);
      setUncertaintyResult(next);
      setReporting({ kind: "ready", audit: next.workflow.reportingAudit });
      setReproducibility({ kind: "ready", audit: next.workflow.reproducibilityAudit });
      toast.success(t("toast.uncertaintyRunComplete"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setRunning(false);
    }
  };

  const runAdvancedVoi = async () => {
    if (!project || !isTauri || advancedVoi.kind !== "ready"
      || !advancedVoi.audit.complete || running) return;
    setRunning(true);
    try {
      const next = await runHeorAdvancedVoi(project.id);
      setAdvancedVoiResult(next);
      setAdvancedVoi({ kind: "ready", audit: await auditHeorAdvancedVoi() });
      toast.success(t("toast.advancedVoiRunComplete"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setRunning(false);
    }
  };

  const submitAdvancedVoiReview = async (
    action: "accept" | "reject",
    checklist: HeorAdvancedVoiChecklist,
    actor: string,
    rationale: string,
  ) => {
    if (!project || advancedVoi.kind !== "ready" || advancedVoiReviewRunning) return;
    const resultSha256 = advancedVoiResult?.resultSha256 ?? advancedVoi.audit.resultSha256;
    const replaySha256 = advancedVoiResult?.replaySha256 ?? advancedVoi.audit.replaySha256;
    if (!resultSha256 || !replaySha256) return;
    setAdvancedVoiReviewRunning(true);
    try {
      await appendHeorAdvancedVoiReview({
        projectId: project.id,
        action,
        resultSha256,
        replaySha256,
        checklist,
        actorLabel: actor,
        rationale,
      });
      setAdvancedVoiReviews(await listHeorAdvancedVoiReviews(project.id));
      setAdvancedVoiDialogOpen(false);
      toast.success(t("toast.advancedVoiReviewRecorded"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setAdvancedVoiReviewRunning(false);
    }
  };

  const runBudgetImpact = async () => {
    if (!project || !isTauri || budgetImpact.kind !== "ready"
      || !budgetImpact.audit.complete || running) return;
    setRunning(true);
    try {
      const next = await runHeorBudgetImpact(project.id);
      setBudgetImpactResult(next);
      setReporting({ kind: "ready", audit: next.workflow.reportingAudit });
      setReproducibility({ kind: "ready", audit: next.workflow.reproducibilityAudit });
      toast.success(t("toast.budgetImpactRunComplete"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setRunning(false);
    }
  };

  const runPartitionedSurvival = async () => {
    if (!project || !isTauri || partitionedSurvival.kind !== "ready"
      || !partitionedSurvival.audit.required || !partitionedSurvival.audit.complete || running) return;
    setRunning(true);
    try {
      const next = await runHeorPartitionedSurvival(project.id);
      setPartitionedSurvivalResult(next);
      setReporting({ kind: "ready", audit: next.workflow.reportingAudit });
      setReproducibility({ kind: "ready", audit: next.workflow.reproducibilityAudit });
      toast.success(t("toast.partitionedSurvivalRunComplete"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setRunning(false);
    }
  };

  const runEvidenceSearch = async (actorLabel: string, rationale: string) => {
    if (!project || evidenceSearch.kind !== "ready" || !evidenceSearch.audit.complete
      || searchRunning || !isTauri) return;
    setSearchRunning(true);
    try {
      const next = await executeHeorEvidenceSearch({
        projectId: project.id,
        requestSha256: evidenceSearch.audit.requestSha256,
        actorLabel,
        rationale,
        confirmedNoSensitiveData: true,
      });
      setSearchResult(next);
      setSearchAuthorizations((current) => ({
        ...current,
        events: current.events.some((event) => event.eventId === next.authorization.eventId)
          ? current.events
          : [...current.events, next.authorization],
        chainHead: next.authorization.eventHash,
      }));
      setSearchDialogOpen(false);
      setEvidenceSearch({ kind: "ready", audit: await auditHeorEvidenceSearch() });
      toast.success(t("toast.searchComplete"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSearchRunning(false);
    }
  };

  const importSearchCandidates = async () => {
    if (!project || evidenceSynthesis.kind !== "ready" || !evidenceSynthesis.audit.importable
      || importRunning || !isTauri) return;
    const authorization = searchResult?.authorization ?? latestSearchAuthorization(searchAuthorizations);
    if (!authorization) return;
    setImportRunning(true);
    try {
      const next = await importHeorSearchCandidates({
        projectId: project.id,
        outputPath: authorization.outputPath,
        outputSha256: authorization.outputSha256,
        synthesisSha256: evidenceSynthesis.audit.synthesisSha256,
      });
      setImportResult(next);
      setEvidenceSynthesis({ kind: "ready", audit: next.audit });
      toast.success(t("toast.candidatesImported"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setImportRunning(false);
    }
  };

  const verifyEvidenceExtractions = async (
    actorLabel: string,
    rationale: string,
    decision: "confirmed" | "rejected",
    extractionIds: string[],
  ) => {
    if (!project || evidenceSynthesis.kind !== "ready" || !evidenceSynthesis.audit.complete
      || extractionIds.length === 0
      || verificationRunning || !isTauri) return;
    setVerificationRunning(true);
    try {
      const audit = await verifyHeorEvidenceExtractions({
        projectId: project.id,
        synthesisSha256: evidenceSynthesis.audit.synthesisSha256,
        extractionIds,
        actorLabel,
        rationale,
        decision,
      });
      setEvidenceSynthesis({ kind: "ready", audit });
      setEvidenceSelection({ kind: "ready", audit: await auditHeorEvidenceSelection() });
      setVerificationDialogOpen(false);
      toast.success(t("toast.evidenceVerified"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setVerificationRunning(false);
    }
  };

  const syncLibrary = async (source: LibrarySyncSource) => {
    if (!project || librarySyncing || !isTauri) return;
    setLibrarySyncing(true);
    try {
      if (source === LIBRARY_SYNC_SOURCE.files) await addHeorLibraryFiles();
      const directoryImport = source === LIBRARY_SYNC_SOURCE.folder
        ? await addHeorLibraryDirectory()
        : null;
      if (directoryImport && directoryImport.added.length === 0
        && directoryImport.skipped.length === 0) return;
      const audit = await syncHeorEvidenceLibrary(project.id);
      setEvidenceLibrary({ kind: "ready", audit });
      toast.success(directoryImport
        ? t("toast.libraryFolderSynced", {
          added: directoryImport.added.length,
          skipped: directoryImport.skipped.length,
        })
        : t("toast.librarySynced"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setLibrarySyncing(false);
    }
  };

  const submitPairedBootstrapReview = async (
    action: "accept" | "reject",
    checklist: HeorPairedBootstrapChecklist,
    actorLabel: string,
    rationale: string,
  ) => {
    if (!project || pairedBootstrap.kind !== "ready" || !pairedBootstrap.audit.resultSha256
      || pairedBootstrapReviewRunning || !isTauri) return;
    setPairedBootstrapReviewRunning(true);
    try {
      await appendHeorPairedBootstrapReview({
        projectId: project.id,
        resultPath: pairedBootstrap.audit.resultPath,
        resultSha256: pairedBootstrap.audit.resultSha256,
        action,
        checklist,
        actorLabel,
        rationale,
      });
      setPairedBootstrapReviews(await listHeorPairedBootstrapReviews(project.id));
      setPairedBootstrapDialogOpen(false);
      toast.success(action === "accept"
        ? t("pairedBootstrap.acceptedToast")
        : t("pairedBootstrap.rejectedToast"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setPairedBootstrapReviewRunning(false);
    }
  };

  const submitNetworkMetaAnalysisReview = async (
    action: "accept" | "reject",
    checklist: HeorNetworkMetaAnalysisChecklist,
    actorLabel: string,
    rationale: string,
  ) => {
    if (!project || networkMetaAnalysis.kind !== "ready" || !networkMetaAnalysis.audit.resultSha256
      || networkMetaAnalysisReviewRunning || !isTauri) return;
    setNetworkMetaAnalysisReviewRunning(true);
    try {
      await appendHeorNetworkMetaAnalysisReview({
        projectId: project.id,
        resultPath: networkMetaAnalysis.audit.resultPath,
        resultSha256: networkMetaAnalysis.audit.resultSha256,
        action,
        checklist,
        actorLabel,
        rationale,
      });
      setNetworkMetaAnalysisReviews(await listHeorNetworkMetaAnalysisReviews(project.id));
      setNetworkMetaAnalysisDialogOpen(false);
      toast.success(action === "accept" ? t("nma.acceptedToast") : t("nma.rejectedToast"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setNetworkMetaAnalysisReviewRunning(false);
    }
  };

  const submitPopulationAdjustedComparisonReview = async (
    action: "accept" | "reject",
    checklist: HeorPopulationAdjustedComparisonChecklist,
    actorLabel: string,
    rationale: string,
  ) => {
    if (!project || populationAdjustedComparison.kind !== "ready"
      || !populationAdjustedComparison.audit.resultSha256
      || populationAdjustedComparisonReviewRunning || !isTauri) return;
    setPopulationAdjustedComparisonReviewRunning(true);
    try {
      await appendHeorPopulationAdjustedComparisonReview({
        projectId: project.id,
        resultPath: populationAdjustedComparison.audit.resultPath,
        resultSha256: populationAdjustedComparison.audit.resultSha256,
        action,
        checklist,
        actorLabel,
        rationale,
      });
      setPopulationAdjustedComparisonReviews(
        await listHeorPopulationAdjustedComparisonReviews(project.id),
      );
      setPopulationAdjustedComparisonDialogOpen(false);
      toast.success(action === "accept" ? t("pac.acceptedToast") : t("pac.rejectedToast"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setPopulationAdjustedComparisonReviewRunning(false);
    }
  };

  const submitRweCausalAnalysisReview = async (
    action: "accept" | "reject",
    checklist: HeorRweCausalAnalysisChecklist,
    actorLabel: string,
    rationale: string,
  ) => {
    if (!project || rweCausalAnalysis.kind !== "ready" || !rweCausalAnalysis.audit.resultSha256
      || rweCausalAnalysisReviewRunning || !isTauri) return;
    setRweCausalAnalysisReviewRunning(true);
    try {
      await appendHeorRweCausalAnalysisReview({
        projectId: project.id,
        resultPath: rweCausalAnalysis.audit.resultPath,
        resultSha256: rweCausalAnalysis.audit.resultSha256,
        action,
        checklist,
        actorLabel,
        rationale,
      });
      setRweCausalAnalysisReviews(await listHeorRweCausalAnalysisReviews(project.id));
      setRweCausalAnalysisDialogOpen(false);
      toast.success(action === "accept" ? t("rweCausal.acceptedToast") : t("rweCausal.rejectedToast"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setRweCausalAnalysisReviewRunning(false);
    }
  };

  return (
    <div className="flex h-full flex-col border-l border-border bg-surface">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-4">
        <PaneTitlebarInset />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-text">{t("panel.title")}</div>
          <div className="truncate text-[10px] uppercase tracking-[0.12em] text-muted">
            {t("panel.subtitle")}
          </div>
        </div>
        <MaximizePaneButton />
        <button onClick={onClose} aria-label={t("closeReview")} className="text-text hover:opacity-60">
          <X size={15} strokeWidth={1.5} />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <StageRail
          currentApprovals={currentApprovals}
          hasResult={!!result || !!uncertaintyResult || !!advancedVoiResult
            || !!budgetImpactResult || !!partitionedSurvivalResult}
        />

        {project && <MethodReviewQueue items={methodReviewItems} />}

        {project && (
          <EvidenceLibraryAssessment
            state={evidenceLibrary}
            syncing={librarySyncing}
            onAddFiles={() => void syncLibrary(LIBRARY_SYNC_SOURCE.files)}
            onAddFolder={() => void syncLibrary(LIBRARY_SYNC_SOURCE.folder)}
            onSync={() => void syncLibrary(LIBRARY_SYNC_SOURCE.none)}
            onAsk={() => onRequestRevision(t("library.searchPrompt"))}
          />
        )}

        {project && (
          <MethodsWatchlistAssessment
            state={methodsWatchlist}
            onPrepare={() => onRequestRevision(t("methodsWatchlist.preparePrompt"))}
          />
        )}

        {project && (
          <EvidenceSearchAssessment
            state={evidenceSearch}
            result={searchResult}
            running={searchRunning}
            onRequestDraft={() => onRequestRevision(t("search.repairPrompt"))}
            onAuthorize={() => setSearchDialogOpen(true)}
          />
        )}

        {project && (
          <EvidenceSynthesisAssessment
            state={evidenceSynthesis}
            authorization={searchResult?.authorization ?? latestSearchAuthorization(searchAuthorizations)}
            importResult={importResult}
            importing={importRunning}
            verifying={verificationRunning}
            onPrepare={() => onRequestRevision(t("synthesis.preparePrompt"))}
            onImport={() => void importSearchCandidates()}
            onContinue={() => onRequestRevision(t("synthesis.continuePrompt"))}
            onVerify={() => setVerificationDialogOpen(true)}
          />
        )}

        {project && (
          <NetworkMetaAnalysisAssessment
            state={networkMetaAnalysis}
            currentReview={currentNetworkMetaAnalysisReview}
            accepted={networkMetaAnalysisAccepted}
            onRequestPreparation={() => onRequestRevision(t("nma.preparePrompt"))}
            onReview={() => setNetworkMetaAnalysisDialogOpen(true)}
          />
        )}

        {project && (
          <PopulationAdjustedComparisonAssessment
            state={populationAdjustedComparison}
            currentReview={currentPopulationAdjustedComparisonReview}
            accepted={populationAdjustedComparisonAccepted}
            onRequestPreparation={() => onRequestRevision(t("pac.preparePrompt"))}
            onReview={() => setPopulationAdjustedComparisonDialogOpen(true)}
          />
        )}

        {project && (
          <RweCausalAnalysisAssessment
            state={rweCausalAnalysis}
            currentReview={currentRweCausalAnalysisReview}
            accepted={rweCausalAnalysisAccepted}
            onRequestPreparation={() => onRequestRevision(t("rweCausal.preparePrompt"))}
            onReview={() => setRweCausalAnalysisDialogOpen(true)}
          />
        )}

        {!project ? (
          <EmptyState title={t("panel.noProjectTitle")} body={t("panel.noProjectBody")} />
        ) : artifact.kind === "loading" ? (
          <div className="flex items-center gap-2 px-5 py-8 text-sm text-muted">
            <Loader2 size={15} className="animate-spin" /> {t("panel.loading")}
          </div>
        ) : artifact.kind === "missing" ? (
          <EmptyState title={t("panel.emptyTitle")} body={t("panel.emptyBody")} />
        ) : artifact.kind === "invalid" ? (
          <div className="m-4 rounded-card border border-error/30 bg-error/5 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-error">
              <AlertTriangle size={16} /> {t("panel.invalidTitle")}
            </div>
            <p className="mt-2 break-words font-mono text-xs leading-5 text-muted">{artifact.message}</p>
          </div>
        ) : (
          <>
            <div className="border-b border-border px-5 py-4">
              <div className="flex items-center gap-2">
                <FileJson size={16} className="text-accent" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-text">
                    {artifact.plan.decision_problem.title}
                  </div>
                  <div className="mt-0.5 truncate font-mono text-[10px] text-muted">{HEOR_PLAN_PATH}</div>
                </div>
                <button
                  onClick={() => void refresh()}
                  title={t("panel.refresh")}
                  aria-label={t("panel.refresh")}
                  className="rounded p-1 text-muted hover:bg-surface-2 hover:text-text"
                >
                  <RefreshCw size={14} />
                </button>
              </div>
              <button
                onClick={() => onRequestRevision(t("panel.revisionPrompt"))}
                className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
              >
                <MessageSquareText size={13} /> {t("panel.askRevision")}
              </button>
            </div>

            <DecisionSnapshot plan={artifact.plan} />

            <ConceptualModelTraceability
              artifact={conceptualArtifact}
              onRequestModel={() => onRequestRevision(t("conceptual.repairPrompt"))}
            />

            <CohortTransitionSummary
              plan={artifact.plan}
              onRequestAudit={() => onRequestRevision(t("transition.repairPrompt"))}
              onRequestRateDerivation={() => onRequestRevision(t("transition.ratePrompt"))}
              onRequestSurvivalDerivation={() => onRequestRevision(t("transition.survivalPrompt"))}
              onRequestSurvivalExtrapolationReview={() => onRequestRevision(t("transition.survivalExtrapolationPrompt"))}
              onRequestProbabilityTime={() => onRequestRevision(t("transition.probabilityTimePrompt"))}
              onRequestBackgroundMortality={() => onRequestRevision(t("transition.backgroundMortalityPrompt"))}
              onRequestRelativeEffect={() => onRequestRevision(t("transition.relativeEffectPrompt"))}
              onRequestHazardRatio={() => onRequestRevision(t("transition.hazardRatioPrompt"))}
            />

            <SurvivalReviewAssessment
              state={survivalReview}
              onRequestRepair={() => onRequestRevision(t("survivalReview.repairPrompt"))}
            />

            <PairedBootstrapAssessment
              state={pairedBootstrap}
              currentReview={currentPairedBootstrapReview}
              accepted={pairedBootstrapCurrentResultAccepted}
              onRequestPreparation={() => onRequestRevision(t("pairedBootstrap.preparePrompt"))}
              onReview={() => setPairedBootstrapDialogOpen(true)}
            />

            <EvidenceTraceability
              audit={evidenceAudit!}
              selection={evidenceSelection}
              onRequestRepair={() => onRequestRevision(t("evidence.repairPrompt"))}
            />

            <ReferenceCaseAssessment
              state={referenceCase}
              onRequestRepair={() => onRequestRevision(t("reference.repairPrompt"))}
            />

            <UncertaintyAssessment
              state={uncertainty}
              onRequestRepair={() => onRequestRevision(t("uncertainty.repairPrompt"))}
            />
            <AdvancedVoiAssessment
              state={advancedVoi}
              accepted={advancedVoiAccepted}
              reviewAction={advancedVoiReviewAction}
              onRequestPreparation={() => onRequestRevision(t("advancedVoi.preparePrompt"))}
              onReview={() => setAdvancedVoiDialogOpen(true)}
            />
            <BudgetImpactAssessment
              state={budgetImpact}
              onRequestRepair={() => onRequestRevision(t("budgetImpact.repairPrompt"))}
            />
            <PartitionedSurvivalAssessment
              state={partitionedSurvival}
              onRequestRepair={() => onRequestRevision(t("partitionedSurvival.repairPrompt"))}
            />
            <ModelValidationAssessment
              state={modelValidation}
              onRequestPreparation={() => onRequestRevision(t("validation.repairPrompt"))}
            />
            <ReportingAssessment
              state={reporting}
              onRequestPreparation={() => onRequestRevision(t("reporting.repairPrompt"))}
            />
            <ReproducibilityAssessment
              state={reproducibility}
              onRequestPreparation={() => onRequestRevision(t("reproducibility.repairPrompt"))}
            />

            <section className="border-b border-border px-5 py-4">
              <div className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-muted">
                {t("reviewSection")}
              </div>
              <div className="space-y-2">
                {REVIEW_GATES.map((gate, index) => {
                  const approved = currentApprovals.includes(gate);
                  const artifactSha256 = gateArtifactHash(
                    gate,
                    artifact,
                    conceptualArtifact,
                    modelValidation,
                    reporting,
                  );
                  const gateEvent = latest.get(gate);
                  const relatedStale = (gate === "analysis_plan" && (
                    (evidenceSelection.kind === "ready"
                      && evidenceSelection.audit.synthesisSha256.length > 0
                      && !eventBinds(
                        gateEvent,
                        HEOR_EVIDENCE_SYNTHESIS_PATH,
                        evidenceSelection.audit.synthesisSha256,
                      ))
                    || (uncertainty.kind === "ready"
                      && !eventBinds(
                        gateEvent,
                        HEOR_UNCERTAINTY_PLAN_PATH,
                        uncertainty.audit.uncertaintySha256,
                      ))
                    || (budgetImpact.kind === "ready"
                      && !eventBinds(
                        gateEvent,
                        HEOR_BUDGET_IMPACT_PLAN_PATH,
                        budgetImpact.audit.budgetImpactSha256,
                      ))
                    || (survivalReview.kind === "ready"
                      && survivalReview.audit.required
                      && !heorSurvivalReviewBindingsCurrent(gateEvent, survivalReview.audit))
                    || (partitionedSurvival.kind === "ready"
                      && partitionedSurvival.audit.required
                      && !partitionedSurvival.audit.artifactBindings.every((expected) =>
                        eventBinds(gateEvent, expected.path, expected.sha256)))
                    || (pairedBootstrapReviewAccepted
                      && currentPairedBootstrapReview
                      && !eventBinds(
                        gateEvent,
                        currentPairedBootstrapReview.recordPath,
                        currentPairedBootstrapReview.recordSha256,
                      ))
                  )) || (gate === "independent_validation"
                    && modelValidation.kind === "ready"
                    && !validationBindingsCurrent(gateEvent, modelValidation.audit))
                    || (gate === "release"
                      && reporting.kind === "ready"
                      && !reportBindingsCurrent(gateEvent, reporting.audit))
                    || (gate === "release"
                      && reproducibility.kind === "ready"
                      && !reproducibilityBindingCurrent(gateEvent, reproducibility.audit));
                  const stale = approvals.effectiveApprovedGates.includes(gate)
                    && gateEvent?.action === "approve"
                    && (gateEvent.artifactSha256 !== artifactSha256 || relatedStale);
                  const conceptualBlocked = gate === "conceptual_model"
                    && gate === nextGate
                    && (conceptualArtifact.kind !== "ready" || !conceptualArtifact.audit.complete);
                  const evidenceBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && (!evidenceAudit?.complete
                      || evidenceSelection.kind !== "ready"
                      || !evidenceSelection.audit.complete);
                  const referenceBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && (referenceCase.kind !== "ready" || !referenceCase.audit.complete);
                  const uncertaintyBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && (uncertainty.kind !== "ready" || !uncertainty.audit.complete);
                  const budgetImpactBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && (budgetImpact.kind !== "ready" || !budgetImpact.audit.complete);
                  const partitionedSurvivalBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && (partitionedSurvival.kind !== "ready" || !partitionedSurvival.audit.complete);
                  const survivalReviewBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && (survivalReview.kind !== "ready" || !survivalReview.audit.complete);
                  const pairedBootstrapBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && pairedBootstrapReviewRequired
                    && !pairedBootstrapReviewAccepted;
                  const validationBlocked = gate === "independent_validation"
                    && gate === nextGate
                    && (modelValidation.kind !== "ready"
                      || !modelValidation.audit.complete
                      || !modelValidation.audit.approvable);
                  const reportingBlocked = gate === "release"
                    && gate === nextGate
                    && (reporting.kind !== "ready" || !reporting.audit.releasable);
                  const reproducibilityBlocked = gate === "release"
                    && gate === nextGate
                    && (reproducibility.kind !== "ready"
                      || !reproducibility.audit.releaseCompanionReady);
                  const waiting = gate === nextGate && !stale && !conceptualBlocked
                    && !evidenceBlocked && !referenceBlocked && !uncertaintyBlocked
                    && !budgetImpactBlocked && !survivalReviewBlocked
                    && !pairedBootstrapBlocked
                    && !partitionedSurvivalBlocked
                    && !validationBlocked && !reportingBlocked && !reproducibilityBlocked;
                  return (
                    <div key={gate} className="rounded-input border border-border bg-bg/50 px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        {approved ? (
                          <Check size={14} className="text-ok" />
                        ) : waiting || stale || conceptualBlocked || evidenceBlocked || referenceBlocked
                          || uncertaintyBlocked || budgetImpactBlocked || validationBlocked
                          || survivalReviewBlocked || pairedBootstrapBlocked
                          || partitionedSurvivalBlocked || reportingBlocked
                          || reproducibilityBlocked ? (
                          <Circle size={12} className={stale ? "text-error" : "text-accent"} />
                        ) : (
                          <LockKeyhole size={13} className="text-muted" />
                        )}
                        <div className="flex-1 text-xs font-medium text-text">{t(`gate.${gate}`)}</div>
                        <span className={cn("text-[10px]", approved ? "text-ok" : stale ? "text-error" : "text-muted")}>
                          {approved
                            ? t("status.approved")
                            : stale
                              ? t("status.stale")
                              : conceptualBlocked
                                ? t("status.conceptualRequired")
                              : evidenceBlocked
                                ? t("status.evidenceRequired")
                              : referenceBlocked
                                ? t("status.referenceRequired")
                              : uncertaintyBlocked
                                ? t("status.uncertaintyRequired")
                              : budgetImpactBlocked
                                ? t("status.budgetImpactRequired")
                              : survivalReviewBlocked
                                ? t("status.survivalReviewRequired")
                              : pairedBootstrapBlocked
                                ? t("status.pairedBootstrapReviewRequired")
                              : validationBlocked
                                ? t("status.validationRequired")
                              : reportingBlocked
                                ? t("status.reportingRequired")
                              : reproducibilityBlocked
                                ? t("status.reproducibilityRequired")
                              : waiting
                                ? t("status.awaiting")
                                : t("status.locked")}
                        </span>
                      </div>
                      {stale && gateEvent ? (
                        <button
                          onClick={() =>
                            setIntent({
                              action: "revoke",
                              gate,
                              artifactSha256: gateEvent.artifactSha256,
                            })
                          }
                          className="mt-2 text-xs font-medium text-error hover:underline"
                        >
                          {t("action.revokeStale")}
                        </button>
                      ) : waiting ? (
                        <button
                          onClick={() =>
                            setIntent({
                              action: "approve",
                              gate,
                              artifactSha256: artifactSha256!,
                              expectedActor: gate === "independent_validation"
                                && modelValidation.kind === "ready"
                                ? modelValidation.audit.reviewerLabel
                                : gate === "release" && reporting.kind === "ready"
                                  ? reporting.audit.releaseOwnerLabel
                                : undefined,
                            })
                          }
                          className="mt-2 text-xs font-medium text-accent hover:underline"
                        >
                          {t("action.approve", { gate: t(`gate.${gate}`) })}
                        </button>
                      ) : null}
                      {index === REVIEW_GATES.length - 1 && approved && artifactSha256 && (
                        <div className="mt-2 font-mono text-[10px] text-muted">
                          {artifactSha256.slice(0, 12)}…
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              <button
                onClick={() => void runAnalysis()}
                disabled={running}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-input bg-accent px-3 py-2 text-xs font-semibold text-accent-fg hover:opacity-90 disabled:opacity-60"
              >
                {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={13} fill="currentColor" />}
                {running ? t("action.running") : t("action.run")}
              </button>
              {isTauri && uncertainty.kind === "ready" && uncertainty.audit.complete && (
                <button
                  onClick={() => void runUncertainty()}
                  disabled={running}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-input border border-accent px-3 py-2 text-xs font-semibold text-accent hover:bg-accent/5 disabled:opacity-60"
                >
                  {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={13} />}
                  {running ? t("action.running") : t("action.runUncertainty")}
                </button>
              )}
              {isTauri && advancedVoi.kind === "ready" && advancedVoi.audit.complete && (
                <button
                  onClick={() => void runAdvancedVoi()}
                  disabled={running}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-input border border-accent px-3 py-2 text-xs font-semibold text-accent hover:bg-accent/5 disabled:opacity-60"
                >
                  {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={13} />}
                  {running ? t("action.running") : t("action.runAdvancedVoi")}
                </button>
              )}
              {isTauri && budgetImpact.kind === "ready" && budgetImpact.audit.complete && (
                <button
                  onClick={() => void runBudgetImpact()}
                  disabled={running}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-input border border-accent px-3 py-2 text-xs font-semibold text-accent hover:bg-accent/5 disabled:opacity-60"
                >
                  {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={13} />}
                  {running ? t("action.running") : t("action.runBudgetImpact")}
                </button>
              )}
              {isTauri && partitionedSurvival.kind === "ready"
                && partitionedSurvival.audit.required && partitionedSurvival.audit.complete && (
                <button
                  onClick={() => void runPartitionedSurvival()}
                  disabled={running}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-input border border-accent px-3 py-2 text-xs font-semibold text-accent hover:bg-accent/5 disabled:opacity-60"
                >
                  {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={13} />}
                  {running ? t("action.running") : t("action.runPartitionedSurvival")}
                </button>
              )}
            </section>

            {result && <ResultCard result={result} locale={i18n.language} />}
            {uncertaintyResult && (
              <UncertaintyResultCard result={uncertaintyResult} locale={i18n.language} />
            )}
            {advancedVoiResult && (
              <AdvancedVoiResultCard result={advancedVoiResult} locale={i18n.language} />
            )}
            {budgetImpactResult && (
              <BudgetImpactResultCard result={budgetImpactResult} locale={i18n.language} />
            )}
            {partitionedSurvivalResult && (
              <PartitionedSurvivalResultCard result={partitionedSurvivalResult} locale={i18n.language} />
            )}

            <section className="px-5 py-4 text-[10px] leading-5 text-muted">
              <div className="flex justify-between gap-3">
                <span>{t("panel.hash")}</span>
                <span className="max-w-[65%] truncate font-mono" title={artifact.sha256}>{artifact.sha256}</span>
              </div>
              <div className="mt-1 flex justify-between gap-3">
                <span>{t("panel.chain")}</span>
                <span>{approvals.chainHead ? t("panel.unanchored") : "—"}</span>
              </div>
              <div className="mt-1 flex justify-between gap-3">
                <span>{t("panel.identity")}</span>
                <span className="font-mono">{approvals.identityAssurance}</span>
              </div>
            </section>
          </>
        )}
      </div>

      {intent && artifact.kind === "ready" && (
        <ApprovalDialog
          intent={intent}
          artifactHash={intent.artifactSha256}
          onCancel={() => setIntent(null)}
          onSubmit={(actor, rationale) => void submitReview(actor, rationale)}
        />
      )}
      {searchDialogOpen && evidenceSearch.kind === "ready" && (
        <SearchAuthorizationDialog
          audit={evidenceSearch.audit}
          running={searchRunning}
          onCancel={() => setSearchDialogOpen(false)}
          onSubmit={(actor, rationale) => void runEvidenceSearch(actor, rationale)}
        />
      )}
      {verificationDialogOpen && evidenceSynthesis.kind === "ready" && (
        <EvidenceVerificationDialog
          audit={evidenceSynthesis.audit}
          running={verificationRunning}
          onCancel={() => setVerificationDialogOpen(false)}
          onSubmit={(actor, rationale, decision, extractionIds) =>
            void verifyEvidenceExtractions(actor, rationale, decision, extractionIds)}
        />
      )}
      {pairedBootstrapDialogOpen && pairedBootstrap.kind === "ready" && (
        <PairedBootstrapReviewDialog
          audit={pairedBootstrap.audit}
          running={pairedBootstrapReviewRunning}
          onCancel={() => setPairedBootstrapDialogOpen(false)}
          onSubmit={(action, checklist, actor, rationale) =>
            void submitPairedBootstrapReview(action, checklist, actor, rationale)}
        />
      )}
      {networkMetaAnalysisDialogOpen && networkMetaAnalysis.kind === "ready" && (
        <NetworkMetaAnalysisReviewDialog
          audit={networkMetaAnalysis.audit}
          running={networkMetaAnalysisReviewRunning}
          onCancel={() => setNetworkMetaAnalysisDialogOpen(false)}
          onSubmit={(action, checklist, actor, rationale) =>
            void submitNetworkMetaAnalysisReview(action, checklist, actor, rationale)}
        />
      )}
      {populationAdjustedComparisonDialogOpen
        && populationAdjustedComparison.kind === "ready" && (
        <PopulationAdjustedComparisonReviewDialog
          audit={populationAdjustedComparison.audit}
          running={populationAdjustedComparisonReviewRunning}
          onCancel={() => setPopulationAdjustedComparisonDialogOpen(false)}
          onSubmit={(action, checklist, actor, rationale) =>
            void submitPopulationAdjustedComparisonReview(action, checklist, actor, rationale)}
        />
      )}
      {rweCausalAnalysisDialogOpen && rweCausalAnalysis.kind === "ready" && (
        <RweCausalAnalysisReviewDialog
          audit={rweCausalAnalysis.audit}
          running={rweCausalAnalysisReviewRunning}
          onCancel={() => setRweCausalAnalysisDialogOpen(false)}
          onSubmit={(action, checklist, actor, rationale) =>
            void submitRweCausalAnalysisReview(action, checklist, actor, rationale)}
        />
      )}
      {advancedVoiDialogOpen && advancedVoi.kind === "ready"
        && advancedVoi.audit.resultSha256 && advancedVoi.audit.replaySha256 && (
        <AdvancedVoiReviewDialog
          audit={advancedVoi.audit}
          running={advancedVoiReviewRunning}
          onCancel={() => setAdvancedVoiDialogOpen(false)}
          onSubmit={(action, checklist, actor, rationale) =>
            void submitAdvancedVoiReview(action, checklist, actor, rationale)}
        />
      )}
    </div>
  );
}

export function AdvancedVoiReviewDialog({
  audit,
  running,
  onCancel,
  onSubmit,
}: {
  audit: HeorAdvancedVoiAudit;
  running: boolean;
  onCancel: () => void;
  onSubmit: (
    action: "accept" | "reject",
    checklist: HeorAdvancedVoiChecklist,
    actor: string,
    rationale: string,
  ) => void;
}) {
  const { t } = useTranslation("heor");
  const [action, setAction] = useState<"accept" | "reject">("accept");
  const [actor, setActor] = useState("");
  const [rationale, setRationale] = useState("");
  const [checklist, setChecklist] = useState<HeorAdvancedVoiChecklist>({
    decisionScopeThresholdReviewed: false,
    populationLifetimeImplementationReviewed: false,
    representedOmittedUncertaintyReviewed: false,
    evppiGroupingCorrelationReviewed: false,
    nestedMonteCarloPrecisionBiasReviewed: false,
    evsiPriorLikelihoodDataModelReviewed: false,
    researchDelayCostOpportunityCostReviewed: false,
    limitationsNoDecisionAuthorityReviewed: false,
  });
  const checks = Object.entries(checklist) as Array<[
    keyof HeorAdvancedVoiChecklist,
    boolean,
  ]>;
  const allConfirmed = checks.every(([, checked]) => checked);
  const valid = !running && actor.trim().length > 0 && rationale.trim().length > 0
    && (action === "reject" || allConfirmed);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
      <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-card border border-border bg-surface p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-text">{t("advancedVoiReview.title")}</div>
            <div className="mt-1 font-mono text-[10px] text-muted">{audit.voiId}</div>
          </div>
          <button onClick={onCancel} disabled={running} aria-label={t("dialog.cancel")} className="rounded p-1 text-muted hover:text-text">
            <X size={16} />
          </button>
        </div>
        <p className="mt-3 text-xs leading-5 text-muted">{t("advancedVoiReview.boundary")}</p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {ADVANCED_VOI_REVIEW_ACTIONS.map((value) => (
            <button key={value} onClick={() => setAction(value)} className={cn(
              "rounded-input border px-3 py-2 text-xs font-semibold",
              action === value ? "border-accent bg-accent/10 text-accent" : "border-border text-muted",
            )}>
              {t(`advancedVoiReview.${value}`)}
            </button>
          ))}
        </div>
        <div className="mt-4 space-y-2">
          {checks.map(([key, checked]) => (
            <label key={key} className="flex cursor-pointer items-start gap-2 rounded-input border border-border px-3 py-2 text-xs leading-5 text-text">
              <input
                type="checkbox"
                checked={checked}
                onChange={(event) => setChecklist((current) => ({ ...current, [key]: event.target.checked }))}
                className="mt-1"
              />
              <span>{t(`advancedVoiReview.checks.${key}`)}</span>
            </label>
          ))}
        </div>
        <label className="mt-4 block text-xs font-medium text-text">
          {t("advancedVoiReview.actor")}
          <input value={actor} onChange={(event) => setActor(event.target.value)} className="mt-2 w-full rounded-input border border-border bg-bg px-3 py-2 text-xs outline-none focus:border-accent" />
        </label>
        <label className="mt-3 block text-xs font-medium text-text">
          {t("advancedVoiReview.rationale")}
          <textarea value={rationale} onChange={(event) => setRationale(event.target.value)} rows={3} className="mt-2 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-xs leading-5 outline-none focus:border-accent" />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button disabled={running} onClick={onCancel} className="rounded-input border border-border px-3 py-2 text-xs text-muted disabled:opacity-50">{t("dialog.cancel")}</button>
          <button disabled={!valid} onClick={() => onSubmit(action, checklist, actor.trim(), rationale.trim())} className={cn(
            "rounded-input px-3 py-2 text-xs font-semibold text-white disabled:opacity-40",
            action === "accept" ? "bg-ok" : "bg-danger",
          )}>
            {running ? t("advancedVoiReview.recording") : t("advancedVoiReview.record")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function EvidenceVerificationDialog({
  audit,
  running,
  onCancel,
  onSubmit,
}: {
  audit: HeorEvidenceSynthesisAudit;
  running: boolean;
  onCancel: () => void;
  onSubmit: (
    actor: string,
    rationale: string,
    decision: "confirmed" | "rejected",
    extractionIds: string[],
  ) => void;
}) {
  const { t } = useTranslation("heor");
  const [actor, setActor] = useState("");
  const [rationale, setRationale] = useState("");
  const [decision, setDecision] = useState<"confirmed" | "rejected">("confirmed");
  const [confirmed, setConfirmed] = useState(false);
  const pendingAll = useMemo(() => {
    const rejected = new Set(audit.rejectedExtractionIds);
    const unverified = new Set(audit.unverifiedExtractionIds);
    return audit.eligibleExtractions
      .filter((item) => unverified.has(item.extractionId) && !rejected.has(item.extractionId));
  }, [audit]);
  const pending = pendingAll.slice(0, 100);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(pending.map((item) => item.extractionId)),
  );
  const valid = actor.trim().length > 0 && rationale.trim().length > 1
    && selectedIds.size > 0 && confirmed && !running;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && !running && onCancel();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel, running]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={() => !running && onCancel()} role="presentation">
      <div role="dialog" aria-modal="true" aria-label={t("synthesis.verifyTitle")} className="w-full max-w-md rounded-card border border-border bg-surface p-5 shadow-card" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center gap-2 text-sm font-semibold text-text">
          <ShieldCheck size={17} className="text-accent" /> {t("synthesis.verifyTitle")}
        </div>
        <p className="mt-2 text-xs leading-5 text-muted">
          {t("synthesis.verifyBody", {
            count: pending.length,
            total: pendingAll.length,
            hash: `${audit.synthesisSha256.slice(0, 12)}…`,
          })}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2" role="group" aria-label={t("synthesis.decisionLabel")}>
          {EVIDENCE_REVIEW_DECISIONS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={decision === value}
              onClick={() => {
                setDecision(value);
                setConfirmed(false);
                setSelectedIds(value === "confirmed"
                  ? new Set(pending.map((item) => item.extractionId))
                  : new Set());
              }}
              className={cn(
                "rounded-input border px-3 py-2 text-xs font-medium",
                decision === value
                  ? value === "confirmed" ? "border-ok bg-ok/10 text-ok" : "border-danger bg-danger/10 text-danger"
                  : "border-border text-muted",
              )}
            >
              {t(`synthesis.${value}`)}
            </button>
          ))}
        </div>
        <div className="mt-3 max-h-56 space-y-2 overflow-y-auto rounded-input border border-border bg-bg p-2">
          {pending.map((item) => (
            <label key={item.extractionId} className="flex cursor-pointer items-start gap-2 rounded-input border border-border bg-surface p-2 text-xs">
              <input
                type="checkbox"
                aria-label={t("synthesis.selectExtraction", { id: item.extractionId })}
                checked={selectedIds.has(item.extractionId)}
                onChange={(event) => setSelectedIds((current) => {
                  const next = new Set(current);
                  if (event.target.checked) next.add(item.extractionId);
                  else next.delete(item.extractionId);
                  setConfirmed(false);
                  return next;
                })}
                className="mt-1 accent-[var(--color-accent)]"
              />
              <span className="min-w-0">
                <span className="block break-all font-mono text-[10px] text-muted">
                  {item.extractionId} · {item.recordId}
                </span>
                <span className="mt-1 block break-words font-medium text-text">{item.extractedValue}</span>
                <span className="mt-1 block break-words text-muted">{item.target}</span>
                <span className="block break-words text-muted">
                  {t("synthesis.sourceLocation")}: {item.sourceLocation}
                </span>
                <span className="block break-words text-muted">
                  {t("synthesis.applicability")}: {item.applicability}
                </span>
              </span>
            </label>
          ))}
        </div>
        <label className="mt-4 block text-xs font-medium text-text">
          {t("dialog.actor")}
          <input value={actor} onChange={(event) => setActor(event.target.value)} autoFocus placeholder={t("dialog.actorPlaceholder")} className="mt-1.5 w-full rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent" />
        </label>
        <label className="mt-3 block text-xs font-medium text-text">
          {t("dialog.rationale")}
          <textarea value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder={t("synthesis.verifyRationale")} rows={3} className="mt-1.5 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent" />
        </label>
        <label className="mt-3 flex items-start gap-2 text-xs leading-5 text-text">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="mt-1 accent-[var(--color-accent)]" />
          <span>{t(decision === "confirmed"
            ? "synthesis.verifyConfirm"
            : "synthesis.rejectConfirm", { count: selectedIds.size })}</span>
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <button disabled={running} onClick={onCancel} className="rounded-input border border-border px-3 py-2 text-xs text-muted hover:text-text disabled:opacity-50">{t("dialog.cancel")}</button>
          <button disabled={!valid} onClick={() => onSubmit(actor.trim(), rationale.trim(), decision, [...selectedIds])} className={cn("rounded-input px-3 py-2 text-xs font-semibold disabled:opacity-50", decision === "confirmed" ? "bg-accent text-accent-fg" : "bg-danger text-white")}>
            {running ? t("synthesis.verifying") : t(decision === "confirmed" ? "synthesis.verifySubmit" : "synthesis.rejectSubmit")}
          </button>
        </div>
      </div>
    </div>
  );
}

function StageRail({ currentApprovals, hasResult }: { currentApprovals: HeorGate[]; hasResult: boolean }) {
  const { t } = useTranslation("heor");
  const stages = [
    { key: "scope", done: currentApprovals.includes("decision_problem") },
    { key: "model", done: currentApprovals.includes("conceptual_model") },
    { key: "plan", done: currentApprovals.includes("analysis_plan") },
    { key: "compute", done: hasResult },
    { key: "validate", done: currentApprovals.includes("independent_validation") },
    { key: "release", done: currentApprovals.includes("release") },
  ] as const;
  return (
    <div className="border-b border-border px-5 py-3">
      <div className="flex items-start">
        {stages.map((stage, index) => (
          <div key={stage.key} className="flex min-w-0 flex-1 items-start">
            <div className="min-w-0 flex-1 text-center">
              <div className={cn("mx-auto flex h-5 w-5 items-center justify-center rounded-full border text-[10px]", stage.done ? "border-ok bg-ok text-white" : "border-border bg-surface text-muted")}>
                {stage.done ? <Check size={11} /> : index + 1}
              </div>
              <div className="mt-1 truncate text-[9px] text-muted">{t(`stage.${stage.key}`)}</div>
            </div>
            {index < stages.length - 1 && (
              <div className={cn("mt-2.5 h-px w-2 shrink-0", stage.done ? "bg-ok/50" : "bg-border")} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export type MethodReviewQueueStatus = "awaiting" | "accepted" | "rejected" | "blocked";

export interface MethodReviewQueueItem {
  id: "nma" | "pac" | "rweCausal" | "pairedBootstrap" | "advancedVoi";
  path: string;
  status: MethodReviewQueueStatus;
  onReview: () => void;
  onPrepare: () => void;
}

function methodReviewQueueStatus(
  reviewable: boolean,
  accepted: boolean,
  currentAction: "accept" | "reject" | null,
): MethodReviewQueueStatus {
  if (accepted) return "accepted";
  if (currentAction === "reject") return "rejected";
  return reviewable ? "awaiting" : "blocked";
}

const METHOD_REVIEW_STATUS_PRIORITY: Record<MethodReviewQueueStatus, number> = {
  rejected: 0,
  awaiting: 1,
  blocked: 2,
  accepted: 3,
};

export function MethodReviewQueue({ items }: { items: MethodReviewQueueItem[] }) {
  const { t } = useTranslation("heor");
  if (items.length === 0) return null;
  const ordered = [...items].sort((left, right) =>
    METHOD_REVIEW_STATUS_PRIORITY[left.status] - METHOD_REVIEW_STATUS_PRIORITY[right.status]);
  const acceptedCount = items.filter((item) => item.status === "accepted").length;
  const awaitingCount = items.filter((item) => item.status === "awaiting").length;
  return (
    <section className="border-b border-border px-5 py-4" aria-labelledby="method-review-queue-title">
      <div className="flex items-start gap-2">
        <ShieldCheck size={16} className="mt-0.5 text-accent" />
        <div className="min-w-0 flex-1">
          <div id="method-review-queue-title" className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("methodReviewQueue.title")}
          </div>
          <div className="mt-1 text-[10px] leading-4 text-muted">
            {t("methodReviewQueue.summary", {
              accepted: acceptedCount,
              awaiting: awaitingCount,
              total: items.length,
            })}
          </div>
        </div>
      </div>
      <ul className="mt-3 divide-y divide-border rounded-input border border-border bg-bg">
        {ordered.map((item) => {
          const accepted = item.status === "accepted";
          const awaiting = item.status === "awaiting";
          const rejected = item.status === "rejected";
          const method = t(`methodReviewQueue.methods.${item.id}`);
          return (
            <li key={item.id} className="flex items-center gap-3 px-3 py-2.5">
              {accepted ? <Check size={14} className="shrink-0 text-ok" />
                : rejected ? <X size={14} className="shrink-0 text-danger" />
                  : awaiting ? <LockKeyhole size={14} className="shrink-0 text-accent" />
                    : <AlertTriangle size={14} className="shrink-0 text-warning" />}
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-medium text-text">{method}</div>
                <div className="truncate font-mono text-[9px] text-muted">{item.path}</div>
              </div>
              <div className="shrink-0 text-right">
                <div className={cn(
                  "text-[10px] font-semibold",
                  accepted ? "text-ok" : rejected ? "text-danger"
                    : awaiting ? "text-accent" : "text-warning",
                )}>
                  {t(`methodReviewQueue.status.${item.status}`)}
                </div>
                {awaiting ? (
                  <button
                    type="button"
                    onClick={item.onReview}
                    aria-label={t("methodReviewQueue.openFor", { method })}
                    className="mt-1 text-[10px] font-medium text-link hover:underline"
                  >
                    {t("methodReviewQueue.open")}
                  </button>
                ) : !accepted ? (
                  <button
                    type="button"
                    onClick={item.onPrepare}
                    aria-label={t("methodReviewQueue.discussFor", { method })}
                    className="mt-1 text-[10px] font-medium text-link hover:underline"
                  >
                    {t("methodReviewQueue.discuss")}
                  </button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("methodReviewQueue.boundary")}</p>
    </section>
  );
}

export function MethodsWatchlistAssessment({
  state,
  onPrepare,
}: {
  state: MethodsWatchlistState;
  onPrepare: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const issues = [
    ...(audit?.overdueSources.map((source) => t("methodsWatchlist.overdueSource", { source })) ?? []),
    ...(audit?.unresolvedChanges.map((change) => t("methodsWatchlist.unresolvedChange", { change })) ?? []),
    ...(audit?.errors ?? []),
    ...(state.kind === "invalid" ? [state.message] : []),
  ];
  const complete = Boolean(audit?.complete);
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        <RefreshCw size={16} className={complete ? "mt-0.5 text-ok" : "mt-0.5 text-warning"} />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("methodsWatchlist.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", complete ? "text-ok" : "text-warning")}>
            {state.kind === "loading"
              ? t("methodsWatchlist.loading")
              : !audit?.exists
                ? t("methodsWatchlist.missing")
                : complete
                  ? t("methodsWatchlist.complete", { date: audit.asOfDate })
                  : t("methodsWatchlist.incomplete", { date: audit?.asOfDate || t("methodsWatchlist.unknownDate") })}
          </div>
        </div>
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">{HEOR_METHODS_WATCHLIST_PATH}</div>
      {audit?.exists && (
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Metric label={t("methodsWatchlist.sources")} value={String(audit.sourceCount)} />
          <Metric label={t("methodsWatchlist.current")} value={String(audit.currentCount)} />
          <Metric label={t("methodsWatchlist.changes")} value={String(audit.unresolvedChangeCount)} />
        </div>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-warning">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      {!complete && state.kind !== "loading" && (
        <button
          type="button"
          onClick={onPrepare}
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
        >
          <MessageSquareText size={13} /> {t("methodsWatchlist.ask")}
        </button>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("methodsWatchlist.note")}</p>
    </section>
  );
}

function EvidenceLibraryAssessment({
  state,
  syncing,
  onAddFiles,
  onAddFolder,
  onSync,
  onAsk,
}: {
  state: EvidenceLibraryState;
  syncing: boolean;
  onAddFiles: () => void;
  onAddFolder: () => void;
  onSync: () => void;
  onAsk: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const issues = audit?.errors ?? (state.kind === "invalid" ? [state.message] : []);
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        <BookOpen
          size={16}
          className={audit?.searchable ? "mt-0.5 text-ok" : "mt-0.5 text-warning"}
        />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("library.title")}
          </div>
          <div className={cn(
            "mt-1 text-xs font-semibold",
            audit?.searchable ? "text-ok" : "text-warning",
          )}>
            {state.kind === "loading"
              ? t("library.loading")
              : audit?.complete
                ? t("library.complete")
                : audit?.searchable
                  ? t("library.partial")
                  : t("library.incomplete")}
          </div>
        </div>
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">
        {HEOR_EVIDENCE_LIBRARY_PATH}
      </div>
      {audit && (
        <>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <Metric label={t("library.documents")} value={String(audit.documentCount)} />
            <Metric label={t("library.indexed")} value={String(audit.indexedCount)} />
            <Metric label={t("library.ocr")} value={String(audit.requiresOcrCount)} />
          </div>
          {audit.manifestSha256 && (
            <div className="mt-2 break-all font-mono text-[9px] text-muted">
              {t("library.hash")} {audit.manifestSha256}
            </div>
          )}
        </>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-warning">
          {issues.slice(0, 4).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-3">
        {isTauri && (
          <button
            disabled={syncing}
            onClick={onAddFolder}
            className="flex items-center gap-1.5 text-xs font-medium text-accent hover:underline disabled:opacity-50"
          >
            {syncing
              ? <Loader2 size={13} className="animate-spin" />
              : <FolderPlus size={13} />}
            {t("library.addFolder")}
          </button>
        )}
        {isTauri && (
          <button
            disabled={syncing}
            onClick={onAddFiles}
            className="flex items-center gap-1.5 text-xs font-medium text-accent hover:underline disabled:opacity-50"
          >
            <FilePlus2 size={13} />
            {t("library.addFiles")}
          </button>
        )}
        {isTauri && (
          <button
            disabled={syncing}
            onClick={onSync}
            className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline disabled:opacity-50"
          >
            <RefreshCw size={13} className={syncing ? "animate-spin" : ""} />
            {t("library.sync")}
          </button>
        )}
        {audit?.searchable && (
          <button
            onClick={onAsk}
            className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
          >
            <MessageSquareText size={13} /> {t("library.ask")}
          </button>
        )}
      </div>
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("library.note")}</p>
    </section>
  );
}

function EvidenceSearchAssessment({
  state,
  result,
  running,
  onRequestDraft,
  onAuthorize,
}: {
  state: EvidenceSearchState;
  result: HeorSearchExecutionResponse | null;
  running: boolean;
  onRequestDraft: () => void;
  onAuthorize: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const complete = audit?.complete === true;
  const issues = audit?.errors ?? (state.kind === "invalid" ? [state.message] : []);
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        <Search size={16} className={complete ? "mt-0.5 text-ok" : "mt-0.5 text-warning"} />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("search.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", complete ? "text-ok" : "text-warning")}>
            {state.kind === "loading"
              ? t("search.loading")
              : complete ? t("search.complete") : t("search.incomplete")}
          </div>
        </div>
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">
        {HEOR_EVIDENCE_SEARCH_REQUEST_PATH}
      </div>
      {audit && complete && (
        <>
          <p className="mt-3 break-words text-xs leading-5 text-text">{audit.query}</p>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <Metric label={t("search.sources")} value={audit.sources.join(" + ")} />
            <Metric
              label={t("search.range")}
              value={`${audit.dateFrom ?? "—"} → ${audit.dateTo ?? "—"}`}
            />
            <Metric label={t("search.cap")} value={String(audit.maxResultsPerSource ?? "—")} />
          </div>
          <div className="mt-2 break-all font-mono text-[9px] text-muted">
            {t("search.hash")} {audit.requestSha256}
          </div>
        </>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-warning">
          {issues.slice(0, 4).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-3">
        {!complete && state.kind !== "loading" && (
          <button onClick={onRequestDraft} className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
            <MessageSquareText size={13} /> {t("search.askDraft")}
          </button>
        )}
        {complete && isTauri && (
          <button
            disabled={running}
            onClick={onAuthorize}
            className="flex items-center gap-1.5 text-xs font-medium text-accent hover:underline disabled:opacity-50"
          >
            {running ? <Loader2 size={13} className="animate-spin" /> : <LockKeyhole size={13} />}
            {running ? t("search.running") : t("search.authorize")}
          </button>
        )}
      </div>
      {result && (
        <div className="mt-4 rounded-input border border-ok/30 bg-ok/5 p-3">
          <div className="text-xs font-semibold text-ok">{t("search.result")}</div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-center">
            <Metric label={t("search.records")} value={String(result.result.records.length)} />
            <Metric
              label={t("search.sourceRuns")}
              value={result.result.sourceRuns.map((run) => `${run.source}: ${run.fetchedCount}`).join(" · ")}
            />
          </div>
          <div className="mt-2 break-all font-mono text-[9px] text-muted">
            {result.result.outputPath} · {result.authorization.eventHash.slice(0, 12)}…
          </div>
        </div>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("search.note")}</p>
    </section>
  );
}

function EvidenceSynthesisAssessment({
  state,
  authorization,
  importResult,
  importing,
  verifying,
  onPrepare,
  onImport,
  onContinue,
  onVerify,
}: {
  state: EvidenceSynthesisState;
  authorization: HeorSearchAuthorizationEvent | null;
  importResult: HeorImportCandidatesResponse | null;
  importing: boolean;
  verifying: boolean;
  onPrepare: () => void;
  onImport: () => void;
  onContinue: () => void;
  onVerify: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const issues = audit
    ? [
        ...audit.errors,
        ...audit.rejectedExtractionIds.map((id) => t("synthesis.rejectedIssue", { id })),
      ]
    : state.kind === "invalid" ? [state.message] : [];
  const canImport = isTauri && authorization !== null && audit?.importable === true;
  const pendingReviewCount = audit
    ? audit.unverifiedExtractionIds.filter((id) => !audit.rejectedExtractionIds.includes(id)).length
    : 0;
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        <FileJson
          size={16}
          className={audit?.complete ? "mt-0.5 text-ok" : "mt-0.5 text-warning"}
        />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("synthesis.title")}
          </div>
          <div className={cn(
            "mt-1 text-xs font-semibold",
            audit?.complete ? "text-ok" : "text-warning",
          )}>
            {state.kind === "loading"
              ? t("synthesis.loading")
              : audit?.complete ? t("synthesis.complete") : t("synthesis.incomplete")}
          </div>
        </div>
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">
        {HEOR_EVIDENCE_SYNTHESIS_PATH}
      </div>
      {audit && audit.synthesisSha256 && (
        <>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <Metric label={t("synthesis.searches")} value={String(audit.searchCount)} />
            <Metric label={t("synthesis.records")} value={String(audit.recordCount)} />
            <Metric label={t("synthesis.notAssessed")} value={String(audit.notAssessedCount)} />
            <Metric label={t("synthesis.included")} value={String(audit.includedCount)} />
            <Metric label={t("synthesis.extractions")} value={String(audit.extractionCount)} />
            <Metric label={t("synthesis.conflicts")} value={String(audit.unresolvedConflicts.length)} />
            <Metric
              label={t("synthesis.dualVerified")}
              value={`${audit.appVerifiedExtractionIds.length}/${audit.eligibleExtractionIds.length}`}
            />
            <Metric
              label={t("synthesis.confirmations")}
              value={`${audit.reviewConfirmationCount}/${audit.eligibleExtractionIds.length * audit.requiredReviewersPerExtraction}`}
            />
          </div>
          <div className="mt-2 break-all font-mono text-[9px] text-muted">
            {t("synthesis.hash")} {audit.synthesisSha256}
          </div>
        </>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-warning">
          {issues.slice(0, 4).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-3">
        {audit?.importable !== true && state.kind !== "loading" && (
          <button onClick={onPrepare} className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
            <MessageSquareText size={13} /> {t("synthesis.askPrepare")}
          </button>
        )}
        {canImport && (
          <button
            disabled={importing}
            onClick={onImport}
            className="flex items-center gap-1.5 text-xs font-medium text-accent hover:underline disabled:opacity-50"
          >
            {importing ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
            {importing ? t("synthesis.importing") : t("synthesis.import")}
          </button>
        )}
        {audit?.recordCount !== undefined && audit.recordCount > 0 && (
          <button onClick={onContinue} className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
            <MessageSquareText size={13} /> {t("synthesis.continue")}
          </button>
        )}
        {isTauri && audit?.complete && pendingReviewCount > 0 && (
          <button
            disabled={verifying}
            onClick={onVerify}
            className="flex items-center gap-1.5 text-xs font-medium text-accent hover:underline disabled:opacity-50"
          >
            {verifying ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
            {t("synthesis.verify")}
          </button>
        )}
      </div>
      {importResult && (
        <div className="mt-4 rounded-input border border-ok/30 bg-ok/5 p-3 text-xs text-ok">
          {t("synthesis.importResult", {
            added: importResult.addedRecords,
            reconciled: importResult.reconciledRecords,
          })}
        </div>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("synthesis.note")}</p>
    </section>
  );
}

function SearchAuthorizationDialog({
  audit,
  running,
  onCancel,
  onSubmit,
}: {
  audit: HeorEvidenceSearchAudit;
  running: boolean;
  onCancel: () => void;
  onSubmit: (actor: string, rationale: string) => void;
}) {
  const { t } = useTranslation("heor");
  const [actor, setActor] = useState("");
  const [rationale, setRationale] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const valid = actor.trim().length > 0 && rationale.trim().length > 1 && confirmed && !running;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && !running && onCancel();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel, running]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={() => !running && onCancel()} role="presentation">
      <div role="dialog" aria-modal="true" aria-label={t("search.dialogTitle")} className="w-full max-w-md rounded-card border border-border bg-surface p-5 shadow-card" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center gap-2 text-sm font-semibold text-text">
          <LockKeyhole size={17} className="text-accent" /> {t("search.dialogTitle")}
        </div>
        <p className="mt-2 text-xs leading-5 text-muted">
          {t("search.dialogBody", { hash: `${audit.requestSha256.slice(0, 12)}…` })}
        </p>
        <div className="mt-3 rounded-input border border-border bg-bg p-3 text-xs leading-5 text-text">
          <div className="break-words">{audit.query}</div>
          <div className="mt-1 font-mono text-[10px] text-muted">{audit.sources.join(" + ")}</div>
        </div>
        <label className="mt-4 block text-xs font-medium text-text">
          {t("dialog.actor")}
          <input value={actor} onChange={(event) => setActor(event.target.value)} autoFocus placeholder={t("dialog.actorPlaceholder")} className="mt-1.5 w-full rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent" />
        </label>
        <label className="mt-3 block text-xs font-medium text-text">
          {t("dialog.rationale")}
          <textarea value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder={t("search.rationalePlaceholder")} rows={3} className="mt-1.5 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent" />
        </label>
        <label className="mt-3 flex items-start gap-2 text-xs leading-5 text-text">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="mt-1 accent-[var(--color-accent)]" />
          <span>{t("search.confirm")}</span>
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <button disabled={running} onClick={onCancel} className="rounded-input border border-border px-3 py-1.5 text-xs font-medium text-text hover:bg-surface-2 disabled:opacity-40">{t("dialog.cancel")}</button>
          <button disabled={!valid} onClick={() => onSubmit(actor.trim(), rationale.trim())} className="rounded-input bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">{running ? t("search.running") : t("search.execute")}</button>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-6 py-12 text-center">
      <FileJson size={24} strokeWidth={1.4} className="mx-auto text-muted" />
      <div className="mt-3 text-sm font-semibold text-text">{title}</div>
      <p className="mx-auto mt-1.5 max-w-xs text-xs leading-5 text-muted">{body}</p>
    </div>
  );
}

function DecisionSnapshot({ plan }: { plan: HeorAnalysisPlan }) {
  const { t } = useTranslation("heor");
  const d = plan.decision_problem;
  const values = [
    [t("snapshot.population"), d.population],
    [t("snapshot.intervention"), d.intervention],
    [t("snapshot.comparator"), d.comparator],
    [t("snapshot.perspective"), d.perspective],
    [t("snapshot.horizon"), t("snapshot.horizonValue", { count: d.time_horizon_years })],
    [t("snapshot.referenceCase"), `${plan.reference_case.id} · ${plan.reference_case.status}`],
    [t("snapshot.states"), plan.states.join(" · ")],
    [t("snapshot.cycles"), String(plan.cycles)],
    [t("snapshot.discount"), `${(plan.discount_rates.costs * 100).toFixed(1)}% / ${(plan.discount_rates.outcomes * 100).toFixed(1)}%`],
    [t("snapshot.halfCycle"), plan.half_cycle_correction ? t("snapshot.enabled") : t("snapshot.disabled")],
    [t("snapshot.evidence"), String(plan.evidence_sources?.length ?? 0)],
    [t("snapshot.assumptions"), String(plan.assumptions?.filter((item) => item.status === "unresolved").length ?? 0)],
  ];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-muted">
        {t("snapshot.title")}
      </div>
      <dl className="grid grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] gap-x-4 gap-y-2">
        {values.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-[11px] text-muted">{label}</dt>
            <dd className="min-w-0 break-words text-right text-[11px] font-medium text-text">{value || "—"}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function ConceptualModelTraceability({
  artifact,
  onRequestModel,
}: {
  artifact: ConceptualArtifactState;
  onRequestModel: () => void;
}) {
  const { t } = useTranslation("heor");
  const ready = artifact.kind === "ready";
  const complete = ready && artifact.audit.complete;
  const issues = ready
    ? artifact.audit.errors.slice(0, 3)
    : artifact.kind === "invalid"
      ? [artifact.message]
      : [];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-center gap-2">
        <ShieldCheck size={15} className={complete ? "text-ok" : "text-warning"} />
        <div className="flex-1 text-xs font-semibold uppercase tracking-[0.12em] text-muted">
          {t("conceptual.title")}
        </div>
        <span className={cn("text-[10px] font-medium", complete ? "text-ok" : "text-warning")}>
          {artifact.kind === "loading"
            ? t("conceptual.loading")
            : complete
              ? t("conceptual.complete")
              : t("conceptual.incomplete")}
        </span>
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">{HEOR_CONCEPTUAL_MODEL_PATH}</div>
      {ready && (
        <>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <Metric label={t("conceptual.states")} value={String(artifact.audit.stateCount)} />
            <Metric label={t("conceptual.transitions")} value={String(artifact.audit.transitionCount)} />
            <Metric label={t("conceptual.alternatives")} value={String(artifact.audit.alternativeCount)} />
          </div>
          <div className="mt-2 text-[10px] text-muted">
            {t("conceptual.modelType")}: {artifact.model.model_type.proposed}
          </div>
        </>
      )}
      {artifact.kind === "missing" && (
        <p className="mt-3 text-xs leading-5 text-muted">{t("conceptual.missing")}</p>
      )}
      {issues.length > 0 && (
        <div className="mt-3 space-y-1">
          {issues.map((issue) => (
            <div key={issue} className="break-words font-mono text-[10px] leading-4 text-warning">
              {issue}
            </div>
          ))}
        </div>
      )}
      {!complete && artifact.kind !== "loading" && (
        <button
          onClick={onRequestModel}
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
        >
          <MessageSquareText size={13} /> {t("conceptual.askRepair")}
        </button>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("conceptual.note")}</p>
    </section>
  );
}

function CohortTransitionSummary({
  plan,
  onRequestAudit,
  onRequestRateDerivation,
  onRequestSurvivalDerivation,
  onRequestSurvivalExtrapolationReview,
  onRequestProbabilityTime,
  onRequestBackgroundMortality,
  onRequestRelativeEffect,
  onRequestHazardRatio,
}: {
  plan: HeorAnalysisPlan;
  onRequestAudit: () => void;
  onRequestRateDerivation: () => void;
  onRequestSurvivalDerivation: () => void;
  onRequestSurvivalExtrapolationReview: () => void;
  onRequestProbabilityTime: () => void;
  onRequestBackgroundMortality: () => void;
  onRequestRelativeEffect: () => void;
  onRequestHazardRatio: () => void;
}) {
  const { t } = useTranslation("heor");
  const strategyIds = plan.schema_version === "0.8.0" || plan.schema_version === "0.9.0"
    || plan.schema_version === "0.10.0" || plan.schema_version === "0.11.0"
    ? (plan.strategy_order ?? []) : ["comparator", "intervention"];
  const summary = (strategyId: string) => {
    const schedule = plan.strategies[strategyId]?.transition_schedule;
    return schedule
      ? t("transition.scheduled", {
          cycles: schedule.map((phase) => phase.start_cycle).join(", "),
        })
      : t("transition.static");
  };
  const hasSchedule = strategyIds.some((strategyId) => (
    Boolean(plan.strategies[strategyId]?.transition_schedule)
  ));
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-center gap-2">
        <ShieldCheck size={15} className="text-accent" />
        <div className="flex-1 text-xs font-semibold uppercase tracking-[0.12em] text-muted">
          {t("transition.title")}
        </div>
        <span className="font-mono text-[10px] text-muted">{plan.schema_version}</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-center">
        {strategyIds.map((strategyId) => (
          <Metric
            key={strategyId}
            label={plan.strategies[strategyId]?.name ?? strategyId}
            value={summary(strategyId)}
          />
        ))}
      </div>
      <button
        onClick={onRequestAudit}
        className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
      >
        <MessageSquareText size={13} /> {t("transition.askAudit")}
      </button>
      <button
        onClick={onRequestRateDerivation}
        className="mt-2 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
      >
        <MessageSquareText size={13} /> {t("transition.askRateDerivation")}
      </button>
      <button
        onClick={onRequestSurvivalDerivation}
        className="mt-2 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
      >
        <MessageSquareText size={13} /> {t("transition.askSurvivalDerivation")}
      </button>
      <button
        onClick={onRequestSurvivalExtrapolationReview}
        className="mt-2 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
      >
        <MessageSquareText size={13} /> {t("transition.askSurvivalExtrapolationReview")}
      </button>
      <button
        onClick={onRequestProbabilityTime}
        className="mt-2 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
      >
        <MessageSquareText size={13} /> {t("transition.askProbabilityTime")}
      </button>
      <button
        onClick={onRequestBackgroundMortality}
        className="mt-2 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
      >
        <MessageSquareText size={13} /> {t("transition.askBackgroundMortality")}
      </button>
      <button
        onClick={onRequestRelativeEffect}
        className="mt-2 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
      >
        <MessageSquareText size={13} /> {t("transition.askRelativeEffect")}
      </button>
      <button
        onClick={onRequestHazardRatio}
        className="mt-2 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
      >
        <MessageSquareText size={13} /> {t("transition.askHazardRatio")}
      </button>
      <p className="mt-3 text-[10px] leading-4 text-muted">
        {hasSchedule ? t("transition.scheduleNote") : t("transition.staticNote")}
      </p>
    </section>
  );
}

function EvidenceTraceability({
  audit,
  selection,
  onRequestRepair,
}: {
  audit: ReturnType<typeof auditHeorEvidence>;
  selection: EvidenceSelectionState;
  onRequestRepair: () => void;
}) {
  const { t } = useTranslation("heor");
  const gaps = [
    ...audit.unsupportedInputs.map((path) => t("evidence.unsupported", { path })),
    ...audit.unresolvedAssumptions.map((id) => t("evidence.unresolved", { id })),
    ...audit.invalidMappings.slice(0, 3),
  ];
  const selectionAudit = selection.kind === "ready" ? selection.audit : null;
  const fullyTraceable = audit.complete && selectionAudit?.complete === true;
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {fullyTraceable ? (
          <ShieldCheck size={16} className="mt-0.5 text-ok" />
        ) : (
          <AlertTriangle size={16} className="mt-0.5 text-accent" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("evidence.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", fullyTraceable ? "text-ok" : "text-accent")}>
            {fullyTraceable ? t("evidence.complete") : t("evidence.incomplete")}
          </div>
        </div>
        <span className="rounded-full border border-border bg-bg px-2 py-0.5 font-mono text-[10px] text-text">
          {audit.coveredInputs}/{audit.requiredInputs}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <Metric label={t("evidence.inputs")} value={`${audit.coveredInputs}/${audit.requiredInputs}`} />
        <Metric label={t("evidence.sources")} value={String(audit.sourceCount)} />
        <Metric label={t("evidence.mappings")} value={String(audit.mappingCount)} />
        <Metric
          label={t("evidence.verified")}
          value={selectionAudit
            ? `${selectionAudit.verifiedExtractionCount}/${selectionAudit.selectedExtractionCount}`
            : "—"}
        />
      </div>
      {!fullyTraceable && (
        <>
          <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
            {gaps.slice(0, 5).map((gap) => <li key={gap}>• {gap}</li>)}
            {selectionAudit?.rejectedExtractionIds.slice(0, 3).map((id) => (
              <li key={`rejected-${id}`}>• {t("evidence.rejected", { id })}</li>
            ))}
            {selectionAudit?.unverifiedExtractionIds
              .filter((id) => !selectionAudit.rejectedExtractionIds.includes(id))
              .slice(0, 3).map((id) => (
              <li key={id}>• {t("evidence.unverified", { id })}</li>
            ))}
            {selectionAudit?.invalidSelections.slice(0, 3).map((issue) => (
              <li key={issue}>• {issue}</li>
            ))}
          </ul>
          <button
            onClick={onRequestRepair}
            className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
          >
            <MessageSquareText size={13} /> {t("evidence.askRepair")}
          </button>
        </>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("evidence.note")}</p>
    </section>
  );
}

function SurvivalReviewAssessment({
  state,
  onRequestRepair,
}: {
  state: SurvivalReviewState;
  onRequestRepair: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const complete = audit?.complete === true;
  const notRequired = audit?.required === false;
  const issues = audit
    ? [...audit.blockingGaps, ...audit.errors.filter((error) => !audit.blockingGaps.includes(error))]
    : state.kind === "invalid" ? [state.message] : [];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {complete ? (
          <ShieldCheck size={16} className="mt-0.5 text-ok" />
        ) : (
          <AlertTriangle size={16} className="mt-0.5 text-warning" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("survivalReview.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", complete ? "text-ok" : "text-warning")}>
            {state.kind === "loading"
              ? t("survivalReview.loading")
              : notRequired
                ? t("survivalReview.notRequired")
                : complete ? t("survivalReview.complete") : t("survivalReview.incomplete")}
          </div>
          {audit?.targetPath && (
            <div className="mt-1 truncate font-mono text-[10px] text-muted">
              {audit.targetPath} · {audit.selectedFamily ?? "—"}
            </div>
          )}
          {audit?.required && audit.targetCount > 1 && (
            <div className="mt-1 text-[10px] leading-4 text-muted">
              {t("survivalReview.collection", {
                reviews: audit.reviewCount,
                targets: audit.targetCount,
              })}
            </div>
          )}
        </div>
        {audit?.required && (
          <span className="rounded-full border border-border bg-bg px-2 py-0.5 font-mono text-[10px] text-text">
            {audit.convergedModels}/{audit.candidateModels}
          </span>
        )}
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">
        {audit && audit.targetCount > 1
          ? HEOR_SURVIVAL_EXTRAPOLATION_REVIEW_INDEX_PATH
          : HEOR_SURVIVAL_EXTRAPOLATION_REVIEW_PATH}
      </div>
      {audit?.required && (
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Metric label={t("survivalReview.candidates")} value={String(audit.candidateModels)} />
          <Metric label={t("survivalReview.converged")} value={String(audit.convergedModels)} />
          <Metric label={t("survivalReview.scenarios")} value={String(audit.scenarioCount)} />
        </div>
      )}
      {audit?.recommendedFamily && (
        <p className="mt-3 text-[10px] leading-4 text-muted">
          {t("survivalReview.recommendation", { family: audit.recommendedFamily })}
        </p>
      )}
      {audit?.executionEnvironment && (
        <p className="mt-2 font-mono text-[10px] leading-4 text-muted">
          {t("survivalReview.execution", {
            environment: audit.executionEnvironment,
            crosscheck: audit.crossImplementationComplete
              ? t("survivalReview.crosscheckComplete")
              : t("survivalReview.crosscheckIncomplete"),
          })}
        </p>
      )}
      {audit && audit.targets.length > 1 && (
        <ul className="mt-3 space-y-2">
          {audit.targets.slice(0, 6).map((target) => (
            <li key={target.targetPath} className="rounded border border-border bg-bg px-2 py-1.5">
              <div className="truncate font-mono text-[10px] text-text">{target.targetPath}</div>
              <div className="mt-0.5 text-[10px] leading-4 text-muted">
                {t("survivalReview.curveSummary", {
                  selected: target.selectedFamily,
                  converged: target.convergedModels,
                  candidates: target.candidateModels,
                  recommended: target.recommendedFamily ?? "—",
                })}
              </div>
            </li>
          ))}
        </ul>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      {!complete && state.kind !== "loading" && (
        <button
          onClick={onRequestRepair}
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
        >
          <MessageSquareText size={13} /> {t("survivalReview.askRepair")}
        </button>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("survivalReview.note")}</p>
    </section>
  );
}

export function PairedBootstrapAssessment({
  state,
  currentReview,
  accepted,
  onRequestPreparation,
  onReview,
}: {
  state: PairedBootstrapState;
  currentReview: HeorPairedBootstrapReviewLog["events"][number] | null;
  accepted: boolean;
  onRequestPreparation: () => void;
  onReview: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const issues = audit?.errors ?? (state.kind === "invalid" ? [state.message] : []);
  const status = state.kind === "loading"
    ? t("pairedBootstrap.loading")
    : accepted
      ? t("pairedBootstrap.accepted")
      : currentReview?.action === "reject"
        ? t("pairedBootstrap.rejected")
        : audit?.reviewable
          ? t("pairedBootstrap.awaiting")
          : audit?.executionId
            ? t("pairedBootstrap.incomplete")
            : t("pairedBootstrap.notPrepared");
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {accepted
          ? <ShieldCheck size={16} className="mt-0.5 text-ok" />
          : <AlertTriangle size={16} className="mt-0.5 text-warning" />}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("pairedBootstrap.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", accepted ? "text-ok" : "text-warning")}>
            {status}
          </div>
          <div className="mt-1 break-all font-mono text-[10px] text-muted">
            {audit?.resultPath || HEOR_PAIRED_BOOTSTRAP_REQUEST_PATH}
          </div>
        </div>
      </div>
      {audit?.executionId && (
        <>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <Metric label={t("pairedBootstrap.replicates")} value={`${audit.completedReplicates}/${audit.iterations}`} />
            <Metric label={t("pairedBootstrap.failures")} value={String(audit.failedReplicates)} />
            <Metric label={t("pairedBootstrap.curves")} value={String(audit.curveCount)} />
          </div>
          <p className="mt-3 text-[10px] leading-4 text-muted">
            {t("pairedBootstrap.dependence", { assumption: audit.betweenStrategyAssumption || "—" })}
          </p>
          {audit.resultSha256 && (
            <div className="mt-2 break-all font-mono text-[9px] text-muted">
              {t("pairedBootstrap.hash")} {audit.resultSha256}
            </div>
          )}
        </>
      )}
      {currentReview && (
        <div className={cn(
          "mt-3 rounded-input border p-3 text-[10px] leading-4",
          accepted ? "border-ok/30 bg-ok/5 text-ok" : "border-warning/30 bg-warning/5 text-warning",
        )}>
          {accepted ? t("pairedBootstrap.currentAccepted") : t("pairedBootstrap.currentRejected")}
          <div className="mt-1 break-all font-mono text-[9px] text-muted">
            {currentReview.recordPath} · {currentReview.recordSha256.slice(0, 12)}…
          </div>
        </div>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-warning">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-3">
        {audit?.reviewable && isTauri && (
          <button
            onClick={onReview}
            className="flex items-center gap-1.5 text-xs font-medium text-accent hover:underline"
          >
            <LockKeyhole size={13} /> {t("pairedBootstrap.review")}
          </button>
        )}
        {!accepted && (
          <button
            onClick={onRequestPreparation}
            className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
          >
            <MessageSquareText size={13} /> {t("pairedBootstrap.askAgent")}
          </button>
        )}
      </div>
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("pairedBootstrap.note")}</p>
    </section>
  );
}

const PAIRED_CHECKLIST_KEYS: Array<keyof HeorPairedBootstrapChecklist> = [
  "resamplingDesignReviewed",
  "endpointsAndCensoringReviewed",
  "selectedFamiliesReviewed",
  "failuresAndConvergenceReviewed",
  "followUpAndExtrapolationReviewed",
  "parallelArmAssumptionReviewed",
  "clinicalPlausibilityReviewed",
];

const EMPTY_PAIRED_CHECKLIST: HeorPairedBootstrapChecklist = {
  resamplingDesignReviewed: false,
  endpointsAndCensoringReviewed: false,
  selectedFamiliesReviewed: false,
  failuresAndConvergenceReviewed: false,
  followUpAndExtrapolationReviewed: false,
  parallelArmAssumptionReviewed: false,
  clinicalPlausibilityReviewed: false,
};

export function PairedBootstrapReviewDialog({
  audit,
  running,
  onCancel,
  onSubmit,
}: {
  audit: HeorPairedBootstrapAudit;
  running: boolean;
  onCancel: () => void;
  onSubmit: (
    action: "accept" | "reject",
    checklist: HeorPairedBootstrapChecklist,
    actor: string,
    rationale: string,
  ) => void;
}) {
  const { t } = useTranslation("heor");
  const [action, setAction] = useState<"accept" | "reject">("accept");
  const [checklist, setChecklist] = useState(EMPTY_PAIRED_CHECKLIST);
  const [actor, setActor] = useState("");
  const [rationale, setRationale] = useState("");
  const acceptedReady = PAIRED_CHECKLIST_KEYS.every((key) => checklist[key]);
  const valid = actor.trim().length > 0 && rationale.trim().length > 1
    && (action === "reject" || acceptedReady) && !running;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && !running && onCancel();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel, running]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={() => !running && onCancel()} role="presentation">
      <div role="dialog" aria-modal="true" aria-label={t("pairedBootstrap.dialogTitle")} className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-card border border-border bg-surface p-5 shadow-card" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center gap-2 text-sm font-semibold text-text">
          <ShieldCheck size={17} className="text-accent" /> {t("pairedBootstrap.dialogTitle")}
        </div>
        <p className="mt-2 text-xs leading-5 text-muted">
          {t("pairedBootstrap.dialogBody", {
            id: audit.executionId,
            hash: audit.resultSha256?.slice(0, 12) ?? "—",
          })}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2" role="group" aria-label={t("pairedBootstrap.decisionLabel")}>
          {PAIRED_BOOTSTRAP_REVIEW_ACTIONS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={action === value}
              onClick={() => setAction(value)}
              className={cn(
                "rounded-input border px-3 py-2 text-xs font-medium",
                action === value
                  ? value === "accept" ? "border-ok bg-ok/10 text-ok" : "border-danger bg-danger/10 text-danger"
                  : "border-border text-muted",
              )}
            >
              {t(`pairedBootstrap.${value}`)}
            </button>
          ))}
        </div>
        <div className="mt-3 space-y-2 rounded-input border border-border bg-bg p-3">
          {PAIRED_CHECKLIST_KEYS.map((key) => (
            <label key={key} className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-text">
              <input
                type="checkbox"
                checked={checklist[key]}
                onChange={(event) => setChecklist((current) => ({
                  ...current,
                  [key]: event.target.checked,
                }))}
                className="mt-1 accent-[var(--color-accent)]"
              />
              <span>{t(`pairedBootstrap.checklist.${key}`)}</span>
            </label>
          ))}
        </div>
        <input
          value={actor}
          onChange={(event) => setActor(event.target.value)}
          placeholder={t("dialog.actorPlaceholder")}
          className="mt-3 w-full rounded-input border border-border bg-bg px-3 py-2 text-xs text-text outline-none focus:border-accent"
        />
        <textarea
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          placeholder={action === "accept" ? t("pairedBootstrap.acceptRationale") : t("pairedBootstrap.rejectRationale")}
          rows={3}
          className="mt-2 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-xs leading-5 text-text outline-none focus:border-accent"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button disabled={running} onClick={onCancel} className="rounded-input border border-border px-3 py-2 text-xs text-muted hover:text-text disabled:opacity-50">
            {t("dialog.cancel")}
          </button>
          <button
            disabled={!valid}
            onClick={() => onSubmit(action, checklist, actor.trim(), rationale.trim())}
            className={cn(
              "rounded-input px-3 py-2 text-xs font-semibold text-white disabled:opacity-40",
              action === "accept" ? "bg-ok" : "bg-danger",
            )}
          >
            {running ? t("pairedBootstrap.recording") : action === "accept" ? t("pairedBootstrap.recordAccept") : t("pairedBootstrap.recordReject")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function NetworkMetaAnalysisAssessment({
  state,
  currentReview,
  accepted,
  onRequestPreparation,
  onReview,
}: {
  state: NetworkMetaAnalysisState;
  currentReview: HeorNetworkMetaAnalysisReviewLog["events"][number] | null;
  accepted: boolean;
  onRequestPreparation: () => void;
  onReview: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const issues = audit?.errors ?? (state.kind === "invalid" ? [state.message] : []);
  const status = state.kind === "loading"
    ? t("nma.loading")
    : accepted
      ? t("nma.accepted")
      : currentReview?.action === "reject"
        ? t("nma.rejected")
        : audit?.reviewable
          ? t("nma.awaiting")
          : audit?.executionId
            ? t("nma.incomplete")
            : t("nma.notPrepared");
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {accepted
          ? <ShieldCheck size={16} className="mt-0.5 text-ok" />
          : <AlertTriangle size={16} className="mt-0.5 text-warning" />}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("nma.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", accepted ? "text-ok" : "text-warning")}>
            {status}
          </div>
          <div className="mt-1 break-all font-mono text-[10px] text-muted">
            {audit?.resultPath || HEOR_NETWORK_META_ANALYSIS_REQUEST_PATH}
          </div>
        </div>
      </div>
      {audit?.executionId && (
        <>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <Metric label={t("nma.studies")} value={String(audit.studyCount)} />
            <Metric label={t("nma.treatments")} value={String(audit.treatmentCount)} />
            <Metric label={t("nma.cycles")} value={String(audit.cycleRank)} />
          </div>
          <p className="mt-3 text-[10px] leading-4 text-muted">
            {t("nma.modelSummary", {
              model: audit.modelType || "—",
              tau: audit.tau === null ? "—" : audit.tau.toPrecision(4),
              global: audit.globalInconsistencyStatus || "—",
              local: audit.localInconsistencyCount,
              ranking: audit.rankingMethod || "none",
            })}
          </p>
          {audit.resultSha256 && (
            <div className="mt-2 break-all font-mono text-[9px] text-muted">
              {t("nma.hash")} {audit.resultSha256}
            </div>
          )}
        </>
      )}
      {currentReview && (
        <div className={cn(
          "mt-3 rounded-input border p-3 text-[10px] leading-4",
          accepted ? "border-ok/30 bg-ok/5 text-ok" : "border-warning/30 bg-warning/5 text-warning",
        )}>
          {accepted ? t("nma.currentAccepted") : t("nma.currentRejected")}
          <div className="mt-1 break-all font-mono text-[9px] text-muted">
            {currentReview.recordPath} · {currentReview.recordSha256.slice(0, 12)}…
          </div>
        </div>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-warning">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-3">
        {audit?.reviewable && isTauri && (
          <button onClick={onReview} className="flex items-center gap-1.5 text-xs font-medium text-accent hover:underline">
            <LockKeyhole size={13} /> {t("nma.review")}
          </button>
        )}
        {!accepted && (
          <button onClick={onRequestPreparation} className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
            <MessageSquareText size={13} /> {t("nma.askAgent")}
          </button>
        )}
      </div>
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("nma.note")}</p>
    </section>
  );
}

const NMA_CHECKLIST_KEYS: Array<keyof HeorNetworkMetaAnalysisChecklist> = [
  "questionOutcomeEstimandReviewed",
  "nodesConnectivityTwoArmBoundaryReviewed",
  "studyContrastsProvenanceRiskOfBiasReviewed",
  "transitivityEffectModifiersReviewed",
  "modelTauMethodReviewed",
  "heterogeneityPredictionReviewed",
  "globalLocalInconsistencyReviewed",
  "rankingTransportabilityLimitationsReviewed",
];

const EMPTY_NMA_CHECKLIST: HeorNetworkMetaAnalysisChecklist = {
  questionOutcomeEstimandReviewed: false,
  nodesConnectivityTwoArmBoundaryReviewed: false,
  studyContrastsProvenanceRiskOfBiasReviewed: false,
  transitivityEffectModifiersReviewed: false,
  modelTauMethodReviewed: false,
  heterogeneityPredictionReviewed: false,
  globalLocalInconsistencyReviewed: false,
  rankingTransportabilityLimitationsReviewed: false,
};

export function NetworkMetaAnalysisReviewDialog({
  audit,
  running,
  onCancel,
  onSubmit,
}: {
  audit: HeorNetworkMetaAnalysisAudit;
  running: boolean;
  onCancel: () => void;
  onSubmit: (
    action: "accept" | "reject",
    checklist: HeorNetworkMetaAnalysisChecklist,
    actor: string,
    rationale: string,
  ) => void;
}) {
  const { t } = useTranslation("heor");
  const [action, setAction] = useState<"accept" | "reject">("accept");
  const [checklist, setChecklist] = useState(EMPTY_NMA_CHECKLIST);
  const [actor, setActor] = useState("");
  const [rationale, setRationale] = useState("");
  const acceptedReady = NMA_CHECKLIST_KEYS.every((key) => checklist[key]);
  const valid = actor.trim().length > 0 && rationale.trim().length > 1
    && (action === "reject" || acceptedReady) && !running;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && !running && onCancel();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel, running]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={() => !running && onCancel()} role="presentation">
      <div role="dialog" aria-modal="true" aria-label={t("nma.dialogTitle")} className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-card border border-border bg-surface p-5 shadow-card" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center gap-2 text-sm font-semibold text-text">
          <ShieldCheck size={17} className="text-accent" /> {t("nma.dialogTitle")}
        </div>
        <p className="mt-2 text-xs leading-5 text-muted">
          {t("nma.dialogBody", {
            id: audit.executionId,
            hash: audit.resultSha256?.slice(0, 12) ?? "—",
          })}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2" role="group" aria-label={t("nma.decisionLabel")}>
          {NMA_REVIEW_ACTIONS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={action === value}
              onClick={() => setAction(value)}
              className={cn(
                "rounded-input border px-3 py-2 text-xs font-medium",
                action === value
                  ? value === "accept" ? "border-ok bg-ok/10 text-ok" : "border-danger bg-danger/10 text-danger"
                  : "border-border text-muted",
              )}
            >
              {t(`nma.${value}`)}
            </button>
          ))}
        </div>
        <div className="mt-3 space-y-2 rounded-input border border-border bg-bg p-3">
          {NMA_CHECKLIST_KEYS.map((key) => (
            <label key={key} className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-text">
              <input
                type="checkbox"
                checked={checklist[key]}
                onChange={(event) => setChecklist((current) => ({ ...current, [key]: event.target.checked }))}
                className="mt-1 accent-[var(--color-accent)]"
              />
              <span>{t(`nma.checklist.${key}`)}</span>
            </label>
          ))}
        </div>
        <input
          value={actor}
          onChange={(event) => setActor(event.target.value)}
          placeholder={t("dialog.actorPlaceholder")}
          className="mt-3 w-full rounded-input border border-border bg-bg px-3 py-2 text-xs text-text outline-none focus:border-accent"
        />
        <textarea
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          placeholder={action === "accept" ? t("nma.acceptRationale") : t("nma.rejectRationale")}
          rows={3}
          className="mt-2 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-xs leading-5 text-text outline-none focus:border-accent"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button disabled={running} onClick={onCancel} className="rounded-input border border-border px-3 py-2 text-xs text-muted hover:text-text disabled:opacity-50">
            {t("dialog.cancel")}
          </button>
          <button
            disabled={!valid}
            onClick={() => onSubmit(action, checklist, actor.trim(), rationale.trim())}
            className={cn(
              "rounded-input px-3 py-2 text-xs font-semibold text-white disabled:opacity-40",
              action === "accept" ? "bg-ok" : "bg-danger",
            )}
          >
            {running ? t("nma.recording") : action === "accept" ? t("nma.recordAccept") : t("nma.recordReject")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function PopulationAdjustedComparisonAssessment({
  state,
  currentReview,
  accepted,
  onRequestPreparation,
  onReview,
}: {
  state: PopulationAdjustedComparisonState;
  currentReview: HeorPopulationAdjustedComparisonReviewLog["events"][number] | null;
  accepted: boolean;
  onRequestPreparation: () => void;
  onReview: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const issues = audit?.errors ?? (state.kind === "invalid" ? [state.message] : []);
  const status = state.kind === "loading"
    ? t("pac.loading")
    : accepted
      ? t("pac.accepted")
      : currentReview?.action === "reject"
        ? t("pac.rejected")
        : audit?.reviewable
          ? t("pac.awaiting")
          : audit?.executionId
            ? t("pac.incomplete")
            : t("pac.notPrepared");
  const format = (value: number | null, digits = 4) =>
    value === null ? "—" : value.toPrecision(digits);
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {accepted
          ? <ShieldCheck size={16} className="mt-0.5 text-ok" />
          : <AlertTriangle size={16} className="mt-0.5 text-warning" />}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("pac.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", accepted ? "text-ok" : "text-warning")}>
            {status}
          </div>
          <div className="mt-1 break-all font-mono text-[10px] text-muted">
            {audit?.resultPath || HEOR_POPULATION_ADJUSTED_COMPARISON_REQUEST_PATH}
          </div>
        </div>
      </div>
      {audit?.executionId && (
        <>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <Metric label={t("pac.rows")} value={String(audit.rowCount)} />
            <Metric label={t("pac.modifiers")} value={String(audit.modifierCount)} />
            <Metric label={t("pac.essRatio")} value={format(audit.essRatio, 3)} />
          </div>
          <p className="mt-3 text-[10px] leading-4 text-muted">
            {t("pac.calibrationSummary", {
              measure: audit.effectMeasure || "—",
              ess: format(audit.essOverall),
              maxWeight: format(audit.maximumWeight),
              balance: format(audit.maxAbsBalanceError, 3),
            })}
          </p>
          <p className="mt-1 text-[10px] leading-4 text-muted">
            {t("pac.effectSummary", {
              unadjusted: format(audit.unadjustedEstimate),
              adjusted: format(audit.adjustedEstimate),
              indirect: format(audit.indirectEstimate),
              se: format(audit.indirectSe),
            })}
          </p>
          <p className="mt-1 text-[10px] leading-4 text-muted">
            {t("pac.bootstrapSummary", {
              iterations: audit.bootstrapIterations,
              failures: audit.bootstrapFailures,
            })}
          </p>
          {audit.resultSha256 && (
            <div className="mt-2 break-all font-mono text-[9px] text-muted">
              {t("pac.hash")} {audit.resultSha256}
            </div>
          )}
        </>
      )}
      {currentReview && (
        <div className={cn(
          "mt-3 rounded-input border p-3 text-[10px] leading-4",
          accepted ? "border-ok/30 bg-ok/5 text-ok" : "border-warning/30 bg-warning/5 text-warning",
        )}>
          {accepted ? t("pac.currentAccepted") : t("pac.currentRejected")}
          <div className="mt-1 break-all font-mono text-[9px] text-muted">
            {currentReview.recordPath} · {currentReview.recordSha256.slice(0, 12)}…
          </div>
        </div>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-warning">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-3">
        {audit?.reviewable && isTauri && (
          <button onClick={onReview} className="flex items-center gap-1.5 text-xs font-medium text-accent hover:underline">
            <LockKeyhole size={13} /> {t("pac.review")}
          </button>
        )}
        {!accepted && (
          <button onClick={onRequestPreparation} className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
            <MessageSquareText size={13} /> {t("pac.askAgent")}
          </button>
        )}
      </div>
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("pac.note")}</p>
    </section>
  );
}

const PAC_CHECKLIST_KEYS: Array<keyof HeorPopulationAdjustedComparisonChecklist> = [
  "questionEstimandTargetCommonComparatorReviewed",
  "randomizedConnectedEvidenceProvenanceReviewed",
  "effectModifierRationaleCompletenessReviewed",
  "ipdIntegrityPrivacyMissingnessReviewed",
  "targetMomentsOverlapReviewed",
  "calibrationBalanceWeightsEssReviewed",
  "bootstrapPrecisionFailuresReviewed",
  "residualBiasTransportabilityDownstreamReviewed",
];

const EMPTY_PAC_CHECKLIST: HeorPopulationAdjustedComparisonChecklist = {
  questionEstimandTargetCommonComparatorReviewed: false,
  randomizedConnectedEvidenceProvenanceReviewed: false,
  effectModifierRationaleCompletenessReviewed: false,
  ipdIntegrityPrivacyMissingnessReviewed: false,
  targetMomentsOverlapReviewed: false,
  calibrationBalanceWeightsEssReviewed: false,
  bootstrapPrecisionFailuresReviewed: false,
  residualBiasTransportabilityDownstreamReviewed: false,
};

export function PopulationAdjustedComparisonReviewDialog({
  audit,
  running,
  onCancel,
  onSubmit,
}: {
  audit: HeorPopulationAdjustedComparisonAudit;
  running: boolean;
  onCancel: () => void;
  onSubmit: (
    action: "accept" | "reject",
    checklist: HeorPopulationAdjustedComparisonChecklist,
    actor: string,
    rationale: string,
  ) => void;
}) {
  const { t } = useTranslation("heor");
  const [action, setAction] = useState<"accept" | "reject">("accept");
  const [checklist, setChecklist] = useState(EMPTY_PAC_CHECKLIST);
  const [actor, setActor] = useState("");
  const [rationale, setRationale] = useState("");
  const acceptedReady = PAC_CHECKLIST_KEYS.every((key) => checklist[key]);
  const valid = actor.trim().length > 0 && rationale.trim().length > 1
    && (action === "reject" || acceptedReady) && !running;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && !running && onCancel();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel, running]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={() => !running && onCancel()} role="presentation">
      <div role="dialog" aria-modal="true" aria-label={t("pac.dialogTitle")} className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-card border border-border bg-surface p-5 shadow-card" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center gap-2 text-sm font-semibold text-text">
          <ShieldCheck size={17} className="text-accent" /> {t("pac.dialogTitle")}
        </div>
        <p className="mt-2 text-xs leading-5 text-muted">
          {t("pac.dialogBody", {
            id: audit.executionId,
            hash: audit.resultSha256?.slice(0, 12) ?? "—",
          })}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2" role="group" aria-label={t("pac.decisionLabel")}>
          {NMA_REVIEW_ACTIONS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={action === value}
              onClick={() => setAction(value)}
              className={cn(
                "rounded-input border px-3 py-2 text-xs font-medium",
                action === value
                  ? value === "accept" ? "border-ok bg-ok/10 text-ok" : "border-danger bg-danger/10 text-danger"
                  : "border-border text-muted",
              )}
            >
              {t(`pac.${value}`)}
            </button>
          ))}
        </div>
        <div className="mt-3 space-y-2 rounded-input border border-border bg-bg p-3">
          {PAC_CHECKLIST_KEYS.map((key) => (
            <label key={key} className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-text">
              <input
                type="checkbox"
                checked={checklist[key]}
                onChange={(event) => setChecklist((current) => ({ ...current, [key]: event.target.checked }))}
                className="mt-1 accent-[var(--color-accent)]"
              />
              <span>{t(`pac.checklist.${key}`)}</span>
            </label>
          ))}
        </div>
        <input
          value={actor}
          onChange={(event) => setActor(event.target.value)}
          placeholder={t("dialog.actorPlaceholder")}
          className="mt-3 w-full rounded-input border border-border bg-bg px-3 py-2 text-xs text-text outline-none focus:border-accent"
        />
        <textarea
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          placeholder={action === "accept" ? t("pac.acceptRationale") : t("pac.rejectRationale")}
          rows={3}
          className="mt-2 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-xs leading-5 text-text outline-none focus:border-accent"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button disabled={running} onClick={onCancel} className="rounded-input border border-border px-3 py-2 text-xs text-muted hover:text-text disabled:opacity-50">
            {t("dialog.cancel")}
          </button>
          <button
            disabled={!valid}
            onClick={() => onSubmit(action, checklist, actor.trim(), rationale.trim())}
            className={cn(
              "rounded-input px-3 py-2 text-xs font-semibold text-white disabled:opacity-40",
              action === "accept" ? "bg-ok" : "bg-danger",
            )}
          >
            {running ? t("pac.recording") : action === "accept" ? t("pac.recordAccept") : t("pac.recordReject")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function RweCausalAnalysisAssessment({
  state,
  currentReview,
  accepted,
  onRequestPreparation,
  onReview,
}: {
  state: RweCausalAnalysisState;
  currentReview: HeorRweCausalAnalysisReviewLog["events"][number] | null;
  accepted: boolean;
  onRequestPreparation: () => void;
  onReview: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const issues = audit?.errors ?? (state.kind === "invalid" ? [state.message] : []);
  const status = state.kind === "loading"
    ? t("rweCausal.loading")
    : accepted
      ? t("rweCausal.accepted")
      : currentReview?.action === "reject"
        ? t("rweCausal.rejected")
        : audit?.reviewable
          ? t("rweCausal.awaiting")
          : audit?.executionId
            ? t("rweCausal.incomplete")
            : t("rweCausal.notPrepared");
  const format = (value: number | null, digits = 4) =>
    value === null ? "—" : value.toPrecision(digits);
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {accepted
          ? <ShieldCheck size={16} className="mt-0.5 text-ok" />
          : <AlertTriangle size={16} className="mt-0.5 text-warning" />}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("rweCausal.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", accepted ? "text-ok" : "text-warning")}>
            {status}
          </div>
          <div className="mt-1 break-all font-mono text-[10px] text-muted">
            {audit?.resultPath || HEOR_RWE_CAUSAL_ANALYSIS_REQUEST_PATH}
          </div>
        </div>
      </div>
      {audit?.executionId && (
        <>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <Metric label={t("rweCausal.rows")} value={String(audit.rowCount)} />
            <Metric label={t("rweCausal.confounders")} value={String(audit.confounderCount)} />
            <Metric label={t("rweCausal.essRatio")} value={format(audit.essRatio, 3)} />
          </div>
          <p className="mt-3 text-[10px] leading-4 text-muted">
            {t("rweCausal.diagnosticSummary", {
              ess: format(audit.essOverall),
              maxWeight: format(audit.maximumWeight),
              pre: format(audit.maxAbsPreSmd, 3),
              post: format(audit.maxAbsPostSmd, 3),
            })}
          </p>
          <p className="mt-1 text-[10px] leading-4 text-muted">
            {t("rweCausal.effectSummary", {
              unadjusted: format(audit.unadjustedRiskDifference),
              weighted: format(audit.weightedRiskDifference),
              se: format(audit.weightedStandardError),
              lower: format(audit.weightedLower),
              upper: format(audit.weightedUpper),
            })}
          </p>
          <p className="mt-1 text-[10px] leading-4 text-muted">
            {t("rweCausal.overlapSummary", {
              lower: format(audit.overlapLower, 3),
              upper: format(audit.overlapUpper, 3),
              iterations: audit.bootstrapIterations,
              failures: audit.bootstrapFailures,
            })}
          </p>
          {audit.resultSha256 && (
            <div className="mt-2 break-all font-mono text-[9px] text-muted">
              {t("rweCausal.hash")} {audit.resultSha256}
            </div>
          )}
        </>
      )}
      {currentReview && (
        <div className={cn(
          "mt-3 rounded-input border p-3 text-[10px] leading-4",
          accepted ? "border-ok/30 bg-ok/5 text-ok" : "border-warning/30 bg-warning/5 text-warning",
        )}>
          {accepted ? t("rweCausal.currentAccepted") : t("rweCausal.currentRejected")}
          <div className="mt-1 break-all font-mono text-[9px] text-muted">
            {currentReview.recordPath} · {currentReview.recordSha256.slice(0, 12)}…
          </div>
        </div>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-warning">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-3">
        {audit?.reviewable && isTauri && (
          <button onClick={onReview} className="flex items-center gap-1.5 text-xs font-medium text-accent hover:underline">
            <LockKeyhole size={13} /> {t("rweCausal.review")}
          </button>
        )}
        {!accepted && (
          <button onClick={onRequestPreparation} className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
            <MessageSquareText size={13} /> {t("rweCausal.askAgent")}
          </button>
        )}
      </div>
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("rweCausal.note")}</p>
    </section>
  );
}

const RWE_CAUSAL_CHECKLIST_KEYS: Array<keyof HeorRweCausalAnalysisChecklist> = [
  "targetTrialEstimandTimeZeroReviewed",
  "dataProvenanceEligibilityNewUserActiveComparatorReviewed",
  "confounderCausalRationaleMeasurementReviewed",
  "missingnessFollowUpOutcomeIntegrityReviewed",
  "propensityOverlapWeightsPositivityReviewed",
  "balanceModelDiagnosticsReviewed",
  "bootstrapPrecisionFailuresReviewed",
  "residualBiasTransportabilityDownstreamReviewed",
];

const EMPTY_RWE_CAUSAL_CHECKLIST: HeorRweCausalAnalysisChecklist = {
  targetTrialEstimandTimeZeroReviewed: false,
  dataProvenanceEligibilityNewUserActiveComparatorReviewed: false,
  confounderCausalRationaleMeasurementReviewed: false,
  missingnessFollowUpOutcomeIntegrityReviewed: false,
  propensityOverlapWeightsPositivityReviewed: false,
  balanceModelDiagnosticsReviewed: false,
  bootstrapPrecisionFailuresReviewed: false,
  residualBiasTransportabilityDownstreamReviewed: false,
};

export function RweCausalAnalysisReviewDialog({
  audit,
  running,
  onCancel,
  onSubmit,
}: {
  audit: HeorRweCausalAnalysisAudit;
  running: boolean;
  onCancel: () => void;
  onSubmit: (
    action: "accept" | "reject",
    checklist: HeorRweCausalAnalysisChecklist,
    actor: string,
    rationale: string,
  ) => void;
}) {
  const { t } = useTranslation("heor");
  const [action, setAction] = useState<"accept" | "reject">("accept");
  const [checklist, setChecklist] = useState(EMPTY_RWE_CAUSAL_CHECKLIST);
  const [actor, setActor] = useState("");
  const [rationale, setRationale] = useState("");
  const acceptedReady = RWE_CAUSAL_CHECKLIST_KEYS.every((key) => checklist[key]);
  const valid = actor.trim().length > 0 && rationale.trim().length > 1
    && (action === "reject" || acceptedReady) && !running;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && !running && onCancel();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel, running]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={() => !running && onCancel()} role="presentation">
      <div role="dialog" aria-modal="true" aria-label={t("rweCausal.dialogTitle")} className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-card border border-border bg-surface p-5 shadow-card" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center gap-2 text-sm font-semibold text-text">
          <ShieldCheck size={17} className="text-accent" /> {t("rweCausal.dialogTitle")}
        </div>
        <p className="mt-2 text-xs leading-5 text-muted">
          {t("rweCausal.dialogBody", {
            id: audit.executionId,
            hash: audit.resultSha256?.slice(0, 12) ?? "—",
          })}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2" role="group" aria-label={t("rweCausal.decisionLabel")}>
          {NMA_REVIEW_ACTIONS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={action === value}
              onClick={() => setAction(value)}
              className={cn(
                "rounded-input border px-3 py-2 text-xs font-medium",
                action === value
                  ? value === "accept" ? "border-ok bg-ok/10 text-ok" : "border-danger bg-danger/10 text-danger"
                  : "border-border text-muted",
              )}
            >
              {t(`rweCausal.${value}`)}
            </button>
          ))}
        </div>
        <div className="mt-3 space-y-2 rounded-input border border-border bg-bg p-3">
          {RWE_CAUSAL_CHECKLIST_KEYS.map((key) => (
            <label key={key} className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-text">
              <input
                type="checkbox"
                checked={checklist[key]}
                onChange={(event) => setChecklist((current) => ({ ...current, [key]: event.target.checked }))}
                className="mt-1 accent-[var(--color-accent)]"
              />
              <span>{t(`rweCausal.checklist.${key}`)}</span>
            </label>
          ))}
        </div>
        <input
          value={actor}
          onChange={(event) => setActor(event.target.value)}
          placeholder={t("dialog.actorPlaceholder")}
          className="mt-3 w-full rounded-input border border-border bg-bg px-3 py-2 text-xs text-text outline-none focus:border-accent"
        />
        <textarea
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          placeholder={action === "accept" ? t("rweCausal.acceptRationale") : t("rweCausal.rejectRationale")}
          rows={3}
          className="mt-2 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-xs leading-5 text-text outline-none focus:border-accent"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button disabled={running} onClick={onCancel} className="rounded-input border border-border px-3 py-2 text-xs text-muted hover:text-text disabled:opacity-50">
            {t("dialog.cancel")}
          </button>
          <button
            disabled={!valid}
            onClick={() => onSubmit(action, checklist, actor.trim(), rationale.trim())}
            className={cn(
              "rounded-input px-3 py-2 text-xs font-semibold text-white disabled:opacity-40",
              action === "accept" ? "bg-ok" : "bg-danger",
            )}
          >
            {running ? t("rweCausal.recording") : action === "accept" ? t("rweCausal.recordAccept") : t("rweCausal.recordReject")}
          </button>
        </div>
      </div>
    </div>
  );
}

function ReferenceCaseAssessment({
  state,
  onRequestRepair,
}: {
  state: ReferenceCaseState;
  onRequestRepair: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const complete = audit?.complete === true;
  const resolvedRequired = audit
    ? audit.metRequiredCount + audit.notApplicableRequiredCount
    : 0;
  const issues = audit
    ? [
        ...audit.blockingGaps.map((id) => t("reference.requiredGap", { id })),
        ...audit.unresolvedRequirements.map((id) => t("reference.unresolved", { id })),
        ...audit.errors,
      ]
    : state.kind === "invalid" ? [state.message] : [];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {complete ? (
          <ShieldCheck size={16} className="mt-0.5 text-ok" />
        ) : (
          <AlertTriangle size={16} className="mt-0.5 text-warning" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("reference.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", complete ? "text-ok" : "text-warning")}>
            {state.kind === "loading"
              ? t("reference.loading")
              : complete ? t("reference.complete") : t("reference.incomplete")}
          </div>
          {audit && (
            <div className="mt-1 text-[10px] text-muted">
              {audit.profileId} · {audit.profileRevision} · {audit.profileStatus}
            </div>
          )}
        </div>
        {audit && (
          <span className="rounded-full border border-border bg-bg px-2 py-0.5 font-mono text-[10px] text-text">
            {resolvedRequired}/{audit.requiredCount}
          </span>
        )}
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">
        {HEOR_REFERENCE_CASE_ASSESSMENT_PATH}
      </div>
      {audit && (
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Metric label={t("reference.required")} value={`${resolvedRequired}/${audit.requiredCount}`} />
          <Metric label={t("reference.blocking")} value={String(audit.blockingGaps.length)} />
          <Metric label={t("reference.recommended")} value={String(audit.recommendedGaps.length)} />
        </div>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      {!complete && state.kind !== "loading" && (
        <button
          onClick={onRequestRepair}
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
        >
          <MessageSquareText size={13} /> {t("reference.askRepair")}
        </button>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("reference.note")}</p>
    </section>
  );
}

function UncertaintyAssessment({
  state,
  onRequestRepair,
}: {
  state: UncertaintyState;
  onRequestRepair: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const complete = audit?.complete === true;
  const issues = audit
    ? [...audit.invalidParameters, ...audit.errors]
    : state.kind === "invalid" ? [state.message] : [];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {complete ? (
          <ShieldCheck size={16} className="mt-0.5 text-ok" />
        ) : (
          <AlertTriangle size={16} className="mt-0.5 text-warning" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("uncertainty.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", complete ? "text-ok" : "text-warning")}>
            {state.kind === "loading"
              ? t("uncertainty.loading")
              : complete ? t("uncertainty.complete") : t("uncertainty.incomplete")}
          </div>
          {audit?.seed && (
            <div className="mt-1 text-[10px] text-muted">
              {t("uncertainty.prng")} · {t("uncertainty.seed")} {audit.seed}
            </div>
          )}
        </div>
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">{HEOR_UNCERTAINTY_PLAN_PATH}</div>
      {audit && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-center">
          <Metric label={t("uncertainty.parameters")} value={String(audit.parameterCount)} />
          <Metric label={t("uncertainty.correlations")} value={String(audit.correlationGroupCount)} />
          <Metric label={t("uncertainty.iterations")} value={audit.iterations?.toLocaleString() ?? "—"} />
          <Metric label={t("uncertainty.thresholds")} value={String(audit.thresholdCount)} />
          <Metric label={t("uncertainty.scenarios")} value={String(audit.scenarioCount)} />
        </div>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      {!complete && state.kind !== "loading" && (
        <button
          onClick={onRequestRepair}
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
        >
          <MessageSquareText size={13} /> {t("uncertainty.askRepair")}
        </button>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("uncertainty.note")}</p>
    </section>
  );
}

function AdvancedVoiAssessment({
  state,
  accepted,
  reviewAction,
  onRequestPreparation,
  onReview,
}: {
  state: AdvancedVoiState;
  accepted: boolean;
  reviewAction: "accept" | "reject" | null;
  onRequestPreparation: () => void;
  onReview: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const complete = audit?.complete === true;
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {complete ? <ShieldCheck size={16} className="mt-0.5 text-ok" />
          : <AlertTriangle size={16} className="mt-0.5 text-warning" />}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("advancedVoi.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", complete ? "text-ok" : "text-warning")}>
            {state.kind === "loading" ? t("advancedVoi.loading")
              : complete ? t("advancedVoi.complete") : t("advancedVoi.incomplete")}
          </div>
          {audit?.reviewable && (
            <div className={cn("mt-1 text-[10px]", accepted ? "text-ok" : "text-muted")}>
              {accepted ? t("advancedVoi.accepted")
                : reviewAction === "reject" ? t("advancedVoi.rejected")
                  : t("advancedVoi.awaitingReview")}
            </div>
          )}
        </div>
      </div>
      {audit && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-center">
          <Metric label={t("advancedVoi.populationYears")} value={String(audit.populationYearCount)} />
          <Metric label={t("advancedVoi.effectivePopulation")} value={audit.effectivePopulation?.toLocaleString() ?? "—"} />
          <Metric label={t("advancedVoi.evppiGroups")} value={String(audit.evppiGroupCount)} />
          <Metric label={t("advancedVoi.evsiDesigns")} value={String(audit.evsiDesignCount)} />
        </div>
      )}
      {audit?.errors.length ? (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
          {audit.errors.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      ) : null}
      {!complete && state.kind !== "loading" && (
        <button onClick={onRequestPreparation} className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
          <MessageSquareText size={13} /> {t("advancedVoi.askPrepare")}
        </button>
      )}
      {audit?.reviewable && (
        <button onClick={onReview} className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
          <ShieldCheck size={13} /> {t("advancedVoi.review")}
        </button>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("advancedVoi.note")}</p>
    </section>
  );
}

function BudgetImpactAssessment({
  state,
  onRequestRepair,
}: {
  state: BudgetImpactState;
  onRequestRepair: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const complete = audit?.complete === true;
  const issues = audit
    ? [...audit.invalidInputs, ...audit.errors]
    : state.kind === "invalid" ? [state.message] : [];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {complete ? (
          <ShieldCheck size={16} className="mt-0.5 text-ok" />
        ) : (
          <AlertTriangle size={16} className="mt-0.5 text-warning" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("budgetImpact.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", complete ? "text-ok" : "text-warning")}>
            {state.kind === "loading"
              ? t("budgetImpact.loading")
              : complete ? t("budgetImpact.complete") : t("budgetImpact.incomplete")}
          </div>
          {audit?.horizonYears && (
            <div className="mt-1 text-[10px] text-muted">
              {t("budgetImpact.horizon", { count: audit.horizonYears })} · {t("budgetImpact.noDiscount")}
            </div>
          )}
        </div>
        {audit && (
          <span className="rounded-full border border-border bg-bg px-2 py-0.5 font-mono text-[10px] text-text">
            {audit.coveredInputCount}/{audit.requiredInputCount}
          </span>
        )}
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">{HEOR_BUDGET_IMPACT_PLAN_PATH}</div>
      {audit && (
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Metric label={t("budgetImpact.costs")} value={String(audit.costCategoryCount)} />
          <Metric label={t("budgetImpact.sensitivity")} value={String(audit.sensitivityParameterCount)} />
          <Metric label={t("budgetImpact.scenarios")} value={String(audit.scenarioCount)} />
        </div>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      {!complete && state.kind !== "loading" && (
        <button
          onClick={onRequestRepair}
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
        >
          <MessageSquareText size={13} /> {t("budgetImpact.askRepair")}
        </button>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("budgetImpact.note")}</p>
    </section>
  );
}

function PartitionedSurvivalAssessment({
  state,
  onRequestRepair,
}: {
  state: PartitionedSurvivalState;
  onRequestRepair: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const complete = audit?.complete === true;
  const issues = audit?.errors ?? (state.kind === "invalid" ? [state.message] : []);
  const status = state.kind === "loading"
    ? t("partitionedSurvival.loading")
    : audit?.required === false
      ? t("partitionedSurvival.notRequired")
      : complete
        ? t("partitionedSurvival.complete")
        : t("partitionedSurvival.incomplete");
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {complete ? (
          <ShieldCheck size={16} className="mt-0.5 text-ok" />
        ) : (
          <AlertTriangle size={16} className="mt-0.5 text-warning" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("partitionedSurvival.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", complete ? "text-ok" : "text-warning")}>
            {status}
          </div>
        </div>
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">{HEOR_PARTITIONED_SURVIVAL_PLAN_PATH}</div>
      {audit && audit.required && (
        <div className="mt-3 grid grid-cols-5 gap-2 text-center">
          <Metric label={t("partitionedSurvival.strategies")} value={String(audit.strategyCount)} />
          <Metric label={t("partitionedSurvival.curves")} value={String(audit.curveCount)} />
          <Metric label={t("partitionedSurvival.points")} value={String(audit.timePointCount)} />
          <Metric label={t("partitionedSurvival.durationScenarios")} value={String(audit.treatmentEffectDurationScenarioCount ?? 0)} />
          <Metric label={t("partitionedSurvival.costItems")} value={String(audit.costInputNormalizationItemCount ?? 0)} />
          <Metric label={t("partitionedSurvival.utilityItems")} value={String(audit.utilityInputsItemCount ?? 0)} />
          <Metric label={t("partitionedSurvival.mappedUtilities")} value={String(audit.utilityInputsMappedItemCount ?? 0)} />
          <Metric label={t("partitionedSurvival.adjustedUtilities")} value={String(audit.utilityInputsAdjustedItemCount ?? 0)} />
          <Metric label={t("partitionedSurvival.eventDisutilities")} value={String(audit.eventDisutilitiesItemCount ?? 0)} />
        </div>
      )}
      {audit?.treatmentEffectDurationBaseCaseId && (
        <p className="mt-2 text-[10px] leading-4 text-muted">
          {t("partitionedSurvival.baseDuration")}: <span className="font-mono text-text">{audit.treatmentEffectDurationBaseCaseId}</span>
        </p>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      {(!complete || audit?.required === false) && state.kind !== "loading" && (
        <button
          onClick={onRequestRepair}
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
        >
          <MessageSquareText size={13} /> {t("partitionedSurvival.askAgent")}
        </button>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("partitionedSurvival.note")}</p>
      {audit?.required && (
        <p className="mt-1 text-[10px] leading-4 text-warning">{t("partitionedSurvival.releaseBoundary")}</p>
      )}
    </section>
  );
}

function ModelValidationAssessment({
  state,
  onRequestPreparation,
}: {
  state: ModelValidationState;
  onRequestPreparation: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const approvable = audit?.complete === true && audit.approvable;
  const issues = audit
    ? [...new Set([...audit.missingCoverage, ...audit.invalidEvidence, ...audit.errors])]
    : state.kind === "invalid" ? [state.message] : [];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {approvable ? (
          <ShieldCheck size={16} className="mt-0.5 text-ok" />
        ) : (
          <AlertTriangle size={16} className="mt-0.5 text-warning" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("validation.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", approvable ? "text-ok" : "text-warning")}>
            {state.kind === "loading"
              ? t("validation.loading")
              : approvable
                ? t("validation.approvable")
                : audit?.complete
                  ? t("validation.notApprovable")
                  : t("validation.incomplete")}
          </div>
          {audit?.reviewerLabel && (
            <div className="mt-1 text-[10px] text-muted">
              {t("validation.reviewer")}: {audit.reviewerLabel} · {t(`validation.${audit.recommendation}`)}
            </div>
          )}
        </div>
        {audit && (
          <span className="rounded-full border border-border bg-bg px-2 py-0.5 font-mono text-[10px] text-text">
            {audit.coveredRequirementCount}/{audit.requiredCoverageCount}
          </span>
        )}
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">{HEOR_MODEL_VALIDATION_PATH}</div>
      {audit && (
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Metric
            label={t("validation.coverage")}
            value={`${audit.coveredRequirementCount}/${audit.requiredCoverageCount}`}
          />
          <Metric label={t("validation.evidence")} value={String(audit.evidenceCount)} />
          <Metric
            label={t("validation.openIssues")}
            value={String(audit.openBlockingIssueCount + audit.openMinorIssueCount)}
          />
        </div>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      {!approvable && state.kind !== "loading" && (
        <button
          onClick={onRequestPreparation}
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
        >
          <MessageSquareText size={13} /> {t("validation.askPrepare")}
        </button>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("validation.note")}</p>
    </section>
  );
}

function ReportingAssessment({
  state,
  onRequestPreparation,
}: {
  state: ReportingState;
  onRequestPreparation: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const releasable = audit?.releasable === true;
  const issues = audit
    ? [...new Set([...audit.missingItems, ...audit.invalidItems, ...audit.errors])]
    : state.kind === "invalid" ? [state.message] : [];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {releasable ? (
          <ShieldCheck size={16} className="mt-0.5 text-ok" />
        ) : (
          <AlertTriangle size={16} className="mt-0.5 text-warning" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("reporting.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", releasable ? "text-ok" : "text-warning")}>
            {state.kind === "loading"
              ? t("reporting.loading")
              : releasable
                ? t("reporting.releasable")
                : t("reporting.incomplete")}
          </div>
          {audit?.releaseOwnerLabel && (
            <div className="mt-1 text-[10px] text-muted">
              {t("reporting.owner")}: {audit.releaseOwnerLabel}
            </div>
          )}
        </div>
        {audit && (
          <span className="rounded-full border border-border bg-bg px-2 py-0.5 font-mono text-[10px] text-text">
            {audit.coveredItemCount}/{audit.requiredItemCount}
          </span>
        )}
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">{HEOR_REPORT_PACKAGE_PATH}</div>
      {audit && (
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Metric
            label={t("reporting.coverage")}
            value={`${audit.coveredItemCount}/${audit.requiredItemCount}`}
          />
          <Metric
            label={t("reporting.bindings")}
            value={String(Object.keys(audit.bindingHashes).length)}
          />
          <Metric label={t("reporting.errors")} value={String(audit.errors.length)} />
        </div>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      {!releasable && state.kind !== "loading" && (
        <button
          onClick={onRequestPreparation}
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
        >
          <MessageSquareText size={13} /> {t("reporting.askPrepare")}
        </button>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("reporting.note")}</p>
    </section>
  );
}

function ReproducibilityAssessment({
  state,
  onRequestPreparation,
}: {
  state: ReproducibilityState;
  onRequestPreparation: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const ready = audit?.releaseCompanionReady === true;
  const issues = audit ? [...new Set(audit.errors)] : state.kind === "invalid" ? [state.message] : [];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {ready ? (
          <ShieldCheck size={16} className="mt-0.5 text-ok" />
        ) : (
          <AlertTriangle size={16} className="mt-0.5 text-warning" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("reproducibility.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", ready ? "text-ok" : "text-warning")}>
            {state.kind === "loading"
              ? t("reproducibility.loading")
              : ready
                ? t("reproducibility.ready")
                : t("reproducibility.incomplete")}
          </div>
        </div>
        {audit && (
          <span className="rounded-full border border-border bg-bg px-2 py-0.5 font-mono text-[10px] text-text">
            {audit.coveredClaimCount}/{audit.requiredClaimCount}
          </span>
        )}
      </div>
      <div className="mt-1 font-mono text-[10px] text-muted">
        {HEOR_REPRODUCIBILITY_PACKAGE_PATH}
      </div>
      {audit && (
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Metric label={t("reproducibility.artifacts")} value={String(audit.artifactCount)} />
          <Metric label={t("reproducibility.executions")} value={String(audit.executionCount)} />
          <Metric
            label={t("reproducibility.claims")}
            value={`${audit.coveredClaimCount}/${audit.requiredClaimCount}`}
          />
          <Metric label={t("reproducibility.sources")} value={String(audit.sourceCount)} />
          <Metric
            label={t("reproducibility.runtime")}
            value={audit.runtimeMatches
              ? t("reproducibility.runtimeMatch")
              : t("reproducibility.runtimeMismatch")}
          />
          <Metric label={t("reproducibility.errors")} value={String(audit.errors.length)} />
        </div>
      )}
      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}
      {!ready && state.kind !== "loading" && (
        <button
          onClick={onRequestPreparation}
          className="mt-3 flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
        >
          <MessageSquareText size={13} /> {t("reproducibility.askPrepare")}
        </button>
      )}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("reproducibility.note")}</p>
    </section>
  );
}

function ApprovalDialog({
  intent,
  artifactHash,
  onCancel,
  onSubmit,
}: {
  intent: ReviewIntent;
  artifactHash: string;
  onCancel: () => void;
  onSubmit: (actor: string, rationale: string) => void;
}) {
  const { t } = useTranslation("heor");
  const [actor, setActor] = useState(intent.expectedActor ?? "");
  const [rationale, setRationale] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const valid = actor.trim().length > 0 && rationale.trim().length > 1 && confirmed;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onCancel();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onCancel} role="presentation">
      <div role="dialog" aria-modal="true" className="w-full max-w-md rounded-card border border-border bg-surface p-5 shadow-card" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center gap-2 text-sm font-semibold text-text">
          <ShieldCheck size={17} className="text-accent" />
          {intent.action === "approve"
            ? t("dialog.approveTitle", { gate: t(`gate.${intent.gate}`) })
            : t("dialog.revokeTitle")}
        </div>
        <p className="mt-2 text-xs leading-5 text-muted">{t("dialog.body", { hash: `${artifactHash.slice(0, 12)}…` })}</p>
        <label className="mt-4 block text-xs font-medium text-text">
          {t("dialog.actor")}
          <input value={actor} onChange={(event) => setActor(event.target.value)} readOnly={Boolean(intent.expectedActor)} autoFocus placeholder={t("dialog.actorPlaceholder")} className="mt-1.5 w-full rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent read-only:text-muted" />
        </label>
        {intent.expectedActor && (
          <p className="mt-1.5 text-[10px] leading-4 text-muted">
            {t("dialog.expectedReviewer")}
          </p>
        )}
        <label className="mt-3 block text-xs font-medium text-text">
          {t("dialog.rationale")}
          <textarea value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder={t("dialog.rationalePlaceholder")} rows={3} className="mt-1.5 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent" />
        </label>
        <label className="mt-3 flex items-start gap-2 text-xs leading-5 text-text">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="mt-1 accent-[var(--color-accent)]" />
          <span>
            {intent.gate === "release" && intent.action === "approve"
              ? t("dialog.confirmRelease")
              : intent.gate === "independent_validation" && intent.action === "approve"
              ? t("dialog.confirmIndependent")
              : t("dialog.confirm")}
          </span>
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-input border border-border px-3 py-1.5 text-xs font-medium text-text hover:bg-surface-2">{t("dialog.cancel")}</button>
          <button disabled={!valid} onClick={() => onSubmit(actor.trim(), rationale.trim())} className={cn("rounded-input px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40", intent.action === "approve" ? "bg-accent" : "bg-error")}>{intent.action === "approve" ? t("dialog.approve") : t("dialog.revoke")}</button>
        </div>
      </div>
    </div>
  );
}

function ResultCard({ result, locale }: { result: HeorRunResult; locale: string }) {
  const { t } = useTranslation("heor");
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 3 });
  const basis = result.calculation.economic_basis;
  const currency = basis
    ? new Intl.NumberFormat(locale, {
        style: "currency",
        currency: basis.currency,
        maximumFractionDigits: 0,
      })
    : null;
  const formatMoney = (value: number) => currency?.format(value) ?? number.format(value);
  const authorized = result.workflow.classification !== "exploratory";
  const decisionReady = result.workflow.decisionReady;
  const strategyOrder = result.calculation.strategy_order ?? ["comparator", "intervention"];
  const rows = strategyOrder
    .map((strategyId) => [strategyId, result.calculation.strategies[strategyId]] as const)
    .filter((row): row is readonly [string, NonNullable<typeof row[1]>] => Boolean(row[1]));
  const frontierRows = result.calculation.fully_incremental_analysis;
  const incremental = result.calculation.incremental;
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        <ShieldCheck size={16} className={authorized ? "text-ok" : "text-accent"} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-text">{t("result.title")}</div>
          <div className={cn("mt-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]", authorized ? "text-ok" : "text-accent")}>
            {decisionReady
              ? t("result.released")
              : authorized ? t("result.authorized") : t("result.exploratory")}
          </div>
        </div>
        <span className="rounded-full border border-border bg-bg px-2 py-0.5 text-[9px] font-semibold uppercase text-muted">
          {decisionReady ? t("status.decisionReady") : t("status.notDecisionReady")}
        </span>
      </div>
      {authorized && (
        <p className="mt-2 text-[10px] leading-4 text-muted">
          {decisionReady ? t("result.releasedNote") : t("result.authorizedNote")}
        </p>
      )}
      <p className={cn("mt-2 text-[10px] leading-4", basis ? "text-muted" : "text-warning")}>
        {basis
          ? t("result.economicBasis", { currency: basis.currency, year: basis.price_year })
          : t("result.economicBasisMissing")}
      </p>
      <div className="mt-4 overflow-hidden rounded-input border border-border">
        <table className="w-full text-[10px]">
          <thead className="bg-bg text-muted">
            <tr><th className="px-2 py-2 text-left font-medium">{t("result.strategy")}</th><th className="px-2 py-2 text-right font-medium">{t("result.cost")}</th><th className="px-2 py-2 text-right font-medium">{t("result.qaly")}</th></tr>
          </thead>
          <tbody>
            {rows.map(([strategyId, row]) => <tr key={strategyId} className="border-t border-border"><td className="px-2 py-2 font-mono text-text">{row.name}</td><td className="px-2 py-2 text-right tabular-nums text-text">{formatMoney(row.total_cost)}</td><td className="px-2 py-2 text-right tabular-nums text-text">{number.format(row.total_qaly)}</td></tr>)}
          </tbody>
        </table>
      </div>
      {incremental && (
        <div className="mt-3 grid grid-cols-3 gap-2">
          <Metric label={t("result.deltaCost")} value={formatMoney(incremental.delta_cost)} />
          <Metric label={t("result.deltaQaly")} value={number.format(incremental.delta_qaly)} />
          <Metric label={t("result.icer")} value={incremental.icer === null ? "—" : formatMoney(incremental.icer)} accent />
        </div>
      )}
      {frontierRows && (
        <div className="mt-3 overflow-hidden rounded-input border border-border">
          <div className="bg-bg px-2 py-1.5 text-[10px] font-semibold text-text">{t("result.fullyIncremental")}</div>
          <table className="w-full text-[10px]">
            <thead className="border-t border-border bg-bg text-muted"><tr><th className="px-2 py-2 text-left font-medium">{t("result.strategy")}</th><th className="px-2 py-2 text-left font-medium">{t("result.frontierStatus")}</th><th className="px-2 py-2 text-right font-medium">{t("result.icer")}</th></tr></thead>
            <tbody>{frontierRows.map((row) => (
              <tr key={row.strategy_id} className="border-t border-border"><td className="px-2 py-2 font-mono text-text">{row.strategy_name}</td><td className="px-2 py-2 text-muted">{t(`result.status.${row.status}`)}</td><td className="px-2 py-2 text-right tabular-nums text-text">{row.icer === null ? "—" : formatMoney(row.icer)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <details className="mt-3 text-[10px] text-muted">
        <summary className="cursor-pointer font-medium text-text">{t("result.warnings")} ({result.calculation.warnings.length})</summary>
        <ul className="mt-2 list-disc space-y-1 pl-4 leading-4">{result.calculation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      </details>
    </section>
  );
}

type DecisionThresholdRow = HeorUncertaintyRunResult["calculation"]["probabilistic_analysis"]["decision_uncertainty"]["threshold_results"][number];

function lineSegments(
  rows: DecisionThresholdRow[],
  x: (row: DecisionThresholdRow) => number,
  y: (row: DecisionThresholdRow) => number | null,
) {
  const segments: string[] = [];
  let current: string[] = [];
  for (const row of rows) {
    const value = y(row);
    if (value === null) {
      if (current.length > 1) segments.push(current.join(" "));
      current = [];
      continue;
    }
    current.push(`${current.length ? "L" : "M"} ${x(row).toFixed(2)} ${value.toFixed(2)}`);
  }
  if (current.length > 1) segments.push(current.join(" "));
  return segments;
}

export function CeacChart({ rows, primaryThreshold, locale, strategyOrder }: {
  rows: DecisionThresholdRow[];
  primaryThreshold: number;
  locale: string;
  strategyOrder?: string[];
}) {
  const { t } = useTranslation("heor");
  if (rows.length < 2) return null;
  const width = 320;
  const height = 168;
  const plot = { left: 42, right: 10, top: 18, bottom: 32 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const minimum = rows[0].threshold;
  const maximum = rows[rows.length - 1].threshold;
  const x = (row: DecisionThresholdRow) => (
    plot.left + ((row.threshold - minimum) / (maximum - minimum)) * innerWidth
  );
  const y = (value: number) => plot.top + (1 - value) * innerHeight;
  const observedStrategyIds = Object.keys(rows[0]?.strategy_optimal_probabilities ?? {});
  const strategyIds = strategyOrder?.length ? strategyOrder : observedStrategyIds;
  const series = strategyIds.length > 0
    ? strategyIds.map((strategyId, index) => ({
        id: strategyId,
        color: `hsl(${(index * 137.508) % 360} 68% 48%)`,
        paths: lineSegments(rows, x, (row) => {
          const value = row.strategy_optimal_probabilities?.[strategyId];
          return value === undefined ? null : y(value);
        }),
      }))
    : [{
        id: "intervention",
        color: "var(--color-link)",
        paths: lineSegments(rows, x, (row) => (
          row.intervention_optimal_probability === undefined
            ? null : y(row.intervention_optimal_probability)
        )),
      }];
  const frontier = lineSegments(rows, x, (row) => (
    row.ceaf_probability === null ? null : y(row.ceaf_probability)
  ));
  const compact = new Intl.NumberFormat(locale, {
    notation: "compact",
    maximumFractionDigits: 1,
  });
  const percent = new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 0,
  });
  const ticks = [...new Set([minimum, primaryThreshold, maximum])].sort((a, b) => a - b);
  const tickX = (value: number) => (
    plot.left + ((value - minimum) / (maximum - minimum)) * innerWidth
  );
  return (
    <figure className="mt-4" aria-labelledby="ceac-chart-title">
      <figcaption>
        <div id="ceac-chart-title" className="text-[10px] font-semibold text-text">
          {t("uncertaintyResult.ceacTitle")}
        </div>
        <div className="mt-0.5 text-[9px] leading-4 text-muted">
          {t("uncertaintyResult.ceacSubtitle")}
        </div>
      </figcaption>
      <div className="mt-2 overflow-hidden rounded-input border border-border bg-bg px-1 py-2">
        <svg
          role="img"
          aria-label={t("uncertaintyResult.ceacAria")}
          viewBox={`0 0 ${width} ${height}`}
          className="h-auto w-full"
        >
          {[0, 0.5, 1].map((value) => (
            <g key={value} className="text-muted">
              <line
                x1={plot.left}
                x2={width - plot.right}
                y1={y(value)}
                y2={y(value)}
                stroke="currentColor"
                strokeOpacity="0.18"
              />
              <text x={plot.left - 6} y={y(value) + 3} textAnchor="end" fill="currentColor" fontSize="9">
                {percent.format(value)}
              </text>
            </g>
          ))}
          <line x1={plot.left} x2={plot.left} y1={plot.top} y2={height - plot.bottom} stroke="currentColor" className="text-muted" />
          <line x1={plot.left} x2={width - plot.right} y1={height - plot.bottom} y2={height - plot.bottom} stroke="currentColor" className="text-muted" />
          {ticks.map((value) => (
            <g key={value} className="text-muted">
              <line x1={tickX(value)} x2={tickX(value)} y1={height - plot.bottom} y2={height - plot.bottom + 4} stroke="currentColor" />
              <text x={tickX(value)} y={height - 12} textAnchor="middle" fill="currentColor" fontSize="9">
                {compact.format(value)}
              </text>
            </g>
          ))}
          {series.flatMap((item) => item.paths.map((path) => (
            <path key={`${item.id}-${path}`} d={path} fill="none" stroke={item.color} strokeWidth="2" />
          )))}
          {frontier.map((path) => (
            <path key={path} d={path} fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="5 4" className="text-text" />
          ))}
          {rows.map((row) => (
            <g key={row.threshold}>
              {series.map((item) => {
                const value = item.id === "intervention" && strategyIds.length === 0
                  ? row.intervention_optimal_probability
                  : row.strategy_optimal_probabilities?.[item.id];
                return value === undefined ? null : <circle key={item.id} cx={x(row)} cy={y(value)} r="2.5" fill={item.color} />;
              })}
              {row.ceaf_probability !== null && (
                <circle cx={x(row)} cy={y(row.ceaf_probability)} r="2.5" fill="var(--color-bg)" stroke="currentColor" className="text-text" />
              )}
            </g>
          ))}
        </svg>
        <div className="flex flex-wrap justify-center gap-x-3 gap-y-1 px-2 text-[9px] text-muted">
          {series.map((item) => <span key={item.id} className="inline-flex items-center gap-1"><span className="h-0.5 w-3" style={{ backgroundColor: item.color }} />{item.id === "intervention" && observedStrategyIds.length === 0 ? t("uncertaintyResult.interventionCeac") : item.id}</span>)}
          <span className="inline-flex items-center gap-1"><span className="w-3 border-t border-dashed border-text" />{t("uncertaintyResult.ceaf")}</span>
        </div>
        <div className="px-2 text-center text-[9px] text-muted">
          {t("uncertaintyResult.thresholdAxis")}
        </div>
      </div>
    </figure>
  );
}

export function UncertaintyResultCard({
  result,
  locale,
}: {
  result: HeorUncertaintyRunResult;
  locale: string;
}) {
  const { t } = useTranslation("heor");
  const calculation = result.calculation;
  const partialEconomicOnly = calculation.calculation_classification
    === "partial_parameter_uncertainty"
    && calculation.uncertainty_scope === "economic_inputs_only";
  const jointSurvival = calculation.calculation_classification
    === "joint_curve_draw_parameter_uncertainty"
    && calculation.uncertainty_scope === "joint_survival_curves_and_economic_inputs";
  const componentUncertainty = calculation.calculation_classification
    === "component_parameter_uncertainty"
    && calculation.uncertainty_scope === "cost_utility_event_components_only";
  const jointComponentUncertainty = calculation.calculation_classification
    === "joint_curve_and_component_parameter_uncertainty"
    && calculation.uncertainty_scope
      === "joint_survival_curves_and_cost_utility_event_components";
  const amount = new Intl.NumberFormat(locale, calculation.economic_basis
    ? {
        style: "currency",
        currency: calculation.economic_basis.currency,
        maximumFractionDigits: 0,
      }
    : { maximumFractionDigits: 0 });
  const probability = new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  });
  const psa = calculation.probabilistic_analysis;
  const decision = psa.decision_uncertainty;
  const primary = decision.threshold_results.find(
    (row) => Math.abs(row.threshold - decision.primary_threshold) <= 1e-9,
  );
  const authorized = result.workflow.classification !== "exploratory";
  const multiStrategy = Boolean((decision.strategy_order ?? psa.strategy_order)?.length);
  const primaryStrategy = primary?.strategy_with_highest_expected_net_benefit;
  const tiedStrategies = primary?.expected_net_benefit_tied_strategy_ids ?? [];
  const primaryProbability = multiStrategy && primaryStrategy
    ? primary?.strategy_optimal_probabilities?.[primaryStrategy]
    : undefined;
  const displayedNmbStrategy = multiStrategy ? (primaryStrategy ?? tiedStrategies[0]) : undefined;
  const primaryMeanNmb = displayedNmbStrategy
    ? primary?.expected_net_monetary_benefit_by_strategy?.[displayedNmbStrategy]
    : psa.mean_incremental_net_monetary_benefit;
  const probabilityLabel = multiStrategy && primaryStrategy
    ? `${t("uncertaintyResult.probability")} · ${primaryStrategy}`
    : t("uncertaintyResult.probability");
  const nmbStrategyLabel = primaryStrategy ?? (tiedStrategies.length > 1
    ? tiedStrategies.join(" = ")
    : null);
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        <ShieldCheck size={16} className={authorized ? "text-ok" : "text-accent"} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-text">{t("uncertaintyResult.title")}</div>
          <div className={cn(
            "mt-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]",
            authorized ? "text-ok" : "text-accent",
          )}>
            {authorized ? t("result.authorized") : t("result.exploratory")}
          </div>
        </div>
        <span className={cn(
          "rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase",
          psa.convergence.passed
            ? "border-ok/30 bg-ok/5 text-ok"
            : "border-warning/30 bg-warning/5 text-warning",
        )}>
          {psa.convergence.passed
            ? t("uncertaintyResult.converged")
            : t("uncertaintyResult.notConverged")}
        </span>
      </div>
      {partialEconomicOnly && (
        <div className="mt-3 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-[10px] leading-4 text-warning">
          <div className="font-semibold">{t("uncertaintyResult.partialEconomicOnly")}</div>
          <div>{t("uncertaintyResult.partialEconomicOnlyDetail")}</div>
        </div>
      )}
      {jointSurvival && (
        <div className="mt-3 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-[10px] leading-4 text-warning">
          <div className="font-semibold">{t("uncertaintyResult.jointSurvival")}</div>
          <div>{t("uncertaintyResult.jointSurvivalDetail")}</div>
        </div>
      )}
      {componentUncertainty && (
        <div className="mt-3 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-[10px] leading-4 text-warning">
          <div className="font-semibold">{t("uncertaintyResult.componentUncertainty")}</div>
          <div>{t("uncertaintyResult.componentUncertaintyDetail")}</div>
        </div>
      )}
      {jointComponentUncertainty && (
        <div className="mt-3 rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-[10px] leading-4 text-warning">
          <div className="font-semibold">{t("uncertaintyResult.jointComponentUncertainty")}</div>
          <div>{t("uncertaintyResult.jointComponentUncertaintyDetail")}</div>
        </div>
      )}
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Metric
          label={probabilityLabel}
          value={multiStrategy
            ? (primaryProbability === undefined ? "—" : probability.format(primaryProbability))
            : (psa.cost_effective_probability === undefined
              ? "—"
              : probability.format(psa.cost_effective_probability))}
          accent
        />
        <Metric
          label={multiStrategy && nmbStrategyLabel
            ? t("uncertaintyResult.bestExpectedNmb", { strategy: nmbStrategyLabel })
            : t("uncertaintyResult.meanInmb")}
          value={primaryMeanNmb === undefined ? "—" : amount.format(primaryMeanNmb)}
        />
        <Metric
          label={t("uncertaintyResult.iterations")}
          value={psa.iterations.toLocaleString(locale)}
        />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Metric
          label={t("uncertaintyResult.parameters")}
          value={String(calculation.deterministic_analysis.length)}
        />
        <Metric
          label={t("uncertaintyResult.correlations")}
          value={String(psa.correlation_groups.length)}
        />
        <Metric
          label={t("uncertaintyResult.scenarios")}
          value={String(calculation.structural_scenarios.length)}
        />
      </div>
      {primary && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <Metric
            label={partialEconomicOnly
              ? t("uncertaintyResult.partialEvpi")
              : jointSurvival
                ? t("uncertaintyResult.jointEvpi")
                : componentUncertainty
                  ? t("uncertaintyResult.componentEvpi")
                  : jointComponentUncertainty
                    ? t("uncertaintyResult.jointComponentEvpi")
                : t("uncertaintyResult.primaryEvpi")}
            value={amount.format(primary.per_person_evpi)}
            accent
          />
          <Metric
            label={t("uncertaintyResult.evpiMcse")}
            value={amount.format(primary.per_person_evpi_mcse)}
          />
        </div>
      )}
      <CeacChart
        rows={decision.threshold_results}
        primaryThreshold={decision.primary_threshold}
        locale={locale}
        strategyOrder={decision.strategy_order ?? psa.strategy_order}
      />
      <details className="mt-3 text-[10px] text-muted">
        <summary className="cursor-pointer font-medium text-text">
          {t("uncertaintyResult.limitations")} ({calculation.limitations.length})
        </summary>
        <ul className="mt-2 list-disc space-y-1 pl-4 leading-4">
          {calculation.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
        </ul>
      </details>
    </section>
  );
}

export function AdvancedVoiResultCard({
  result,
  locale,
}: {
  result: HeorAdvancedVoiRunResult;
  locale: string;
}) {
  const { t } = useTranslation("heor");
  const calculation = result.calculation;
  const basis = calculation.evsi.study_cost_basis;
  const amount = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: basis.currency,
    maximumFractionDigits: 0,
  });
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 });
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        <ShieldCheck size={16} className="mt-0.5 text-accent" />
        <div>
          <div className="text-sm font-semibold text-text">{t("advancedVoiResult.title")}</div>
          <div className="mt-1 text-[10px] text-muted">{t("advancedVoiResult.awaitingHuman")}</div>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Metric label={t("advancedVoiResult.populationEvpi")} value={amount.format(calculation.population_evpi.population_evpi)} accent />
        <Metric label={t("advancedVoiResult.effectivePopulation")} value={number.format(calculation.population.effective_population)} />
      </div>
      <div className="mt-3 overflow-x-auto rounded-md border border-border">
        <table className="w-full min-w-[440px] text-left text-[10px]">
          <thead className="bg-surface-2 text-muted"><tr>
            <th className="px-2 py-1.5">{t("advancedVoiResult.parameterGroup")}</th>
            <th className="px-2 py-1.5">{t("advancedVoiResult.perPerson")}</th>
            <th className="px-2 py-1.5">{t("advancedVoiResult.populationValue")}</th>
            <th className="px-2 py-1.5">MCSE</th>
          </tr></thead>
          <tbody>{calculation.evppi.map((row) => <tr key={row.group_id} className="border-t border-border">
            <td className="px-2 py-1.5 text-text">{row.label}</td>
            <td className="px-2 py-1.5">{amount.format(row.per_person_evppi)}</td>
            <td className="px-2 py-1.5">{amount.format(row.population_evppi)}</td>
            <td className="px-2 py-1.5">{amount.format(row.per_person_evppi_mcse)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <div className="mt-3 overflow-x-auto rounded-md border border-border">
        <table className="w-full min-w-[480px] text-left text-[10px]">
          <thead className="bg-surface-2 text-muted"><tr>
            <th className="px-2 py-1.5">{t("advancedVoiResult.sampleSize")}</th>
            <th className="px-2 py-1.5">EVSI</th>
            <th className="px-2 py-1.5">{t("advancedVoiResult.studyCost")}</th>
            <th className="px-2 py-1.5">ENBS</th>
          </tr></thead>
          <tbody>{calculation.evsi.designs.map((row) => <tr key={row.sample_size} className="border-t border-border">
            <td className="px-2 py-1.5 text-text">{row.sample_size.toLocaleString(locale)}</td>
            <td className="px-2 py-1.5">{amount.format(row.population_evsi)}</td>
            <td className="px-2 py-1.5">{amount.format(row.study_cost)}</td>
            <td className={cn("px-2 py-1.5 font-medium", row.expected_net_benefit_of_sampling >= 0 ? "text-ok" : "text-warning")}>
              {amount.format(row.expected_net_benefit_of_sampling)}
            </td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("advancedVoiResult.note")}</p>
    </section>
  );
}

export function BudgetImpactResultCard({
  result,
  locale,
}: {
  result: HeorBudgetImpactRunResult;
  locale: string;
}) {
  const { t } = useTranslation("heor");
  const calculation = result.calculation;
  const currency = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: calculation.currency,
    maximumFractionDigits: 0,
  });
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  const percent = new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  });
  const authorized = result.workflow.classification !== "exploratory";
  const dynamic = calculation.schema_version === "0.2.0"
    && calculation.base_case.model_type === "dynamic_annual_cohort";
  const leadingDriver = [...calculation.one_way_sensitivity]
    .sort((left, right) => right.cumulative_span - left.cumulative_span)[0];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        <ShieldCheck size={16} className={authorized ? "text-ok" : "text-accent"} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-text">{t("budgetImpactResult.title")}</div>
          <div className={cn(
            "mt-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]",
            authorized ? "text-ok" : "text-accent",
          )}>
            {authorized ? t("result.authorized") : t("result.exploratory")}
          </div>
        </div>
        <span className="rounded-full border border-border bg-bg px-2 py-0.5 text-[9px] font-semibold uppercase text-muted">
          {dynamic ? t("budgetImpactResult.dynamicCohort") : t("budgetImpactResult.staticCalculator")} · {calculation.price_year} {calculation.currency} · {t("budgetImpact.noDiscount")}
        </span>
      </div>
      <div className="mt-4 overflow-hidden rounded-input border border-border">
        <table className="w-full text-[10px]">
          <thead className="bg-bg text-muted">
            <tr>
              <th className="px-2 py-2 text-left font-medium">{t("budgetImpactResult.year")}</th>
              <th className="px-2 py-2 text-right font-medium">{t("budgetImpactResult.population")}</th>
              <th className="px-2 py-2 text-right font-medium">{t("budgetImpactResult.uptake")}</th>
              <th className="px-2 py-2 text-right font-medium">{t("budgetImpactResult.netImpact")}</th>
            </tr>
          </thead>
          <tbody>
            {calculation.base_case.annual_results.map((row) => (
              <tr key={row.year} className="border-t border-border">
                <td className="px-2 py-2 text-text">{row.year}</td>
                <td className="px-2 py-2 text-right tabular-nums text-text">
                  {number.format(row.eligible_population)}
                </td>
                <td className="px-2 py-2 text-right tabular-nums text-text">
                  {percent.format(row.with_new_intervention_share)}
                </td>
                <td className="px-2 py-2 text-right tabular-nums text-text">
                  {currency.format(row.net_budget_impact)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {dynamic && (
        <details className="mt-3 rounded-input border border-border bg-bg/40 px-3 py-2 text-[10px] text-muted">
          <summary className="cursor-pointer font-medium text-text">
            {t("budgetImpactResult.dynamicFlowLedger")}
          </summary>
          <div className="mt-2 space-y-2">
            {calculation.base_case.annual_results.map((row) => {
              const flow = row.with_new_intervention_flow;
              if (!flow) return null;
              return (
                <div key={row.year} className="grid grid-cols-4 gap-2 rounded border border-border px-2 py-2">
                  <Metric label={t("budgetImpactResult.yearLabel", { year: row.year })} value={number.format(flow.treated_population)} />
                  <Metric label={t("budgetImpactResult.starts")} value={number.format(flow.incident_intervention_starts + flow.comparator_displacement_starts)} />
                  <Metric label={t("budgetImpactResult.unmetStarts")} value={number.format(flow.capacity_unmet_starts)} />
                  <Metric label={t("budgetImpactResult.deathsAndExits")} value={number.format(flow.deaths + flow.comparator_discontinuers_exiting)} />
                </div>
              );
            })}
          </div>
          <p className="mt-2 leading-4">{t("budgetImpactResult.dynamicOrderNote")}</p>
        </details>
      )}
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Metric
          label={t("budgetImpactResult.cumulative")}
          value={currency.format(calculation.base_case.cumulative_net_budget_impact)}
          accent
        />
        <Metric
          label={t("budgetImpactResult.leadingDriver")}
          value={leadingDriver?.label ?? "—"}
        />
        <Metric
          label={t("budgetImpactResult.scenarios")}
          value={String(calculation.alternative_scenarios.length)}
        />
      </div>
      <details className="mt-3 text-[10px] text-muted">
        <summary className="cursor-pointer font-medium text-text">
          {t("budgetImpactResult.limitations")} ({calculation.limitations.length})
        </summary>
        <ul className="mt-2 list-disc space-y-1 pl-4 leading-4">
          {calculation.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
        </ul>
      </details>
    </section>
  );
}

function PartitionedSurvivalResultCard({
  result,
  locale,
}: {
  result: HeorPartitionedSurvivalRunResult;
  locale: string;
}) {
  const { t } = useTranslation("heor");
  const calculation = result.calculation;
  const currency = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: calculation.economic_basis.currency,
    maximumFractionDigits: 0,
  });
  const qaly = new Intl.NumberFormat(locale, { maximumFractionDigits: 3 });
  const authorized = result.workflow.classification !== "exploratory";
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        <ShieldCheck size={16} className={authorized ? "text-ok" : "text-accent"} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-text">{t("partitionedSurvivalResult.title")}</div>
          <div className={cn(
            "mt-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]",
            authorized ? "text-ok" : "text-accent",
          )}>
            {authorized ? t("result.authorized") : t("result.exploratory")}
          </div>
        </div>
        <span className="rounded-full border border-border bg-bg px-2 py-0.5 text-[9px] font-semibold uppercase text-muted">
          {t("result.endpointBadge", { origin: calculation.time_origin })}
        </span>
      </div>
      <div className="mt-4 overflow-hidden rounded-input border border-border">
        <table className="w-full text-[10px]">
          <thead className="bg-bg text-muted">
            <tr>
              <th className="px-2 py-2 text-left font-medium">{t("partitionedSurvivalResult.strategy")}</th>
              <th className="px-2 py-2 text-right font-medium">{t("result.cost")}</th>
              <th className="px-2 py-2 text-right font-medium">{t("result.qaly")}</th>
              {calculation.event_disutilities_summary && (
                <th className="px-2 py-2 text-right font-medium">{t("result.eventQalyLoss")}</th>
              )}
            </tr>
          </thead>
          <tbody>
            {calculation.strategy_order.map((strategyId) => {
              const strategy = calculation.strategies[strategyId];
              return (
                <tr key={strategyId} className="border-t border-border">
                  <td className="px-2 py-2 text-text">{strategy.name}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-text">{currency.format(strategy.total_cost)}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-text">{qaly.format(strategy.total_qaly)}</td>
                  {calculation.event_disutilities_summary && (
                    <td className="px-2 py-2 text-right tabular-nums text-text">
                      {qaly.format(strategy.event_disutility_qaly_loss ?? 0)}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {calculation.treatment_effect_duration_scenarios?.length ? (
        <div className="mt-4">
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
            {t("partitionedSurvivalResult.durationScenarios")}
          </div>
          <div className="space-y-2">
            {calculation.treatment_effect_duration_scenarios.map((scenario) => {
              const interventionId = scenario.strategy_order.find((id) => id !== scenario.baseline_strategy_id);
              const incremental = interventionId ? scenario.pairwise_vs_baseline[interventionId] : undefined;
              return (
                <div key={scenario.scenario_id} className="rounded-input border border-border bg-bg px-3 py-2">
                  <div className="text-[10px] font-medium text-text">{scenario.label}</div>
                  <div className="mt-1 flex gap-4 text-[9px] tabular-nums text-muted">
                    <span>{t("partitionedSurvivalResult.incrementalCost")}: {incremental ? currency.format(incremental.delta_cost) : "—"}</span>
                    <span>{t("partitionedSurvivalResult.incrementalQaly")}: {incremental ? qaly.format(incremental.delta_qaly) : "—"}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
      <p className="mt-3 text-[10px] leading-4 text-muted">{t("partitionedSurvivalResult.note")}</p>
    </section>
  );
}

function Metric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return <div className="rounded-input bg-bg px-2 py-2"><div className="text-[9px] text-muted">{label}</div><div className={cn("mt-1 truncate font-mono text-[11px] font-semibold", accent ? "text-accent" : "text-text")} title={value}>{value}</div></div>;
}

function latestByGate(events: HeorApprovalEvent[]): Map<HeorGate, HeorApprovalEvent> {
  const latest = new Map<HeorGate, HeorApprovalEvent>();
  for (const event of events) latest.set(event.gate, event);
  return latest;
}

function summarizeBrowserLog(events: HeorApprovalEvent[]): HeorApprovalLog {
  const latest = latestByGate(events);
  const effectiveApprovedGates: HeorGate[] = [];
  let prerequisiteSequence = 0;
  for (const gate of ALL_GATES) {
    const event = latest.get(gate);
    if (!event || event.action !== "approve" || event.sequence <= prerequisiteSequence) break;
    effectiveApprovedGates.push(gate);
    prerequisiteSequence = event.sequence;
  }
  return {
    events,
    effectiveApprovedGates,
    chainHead: events.length > 0 ? events[events.length - 1].eventHash : null,
    integrity: "verified_unanchored_sha256_chain",
    identityAssurance: "local_human_assertion",
  };
}

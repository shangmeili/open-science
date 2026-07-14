import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  BookOpen,
  Check,
  Circle,
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
  auditHeorBudgetImpact,
  auditHeorConceptualModel,
  auditHeorEvidence,
  auditHeorEvidenceLibrary,
  auditHeorEvidenceSearch,
  auditHeorEvidenceSynthesis,
  auditHeorReferenceCase,
  auditHeorUncertainty,
  auditHeorModelValidation,
  auditHeorReporting,
  addHeorLibraryFiles,
  browserDemoRun,
  HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL,
  HEOR_BROWSER_DEMO_PLAN,
  HEOR_CONCEPTUAL_MODEL_PATH,
  HEOR_BUDGET_IMPACT_PLAN_PATH,
  HEOR_MODEL_VALIDATION_PATH,
  HEOR_REPORT_PACKAGE_PATH,
  HEOR_REPORT_DOCUMENT_PATH,
  HEOR_BASE_CASE_RESULT_PATH,
  HEOR_UNCERTAINTY_RESULT_PATH,
  HEOR_BUDGET_IMPACT_RESULT_PATH,
  HEOR_EVIDENCE_SEARCH_REQUEST_PATH,
  HEOR_EVIDENCE_LIBRARY_PATH,
  HEOR_EVIDENCE_SYNTHESIS_PATH,
  HEOR_PLAN_PATH,
  HEOR_REFERENCE_CASE_ASSESSMENT_PATH,
  HEOR_UNCERTAINTY_PLAN_PATH,
  type HeorAnalysisPlan,
  type HeorApprovalAction,
  type HeorApprovalEvent,
  type HeorApprovalLog,
  type HeorConceptualModel,
  type HeorConceptualModelAudit,
  type HeorBudgetImpactAudit,
  type HeorBudgetImpactRunResult,
  type HeorModelValidationAudit,
  type HeorReportingAudit,
  type HeorGate,
  type HeorReferenceCaseAudit,
  type HeorRunResult,
  type HeorEvidenceSearchAudit,
  type HeorEvidenceLibraryAudit,
  type HeorEvidenceSynthesisAudit,
  type HeorImportCandidatesResponse,
  type HeorSearchAuthorizationLog,
  type HeorSearchExecutionResponse,
  type HeorSearchAuthorizationEvent,
  type HeorUncertaintyAudit,
  type HeorUncertaintyRunResult,
  listHeorApprovals,
  listHeorSearchAuthorizations,
  parseHeorConceptualModel,
  parseHeorPlan,
  runHeorMarkov,
  runHeorBudgetImpact,
  syncHeorEvidenceLibrary,
  executeHeorEvidenceSearch,
  importHeorSearchCandidates,
  runHeorUncertainty,
  sha256Text,
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

type BudgetImpactState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorBudgetImpactAudit };

type ModelValidationState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorModelValidationAudit };

type ReportingState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorReportingAudit };

type EvidenceSearchState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorEvidenceSearchAudit };

type EvidenceSynthesisState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorEvidenceSynthesisAudit };

type EvidenceLibraryState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: HeorEvidenceLibraryAudit };

const EMPTY_SEARCH_LOG: HeorSearchAuthorizationLog = {
  events: [],
  chainHead: null,
  integrity: "verified_unanchored_sha256_chain",
  identityAssurance: "local_human_assertion",
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

const REPORT_BINDING_PATHS: Record<string, string> = {
  report_document: HEOR_REPORT_DOCUMENT_PATH,
  analysis_plan: HEOR_PLAN_PATH,
  conceptual_model: HEOR_CONCEPTUAL_MODEL_PATH,
  uncertainty_plan: HEOR_UNCERTAINTY_PLAN_PATH,
  budget_impact_plan: HEOR_BUDGET_IMPACT_PLAN_PATH,
  model_validation: HEOR_MODEL_VALIDATION_PATH,
  base_case_result: HEOR_BASE_CASE_RESULT_PATH,
  uncertainty_result: HEOR_UNCERTAINTY_RESULT_PATH,
  budget_impact_result: HEOR_BUDGET_IMPACT_RESULT_PATH,
};

function reportBindingsCurrent(
  event: HeorApprovalEvent | undefined,
  audit: HeorReportingAudit,
): boolean {
  return event?.actorLabel === audit.releaseOwnerLabel
    && Object.entries(REPORT_BINDING_PATHS).every(([key, path]) =>
      eventBinds(event, path, audit.bindingHashes[key] ?? ""));
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
  return eventBinds(event, HEOR_PLAN_PATH, audit.analysisPlanSha256)
    && eventBinds(event, HEOR_CONCEPTUAL_MODEL_PATH, audit.conceptualModelSha256)
    && eventBinds(event, HEOR_UNCERTAINTY_PLAN_PATH, audit.uncertaintyPlanSha256)
    && eventBinds(event, HEOR_BUDGET_IMPACT_PLAN_PATH, audit.budgetImpactPlanSha256);
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
  const [budgetImpact, setBudgetImpact] = useState<BudgetImpactState>({ kind: "loading" });
  const [modelValidation, setModelValidation] = useState<ModelValidationState>({ kind: "loading" });
  const [reporting, setReporting] = useState<ReportingState>({ kind: "loading" });
  const [evidenceSearch, setEvidenceSearch] = useState<EvidenceSearchState>({ kind: "loading" });
  const [evidenceSynthesis, setEvidenceSynthesis] = useState<EvidenceSynthesisState>({ kind: "loading" });
  const [evidenceLibrary, setEvidenceLibrary] = useState<EvidenceLibraryState>({ kind: "loading" });
  const [searchAuthorizations, setSearchAuthorizations] = useState(EMPTY_SEARCH_LOG);
  const [searchResult, setSearchResult] = useState<HeorSearchExecutionResponse | null>(null);
  const [importResult, setImportResult] = useState<HeorImportCandidatesResponse | null>(null);
  const [searchRunning, setSearchRunning] = useState(false);
  const [importRunning, setImportRunning] = useState(false);
  const [librarySyncing, setLibrarySyncing] = useState(false);
  const [searchDialogOpen, setSearchDialogOpen] = useState(false);
  const [approvals, setApprovals] = useState<HeorApprovalLog>(EMPTY_LOG);
  const [result, setResult] = useState<HeorRunResult | null>(null);
  const [uncertaintyResult, setUncertaintyResult] = useState<HeorUncertaintyRunResult | null>(null);
  const [budgetImpactResult, setBudgetImpactResult] = useState<HeorBudgetImpactRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [intent, setIntent] = useState<ReviewIntent | null>(null);

  const refresh = useCallback(async () => {
    setResult(null);
    setUncertaintyResult(null);
    setBudgetImpactResult(null);
    setSearchResult(null);
    setImportResult(null);
    if (!project) {
      setArtifact({ kind: "missing" });
      setConceptualArtifact({ kind: "missing" });
      setReferenceCase({ kind: "invalid", message: t("reference.noProject") });
      setUncertainty({ kind: "invalid", message: t("uncertainty.noProject") });
      setBudgetImpact({ kind: "invalid", message: t("budgetImpact.noProject") });
      setModelValidation({ kind: "invalid", message: t("validation.noProject") });
      setReporting({ kind: "invalid", message: t("reporting.noProject") });
      setEvidenceSearch({ kind: "invalid", message: t("search.noProject") });
      setEvidenceSynthesis({ kind: "invalid", message: t("synthesis.noProject") });
      setEvidenceLibrary({ kind: "invalid", message: t("library.noProject") });
      setSearchAuthorizations(EMPTY_SEARCH_LOG);
      setApprovals(EMPTY_LOG);
      return;
    }
    setArtifact({ kind: "loading" });
    setConceptualArtifact({ kind: "loading" });
    setReferenceCase({ kind: "loading" });
    setUncertainty({ kind: "loading" });
    setBudgetImpact({ kind: "loading" });
    setModelValidation({ kind: "loading" });
    setReporting({ kind: "loading" });
    setEvidenceSearch({ kind: "loading" });
    setEvidenceSynthesis({ kind: "loading" });
    setEvidenceLibrary({ kind: "loading" });
    try {
      setEvidenceLibrary({ kind: "ready", audit: await auditHeorEvidenceLibrary() });
    } catch (error) {
      setEvidenceLibrary({
        kind: "invalid",
        message: error instanceof Error ? error.message : String(error),
      });
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
        setBudgetImpact({ kind: "invalid", message: t("budgetImpact.missingPlan") });
        setModelValidation({ kind: "invalid", message: t("validation.missingPlan") });
        setReporting({ kind: "invalid", message: t("reporting.missingPlan") });
        setApprovals(await listHeorApprovals(project.id));
        return;
      }
      const plan = parseHeorPlan(raw);
      const sha256 = await sha256Text(raw);
      setArtifact({ kind: "ready", plan, raw, sha256 });
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
        setBudgetImpact({ kind: "ready", audit: await auditHeorBudgetImpact() });
      } catch (error) {
        setBudgetImpact({
          kind: "invalid",
          message: error instanceof Error ? error.message : String(error),
        });
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
      setBudgetImpact({
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
      toast.error(t("toast.loadFailed"));
    }
  }, [project, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

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
          || referenceCase.kind !== "ready"
          || !referenceCase.audit.complete
          || uncertainty.kind !== "ready"
          || !uncertainty.audit.complete
          || budgetImpact.kind !== "ready"
          || !budgetImpact.audit.complete)) break;
      if (gate === "independent_validation"
        && (modelValidation.kind !== "ready"
          || !modelValidation.audit.complete
          || !modelValidation.audit.approvable)) break;
      if (gate === "release"
        && (reporting.kind !== "ready" || !reporting.audit.releasable)) break;
      const event = latest.get(gate);
      if (
        !event ||
        event.action !== "approve" ||
        event.artifactSha256 !== artifactSha256 ||
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
        (gate === "independent_validation"
          && modelValidation.kind === "ready"
          && !validationBindingsCurrent(event, modelValidation.audit)) ||
        (gate === "release"
          && reporting.kind === "ready"
          && !reportBindingsCurrent(event, reporting.audit)) ||
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
    referenceCase,
    uncertainty,
    budgetImpact,
    modelValidation,
    reporting,
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
      ? [
          { path: HEOR_UNCERTAINTY_PLAN_PATH, sha256: uncertainty.audit.uncertaintySha256 },
          { path: HEOR_BUDGET_IMPACT_PLAN_PATH, sha256: budgetImpact.audit.budgetImpactSha256 },
        ]
      : gate === "independent_validation" && modelValidation.kind === "ready"
        ? [
            { path: HEOR_PLAN_PATH, sha256: modelValidation.audit.analysisPlanSha256 },
            {
              path: HEOR_CONCEPTUAL_MODEL_PATH,
              sha256: modelValidation.audit.conceptualModelSha256,
            },
            {
              path: HEOR_UNCERTAINTY_PLAN_PATH,
              sha256: modelValidation.audit.uncertaintyPlanSha256,
            },
            {
              path: HEOR_BUDGET_IMPACT_PLAN_PATH,
              sha256: modelValidation.audit.budgetImpactPlanSha256,
            },
          ]
        : gate === "release" && reporting.kind === "ready"
          ? Object.entries(REPORT_BINDING_PATHS).map(([key, path]) => ({
              path,
              sha256: reporting.audit.bindingHashes[key],
            }))
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
      toast.success(t("toast.uncertaintyRunComplete"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setRunning(false);
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
      toast.success(t("toast.budgetImpactRunComplete"));
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

  const syncLibrary = async (pickFiles: boolean) => {
    if (!project || librarySyncing || !isTauri) return;
    setLibrarySyncing(true);
    try {
      if (pickFiles) await addHeorLibraryFiles();
      const audit = await syncHeorEvidenceLibrary(project.id);
      setEvidenceLibrary({ kind: "ready", audit });
      toast.success(t("toast.librarySynced"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setLibrarySyncing(false);
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
          hasResult={!!result || !!uncertaintyResult || !!budgetImpactResult}
        />

        {project && (
          <EvidenceLibraryAssessment
            state={evidenceLibrary}
            syncing={librarySyncing}
            onAdd={() => void syncLibrary(true)}
            onSync={() => void syncLibrary(false)}
            onAsk={() => onRequestRevision(t("library.searchPrompt"))}
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
            onPrepare={() => onRequestRevision(t("synthesis.preparePrompt"))}
            onImport={() => void importSearchCandidates()}
            onContinue={() => onRequestRevision(t("synthesis.continuePrompt"))}
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

            <EvidenceTraceability
              audit={evidenceAudit!}
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
            <BudgetImpactAssessment
              state={budgetImpact}
              onRequestRepair={() => onRequestRevision(t("budgetImpact.repairPrompt"))}
            />
            <ModelValidationAssessment
              state={modelValidation}
              onRequestPreparation={() => onRequestRevision(t("validation.repairPrompt"))}
            />
            <ReportingAssessment
              state={reporting}
              onRequestPreparation={() => onRequestRevision(t("reporting.repairPrompt"))}
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
                    (uncertainty.kind === "ready"
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
                  )) || (gate === "independent_validation"
                    && modelValidation.kind === "ready"
                    && !validationBindingsCurrent(gateEvent, modelValidation.audit))
                    || (gate === "release"
                      && reporting.kind === "ready"
                      && !reportBindingsCurrent(gateEvent, reporting.audit));
                  const stale = approvals.effectiveApprovedGates.includes(gate)
                    && gateEvent?.action === "approve"
                    && (gateEvent.artifactSha256 !== artifactSha256 || relatedStale);
                  const conceptualBlocked = gate === "conceptual_model"
                    && gate === nextGate
                    && (conceptualArtifact.kind !== "ready" || !conceptualArtifact.audit.complete);
                  const evidenceBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && !evidenceAudit?.complete;
                  const referenceBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && (referenceCase.kind !== "ready" || !referenceCase.audit.complete);
                  const uncertaintyBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && (uncertainty.kind !== "ready" || !uncertainty.audit.complete);
                  const budgetImpactBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && (budgetImpact.kind !== "ready" || !budgetImpact.audit.complete);
                  const validationBlocked = gate === "independent_validation"
                    && gate === nextGate
                    && (modelValidation.kind !== "ready"
                      || !modelValidation.audit.complete
                      || !modelValidation.audit.approvable);
                  const reportingBlocked = gate === "release"
                    && gate === nextGate
                    && (reporting.kind !== "ready" || !reporting.audit.releasable);
                  const waiting = gate === nextGate && !stale && !conceptualBlocked
                    && !evidenceBlocked && !referenceBlocked && !uncertaintyBlocked
                    && !budgetImpactBlocked && !validationBlocked && !reportingBlocked;
                  return (
                    <div key={gate} className="rounded-input border border-border bg-bg/50 px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        {approved ? (
                          <Check size={14} className="text-ok" />
                        ) : waiting || stale || conceptualBlocked || evidenceBlocked || referenceBlocked
                          || uncertaintyBlocked || budgetImpactBlocked || validationBlocked
                          || reportingBlocked ? (
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
                              : validationBlocked
                                ? t("status.validationRequired")
                              : reportingBlocked
                                ? t("status.reportingRequired")
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
            </section>

            {result && <ResultCard result={result} locale={i18n.language} />}
            {uncertaintyResult && (
              <UncertaintyResultCard result={uncertaintyResult} locale={i18n.language} />
            )}
            {budgetImpactResult && (
              <BudgetImpactResultCard result={budgetImpactResult} locale={i18n.language} />
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

function EvidenceLibraryAssessment({
  state,
  syncing,
  onAdd,
  onSync,
  onAsk,
}: {
  state: EvidenceLibraryState;
  syncing: boolean;
  onAdd: () => void;
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
            onClick={onAdd}
            className="flex items-center gap-1.5 text-xs font-medium text-accent hover:underline disabled:opacity-50"
          >
            {syncing
              ? <Loader2 size={13} className="animate-spin" />
              : <FolderPlus size={13} />}
            {t("library.add")}
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
  onPrepare,
  onImport,
  onContinue,
}: {
  state: EvidenceSynthesisState;
  authorization: HeorSearchAuthorizationEvent | null;
  importResult: HeorImportCandidatesResponse | null;
  importing: boolean;
  onPrepare: () => void;
  onImport: () => void;
  onContinue: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const issues = audit?.errors ?? (state.kind === "invalid" ? [state.message] : []);
  const canImport = isTauri && authorization !== null && audit?.importable === true;
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

function EvidenceTraceability({
  audit,
  onRequestRepair,
}: {
  audit: ReturnType<typeof auditHeorEvidence>;
  onRequestRepair: () => void;
}) {
  const { t } = useTranslation("heor");
  const gaps = [
    ...audit.unsupportedInputs.map((path) => t("evidence.unsupported", { path })),
    ...audit.unresolvedAssumptions.map((id) => t("evidence.unresolved", { id })),
    ...audit.invalidMappings.slice(0, 3),
  ];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        {audit.complete ? (
          <ShieldCheck size={16} className="mt-0.5 text-ok" />
        ) : (
          <AlertTriangle size={16} className="mt-0.5 text-accent" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("evidence.title")}
          </div>
          <div className={cn("mt-1 text-xs font-semibold", audit.complete ? "text-ok" : "text-accent")}>
            {audit.complete ? t("evidence.complete") : t("evidence.incomplete")}
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
      </div>
      {!audit.complete && (
        <>
          <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
            {gaps.slice(0, 5).map((gap) => <li key={gap}>• {gap}</li>)}
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
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Metric label={t("uncertainty.parameters")} value={String(audit.parameterCount)} />
          <Metric label={t("uncertainty.iterations")} value={audit.iterations?.toLocaleString() ?? "—"} />
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
  const currency = new Intl.NumberFormat(locale, { style: "currency", currency: "CNY", maximumFractionDigits: 0 });
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 3 });
  const authorized = result.workflow.classification !== "exploratory";
  const decisionReady = result.workflow.decisionReady;
  const rows = [result.calculation.strategies.comparator, result.calculation.strategies.intervention];
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
      <div className="mt-4 overflow-hidden rounded-input border border-border">
        <table className="w-full text-[10px]">
          <thead className="bg-bg text-muted">
            <tr><th className="px-2 py-2 text-left font-medium">{t("result.strategy")}</th><th className="px-2 py-2 text-right font-medium">{t("result.cost")}</th><th className="px-2 py-2 text-right font-medium">{t("result.qaly")}</th></tr>
          </thead>
          <tbody>
            {rows.map((row) => <tr key={row.name} className="border-t border-border"><td className="px-2 py-2 font-mono text-text">{row.name}</td><td className="px-2 py-2 text-right tabular-nums text-text">{currency.format(row.total_cost)}</td><td className="px-2 py-2 text-right tabular-nums text-text">{number.format(row.total_qaly)}</td></tr>)}
          </tbody>
        </table>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Metric label={t("result.deltaCost")} value={currency.format(result.calculation.incremental.delta_cost)} />
        <Metric label={t("result.deltaQaly")} value={number.format(result.calculation.incremental.delta_qaly)} />
        <Metric label={t("result.icer")} value={result.calculation.incremental.icer === null ? "—" : currency.format(result.calculation.incremental.icer)} accent />
      </div>
      <details className="mt-3 text-[10px] text-muted">
        <summary className="cursor-pointer font-medium text-text">{t("result.warnings")} ({result.calculation.warnings.length})</summary>
        <ul className="mt-2 list-disc space-y-1 pl-4 leading-4">{result.calculation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      </details>
    </section>
  );
}

function UncertaintyResultCard({
  result,
  locale,
}: {
  result: HeorUncertaintyRunResult;
  locale: string;
}) {
  const { t } = useTranslation("heor");
  const currency = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0,
  });
  const probability = new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  });
  const calculation = result.calculation;
  const psa = calculation.probabilistic_analysis;
  const authorized = result.workflow.classification !== "exploratory";
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
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Metric
          label={t("uncertaintyResult.probability")}
          value={probability.format(psa.cost_effective_probability)}
          accent
        />
        <Metric
          label={t("uncertaintyResult.meanInmb")}
          value={currency.format(psa.mean_incremental_net_monetary_benefit)}
        />
        <Metric
          label={t("uncertaintyResult.iterations")}
          value={psa.iterations.toLocaleString(locale)}
        />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Metric
          label={t("uncertaintyResult.parameters")}
          value={String(calculation.deterministic_analysis.length)}
        />
        <Metric
          label={t("uncertaintyResult.scenarios")}
          value={String(calculation.structural_scenarios.length)}
        />
      </div>
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

function BudgetImpactResultCard({
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
          {calculation.price_year} {calculation.currency} · {t("budgetImpact.noDiscount")}
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

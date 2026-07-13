import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  Check,
  Circle,
  FileJson,
  Loader2,
  LockKeyhole,
  MessageSquareText,
  Play,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { readArtifact } from "@/lib/artifactFile";
import { cn } from "@/lib/cn";
import {
  appendHeorApproval,
  auditHeorConceptualModel,
  auditHeorEvidence,
  browserDemoRun,
  HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL,
  HEOR_BROWSER_DEMO_PLAN,
  HEOR_CONCEPTUAL_MODEL_PATH,
  HEOR_PLAN_PATH,
  type HeorAnalysisPlan,
  type HeorApprovalAction,
  type HeorApprovalEvent,
  type HeorApprovalLog,
  type HeorConceptualModel,
  type HeorConceptualModelAudit,
  type HeorGate,
  type HeorRunResult,
  listHeorApprovals,
  parseHeorConceptualModel,
  parseHeorPlan,
  runHeorMarkov,
  sha256Text,
} from "@/lib/heor";
import { isTauri } from "@/lib/tauri";
import { toast } from "@/lib/toast";
import { MaximizePaneButton, PaneTitlebarInset } from "@/components/inspector/RightPane";

const REVIEW_GATES: HeorGate[] = ["decision_problem", "conceptual_model", "analysis_plan"];
const ALL_GATES: HeorGate[] = [...REVIEW_GATES, "independent_validation", "release"];

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

type ReviewIntent = {
  action: HeorApprovalAction;
  gate: HeorGate;
  artifactSha256: string;
};

function gateArtifactHash(
  gate: HeorGate,
  planArtifact: ArtifactState,
  conceptualArtifact: ConceptualArtifactState,
): string | null {
  if (planArtifact.kind !== "ready") return null;
  if (gate === "conceptual_model") {
    return conceptualArtifact.kind === "ready" ? conceptualArtifact.sha256 : null;
  }
  return planArtifact.sha256;
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
  const [approvals, setApprovals] = useState<HeorApprovalLog>(EMPTY_LOG);
  const [result, setResult] = useState<HeorRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [intent, setIntent] = useState<ReviewIntent | null>(null);

  const refresh = useCallback(async () => {
    setResult(null);
    if (!project) {
      setArtifact({ kind: "missing" });
      setConceptualArtifact({ kind: "missing" });
      setApprovals(EMPTY_LOG);
      return;
    }
    setArtifact({ kind: "loading" });
    setConceptualArtifact({ kind: "loading" });
    try {
      const raw = isTauri
        ? (await readArtifact(HEOR_PLAN_PATH))?.data ?? null
        : JSON.stringify(HEOR_BROWSER_DEMO_PLAN, null, 2);
      if (raw === null) {
        setArtifact({ kind: "missing" });
        setApprovals(await listHeorApprovals(project.id));
        return;
      }
      const plan = parseHeorPlan(raw);
      const sha256 = await sha256Text(raw);
      setArtifact({ kind: "ready", plan, raw, sha256 });
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
      const artifactSha256 = gateArtifactHash(gate, artifact, conceptualArtifact);
      if (!artifactSha256) break;
      if (gate === "conceptual_model"
        && conceptualArtifact.kind === "ready"
        && !conceptualArtifact.audit.complete) break;
      if (gate === "analysis_plan" && !auditHeorEvidence(artifact.plan).complete) break;
      const event = latest.get(gate);
      if (
        !event ||
        event.action !== "approve" ||
        event.artifactSha256 !== artifactSha256 ||
        event.sequence <= previousSequence
      ) {
        break;
      }
      effective.push(gate);
      previousSequence = event.sequence;
    }
    return effective;
  }, [approvals.events, artifact, conceptualArtifact]);

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
    const eventHash = await sha256Text(
      JSON.stringify({ sequence, action, gate, artifactSha256, actorLabel, rationale }),
    );
    const event: HeorApprovalEvent = {
      schemaVersion: 1,
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
      toast.success(t("toast.runComplete"));
    } catch (error) {
      toast.error(`${t("toast.actionFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setRunning(false);
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
        <StageRail currentApprovals={currentApprovals} hasResult={!!result} />

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

            <section className="border-b border-border px-5 py-4">
              <div className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-muted">
                {t("reviewSection")}
              </div>
              <div className="space-y-2">
                {REVIEW_GATES.map((gate, index) => {
                  const approved = currentApprovals.includes(gate);
                  const artifactSha256 = gateArtifactHash(gate, artifact, conceptualArtifact);
                  const gateEvent = latest.get(gate);
                  const stale = approvals.effectiveApprovedGates.includes(gate)
                    && gateEvent?.action === "approve"
                    && gateEvent.artifactSha256 !== artifactSha256;
                  const conceptualBlocked = gate === "conceptual_model"
                    && gate === nextGate
                    && (conceptualArtifact.kind !== "ready" || !conceptualArtifact.audit.complete);
                  const evidenceBlocked = gate === "analysis_plan"
                    && gate === nextGate
                    && !evidenceAudit?.complete;
                  const waiting = gate === nextGate && !stale && !conceptualBlocked && !evidenceBlocked;
                  return (
                    <div key={gate} className="rounded-input border border-border bg-bg/50 px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        {approved ? (
                          <Check size={14} className="text-ok" />
                        ) : waiting || stale || conceptualBlocked || evidenceBlocked ? (
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
                            setIntent({ action: "approve", gate, artifactSha256: artifactSha256! })
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
            </section>

            {result && <ResultCard result={result} locale={i18n.language} />}

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
    { key: "validate", done: false },
    { key: "release", done: false },
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
  const [actor, setActor] = useState("");
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
          <input value={actor} onChange={(event) => setActor(event.target.value)} autoFocus placeholder={t("dialog.actorPlaceholder")} className="mt-1.5 w-full rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent" />
        </label>
        <label className="mt-3 block text-xs font-medium text-text">
          {t("dialog.rationale")}
          <textarea value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder={t("dialog.rationalePlaceholder")} rows={3} className="mt-1.5 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent" />
        </label>
        <label className="mt-3 flex items-start gap-2 text-xs leading-5 text-text">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="mt-1 accent-[var(--color-accent)]" />
          <span>{t("dialog.confirm")}</span>
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
  const authorized = result.workflow.classification === "analysis_authorized_local_assertion";
  const rows = [result.calculation.strategies.comparator, result.calculation.strategies.intervention];
  return (
    <section className="border-b border-border px-5 py-4">
      <div className="flex items-start gap-2">
        <ShieldCheck size={16} className={authorized ? "text-ok" : "text-accent"} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-text">{t("result.title")}</div>
          <div className={cn("mt-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]", authorized ? "text-ok" : "text-accent")}>
            {authorized ? t("result.authorized") : t("result.exploratory")}
          </div>
        </div>
        <span className="rounded-full border border-border bg-bg px-2 py-0.5 text-[9px] font-semibold uppercase text-muted">
          {t("status.notDecisionReady")}
        </span>
      </div>
      {authorized && <p className="mt-2 text-[10px] leading-4 text-muted">{t("result.authorizedNote")}</p>}
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

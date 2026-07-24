import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bot, Boxes, Check, Loader2, Package, Puzzle, RefreshCw, Settings2, ShieldCheck, X } from "lucide-react";
import { useRuntimeStore } from "@/lib/runtime";
import { useSetupStore } from "@/lib/setup";
import { useUiStore } from "@/lib/store";
import { cn } from "@/lib/cn";
import { localizeSkill } from "@/i18n/skillLocalization";
import { PreferenceLearningSection } from "@/components/skills/PreferenceLearningSection";
import {
  appendSkillCandidateReview,
  auditAssetAdmission,
  auditSkillCandidates,
  type AssetAdmissionAudit,
  type AssetAdmissionRecord,
  type SkillCandidateAudit,
  type SkillCandidateReviewAction,
  type SkillCandidateSummary,
  type JupyterStatus,
  isTauri,
  jupyterStatus,
  openExternal,
} from "@/lib/tauri";

/**
 * Runtime capabilities plus the app-owned external-adapter release registry.
 * Unresolved and excluded sources are internal engineering records, not user
 * choices. Only fully validated adapters may appear here.
 */
export function SkillsPage() {
  const { t, i18n } = useTranslation(["pages", "common", "skills"]);
  const navigate = useNavigate();
  const {
    skills,
    agents,
    tools,
    status,
    workspace,
    loadCatalog,
    detectTools,
    connectRetry,
    reviewAssetCandidate,
  } = useRuntimeStore();
  const connected = status === "ready";
  const [text, setText] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [admission, setAdmission] = useState<AssetAdmissionAudit | null>(null);
  const [admissionError, setAdmissionError] = useState(false);
  const [candidateAudit, setCandidateAudit] = useState<SkillCandidateAudit | null>(null);
  const [candidateError, setCandidateError] = useState(false);
  const [candidateLoading, setCandidateLoading] = useState(true);
  const [reviewTarget, setReviewTarget] = useState<SkillCandidateSummary | null>(null);
  const [reviewAction, setReviewAction] = useState<SkillCandidateReviewAction>("activate");
  const [reviewRunning, setReviewRunning] = useState(false);
  const [jupyter, setJupyter] = useState<JupyterStatus | null>(null);
  const jupyterBusy = useSetupStore((state) => state.jupyterBusy);
  const setupGeneration = useSetupStore((state) => state.generation);

  useEffect(() => {
    if (connected) void loadCatalog();
    void detectTools();
    if (isTauri) void jupyterStatus().then(setJupyter).catch(() => setJupyter(null));
  }, [connected, loadCatalog, detectTools, setupGeneration]);

  const openSkillTask = (name: string, label: string) => {
    const runtime = useRuntimeStore.getState();
    const currentProject = runtime.projects.find((project) => project.path === runtime.workspace);
    if (currentProject) void runtime.startDraftInWorkspace(currentProject.path);
    else runtime.startDraft();
    useUiStore.getState().setComposerDraft(null);
    useUiStore.getState().setComposerSkill({ id: name, label });
    navigate("/heor/new");
  };
  const visibleSkills = skills.filter((skill) => sourceOf(skill.location) !== "builtin");

  useEffect(() => {
    let current = true;
    void auditAssetAdmission()
      .then((result) => {
        if (current) setAdmission(result);
      })
      .catch(() => {
        if (current) setAdmissionError(true);
      });
    return () => {
      current = false;
    };
  }, []);

  const loadCandidates = useCallback(async () => {
    setCandidateLoading(true);
    setCandidateError(false);
    try {
      setCandidateAudit(await auditSkillCandidates());
    } catch {
      setCandidateError(true);
    } finally {
      setCandidateLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCandidates();
  }, [workspace, loadCandidates]);

  const onReview = async () => {
    if (!text.trim()) return;
    setReviewing(true);
    const id = await reviewAssetCandidate(text.trim());
    setReviewing(false);
    if (id) {
      setText("");
      navigate(`/heor/${id}`); // continue in the AI4HEOR research workspace
    }
  };

  const openCandidateReview = (candidate: SkillCandidateSummary, action: SkillCandidateReviewAction) => {
    setReviewTarget(candidate);
    setReviewAction(action);
  };

  const submitCandidateReview = async (actorLabel: string, rationale: string) => {
    if (!reviewTarget || !candidateAudit?.projectId) return;
    setReviewRunning(true);
    try {
      await appendSkillCandidateReview({
        projectId: candidateAudit.projectId,
        candidateId: reviewTarget.candidateId,
        decisionSha256: reviewTarget.decisionSha256,
        acceptanceChecksSha256: reviewTarget.acceptanceChecksSha256,
        action: reviewAction,
        actorLabel,
        rationale,
      });
      setReviewTarget(null);
      await loadCandidates();
      if (connected && reviewAction !== "reject") {
        await connectRetry();
      }
      if (connected) void loadCatalog();
    } catch {
      setCandidateError(true);
    } finally {
      setReviewRunning(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-8 py-8">
        <h1 className="text-xl font-semibold tracking-[-0.02em] text-text">{t("skills.title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("skills.description.prefix")}</p>

        {/* Natural-language work first: review and adapt, never install directly. */}
        <Section title={t("skills.install.sectionTitle")} icon={<Boxes size={15} />}>
          <div className="p-4">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={t("skills.install.placeholder")}
              rows={3}
              className="w-full resize-y rounded-input border border-border bg-surface px-3 py-2 text-sm text-text outline-none placeholder:text-muted"
            />
            <div className="mt-2 flex items-center gap-3">
              <button
                onClick={onReview}
                disabled={!connected || !text.trim() || reviewing}
                className="rounded-input bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg hover:opacity-90 disabled:opacity-40"
              >
                {reviewing ? t("skills.install.starting") : t("skills.install.cta")}
              </button>
              <span className="text-xs text-muted">
                {connected ? t("skills.install.hintConnected") : t("skills.install.hintDisconnected")}
              </span>
            </div>
          </div>
        </Section>

        <Section title={t("skills.candidates.sectionTitle")} icon={<ShieldCheck size={15} />}>
          <div className="flex items-start justify-between gap-3 px-4 py-3">
            <p className="text-xs leading-5 text-muted">{t("skills.candidates.boundary")}</p>
            <button
              type="button"
              aria-label={t("skills.candidates.refresh")}
              onClick={() => void loadCandidates()}
              disabled={candidateLoading}
              className="shrink-0 rounded-input border border-border p-1.5 text-muted hover:bg-surface-2 disabled:opacity-40"
            >
              <RefreshCw size={14} className={candidateLoading ? "animate-spin" : undefined} />
            </button>
          </div>
          {candidateError && <div className="px-4 py-3 text-xs text-danger">{t("skills.candidates.unavailable")}</div>}
          {candidateLoading && !candidateAudit && <Empty>{t("skills.candidates.loading")}</Empty>}
          {candidateAudit && !candidateAudit.projectAvailable && <Empty>{t("skills.candidates.noProject")}</Empty>}
          {candidateAudit?.projectAvailable && candidateAudit.candidates.length === 0 && (
            <Empty>{t("skills.candidates.empty")}</Empty>
          )}
          {candidateAudit?.errors.map((error) => (
            <div key={error} className="px-4 py-2 text-xs text-danger">{error}</div>
          ))}
          {candidateAudit?.candidates.map((candidate) => (
            <CandidateRow
              key={candidate.candidateId}
              candidate={candidate}
              locale={i18n.resolvedLanguage}
              onReview={openCandidateReview}
            />
          ))}
        </Section>

        <PreferenceLearningSection workspace={workspace} />

        <Section title={t("skills.assetAdmission.sectionTitle")} icon={<ShieldCheck size={15} />}>
          {admissionError && <Empty>{t("skills.assetAdmission.unavailable")}</Empty>}
          {!admission && !admissionError && <Empty>{t("skills.assetAdmission.loading")}</Empty>}
          {admission && (
            <>
              <div className="bg-surface-2 px-4 py-3">
                <p className="text-sm font-medium text-text">{t("skills.assetAdmission.firstPartyTitle")}</p>
                <p className="mt-1 text-xs leading-5 text-muted">{t("skills.assetAdmission.firstPartyBoundary")}</p>
              </div>
              <p className={cn("px-4 py-3 text-xs", admission.complete ? "text-muted" : "text-danger") }>
                {admission.complete
                  ? admission.admittedCount === 0
                    ? t("skills.assetAdmission.noneAdmitted")
                    : t("skills.assetAdmission.registryValid")
                  : t("skills.assetAdmission.failClosed")}
              </p>
              {admission.errors.map((error) => (
                <div key={error} className="px-4 py-2 text-xs text-danger">{error}</div>
              ))}
              {admission.assets.length > 0 && (
                <div>
                  <div className="bg-surface-2 px-4 py-2 text-xs font-medium text-text">
                    {t("skills.assetAdmission.groupAdmitted")}
                  </div>
                  {admission.assets.map((asset) => (
                    <AdmissionRow
                      key={asset.assetId}
                      asset={asset}
                      locale={i18n.resolvedLanguage}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </Section>

        {/* Environment (#2) */}
        <Section title={t("skills.environment.sectionTitle")} icon={<Package size={15} />}>
          {tools.length === 0 && <Empty>{t("skills.environment.detectionUnavailable")}</Empty>}
          {tools.filter((tool) => tool.name === "Python" || tool.name === "R").map((tool) => (
            <div key={tool.name} className="flex items-center gap-3 px-4 py-2.5 text-sm">
              {tool.found ? <Check size={15} className="text-ok" /> : <X size={15} className="text-muted" />}
              <span className="w-24 text-text">{tool.name}</span>
              <span className="flex-1 text-xs text-muted">
                {tool.found ? t("skills.environment.found") : t("skills.environment.notFound")}
              </span>
              {!tool.found && isTauri && tool.name === "Python" && (
                <button
                  type="button"
                  onClick={() => void useSetupStore.getState().enableJupyter()}
                  disabled={jupyterBusy}
                  className="inline-flex items-center gap-1.5 rounded-input border border-border px-2 py-1 text-xs text-text hover:bg-surface-2 disabled:opacity-40"
                >
                  {jupyterBusy && <Loader2 size={12} className="animate-spin" />}
                  {jupyterBusy
                    ? t("skills.environment.installing")
                    : t("skills.environment.installLocal")}
                </button>
              )}
              {!tool.found && isTauri && tool.name === "R" && (
                <button
                  type="button"
                  onClick={() => void openExternal("https://cran.r-project.org/")}
                  className="rounded-input border border-border px-2 py-1 text-xs text-text hover:bg-surface-2"
                >
                  {t("skills.environment.getR")}
                </button>
              )}
            </div>
          ))}
          {isTauri && (
            <div className="flex items-center gap-3 px-4 py-2.5 text-sm">
              {jupyter?.installed ? (
                <Check size={15} className="text-ok" />
              ) : (
                <Settings2 size={15} className="text-muted" />
              )}
              <span className="w-24 text-text">{t("skills.environment.jupyter")}</span>
              <span className="flex-1 text-xs text-muted">
                {jupyter?.installed ? t("skills.environment.ready") : t("skills.environment.optional")}
              </span>
              {!jupyter?.installed && (
                <button
                  type="button"
                  onClick={() => void useSetupStore.getState().enableJupyter()}
                  disabled={jupyterBusy}
                  className="inline-flex items-center gap-1.5 rounded-input border border-border px-2 py-1 text-xs text-text hover:bg-surface-2 disabled:opacity-40"
                >
                  {jupyterBusy && <Loader2 size={12} className="animate-spin" />}
                  {jupyterBusy
                    ? t("skills.environment.installing")
                    : t("skills.environment.installLocal")}
                </button>
              )}
            </div>
          )}
          <p className="px-4 py-2 text-xs text-muted">{t("skills.environment.note")}</p>
        </Section>

        {connected ? (
          <>
            <Section title={t("skills.agentsSection.sectionTitle")} icon={<Bot size={15} />}>
              {agents.length === 0 && <Empty>{t("skills.agentsSection.empty")}</Empty>}
              {agents.map((a) => {
                const mode = modeOf(a.mode);
                const modeLabel = mode ? t(`skills.agentsSection.agentMode.${mode}`) : a.mode;
                const description = t(`skills.agentsSection.catalog.${a.name}`, {
                  defaultValue: a.description,
                });
                return <RowItem key={a.name} name={a.name} desc={description} tag={modeLabel} />;
              })}
            </Section>
            <Section title={t("skills.skillsListSection.sectionTitle")} icon={<Puzzle size={15} />}>
              {visibleSkills.length === 0 && (
                <Empty>{t("skills.skillsListSection.empty")}</Empty>
              )}
              {visibleSkills.map((s) => {
                const copy = localizeSkill(s.name, s.description, i18n.resolvedLanguage);
                const source = sourceOf(s.location);
                const sourceLabel = source === "project"
                  ? t("skills.skillsListSection.source.project")
                  : undefined;
                return (
                  <RowItem
                    key={s.name}
                    name={copy.displayName}
                    code={copy.localized ? `$${s.name}` : undefined}
                    desc={copy.description}
                    tag={sourceLabel}
                    actionLabel={t("skills.skillsListSection.use")}
                    onAction={() => openSkillTask(s.name, copy.displayName)}
                  />
                );
              })}
            </Section>
          </>
        ) : (
          <div className="mt-6 rounded-card border border-border bg-surface p-5 text-sm text-muted">
            {t("skills.disconnected")}
          </div>
        )}
      </div>
      {reviewTarget && (
        <CandidateReviewDialog
          candidate={reviewTarget}
          locale={i18n.resolvedLanguage}
          action={reviewAction}
          running={reviewRunning}
          onCancel={() => !reviewRunning && setReviewTarget(null)}
          onSubmit={(actor, rationale) => void submitCandidateReview(actor, rationale)}
        />
      )}
    </div>
  );
}

function candidateCopy(candidate: SkillCandidateSummary, locale?: string): {
  name: string;
  description: string;
  licenseNote: string;
  limitations: string[];
  acceptanceChecks: string[];
} {
  const normalized = locale?.toLowerCase();
  const exact = locale ? candidate.localized[locale] : undefined;
  const language = Object.entries(candidate.localized).find(([key]) =>
    normalized?.startsWith(key.toLowerCase().split("-")[0]),
  )?.[1];
  const copy = exact ?? language ?? candidate.localized["zh-Hans"] ?? candidate.localized.en;
  return {
    name: copy?.displayName ?? candidate.candidateId,
    description: copy?.description ?? candidate.request,
    licenseNote: copy?.licenseNote ?? candidate.licenseNote,
    limitations: copy?.limitations ?? [],
    acceptanceChecks: copy?.acceptanceChecks ?? [],
  };
}

function CandidateRow({
  candidate,
  locale,
  onReview,
}: {
  candidate: SkillCandidateSummary;
  locale?: string;
  onReview: (candidate: SkillCandidateSummary, action: SkillCandidateReviewAction) => void;
}) {
  const { t } = useTranslation("pages");
  const copy = candidateCopy(candidate, locale);
  return (
    <div className="px-4 py-3">
      <div className="flex items-start gap-3">
        {candidate.valid ? (
          <Check size={16} className="mt-0.5 shrink-0 text-ok" />
        ) : (
          <X size={16} className="mt-0.5 shrink-0 text-danger" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-text">{copy.name}</span>
            <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted ring-1 ring-border">
              {t(`skills.candidates.status.${candidateStatus(candidate.status)}`)}
            </span>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted">{copy.description}</p>
          {candidate.validationErrors.map((error) => (
            <p key={error} className="mt-2 text-xs text-danger">{error}</p>
          ))}
        </div>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        {candidate.canReject && (
          <button
            type="button"
            onClick={() => onReview(candidate, "reject")}
            className="rounded-input border border-border px-3 py-1.5 text-xs font-medium text-muted hover:bg-surface-2"
          >
            {t("skills.candidates.reject")}
          </button>
        )}
        {candidate.canRevoke && (
          <button
            type="button"
            onClick={() => onReview(candidate, "revoke")}
            className="rounded-input border border-danger/40 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/5"
          >
            {t("skills.candidates.revoke")}
          </button>
        )}
        {candidate.canActivate && (
          <button
            type="button"
            onClick={() => onReview(candidate, "activate")}
            className="rounded-input bg-accent px-3 py-1.5 text-xs font-semibold text-white"
          >
            {t("skills.candidates.activate")}
          </button>
        )}
      </div>
    </div>
  );
}

type CandidateStatus =
  | "inactive"
  | "active"
  | "rejected"
  | "revoked"
  | "invalid"
  | "drifted"
  | "activeCandidateChanged"
  | "unmanagedConflict"
  | "candidateMissing";

function candidateStatus(status: string): CandidateStatus {
  switch (status) {
    case "active":
    case "rejected":
    case "revoked":
    case "invalid":
    case "drifted":
    case "inactive":
      return status;
    case "active_candidate_changed":
      return "activeCandidateChanged";
    case "unmanaged_conflict":
      return "unmanagedConflict";
    case "candidate_missing":
      return "candidateMissing";
    default:
      return "invalid";
  }
}

function CandidateReviewDialog({
  candidate,
  locale,
  action,
  running,
  onCancel,
  onSubmit,
}: {
  candidate: SkillCandidateSummary;
  locale?: string;
  action: SkillCandidateReviewAction;
  running: boolean;
  onCancel: () => void;
  onSubmit: (actor: string, rationale: string) => void;
}) {
  const { t } = useTranslation("pages");
  const copy = candidateCopy(candidate, locale);
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onClick={onCancel}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t(`skills.candidates.dialog.title.${action}`)}
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-card border border-border bg-surface p-5 shadow-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2 text-sm font-semibold text-text">
          <ShieldCheck size={17} className="text-accent" />
          {t(`skills.candidates.dialog.title.${action}`)}
        </div>
        <p className="mt-2 text-xs leading-5 text-text">{t(`skills.candidates.dialog.purpose.${action}`)}</p>
        <p className="mt-2 text-xs leading-5 text-muted">{t(`skills.candidates.dialog.boundary.${action}`)}</p>
        <div className="mt-3 rounded-input border border-border bg-bg p-3">
          <div className="text-[10px] font-medium uppercase tracking-[0.12em] text-muted">
            {t("skills.candidates.dialog.capabilityTitle")}
          </div>
          <div className="mt-1 text-sm font-semibold text-text">{copy.name}</div>
          <p className="mt-1 text-xs leading-5 text-muted">{copy.description}</p>
          <div className="mt-3 text-[10px] font-medium text-muted">
            {t("skills.candidates.dialog.requestTitle")}
          </div>
          <p className="mt-1 break-words text-xs leading-5 text-text">{candidate.request}</p>
        </div>
        {action !== "revoke" && (
          <>
            <div className="mt-4 text-xs font-medium text-text">{t("skills.candidates.dialog.acceptanceTitle")}</div>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-xs leading-5 text-muted">
              {copy.acceptanceChecks.map((check) => <li key={check}>{check}</li>)}
            </ul>
            <div className="mt-4 text-xs font-medium text-text">{t("skills.candidates.dialog.limitationsTitle")}</div>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-xs leading-5 text-muted">
              {copy.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
            </ul>
            <div className="mt-4 text-xs font-medium text-text">{t("skills.candidates.dialog.licenseTitle")}</div>
            <p className="mt-1 text-xs leading-5 text-muted">{copy.licenseNote}</p>
          </>
        )}
        <details className="mt-4 rounded-input border border-border bg-bg px-3 py-2 text-xs text-muted">
          <summary className="cursor-pointer font-medium text-text">
            {t("skills.candidates.dialog.technicalDetails")}
          </summary>
          <dl className="mt-3 grid grid-cols-[auto,minmax(0,1fr)] gap-x-3 gap-y-2 leading-5">
            <dt>{t("skills.candidates.dialog.technical.candidateId")}</dt>
            <dd className="break-all font-mono text-text">${candidate.candidateId}</dd>
            <dt>{t("skills.candidates.dialog.technical.provider")}</dt>
            <dd className="break-all text-text">{candidate.provider}</dd>
            <dt>{t("skills.candidates.dialog.technical.model")}</dt>
            <dd className="break-all text-text">{candidate.model}</dd>
            <dt>{t("skills.candidates.dialog.technical.license")}</dt>
            <dd className="break-all font-mono text-text">{candidate.licenseSpdx}</dd>
            <dt>{t("skills.candidates.dialog.technical.decisionHash")}</dt>
            <dd className="break-all font-mono text-[10px] text-text">{candidate.decisionSha256}</dd>
          </dl>
        </details>
        <label className="mt-4 block text-xs font-medium text-text">
          {t("skills.candidates.dialog.actor")}
          <input
            value={actor}
            onChange={(event) => setActor(event.target.value)}
            autoFocus
            placeholder={t("skills.candidates.dialog.actorPlaceholder")}
            className="mt-1.5 w-full rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent"
          />
        </label>
        <label className="mt-3 block text-xs font-medium text-text">
          {t("skills.candidates.dialog.rationale")}
          <textarea
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            placeholder={t(`skills.candidates.dialog.rationalePlaceholder.${action}`)}
            rows={3}
            className="mt-1.5 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent"
          />
        </label>
        <label className="mt-3 flex items-start gap-2 text-xs leading-5 text-text">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
            className="mt-1 accent-[var(--color-accent)]"
          />
          <span>{t(`skills.candidates.dialog.confirm.${action}`)}</span>
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            disabled={running}
            onClick={onCancel}
            className="rounded-input border border-border px-3 py-1.5 text-xs font-medium text-text hover:bg-surface-2 disabled:opacity-40"
          >
            {t("skills.candidates.dialog.cancel")}
          </button>
          <button
            type="button"
            disabled={!valid}
            onClick={() => onSubmit(actor.trim(), rationale.trim())}
            className="rounded-input bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
          >
            {running ? t("skills.candidates.dialog.recording") : t(`skills.candidates.dialog.submit.${action}`)}
          </button>
        </div>
      </div>
    </div>
  );
}

type SkillSource = "builtin" | "project" | "bundled";

function sourceOf(location?: string): SkillSource | undefined {
  if (!location) return undefined;
  const normalized = location.split("\\").join("/");
  if (normalized.includes("/builtin/")) return "builtin";
  if (normalized.includes("/.opencode/")) return "project";
  return "bundled";
}

// AgentInfo.mode is typed `string` (external SDK), but OpenCode only ever
// emits "primary" | "subagent" | "all" — see useRuntimeStore's a.mode ===
// "primary" check. Narrow to the known set so we can translate it; unknown
// values (future SDK additions) fall back to the raw string at the call site.
type AgentMode = "primary" | "subagent" | "all";

function modeOf(mode?: string): AgentMode | undefined {
  return mode === "primary" || mode === "subagent" || mode === "all" ? mode : undefined;
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted">
        {icon} {title}
      </h2>
      <div className="divide-y divide-border overflow-hidden rounded-card border border-border bg-surface">
        {children}
      </div>
    </section>
  );
}

function RowItem({
  name,
  desc,
  tag,
  code,
  actionLabel,
  onAction,
}: {
  name: string;
  desc: string;
  tag?: string;
  code?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex items-start gap-3 px-4 py-3">
      <Package size={16} className="mt-0.5 shrink-0 text-muted" />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-baseline gap-2">
          <div className="truncate text-sm font-medium text-text">{name}</div>
          {code && <span className="truncate font-mono text-[10.5px] text-muted">{code}</span>}
        </div>
        <div className={cn("text-xs text-muted", "line-clamp-2")}>{desc}</div>
      </div>
      {tag && (
        <span className="shrink-0 rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted ring-1 ring-border">
          {tag}
        </span>
      )}
      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="shrink-0 rounded-input border border-border px-2.5 py-1 text-xs font-medium text-text hover:border-accent/40 hover:bg-surface-2"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}

function AdmissionRow({
  asset,
  locale,
}: {
  asset: AssetAdmissionRecord;
  locale: string | null | undefined;
}) {
  const { t } = useTranslation("pages");
  const skillName = asset.assetId.split("/").slice(-1)[0] ?? asset.assetId;
  const copy = localizeSkill(skillName, "", locale);
  return (
    <div className="flex items-start gap-3 px-4 py-3">
      <Check size={16} className="mt-0.5 shrink-0 text-ok" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-text">{asset.displayName}</span>
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted ring-1 ring-border">
            {t("skills.assetAdmission.admitted")}
          </span>
          <span className="font-mono text-[11px] text-muted">{asset.licenseSpdx}</span>
        </div>
        <p className="mt-1 text-xs leading-5 text-muted">{copy.description}</p>
        <p className="mt-1 text-[11px] leading-5 text-muted/80">
          {t("skills.assetAdmission.adapterBoundary")}
        </p>
      </div>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="px-4 py-6 text-center text-sm text-muted">{children}</div>;
}

import { useCallback, useEffect, useState } from "react";
import { Check, RefreshCw, Settings2, ShieldCheck, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  appendLocalPreferenceReview,
  auditLocalPreferences,
  type AcceptedPreferenceSummary,
  type PreferenceAudit,
  type PreferenceProposalSummary,
  type PreferenceReviewAction,
} from "@/lib/tauri";

type ReviewTarget =
  | { action: "accept"; proposal: PreferenceProposalSummary }
  | { action: Exclude<PreferenceReviewAction, "accept">; preference: AcceptedPreferenceSummary };

const ACCEPT_ACTION = "accept" as const;

export function PreferenceLearningSection({ workspace }: { workspace: string | null }) {
  const { t } = useTranslation("pages");
  const [audit, setAudit] = useState<PreferenceAudit | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [target, setTarget] = useState<ReviewTarget | null>(null);
  const [reviewing, setReviewing] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      setAudit(await auditLocalPreferences());
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [workspace, refresh]);

  const submit = async (rule: string, actorLabel: string, rationale: string) => {
    if (!target || !audit?.projectId) return;
    const preference = "preference" in target ? target.preference : undefined;
    const proposal = "proposal" in target ? target.proposal : undefined;
    setReviewing(true);
    try {
      await appendLocalPreferenceReview({
        projectId: audit.projectId,
        preferenceId: proposal?.proposalId ?? preference!.id,
        proposalSha256: proposal?.proposalSha256 ?? preference!.sourceProposalSha256,
        storeSha256: audit.storeSha256,
        action: target.action,
        rule,
        actorLabel,
        rationale,
      });
      setTarget(null);
      await refresh();
    } catch {
      setFailed(true);
    } finally {
      setReviewing(false);
    }
  };

  const empty = audit?.projectAvailable && audit.proposals.length === 0 && audit.preferences.length === 0;
  return (
    <section className="mt-6">
      <h2 className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted">
        <Settings2 size={15} /> {t("skills.preferences.sectionTitle")}
      </h2>
      <div className="divide-y divide-border overflow-hidden rounded-card border border-border bg-surface">
        <div className="flex items-start justify-between gap-3 px-4 py-3">
          <p className="text-xs leading-5 text-muted">{t("skills.preferences.boundary")}</p>
          <button
            type="button"
            aria-label={t("skills.preferences.refresh")}
            onClick={() => void refresh()}
            disabled={loading}
            className="shrink-0 rounded-input border border-border p-1.5 text-muted hover:bg-surface-2 disabled:opacity-40"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : undefined} />
          </button>
        </div>
        {failed && <PreferenceEmpty danger>{t("skills.preferences.unavailable")}</PreferenceEmpty>}
        {loading && !audit && <PreferenceEmpty>{t("skills.preferences.loading")}</PreferenceEmpty>}
        {audit && !audit.projectAvailable && <PreferenceEmpty>{t("skills.preferences.noProject")}</PreferenceEmpty>}
        {empty && <PreferenceEmpty>{t("skills.preferences.empty")}</PreferenceEmpty>}
        {audit?.errors.map((error) => <PreferenceEmpty key={error} danger>{error}</PreferenceEmpty>)}
        {audit?.proposals.map((proposal) => (
          <ProposalRow key={proposal.proposalId} proposal={proposal} onAccept={() => setTarget({ action: ACCEPT_ACTION, proposal })} />
        ))}
        {audit?.preferences.map((preference) => (
          <PreferenceRow
            key={preference.id}
            preference={preference}
            onAction={(action) => setTarget({ action, preference })}
          />
        ))}
      </div>
      {target && (
        <PreferenceReviewDialog
          target={target}
          running={reviewing}
          onCancel={() => !reviewing && setTarget(null)}
          onSubmit={(rule, actor, rationale) => void submit(rule, actor, rationale)}
        />
      )}
    </section>
  );
}

function ProposalRow({ proposal, onAccept }: { proposal: PreferenceProposalSummary; onAccept: () => void }) {
  const { t } = useTranslation("pages");
  const scope = preferenceScope(proposal.scope);
  return (
    <div className="px-4 py-3">
      <div className="flex items-start gap-3">
        {proposal.valid ? <Check size={16} className="mt-0.5 shrink-0 text-ok" /> : <X size={16} className="mt-0.5 shrink-0 text-danger" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-text">{t("skills.preferences.proposal")}</span>
            <span className="font-mono text-[10.5px] text-muted">{proposal.proposalId}</span>
            <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted ring-1 ring-border">
              {proposal.accepted ? t("skills.preferences.accepted") : scope ? t(`skills.preferences.scope.${scope}`) : proposal.scope}
            </span>
          </div>
          <p className="mt-1 text-xs leading-5 text-text">{proposal.proposedRule}</p>
          <p className="mt-1 text-[10.5px] leading-4 text-muted">
            {t("skills.preferences.evidenceCount", { count: proposal.evidence.length })} · {proposal.reviewCondition}
          </p>
          {proposal.validationErrors.map((error) => <p key={error} className="mt-2 text-xs text-danger">{error}</p>)}
        </div>
      </div>
      {proposal.valid && !proposal.accepted && (
        <div className="mt-3 flex justify-end">
          <button type="button" onClick={onAccept} className="rounded-input bg-accent px-3 py-1.5 text-xs font-semibold text-white">
            {t("skills.preferences.reviewAccept")}
          </button>
        </div>
      )}
    </div>
  );
}

type PreferenceScope = "language" | "presentation" | "workflow" | "audit";

function preferenceScope(scope: string): PreferenceScope | undefined {
  return scope === "language" || scope === "presentation" || scope === "workflow" || scope === "audit"
    ? scope
    : undefined;
}

function PreferenceRow({
  preference,
  onAction,
}: {
  preference: AcceptedPreferenceSummary;
  onAction: (action: Exclude<PreferenceReviewAction, "accept">) => void;
}) {
  const { t } = useTranslation("pages");
  return (
    <div className="px-4 py-3">
      <div className="flex items-start gap-3">
        <ShieldCheck size={16} className={preference.enabled ? "mt-0.5 shrink-0 text-ok" : "mt-0.5 shrink-0 text-muted"} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-text">{t("skills.preferences.current")}</span>
            <span className="font-mono text-[10.5px] text-muted">{preference.id}</span>
            <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted ring-1 ring-border">
              {preference.enabled ? t("skills.preferences.enabled") : t("skills.preferences.disabled")}
            </span>
          </div>
          <p className="mt-1 text-xs leading-5 text-text">{preference.rule}</p>
          <p className="mt-1 text-[10.5px] leading-4 text-muted">{preference.reviewCondition}</p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap justify-end gap-2">
        <button type="button" onClick={() => onAction("update")} className="rounded-input border border-border px-3 py-1.5 text-xs font-medium text-muted hover:bg-surface-2">
          {t("skills.preferences.edit")}
        </button>
        <button type="button" onClick={() => onAction(preference.enabled ? "disable" : "enable")} className="rounded-input border border-border px-3 py-1.5 text-xs font-medium text-muted hover:bg-surface-2">
          {preference.enabled ? t("skills.preferences.disable") : t("skills.preferences.enable")}
        </button>
        <button type="button" onClick={() => onAction("delete")} className="rounded-input border border-danger/40 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/5">
          {t("skills.preferences.delete")}
        </button>
      </div>
    </div>
  );
}

function PreferenceReviewDialog({
  target,
  running,
  onCancel,
  onSubmit,
}: {
  target: ReviewTarget;
  running: boolean;
  onCancel: () => void;
  onSubmit: (rule: string, actor: string, rationale: string) => void;
}) {
  const { t } = useTranslation("pages");
  const initialRule = "proposal" in target ? target.proposal.proposedRule : target.preference.rule;
  const [rule, setRule] = useState(initialRule);
  const [actor, setActor] = useState("");
  const [rationale, setRationale] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const editable = target.action === "accept" || target.action === "update";
  const valid = rule.trim().length > 0 && actor.trim().length > 0 && rationale.trim().length > 1 && confirmed && !running;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && !running && onCancel();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel, running]);
  const evidence = "proposal" in target ? target.proposal.evidence : [];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onCancel} role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t(`skills.preferences.dialog.title.${target.action}`)}
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-card border border-border bg-surface p-5 shadow-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2 text-sm font-semibold text-text">
          <Settings2 size={17} className="text-accent" />
          {t(`skills.preferences.dialog.title.${target.action}`)}
        </div>
        <p className="mt-2 text-xs leading-5 text-muted">{t(`skills.preferences.dialog.boundary.${target.action}`)}</p>
        {evidence.length > 0 && (
          <div className="mt-4">
            <div className="text-xs font-medium text-text">{t("skills.preferences.dialog.evidence")}</div>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-xs leading-5 text-muted">
              {evidence.map((item) => <li key={item.interactionRef}>{item.summary}</li>)}
            </ul>
          </div>
        )}
        <label className="mt-4 block text-xs font-medium text-text">
          {t("skills.preferences.dialog.rule")}
          <textarea
            value={rule}
            onChange={(event) => setRule(event.target.value)}
            readOnly={!editable}
            rows={3}
            className="mt-1.5 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none read-only:text-muted focus:border-accent"
          />
        </label>
        <label className="mt-3 block text-xs font-medium text-text">
          {t("skills.preferences.dialog.actor")}
          <input
            value={actor}
            onChange={(event) => setActor(event.target.value)}
            autoFocus
            placeholder={t("skills.preferences.dialog.actorPlaceholder")}
            className="mt-1.5 w-full rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent"
          />
        </label>
        <label className="mt-3 block text-xs font-medium text-text">
          {t("skills.preferences.dialog.rationale")}
          <textarea
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            placeholder={t(`skills.preferences.dialog.rationalePlaceholder.${target.action}`)}
            rows={3}
            className="mt-1.5 w-full resize-none rounded-input border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent"
          />
        </label>
        <label className="mt-3 flex items-start gap-2 text-xs leading-5 text-text">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="mt-1 accent-[var(--color-accent)]" />
          <span>{t(`skills.preferences.dialog.confirm.${target.action}`)}</span>
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" disabled={running} onClick={onCancel} className="rounded-input border border-border px-3 py-1.5 text-xs font-medium text-text hover:bg-surface-2 disabled:opacity-40">
            {t("skills.preferences.dialog.cancel")}
          </button>
          <button type="button" disabled={!valid} onClick={() => onSubmit(rule.trim(), actor.trim(), rationale.trim())} className="rounded-input bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">
            {running ? t("skills.preferences.dialog.recording") : t(`skills.preferences.dialog.submit.${target.action}`)}
          </button>
        </div>
      </div>
    </div>
  );
}

function PreferenceEmpty({ children, danger = false }: { children: React.ReactNode; danger?: boolean }) {
  return <div className={`px-4 py-5 text-center text-sm ${danger ? "text-danger" : "text-muted"}`}>{children}</div>;
}

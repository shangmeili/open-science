import { ClipboardCheck, ExternalLink, FileJson2, Loader2, MessageSquareText, WandSparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { openArtifactExternally } from "@/lib/artifactFile";
import {
  JOURNAL_SUBMISSION_MANIFEST_PATH,
  type JournalSubmissionAudit,
} from "@/lib/heor";

export type JournalSubmissionState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: JournalSubmissionAudit };

export function JournalSubmissionAssessment({
  state,
  generating,
  onRequestPreparation,
  onGenerate,
}: {
  state: JournalSubmissionState;
  generating: boolean;
  onRequestPreparation: () => void;
  onGenerate: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const ready = audit?.readyToGenerate === true;
  const current = audit?.outputsCurrent === true;
  const issues = state.kind === "invalid"
    ? [state.message]
    : [...(audit?.errors ?? []), ...(audit?.warnings ?? [])];

  return (
    <section className="border-b border-border px-5 py-4" data-testid="journal-submission-assessment">
      <div className="flex items-start gap-2">
        <ClipboardCheck size={16} className="mt-0.5 shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("journalSubmission.title")}
          </div>
          <div className="mt-1 text-sm font-semibold text-text">
            {state.kind === "loading"
              ? t("journalSubmission.loading")
              : current
                ? t("journalSubmission.current")
                : ready
                  ? t("journalSubmission.ready")
                  : t("journalSubmission.missing")}
          </div>
          <p className="mt-1 text-xs leading-5 text-muted">{t("journalSubmission.note")}</p>
          {audit?.journalName && (
            <p className="mt-1 text-xs text-text">
              {audit.journalName} · {audit.articleType} · {t("journalSubmission.guideDate", { date: audit.guideAccessedOn })}
            </p>
          )}
        </div>
      </div>

      {audit && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
          <Metric label={t("journalSubmission.passed")} value={String(audit.passedCount)} />
          <Metric label={t("journalSubmission.requiredIssues")} value={String(audit.failedRequiredCount)} />
          <Metric label={t("journalSubmission.reviewIssues")} value={String(audit.reviewIssueCount)} />
          <Metric label={t("journalSubmission.unresolved")} value={String(audit.unresolvedCount)} />
        </div>
      )}

      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
          {issues.slice(0, 6).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        {!ready && state.kind !== "loading" && (
          <button
            type="button"
            onClick={onRequestPreparation}
            className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
          >
            <MessageSquareText size={13} /> {t("journalSubmission.askPrepare")}
          </button>
        )}
        {ready && !current && (
          <button
            type="button"
            onClick={onGenerate}
            disabled={generating}
            className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
          >
            {generating ? <Loader2 size={13} className="animate-spin" /> : <WandSparkles size={13} />}
            {generating ? t("journalSubmission.generating") : t("journalSubmission.generate")}
          </button>
        )}
        {current && audit && (
          <>
            <button
              type="button"
              onClick={() => void openArtifactExternally(audit.markdownPath)}
              className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
            >
              <ExternalLink size={13} /> {t("journalSubmission.openReport")}
            </button>
            <button
              type="button"
              onClick={() => void openArtifactExternally(audit.resultsPath)}
              className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
            >
              <FileJson2 size={13} /> {t("journalSubmission.openResults")}
            </button>
          </>
        )}
      </div>

      <div className="mt-2 truncate font-mono text-[10px] text-muted">
        {audit?.manifestPath ?? JOURNAL_SUBMISSION_MANIFEST_PATH}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-surface-2 px-2 py-2">
      <div className="text-sm font-semibold text-text">{value}</div>
      <div className="mt-0.5 text-[10px] leading-4 text-muted">{label}</div>
    </div>
  );
}

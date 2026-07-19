import { ExternalLink, FileText, Loader2, MessageSquareText, WandSparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { openArtifactExternally } from "@/lib/artifactFile";
import {
  RESEARCH_REPORT_MANIFEST_PATH,
  type ResearchReportAudit,
} from "@/lib/heor";

export type ResearchReportState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: ResearchReportAudit };

export function ResearchReportAssessment({
  state,
  generating,
  onRequestPreparation,
  onGenerate,
}: {
  state: ResearchReportState;
  generating: boolean;
  onRequestPreparation: () => void;
  onGenerate: () => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const ready = audit?.readyToGenerate === true;
  const current = audit?.outputsCurrent === true;
  const issues = state.kind === "invalid" ? [state.message] : audit?.errors ?? [];

  return (
    <section className="border-b border-border px-5 py-4" data-testid="research-report-assessment">
      <div className="flex items-start gap-2">
        <FileText size={16} className="mt-0.5 shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("reportExport.title")}
          </div>
          <div className="mt-1 text-sm font-semibold text-text">
            {state.kind === "loading"
              ? t("reportExport.loading")
              : current
                ? t("reportExport.current")
                : ready
                  ? t("reportExport.ready")
                  : t("reportExport.missing")}
          </div>
          <p className="mt-1 text-xs leading-5 text-muted">{t("reportExport.note")}</p>
        </div>
      </div>

      {audit && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
          <Metric label={t("reportExport.blocks")} value={String(audit.blockCount)} />
          <Metric label={t("reportExport.tables")} value={String(audit.tableCount)} />
          <Metric label={t("reportExport.pages")} value={audit.outputsCurrent ? String(audit.pdfPageCount) : "—"} />
          <Metric label={t("reportExport.workbookSheets")} value={audit.outputsCurrent ? String(audit.workbookSheetCount) : "—"} />
        </div>
      )}

      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-muted">
          {issues.slice(0, 5).map((issue) => <li key={issue}>• {issue}</li>)}
        </ul>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        {!ready && state.kind !== "loading" && (
          <button
            type="button"
            onClick={onRequestPreparation}
            className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
          >
            <MessageSquareText size={13} /> {t("reportExport.askPrepare")}
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
            {generating ? t("reportExport.generating") : t("reportExport.generate")}
          </button>
        )}
        {current && audit && (
          <>
            <button
              type="button"
              onClick={() => void openArtifactExternally(audit.docxPath)}
              className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
            >
              <ExternalLink size={13} /> {t("reportExport.openDocx")}
            </button>
            <button
              type="button"
              onClick={() => void openArtifactExternally(audit.pdfPath)}
              className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
            >
              <ExternalLink size={13} /> {t("reportExport.openPdf")}
            </button>
            <button
              type="button"
              onClick={() => void openArtifactExternally(audit.xlsxPath)}
              className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
            >
              <ExternalLink size={13} /> {t("reportExport.openXlsx")}
            </button>
          </>
        )}
      </div>

      <div className="mt-2 truncate font-mono text-[10px] text-muted">
        {audit?.manifestPath ?? RESEARCH_REPORT_MANIFEST_PATH}
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

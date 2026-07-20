import { ExternalLink, FolderOpen, Loader2, MessageSquareText, TableProperties, WandSparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { openArtifactExternally } from "@/lib/artifactFile";
import {
  RESEARCH_TABLES_MANIFEST_PATH,
  type ResearchTablesAudit,
} from "@/lib/heor";

export type ResearchTablesState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: ResearchTablesAudit };

export function ResearchTablesAssessment({
  state,
  generating,
  onRequestPreparation,
  onGenerate,
}: {
  state: ResearchTablesState;
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
    <section className="border-b border-border px-5 py-4" data-testid="research-tables-assessment">
      <div className="flex items-start gap-2">
        <TableProperties size={16} className="mt-0.5 shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("researchTables.title")}
          </div>
          <div className="mt-1 text-sm font-semibold text-text">
            {state.kind === "loading"
              ? t("researchTables.loading")
              : current
                ? t("researchTables.current")
                : ready
                  ? t("researchTables.ready")
                  : t("researchTables.missing")}
          </div>
          <p className="mt-1 text-xs leading-5 text-muted">{t("researchTables.note")}</p>
        </div>
      </div>

      {audit && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
          <Metric label={t("researchTables.tables")} value={String(audit.tableCount)} />
          <Metric label={t("researchTables.rows")} value={String(audit.rowCount)} />
          <Metric label={t("researchTables.sources")} value={String(audit.sourceCount)} />
          <Metric label={t("researchTables.csvFiles")} value={current ? String(audit.csvFileCount) : "—"} />
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
            <MessageSquareText size={13} /> {t("researchTables.askPrepare")}
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
            {generating ? t("researchTables.generating") : t("researchTables.generate")}
          </button>
        )}
        {current && audit && (
          <>
            <button
              type="button"
              onClick={() => void openArtifactExternally(audit.xlsxPath)}
              className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
            >
              <ExternalLink size={13} /> {t("researchTables.openXlsx")}
            </button>
            <button
              type="button"
              onClick={() => void openArtifactExternally(audit.csvDirectory)}
              className="flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
            >
              <FolderOpen size={13} /> {t("researchTables.openCsvFolder")}
            </button>
          </>
        )}
      </div>

      <div className="mt-2 truncate font-mono text-[10px] text-muted">
        {audit?.manifestPath ?? RESEARCH_TABLES_MANIFEST_PATH}
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

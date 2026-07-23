import { useState } from "react";
import { FileDown, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { exportSupportReport, isTauri } from "@/lib/tauri";
import { toast } from "@/lib/toast";

/**
 * A narrow product-support surface for acceptance testing. The native command
 * owns report contents and privacy invariants; this component only asks where
 * to save the generated JSON file.
 */
export function SupportReportCard() {
  const { t } = useTranslation("settings");
  const [exporting, setExporting] = useState(false);

  if (!isTauri) return null;

  const exportReport = async () => {
    setExporting(true);
    try {
      const result = await exportSupportReport();
      if (result.kind === "saved") toast.success(t("supportReport.saved"));
    } catch (error) {
      toast.error(
        `${t("supportReport.failed")}: ${error instanceof Error ? error.message : String(error)}`,
      );
    } finally {
      setExporting(false);
    }
  };

  return (
    <section className="mt-5 rounded-card border border-border bg-surface shadow-card">
      <header className="border-b border-border px-5 py-3">
        <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-text">{t("supportReport.title")}</h2>
        <p className="mt-0.5 text-xs text-muted">{t("supportReport.hint")}</p>
      </header>
      <div className="px-5 py-4">
        <p className="text-[13px] leading-relaxed text-muted">
          {t("supportReport.description")}
        </p>
        <button
          className="mt-3 inline-flex h-9 items-center gap-1.5 rounded-input bg-accent px-3.5 text-[13px] font-medium text-accent-fg transition-colors hover:bg-accent/90 disabled:bg-accent/50"
          onClick={() => void exportReport()}
          disabled={exporting}
        >
          {exporting ? <Loader2 size={13} className="animate-spin" /> : <FileDown size={13} />}
          {exporting ? t("supportReport.exporting") : t("supportReport.export")}
        </button>
      </div>
    </section>
  );
}

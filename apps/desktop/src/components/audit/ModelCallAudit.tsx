import { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { listModelCalls, type ModelCallRecord } from "@/lib/modelCalls";
import { cn } from "@/lib/cn";
import i18n from "@/i18n";

type LoadState = "idle" | "loading" | "ready" | "missing" | "error";

export function ModelCallAudit({
  assistantMessageId,
  sessionId,
}: {
  assistantMessageId: string;
  sessionId?: string;
}) {
  const { t } = useTranslation("common");
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<LoadState>("idle");
  const [record, setRecord] = useState<ModelCallRecord | null>(null);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (!next || state !== "idle") return;
    setState("loading");
    try {
      const records = await listModelCalls();
      const match = records.find(
        (candidate) =>
          candidate.messageId === assistantMessageId &&
          (!sessionId || candidate.sessionId === sessionId),
      );
      setRecord(match ?? null);
      setState(match ? "ready" : "missing");
    } catch {
      setRecord(null);
      setState("error");
    }
  };

  return (
    <div className="rounded-input bg-surface-2/60 text-xs">
      <button
        type="button"
        className="flex w-full items-center gap-1.5 px-2.5 py-2 text-left text-link hover:text-text"
        onClick={() => void toggle()}
        aria-expanded={open}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <span>{t("modelCallAudit.button")}</span>
      </button>
      {open && (
        <div className="border-t border-border-faint px-2.5 py-2.5">
          {state === "loading" && (
            <div className="flex items-center gap-2 text-muted">
              <Loader2 size={12} className="animate-spin" /> {t("modelCallAudit.loading")}
            </div>
          )}
          {state === "missing" && <p className="text-muted">{t("modelCallAudit.missing")}</p>}
          {state === "error" && <p className="text-error">{t("modelCallAudit.error")}</p>}
          {state === "ready" && record && <ModelCallDetails record={record} />}
        </div>
      )}
    </div>
  );
}

function ModelCallDetails({ record }: { record: ModelCallRecord }) {
  const { t } = useTranslation("common");
  const durationMs = Math.max(0, record.completedAt - record.createdAt);
  const tokenItems = [
    ["input", record.tokens.input],
    ["output", record.tokens.output],
    ["reasoning", record.tokens.reasoning],
    ["cacheRead", record.tokens.cacheRead],
    ["cacheWrite", record.tokens.cacheWrite],
  ] as const;

  return (
    <div className="space-y-2.5 text-muted">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-text">
          {record.providerId} / {record.modelId}
        </span>
        <span className="flex items-center gap-1 text-ok">
          <CheckCircle2 size={12} /> {t("modelCallAudit.verified")}
        </span>
      </div>
      <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1">
        <dt>{t("modelCallAudit.completedAt")}</dt>
        <dd className="text-text">{new Date(record.completedAt).toLocaleString(i18n.language)}</dd>
        <dt>{t("modelCallAudit.duration")}</dt>
        <dd className="text-text">{t("modelCallAudit.seconds", { value: (durationMs / 1000).toFixed(2) })}</dd>
        <dt>{t("modelCallAudit.cost")}</dt>
        <dd className="text-text">
          {formatCost(record.runtimeReportedCost)}
          <span className="ml-1 text-muted">({t("modelCallAudit.costUnit")})</span>
        </dd>
        {record.promptTemplateId && (
          <>
            <dt>{t("modelCallAudit.promptVersion")}</dt>
            <dd className="font-mono text-text">{record.promptTemplateId}</dd>
          </>
        )}
        {record.responseLanguage && (
          <>
            <dt>{t("modelCallAudit.responseLanguage")}</dt>
            <dd className="text-text">{record.responseLanguage}</dd>
          </>
        )}
      </dl>
      <div className="flex flex-wrap gap-1.5">
        {tokenItems.map(([key, value]) => (
          <span
            key={key}
            className={cn(
              "rounded bg-surface px-1.5 py-0.5 tabular-nums text-text",
              value === 0 && "text-muted",
            )}
          >
            {t(`modelCallAudit.tokens.${key}`)} {value.toLocaleString(i18n.language)}
          </span>
        ))}
      </div>
      {record.systemContextContract && (
        <p className="flex items-center gap-1 text-ok">
          <CheckCircle2 size={12} /> {t("modelCallAudit.constraintsRecorded")}
        </p>
      )}
    </div>
  );
}

function formatCost(value: number): string {
  return value.toLocaleString(i18n.language, { maximumFractionDigits: 8 });
}

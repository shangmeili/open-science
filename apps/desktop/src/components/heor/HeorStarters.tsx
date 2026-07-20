import {
  BookOpenCheck,
  CheckCircle2,
  FileSearch,
  GraduationCap,
  HeartPulse,
  Loader2,
  PlayCircle,
  Route,
  Search,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import {
  installExample,
  isTauri,
  runHeorTeachingExample,
  type TeachingExampleRunResult,
} from "@/lib/tauri";
import { toast } from "@/lib/toast";

export function HeorStarters({
  onPick,
  ensureWorkspace,
}: {
  onPick: (prompt: string) => void;
  /** A starter that writes files must first materialize the draft's local
   * research scope. This is not a project requirement. */
  ensureWorkspace?: () => Promise<boolean>;
}) {
  const { t, i18n } = useTranslation("heor");
  const [exampleReady, setExampleReady] = useState(false);
  const [confirmRun, setConfirmRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<TeachingExampleRunResult | null>(null);
  const items = [
    { key: "learn" as const, icon: GraduationCap, prepare: undefined },
    { key: "scope" as const, icon: Route, prepare: undefined },
    { key: "search" as const, icon: Search, prepare: undefined },
    { key: "inputs" as const, icon: FileSearch, prepare: undefined },
    { key: "audit" as const, icon: BookOpenCheck, prepare: undefined },
    {
      key: "example" as const,
      icon: HeartPulse,
      prepare: async () => {
        if (isTauri) {
          await installExample("heor-cost-effectiveness");
          setExampleReady(true);
        }
      },
    },
  ];

  return (
    <section className="fade-in py-8">
      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">
        {t("starter.eyebrow")}
      </div>
      <h1 className="mt-2 font-serif text-3xl font-semibold tracking-tight text-text">
        {t("starter.title")}
      </h1>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">{t("starter.body")}</p>
      <div className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">
        {items.map(({ key, icon: Icon, prepare }) => (
          <button
            key={key}
            type="button"
            onClick={() => {
              void (async () => {
                try {
                  if (prepare && ensureWorkspace && !(await ensureWorkspace())) return;
                  await prepare?.();
                } catch (error) {
                  toast.error(
                    t("starter.error.setup", {
                      message: error instanceof Error ? error.message : String(error),
                    }),
                  );
                  return;
                }
                onPick(t(`starter.${key}.prompt`));
              })();
            }}
            className="group rounded-card border border-border bg-surface p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-card"
          >
            <Icon size={18} strokeWidth={1.6} className="text-accent" />
            <div className="mt-3 text-sm font-semibold text-text">{t(`starter.${key}.title`)}</div>
            <p className="mt-1.5 text-xs leading-5 text-muted">{t(`starter.${key}.body`)}</p>
          </button>
        ))}
      </div>
      {isTauri && exampleReady && (
        <div className="mt-4 rounded-card border border-border bg-surface p-4 shadow-sm">
          <div className="flex items-start gap-3">
            {runResult ? (
              <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-accent" />
            ) : (
              <PlayCircle size={18} className="mt-0.5 shrink-0 text-accent" />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-text">
                {runResult ? t("starter.local.completedTitle") : t("starter.local.readyTitle")}
              </div>
              <p className="mt-1 text-xs leading-5 text-muted">
                {runResult ? t("starter.local.completedBody") : t("starter.local.readyBody")}
              </p>
              {runResult && (
                <div className="mt-3 grid gap-2 text-xs text-muted sm:grid-cols-3">
                  <ResultValue
                    label={t("starter.local.incrementalCost")}
                    value={formatNumber(runResult.baseCase.incrementalCostPerPerson, i18n.language)}
                  />
                  <ResultValue
                    label={t("starter.local.incrementalQalys")}
                    value={formatNumber(runResult.baseCase.incrementalQalysPerPerson, i18n.language, 6)}
                  />
                  <ResultValue
                    label={t("starter.local.icer")}
                    value={
                      runResult.baseCase.icerPerQaly === null
                        ? t("starter.local.notCalculated")
                      : formatNumber(runResult.baseCase.icerPerQaly, i18n.language)
                    }
                  />
                  <div className="sm:col-span-3">
                    <span className="font-medium text-text">
                      {t("starter.local.sensitivityRange")}:{" "}
                    </span>
                    <span className="font-mono">
                      {formatNullableNumber(
                        runResult.sensitivityLow.icerPerQaly,
                        i18n.language,
                        t("starter.local.notCalculated"),
                      )}
                      {" – "}
                      {formatNullableNumber(
                        runResult.sensitivityHigh.icerPerQaly,
                        i18n.language,
                        t("starter.local.notCalculated"),
                      )}
                    </span>
                  </div>
                  <div className="sm:col-span-3">
                    <span className="font-medium text-text">{t("starter.local.output")}: </span>
                    <code className="break-all">{runResult.baseCase.path}</code>
                  </div>
                  <div className="sm:col-span-3">
                    <span className="font-medium text-text">
                      {t("starter.local.checksum")}:{" "}
                    </span>
                    <code className="break-all">{runResult.baseCase.sha256}</code>
                  </div>
                  <div className="sm:col-span-3">
                    <span className="font-medium text-text">{t("starter.local.runRecord")}: </span>
                    <code>{runResult.runId}</code>
                  </div>
                </div>
              )}
            </div>
            <button
              type="button"
              disabled={running}
              onClick={() => setConfirmRun(true)}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-input border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text transition hover:border-accent/40 hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {running ? <Loader2 size={14} className="animate-spin" /> : <PlayCircle size={14} />}
              {running
                ? t("starter.local.running")
                : runResult
                  ? t("starter.local.runAgain")
                  : t("starter.local.runAction")}
            </button>
          </div>
        </div>
      )}
      {confirmRun && (
        <ConfirmDialog
          title={t("starter.local.confirmTitle")}
          body={t("starter.local.confirmBody")}
          confirmLabel={t("starter.local.confirmAction")}
          tone={PRIMARY_DIALOG_TONE}
          onCancel={() => setConfirmRun(false)}
          onConfirm={() => {
            setConfirmRun(false);
            setRunning(true);
            void runHeorTeachingExample()
              .then((result) => {
                setRunResult(result);
                toast.success(t("starter.local.success"));
              })
              .catch((error) => {
                toast.error(t(localRunErrorKey(error)));
              })
              .finally(() => setRunning(false));
          }}
        />
      )}
    </section>
  );
}

const PRIMARY_DIALOG_TONE = "primary" as const;

function localRunErrorKey(error: unknown):
  | "starter.error.inputChanged"
  | "starter.error.outputConflict"
  | "starter.error.pythonMissing"
  | "starter.error.runGeneric" {
  const message = error instanceof Error ? error.message : String(error);
  if (message.includes("differs from the bundled teaching example")) {
    return "starter.error.inputChanged";
  }
  if (message.includes("already exists with different bytes")) {
    return "starter.error.outputConflict";
  }
  if (message.includes("no Python found") || message.includes("configured Python")) {
    return "starter.error.pythonMissing";
  }
  return "starter.error.runGeneric";
}

function ResultValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-medium text-text">{label}</div>
      <div className="mt-0.5 font-mono">{value}</div>
    </div>
  );
}

function formatNumber(value: number, language: string, digits = 2): string {
  return new Intl.NumberFormat(language, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

function formatNullableNumber(
  value: number | null,
  language: string,
  notCalculated: string,
): string {
  return value === null ? notCalculated : formatNumber(value, language);
}

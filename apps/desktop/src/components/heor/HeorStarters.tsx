import {
  ArrowRight,
  BookOpenCheck,
  CheckCircle2,
  Circle,
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
import { installBundledHeorKnowledgeBase } from "@/lib/heor";
import {
  currentResearchScope,
  installExample,
  isTauri,
  runHeorTeachingExample,
  type TeachingExampleRunResult,
} from "@/lib/tauri";
import { toast } from "@/lib/toast";

export function HeorStarters({
  onPick,
  ensureWorkspace,
  desktopRuntime = isTauri,
}: {
  onPick: (prompt: string) => void;
  /** A starter that writes files must first materialize the draft's local
   * research scope. This is not a project requirement. */
  ensureWorkspace?: () => Promise<boolean>;
  /** Allows the browser preview and tests to render the honest non-installing
   * case outline even when the surrounding host provides compatibility shims. */
  desktopRuntime?: boolean;
}) {
  const { t, i18n } = useTranslation("heor");
  const [exampleReady, setExampleReady] = useState(false);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<TeachingExampleRunResult | null>(null);
  const workflowStages = [
    "workflowDecision",
    "workflowEvidence",
    "workflowModel",
    "workflowUncertainty",
    "workflowValidation",
    "workflowReporting",
  ] as const;
  const items = [
    {
      key: "learn" as const,
      icon: GraduationCap,
      tone: "text-[var(--series-1)]",
    },
    { key: "scope" as const, icon: Route, tone: "text-[var(--series-5)]" },
    { key: "search" as const, icon: Search, tone: "text-[var(--series-3)]" },
    { key: "inputs" as const, icon: FileSearch, tone: "text-[var(--series-6)]" },
    { key: "audit" as const, icon: BookOpenCheck, tone: "text-[var(--series-2)]" },
    {
      key: "example" as const,
      icon: HeartPulse,
      tone: "text-[var(--series-7)]",
    },
  ];

  return (
    <section className="fade-in py-8">
      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">
        {t("starter.eyebrow")}
      </div>
      <h1 className="mt-2 text-3xl font-semibold tracking-[-0.025em] text-text">
        {t("starter.title")}
      </h1>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">{t("starter.body")}</p>
      <div className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">
        {items.map(({ key, icon: Icon, tone }) => (
          <button
            key={key}
            type="button"
            onClick={() => {
              if (key === "example" && !desktopRuntime) {
                setExampleReady(true);
                return;
              }
              void (async () => {
                try {
                  if (key === "learn" && desktopRuntime) {
                    if (ensureWorkspace && !(await ensureWorkspace())) return;
                    const scope = await currentResearchScope();
                    if (!scope) throw new Error("research scope unavailable");
                    await installBundledHeorKnowledgeBase(scope.id);
                  }
                  if (key === "example") {
                    if (ensureWorkspace && !(await ensureWorkspace())) return;
                    await installExample("heor-cost-effectiveness");
                    setExampleReady(true);
                    return;
                  }
                } catch {
                  toast.error(t(key === "learn" ? "starter.error.learnSetup" : "starter.error.setup"));
                  return;
                }
                onPick(t(`starter.${key}.prompt`));
              })();
            }}
            className="group rounded-card border border-border bg-surface p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-card"
          >
            <Icon size={18} strokeWidth={1.6} className={tone} />
            <div className="mt-3 text-sm font-semibold text-text">{t(`starter.${key}.title`)}</div>
            <p className="mt-1.5 text-xs leading-5 text-muted">{t(`starter.${key}.body`)}</p>
          </button>
        ))}
      </div>
      {exampleReady && (
        <div className="mt-4 rounded-card border border-border bg-surface p-4 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
            {runResult ? (
              <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-accent" />
            ) : (
              <PlayCircle size={18} className="mt-0.5 shrink-0 text-accent" />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-text">
                {runResult
                  ? t("starter.local.completedTitle")
                  : desktopRuntime
                    ? t("starter.local.readyTitle")
                    : t("starter.local.previewTitle")}
              </div>
              <p className="mt-1 text-xs leading-5 text-muted">
                {runResult
                  ? t("starter.local.completedBody")
                  : desktopRuntime
                    ? t("starter.local.readyBody")
                    : t("starter.local.previewBody")}
              </p>
              <div className="mt-3 rounded-input bg-surface-2 px-3 py-2.5">
                <div className="text-xs font-medium text-text">{t("starter.local.caseQuestion")}</div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                  <span>{t("starter.local.stateStable")}</span>
                  <ArrowRight size={13} aria-hidden={true} />
                  <span>{t("starter.local.stateProgressed")}</span>
                  <ArrowRight size={13} aria-hidden={true} />
                  <span>{t("starter.local.stateDead")}</span>
                </div>
                <p className="mt-2 text-xs leading-5 text-muted">
                  {t("starter.local.caseAssumptions")}
                </p>
              </div>
              <div className="mt-3">
                <div className="text-xs font-medium text-text">
                  {t("starter.local.workflowTitle")}
                </div>
                <div className="mt-2 grid gap-x-4 gap-y-2 sm:grid-cols-2">
                  {workflowStages.map((stage) => (
                    <div key={stage} className="flex items-center gap-2 text-xs text-muted">
                      <Circle
                        size={11}
                        strokeWidth={1.8}
                        className="text-accent"
                        aria-hidden={true}
                      />
                      <span>{t(`starter.local.${stage}`)}</span>
                    </div>
                  ))}
                </div>
              </div>
              {runResult && (
                <div className="mt-4 space-y-3 text-xs text-muted">
                  <div className="grid gap-2 sm:grid-cols-3">
                    <ResultValue
                      label={t("starter.local.incrementalCost")}
                      value={formatNumber(runResult.baseCase.incrementalCostPerPerson, i18n.language)}
                    />
                    <ResultValue
                      label={t("starter.local.incrementalQalys")}
                      value={formatNumber(
                        runResult.baseCase.incrementalQalysPerPerson,
                        i18n.language,
                        6,
                      )}
                    />
                    <ResultValue
                      label={t("starter.local.icer")}
                      value={
                        runResult.baseCase.icerPerQaly === null
                          ? t("starter.local.notCalculated")
                          : formatNumber(runResult.baseCase.icerPerQaly, i18n.language)
                      }
                    />
                  </div>
                  <div>
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
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    <SummaryValue
                      label={t("starter.local.dsaSummary")}
                      value={t("starter.local.dsaValue", {
                        count: runResult.sensitivityParameterCount,
                      })}
                    />
                    <SummaryValue
                      label={t("starter.local.scenarioSummary")}
                      value={t("starter.local.scenarioValue", {
                        count: runResult.structuralScenarioCount,
                      })}
                    />
                    <SummaryValue
                      label={t("starter.local.psaSummary")}
                      value={t("starter.local.psaValue", {
                        iterations: formatInteger(
                          runResult.probabilisticIterations,
                          i18n.language,
                        ),
                        count: runResult.representedParameterCount,
                      })}
                    />
                    <SummaryValue
                      label={t("starter.local.validationSummary")}
                      value={t("starter.local.validationValue", {
                        passed: runResult.mechanicalChecksPassed,
                        total: runResult.mechanicalChecksTotal,
                      })}
                    />
                  </div>
                  <div className="rounded-input bg-surface-2 px-3 py-2.5">
                    <div className="font-medium text-text">{t("starter.local.positiveNmb")}</div>
                    <div className="mt-1 font-mono text-sm text-text">
                      {formatPercent(
                        runResult.probabilityPositiveIncrementalNmb,
                        i18n.language,
                      )}
                    </div>
                  </div>
                  <div className="rounded-input border border-accent/25 bg-accent/5 px-3 py-2.5">
                    <div className="font-medium text-text">
                      {t("starter.local.humanReviewTitle")}
                    </div>
                    <p className="mt-1 leading-5 text-muted">
                      {t("starter.local.humanReviewBody")}
                    </p>
                  </div>
                  <details className="rounded-input border border-border px-3 py-2">
                    <summary className="cursor-pointer select-none font-medium text-text">
                      {t("starter.local.technicalDetails")}
                    </summary>
                    <div className="mt-2 space-y-2">
                      <div>
                        <span className="font-medium text-text">{t("starter.local.output")}: </span>
                        <code className="break-all">{runResult.baseCase.path}</code>
                      </div>
                      <div>
                        <span className="font-medium text-text">
                          {t("starter.local.checksum")}:{" "}
                        </span>
                        <code className="break-all">{runResult.baseCase.sha256}</code>
                      </div>
                      <TechnicalArtifact
                        label={t("starter.local.report")}
                        path={runResult.reportPath}
                        sha256={runResult.reportSha256}
                        checksumLabel={t("starter.local.checksum")}
                      />
                      <TechnicalArtifact
                        label={t("starter.local.evidenceRegister")}
                        path={runResult.evidenceRegisterPath}
                        sha256={runResult.evidenceRegisterSha256}
                        checksumLabel={t("starter.local.checksum")}
                      />
                      <TechnicalArtifact
                        label={t("starter.local.reviewChecklist")}
                        path={runResult.reviewChecklistPath}
                        sha256={runResult.reviewChecklistSha256}
                        checksumLabel={t("starter.local.checksum")}
                      />
                      <div>
                        <span className="font-medium text-text">{t("starter.local.runRecord")}: </span>
                        <code>{runResult.runId}</code>
                      </div>
                    </div>
                  </details>
                </div>
              )}
            </div>
            <div className="flex w-full shrink-0 items-center justify-between gap-3 sm:w-auto sm:flex-col sm:items-end">
              {desktopRuntime ? (
                <button
                  type="button"
                  disabled={running}
                  onClick={() => {
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
                  className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-input bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {running ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <PlayCircle size={14} />
                  )}
                  {running
                    ? t("starter.local.running")
                    : runResult
                      ? t("starter.local.runAgain")
                      : t("starter.local.runAction")}
                </button>
              ) : (
                <div className="whitespace-nowrap rounded-input bg-surface-2 px-3 py-1.5 text-xs font-medium text-muted">
                  {t("starter.local.desktopOnly")}
                </div>
              )}
              <button
                type="button"
                disabled={running}
                onClick={() => onPick(t("starter.example.prompt"))}
                className="text-xs font-medium text-accent transition hover:text-accent-strong disabled:cursor-not-allowed disabled:opacity-60"
              >
                {t("starter.local.discussAction")}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

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

function SummaryValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-input bg-surface-2 px-3 py-2.5">
      <div className="font-medium text-text">{label}</div>
      <div className="mt-1 text-muted">{value}</div>
    </div>
  );
}

function TechnicalArtifact({
  label,
  path,
  sha256,
  checksumLabel,
}: {
  label: string;
  path: string;
  sha256: string;
  checksumLabel: string;
}) {
  return (
    <div>
      <span className="font-medium text-text">{label}: </span>
      <code className="break-all">{path}</code>
      <div className="mt-0.5 break-all font-mono text-[11px] text-muted">
        {checksumLabel}: {sha256}
      </div>
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

function formatPercent(value: number, language: string): string {
  return new Intl.NumberFormat(language, {
    style: "percent",
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
  }).format(value);
}

function formatInteger(value: number, language: string): string {
  return new Intl.NumberFormat(language, { maximumFractionDigits: 0 }).format(value);
}

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Circle,
  Loader2,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  auditStartupEnvironment,
  isTauri,
  type StartupEnvironmentAudit,
  type StartupEnvironmentCheck,
} from "@/lib/tauri";
import { useRuntimeStore } from "@/lib/runtime";
import { cn } from "@/lib/cn";

interface StartupReadinessProps {
  compact?: boolean;
  onOpenSettings?: () => void;
}

type AuditState =
  | { phase: "checking"; audit: null; error: null }
  | { phase: "ready"; audit: StartupEnvironmentAudit; error: null }
  | { phase: "error"; audit: null; error: string };

/**
 * Local startup readiness, not a scientific or model-provider check. The
 * compact form belongs in first use; the full form provides recovery in
 * Settings without turning the research conversation into a setup wizard.
 */
export function StartupReadiness({ compact = false, onOpenSettings }: StartupReadinessProps) {
  const { t } = useTranslation("settings");
  const runtimeStatus = useRuntimeStore((state) => state.status);
  const defaultModel = useRuntimeStore((state) => state.defaultModel);
  const restartLocalRuntime = useRuntimeStore((state) => state.restartLocalRuntime);
  const [state, setState] = useState<AuditState>({
    phase: "checking",
    audit: null,
    error: null,
  });
  const [recovering, setRecovering] = useState(false);

  const runAudit = useCallback(async () => {
    setState({ phase: "checking", audit: null, error: null });
    try {
      const audit = await auditStartupEnvironment();
      setState({ phase: "ready", audit, error: null });
    } catch (error) {
      setState({
        phase: "error",
        audit: null,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }, []);

  useEffect(() => {
    if (isTauri) void runAudit();
  }, [runAudit]);

  if (!isTauri) return null;

  const auditReady = state.phase === "ready" && state.audit.requiredReady;
  const runtimeReady = runtimeStatus === "ready";
  const checking = state.phase === "checking" || runtimeStatus === "connecting" || recovering;
  const ready = auditReady && runtimeReady;
  const technicalErrors = [
    ...(state.phase === "error" ? [state.error] : []),
    ...(state.phase === "ready"
      ? state.audit.checks.filter((check) => !check.ready).map((check) => check.detail)
      : []),
  ];

  const nativeCheckTitle = (check: StartupEnvironmentCheck) => {
    switch (check.id) {
      case "workspace":
        return t("readiness.checks.workspace.title");
      case "skills":
        return t("readiness.checks.skills.title");
      case "heorCore":
        return t("readiness.checks.heorCore.title");
      case "harness":
        return t("readiness.checks.harness.title");
      default:
        return check.id;
    }
  };
  const nativeCheckDetail = (check: StartupEnvironmentCheck) => {
    if (!check.ready) return t("readiness.checks.needsAttention");
    switch (check.id) {
      case "workspace":
        return check.detail;
      case "skills":
        return t("readiness.checks.skills.ready");
      case "heorCore":
        return t("readiness.checks.heorCore.ready");
      case "harness":
        return t("readiness.checks.harness.ready");
      default:
        return check.detail;
    }
  };

  const recover = async () => {
    setRecovering(true);
    await restartLocalRuntime();
    await runAudit();
    setRecovering(false);
  };

  const Icon = checking ? Loader2 : ready ? CheckCircle2 : AlertTriangle;
  const title = checking
    ? t("readiness.checking")
    : ready
      ? t("readiness.readyTitle")
      : t("readiness.attentionTitle");
  const body = ready ? t("readiness.readyBody") : t("readiness.attentionBody");

  if (compact) {
    return (
      <div
        className={cn(
          "mt-4 flex flex-wrap items-center gap-2 rounded-input border px-3 py-2.5 text-xs",
          ready ? "border-ok/25 bg-ok/5" : checking ? "border-border bg-surface-2/60" : "border-error/25 bg-error/5",
        )}
        role="status"
      >
        <Icon
          size={14}
          className={cn("shrink-0", checking && "animate-spin", ready ? "text-ok" : checking ? "text-muted" : "text-error")}
          aria-hidden={true}
        />
        <span className="font-medium text-text">{title}</span>
        {!checking && <span className="text-muted">{body}</span>}
        {!ready && !checking && onOpenSettings && (
          <button
            type="button"
            onClick={onOpenSettings}
            className="ml-auto font-medium text-accent hover:underline"
          >
            {t("readiness.actions.openSettings")}
          </button>
        )}
      </div>
    );
  }

  // The bundled harness is an internal project-initialization resource, not a
  // researcher-facing capability or a scientific audit. Keep a healthy check
  // out of the everyday readiness summary; surface it only when it is missing
  // so the researcher still gets an actionable setup failure.
  const nativeChecks = state.phase === "ready"
    ? state.audit.checks.filter((check) => check.id !== "harness" || !check.ready)
    : [];
  return (
    <section
      aria-labelledby="startup-readiness-title"
      className="mt-5 rounded-card border border-border bg-surface p-4 shadow-card"
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
            ready ? "bg-ok/10 text-ok" : checking ? "bg-surface-2 text-muted" : "bg-error/10 text-error",
          )}
        >
          <Icon size={16} className={cn(checking && "animate-spin")} aria-hidden={true} />
        </div>
        <div className="min-w-0 flex-1">
          <h2 id="startup-readiness-title" className="text-sm font-semibold text-text">
            {t("readiness.title")}
          </h2>
          <div className="mt-0.5 text-[13px] font-medium text-text">{title}</div>
          <p className="mt-0.5 text-xs leading-5 text-muted">{body}</p>
        </div>
        <button
          type="button"
          onClick={() => void runAudit()}
          disabled={checking}
          className="flex items-center gap-1.5 rounded-input border border-border px-2.5 py-1.5 text-xs font-medium text-text hover:bg-surface-2 disabled:opacity-50"
        >
          <RefreshCw size={12} className={cn(state.phase === "checking" && "animate-spin")} />
          {t("readiness.actions.recheck")}
        </button>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {nativeChecks.map((check) => (
          <ReadinessRow
            key={check.id}
            ready={check.ready}
            title={nativeCheckTitle(check)}
            detail={nativeCheckDetail(check)}
          />
        ))}
        <ReadinessRow
          ready={runtimeReady}
          pending={runtimeStatus === "connecting" || recovering}
          title={t("readiness.checks.runtime.title")}
          detail={t(`readiness.checks.runtime.${runtimeStatus}`)}
        />
        <ReadinessRow
          ready={Boolean(defaultModel)}
          optional={true}
          title={t("readiness.checks.model.title")}
          detail={defaultModel ?? t("readiness.checks.model.optional")}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
        {!runtimeReady && runtimeStatus !== "connecting" && (
          <button
            type="button"
            onClick={() => void recover()}
            disabled={recovering}
            className="flex items-center gap-1.5 rounded-input bg-accent px-3 py-2 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-50"
          >
            {recovering ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
            {recovering ? t("readiness.actions.restarting") : t("readiness.actions.restart")}
          </button>
        )}
        <p className="text-[11px] leading-5 text-muted">{t("readiness.scope")}</p>
      </div>

      {technicalErrors.length > 0 && (
        <details className="group mt-3 border-t border-border pt-3 text-[11px] text-muted">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 font-medium hover:text-text">
            <ChevronRight size={12} className="transition-transform group-open:rotate-90" />
            {t("readiness.technical")}
          </summary>
          <ul className="mt-2 space-y-1 font-mono">
            {technicalErrors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function ReadinessRow({
  ready,
  pending = false,
  optional = false,
  title,
  detail,
}: {
  ready: boolean;
  pending?: boolean;
  optional?: boolean;
  title: string;
  detail: string;
}) {
  const Icon = pending ? Loader2 : ready ? CheckCircle2 : optional ? Circle : AlertTriangle;
  return (
    <div className="flex min-w-0 gap-2 rounded-input bg-surface-2/60 px-3 py-2.5">
      <Icon
        size={13}
        className={cn(
          "mt-0.5 shrink-0",
          pending && "animate-spin text-muted",
          !pending && ready && "text-ok",
          !pending && !ready && optional && "text-muted",
          !pending && !ready && !optional && "text-error",
        )}
        aria-hidden={true}
      />
      <div className="min-w-0">
        <div className="text-xs font-medium text-text">{title}</div>
        <div className="truncate text-[11px] text-muted" title={detail}>
          {detail}
        </div>
      </div>
    </div>
  );
}

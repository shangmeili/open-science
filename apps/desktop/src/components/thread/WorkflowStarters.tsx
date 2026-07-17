import { useTranslation } from "react-i18next";
import { ChevronRight, FileSearch, FlaskConical, HeartPulse, LineChart } from "lucide-react";
import { installExample, isTauri } from "@/lib/tauri";
import { toast } from "@/lib/toast";

export interface WorkflowStarter {
  id: string;
  icon: React.ReactNode;
  /** Side effect to run before sending the prompt (e.g. install example files). */
  prepare?: () => Promise<void>;
}

/** One-click full-workflow prompts (P0-1): a single request that carries the
 *  agent through data → code → figure → report, all inside the app. */
export const WORKFLOW_STARTERS: WorkflowStarter[] = [
  {
    id: "design",
    icon: <FlaskConical size={17} strokeWidth={1.75} />,
  },
  {
    id: "analyze",
    icon: <LineChart size={17} strokeWidth={1.75} />,
  },
  {
    id: "audit",
    icon: <FileSearch size={17} strokeWidth={1.75} />,
  },
  {
    id: "example-cea",
    icon: <HeartPulse size={17} strokeWidth={1.75} />,
    prepare: async () => {
      if (isTauri) await installExample("heor-cost-effectiveness");
    },
  },
];

/**
 * Empty-session welcome: a quiet, centered composition in the app's paper
 * aesthetic. The conversation is the point, so the copy invites a message
 * first; the starters below are an optional on-ramp, not a dashboard.
 */
export function WorkflowStarters({ onPick }: { onPick: (prompt: string) => void }) {
  const { t } = useTranslation(["session", "common"]);
  // Display copy per starter id — t()'s generated key type rejects a dynamic
  // `starters.${id}.title` template, so each card's copy is looked up by id
  // from this literal-keyed map instead.
  const starterCopy: Record<string, { title: string; description: string; prompt: string }> = {
    design: {
      title: t("starters.design.title"),
      description: t("starters.design.description"),
      prompt: t("starters.design.prompt"),
    },
    analyze: {
      title: t("starters.analyze.title"),
      description: t("starters.analyze.description"),
      prompt: t("starters.analyze.prompt"),
    },
    audit: {
      title: t("starters.audit.title"),
      description: t("starters.audit.description"),
      prompt: t("starters.audit.prompt"),
    },
    "example-cea": {
      title: t("starters.example-cea.title"),
      description: t("starters.example-cea.description"),
      prompt: t("starters.example-cea.prompt"),
    },
  };
  return (
    <div className="flex min-h-[62vh] flex-col items-center justify-center">
      <div className="w-full max-w-[500px]">
        <div className="text-center">
          <div className="text-[10.5px] font-medium uppercase tracking-[0.2em] text-muted">
            {t("starters.newSession")}
          </div>
          <h2 className="mt-2.5 font-serif text-[26px] leading-tight text-text">
            {t("starters.heading")}
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">{t("starters.subheading")}</p>
        </div>

        <div className="mt-7 overflow-hidden rounded-card border border-border bg-surface shadow-card">
          {WORKFLOW_STARTERS.map((s) => (
            <button
              key={s.id}
              onClick={() => {
                void (async () => {
                  try {
                    await s.prepare?.();
                  } catch (e) {
                    toast.error(
                      t("starters.error.setup", {
                        message: e instanceof Error ? e.message : String(e),
                      }),
                    );
                    return;
                  }
                  onPick(starterCopy[s.id]?.prompt ?? "");
                })();
              }}
              className="group flex w-full items-center gap-3.5 border-t border-border px-4 py-3.5 text-left transition-colors first:border-t-0 hover:bg-surface-2"
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface-2 text-accent ring-1 ring-border transition-colors group-hover:bg-surface">
                {s.icon}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13.5px] font-medium text-text">
                  {starterCopy[s.id]?.title}
                </span>
                <span className="mt-0.5 block text-xs leading-snug text-muted">
                  {starterCopy[s.id]?.description}
                </span>
              </span>
              <ChevronRight
                size={16}
                className="shrink-0 text-muted/60 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-muted"
              />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

import { HardDrive, KeyRound, ShieldCheck, UserCheck } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

export const AI4HEOR_FIRST_RUN_KEY = "ai4heor.onboarding.v1";

function wasCompleted(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(AI4HEOR_FIRST_RUN_KEY) === "complete";
}

export function FirstRunGuide({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { t } = useTranslation("session");
  const [complete, setComplete] = useState(wasCompleted);

  if (complete) return null;

  const finish = () => {
    window.localStorage.setItem(AI4HEOR_FIRST_RUN_KEY, "complete");
    setComplete(true);
  };

  const points = [
    { key: "local", icon: HardDrive },
    { key: "provider", icon: KeyRound },
    { key: "approval", icon: ShieldCheck },
    { key: "human", icon: UserCheck },
  ] as const;

  return (
    <section
      aria-labelledby="ai4heor-first-run-title"
      className="rounded-card border border-accent/25 bg-surface p-5 shadow-card"
    >
      <div className="max-w-[620px]">
        <h2 id="ai4heor-first-run-title" className="text-lg font-semibold tracking-tight text-text">
          {t("firstRun.title")}
        </h2>
        <p className="mt-1.5 text-sm leading-6 text-muted">{t("firstRun.body")}</p>
      </div>

      <div className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2">
        {points.map(({ key, icon: Icon }) => (
          <div key={key} className="flex gap-3">
            <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-accent/10 text-accent">
              <Icon size={14} strokeWidth={1.8} aria-hidden={true} />
            </div>
            <div>
              <div className="text-sm font-medium text-text">{t(`firstRun.points.${key}.title`)}</div>
              <p className="mt-0.5 text-xs leading-5 text-muted">{t(`firstRun.points.${key}.body`)}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border pt-4">
        <button
          type="button"
          onClick={finish}
          className="rounded-input bg-accent px-3.5 py-2 text-xs font-medium text-white hover:bg-accent/90"
        >
          {t("firstRun.continue")}
        </button>
        <button
          type="button"
          onClick={onOpenSettings}
          className="rounded-input border border-border bg-surface px-3.5 py-2 text-xs font-medium text-text hover:bg-surface-2"
        >
          {t("firstRun.settings")}
        </button>
      </div>
    </section>
  );
}

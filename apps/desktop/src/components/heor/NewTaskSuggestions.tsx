import { BookOpenCheck, FileSearch, Route, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { BrandWordmark } from "@/components/brand/BrandWordmark";

const suggestions = [
  { key: "scope", icon: Route, tone: "text-[var(--series-5)]" },
  { key: "evidence", icon: Search, tone: "text-[var(--series-1)]" },
  { key: "model", icon: FileSearch, tone: "text-[var(--series-2)]" },
  { key: "deliverable", icon: BookOpenCheck, tone: "text-[var(--series-3)]" },
] as const;

/** Broad, optional shortcuts for a blank task. The research workbench owns the
 * detailed HEOR workflow cards; these shortcuts only prefill an unconstrained
 * natural-language task and never start work by themselves. */
export function NewTaskSuggestions({ onPick }: { onPick: (prompt: string) => void }) {
  const { t } = useTranslation("session");

  return (
    <section className="flex w-full flex-col items-center">
      <BrandWordmark
        alt=""
        data-testid="ai4heor-new-task-wordmark"
        className="h-auto w-56 max-w-[70vw] object-contain"
      />
      <h2 className="mt-4 text-center text-2xl font-semibold tracking-[-0.025em] text-text sm:text-3xl">
        {t("newTask.heading")}
      </h2>
      <div className="mt-6 grid w-full grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {suggestions.map(({ key, icon: Icon, tone }) => (
          <button
            key={key}
            type="button"
            aria-label={t(`newTask.suggestions.${key}.title`)}
            onClick={() => onPick(t(`newTask.suggestions.${key}.prompt`))}
            className="group flex min-h-28 flex-col items-start rounded-card border border-border bg-surface p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-muted/50 hover:shadow-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border"
          >
            <Icon size={16} strokeWidth={1.7} className={tone} />
            <span className="mt-3 text-[13px] font-semibold leading-5 text-text">
              {t(`newTask.suggestions.${key}.title`)}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

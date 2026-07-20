import { ChartNoAxesCombined, FileSearch, Presentation, Route } from "lucide-react";
import { useTranslation } from "react-i18next";
import logo from "@/assets/logo.webp";

const suggestions = [
  { key: "scope", icon: Route, tone: "text-info" },
  { key: "evidence", icon: FileSearch, tone: "text-accent" },
  { key: "model", icon: ChartNoAxesCombined, tone: "text-ok" },
  { key: "deliverable", icon: Presentation, tone: "text-warn" },
] as const;

/** Compact, Codex-style entry points for a blank HEOR task. Each suggestion
 * only fills the natural-language composer; the researcher still reviews and
 * sends it, and the input remains completely unconstrained. */
export function NewTaskSuggestions({ onPick }: { onPick: (prompt: string) => void }) {
  const { t } = useTranslation("session");

  return (
    <section className="flex min-h-[calc(100vh-210px)] flex-col items-center justify-center py-8">
      <img src={logo} alt="" className="h-12 w-12 object-contain" />
      <h2 className="mt-5 text-center font-serif text-3xl font-semibold tracking-tight text-text">
        {t("newTask.heading")}
      </h2>
      <div className="mt-7 grid w-full grid-cols-2 gap-3 md:grid-cols-4">
        {suggestions.map(({ key, icon: Icon, tone }) => (
          <button
            key={key}
            type="button"
            onClick={() => onPick(t(`newTask.suggestions.${key}.prompt`))}
            className="group flex min-h-24 flex-col items-start rounded-card border border-border bg-surface p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-accent/35 hover:shadow-card"
          >
            <Icon size={16} strokeWidth={1.7} className={tone} />
            <span className="mt-auto pt-4 text-[13px] font-medium leading-5 text-text">
              {t(`newTask.suggestions.${key}.title`)}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

import { BookOpenCheck, FileSearch, Route } from "lucide-react";
import { useTranslation } from "react-i18next";

export function HeorStarters({ onPick }: { onPick: (prompt: string) => void }) {
  const { t } = useTranslation("heor");
  const items = [
    { key: "scope" as const, icon: Route },
    { key: "inputs" as const, icon: FileSearch },
    { key: "audit" as const, icon: BookOpenCheck },
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
        {items.map(({ key, icon: Icon }) => (
          <button
            key={key}
            onClick={() => onPick(t(`starter.${key}.prompt`))}
            className="group rounded-card border border-border bg-surface p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-card"
          >
            <Icon size={18} strokeWidth={1.6} className="text-accent" />
            <div className="mt-3 text-sm font-semibold text-text">{t(`starter.${key}.title`)}</div>
            <p className="mt-1.5 text-xs leading-5 text-muted">{t(`starter.${key}.body`)}</p>
          </button>
        ))}
      </div>
    </section>
  );
}

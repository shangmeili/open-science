import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import type { ProviderInfo } from "@ai4s/sdk";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { Section } from "./Section";

interface ProviderManagerCardProps {
  providers: ProviderInfo[];
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  children: ReactNode;
}

export function ProviderManagerCard({
  providers,
  expanded,
  onExpandedChange,
  children,
}: ProviderManagerCardProps) {
  const { t } = useTranslation("settings");
  const names = providers.map((provider) => provider.name).join(", ");
  const summary = providers.length
    ? t("providers.connectedSummary", { count: providers.length, names })
    : t("providers.noneConnected");

  return (
    <Section
      title={t("providers.title")}
      hint={t("providers.hint")}
      flush
    >
      <div className="flex min-h-12 items-center gap-3 px-4 py-2">
        <p className="min-w-0 flex-1 truncate text-[13px] text-muted">{summary}</p>
        {/* This only shows or hides settings, so it remains a secondary action
            and stays available even while the local service is disconnected. */}
        <button
          aria-expanded={expanded}
          onClick={() => onExpandedChange(!expanded)}
          className="flex h-9 shrink-0 items-center gap-1 rounded-input border border-border bg-surface px-3.5 text-[13px] text-text transition-colors hover:bg-surface-2 disabled:text-muted"
        >
          <ChevronRight size={13} className={cn("transition-transform", expanded && "rotate-90")} />
          {t(expanded ? "providers.collapse" : "providers.manage")}
        </button>
      </div>
      {expanded && <div className="border-t border-border">{children}</div>}
    </Section>
  );
}

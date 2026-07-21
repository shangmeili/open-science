import { memo } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReasoningBlock } from "@ai4s/shared";
import { cn } from "@/lib/cn";

/** Model-provided reasoning is transport detail, not a research deliverable.
 *  While it streams, expose only a localized activity signal. Raw reasoning
 *  can contain provider-specific English, internal planning, or hidden prompt
 *  fragments and must never be presented as task progress. Completed reasoning
 *  disappears; real progress remains visible through tool steps and results. */
export const ReasoningRow = memo(function ReasoningRow({
  block,
  streaming = false,
  inline = false,
}: {
  block: ReasoningBlock;
  streaming?: boolean;
  inline?: boolean;
}) {
  const { t } = useTranslation("session");
  if (!streaming || !block.text.trim()) return null;
  return (
    <div
      className={cn(
        "flex items-center gap-2 text-xs text-muted",
        inline ? "px-2 py-1" : "px-1 py-1.5",
      )}
      role="status"
      aria-live="polite"
    >
      <Loader2
        size={13}
        className="shrink-0 animate-spin text-muted/70"
        aria-hidden
      >
      </Loader2>
      <span>{t("reasoning.thinking")}</span>
    </div>
  );
});

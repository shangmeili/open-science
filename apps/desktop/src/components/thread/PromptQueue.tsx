import { ArrowDown, ArrowUp, ListOrdered, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { QueuedPrompt } from "@/lib/runtime";

export function PromptQueue({
  items,
  onMove,
  onRemove,
}: {
  items: QueuedPrompt[];
  onMove: (id: string, direction: "up" | "down") => void;
  onRemove: (id: string) => void;
}) {
  const { t } = useTranslation("session");
  if (items.length === 0) return null;

  return (
    <section
      aria-label={t("composer.queue.title")}
      className="overflow-hidden rounded-card border border-border bg-surface shadow-card"
    >
      <div className="flex items-center gap-2 border-b border-faint px-3 py-2 text-xs font-medium text-text">
        <ListOrdered size={13} className="text-muted" aria-hidden />
        <span>{t("composer.queue.title")}</span>
      </div>
      <ol className="divide-y divide-faint">
        {items.map((item, index) => (
          <li key={item.id} className="flex min-w-0 items-center gap-2 px-3 py-2">
            <span className="w-12 shrink-0 text-[11px] text-muted">
              {index === 0 ? t("composer.queue.next") : index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs text-text" title={item.text}>{item.text}</p>
              {item.skill && (
                <p className="mt-0.5 truncate text-[11px] text-muted">
                  {t("composer.queue.skill", { skill: item.skill.label })}
                </p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-0.5">
              <button
                type="button"
                className="rounded p-1 text-muted hover:bg-surface-2 hover:text-text disabled:opacity-25"
                aria-label={t("composer.queue.moveUp", { position: index + 1 })}
                onClick={() => onMove(item.id, "up")}
                disabled={index === 0}
              >
                <ArrowUp size={13} />
              </button>
              <button
                type="button"
                className="rounded p-1 text-muted hover:bg-surface-2 hover:text-text disabled:opacity-25"
                aria-label={t("composer.queue.moveDown", { position: index + 1 })}
                onClick={() => onMove(item.id, "down")}
                disabled={index === items.length - 1}
              >
                <ArrowDown size={13} />
              </button>
              <button
                type="button"
                className="rounded p-1 text-muted hover:bg-error/10 hover:text-error"
                aria-label={t("composer.queue.remove", { position: index + 1 })}
                onClick={() => onRemove(item.id)}
              >
                <Trash2 size={13} />
              </button>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

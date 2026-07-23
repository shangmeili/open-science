import { useEffect, useRef, useState } from "react";
import { Check, Copy, Loader2, Paperclip, Pencil, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  ArtifactBlock,
  DataTableBlock,
  RunningJobsBlock,
  StatusLineBlock,
  UserMessageBlock,
} from "@ai4s/shared";
import { cn } from "@/lib/cn";
import { MarkdownViewer } from "@/components/markdown-viewer/MarkdownViewer";
import { extractArtifactRefs, refToArtifactBlock } from "@/lib/artifacts";
import { resolveArtifactPath } from "@/lib/artifactFile";
import { copyText } from "@/lib/clipboard";
import { toast } from "@/lib/toast";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useThrottledValue } from "@/lib/useThrottledValue";

export function UserMessage({
  block,
  onEdit,
  onRevert,
}: {
  block: UserMessageBlock;
  onEdit?: (messageID: string, text: string) => void;
  onRevert?: (messageID: string, text: string) => void;
}) {
  const { t } = useTranslation("session");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(block.text);
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const editor = useRef<HTMLTextAreaElement>(null);
  const actionable = !!block.messageID && !!onEdit && !!onRevert;

  useEffect(() => {
    setDraft(block.text);
  }, [block.text]);

  useEffect(() => {
    if (!editing) return;
    editor.current?.focus();
    editor.current?.setSelectionRange(draft.length, draft.length);
  }, [editing, draft.length]);

  const copy = async () => {
    try {
      await copyText(block.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  };

  const submit = () => {
    const text = draft.trim();
    if (!text || !block.messageID) return;
    setEditing(false);
    onEdit?.(block.messageID, text);
  };

  return (
    <div className="group flex justify-end">
      <div className="max-w-[92%]">
        <div className="whitespace-pre-wrap rounded-card bg-surface-2 px-4 py-3 text-[15px] leading-relaxed text-text">
          {editing ? (
            <div className="min-w-[320px] space-y-2">
              <textarea
                ref={editor}
                value={draft}
                rows={Math.min(12, Math.max(3, draft.split("\n").length))}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    setDraft(block.text);
                    setEditing(false);
                  }
                  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit();
                }}
                className="w-full resize-y rounded-input border border-border bg-surface px-3 py-2 text-[15px] leading-relaxed text-text outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
                aria-label={t("message.editField")}
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setDraft(block.text);
                    setEditing(false);
                  }}
                  className="rounded-input border border-border px-3 py-1.5 text-xs text-text hover:bg-surface-2"
                >
                  {t("message.cancel")}
                </button>
                <button
                  type="button"
                  onClick={submit}
                  disabled={!draft.trim()}
                  className="rounded-input bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg hover:opacity-90 disabled:opacity-40"
                >
                  {t("message.resend")}
                </button>
              </div>
            </div>
          ) : (
            block.text
          )}
        </div>
        {!editing && (
          <div className="mt-1 flex justify-end gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
            <button
              type="button"
              onClick={() => void copy()}
              className="rounded-input p-1.5 text-muted hover:bg-surface-2 hover:text-text"
              aria-label={copied ? t("message.copied") : t("message.copy")}
              title={copied ? t("message.copied") : t("message.copy")}
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
            {actionable && (
              <>
                <button
                  type="button"
                  onClick={() => setEditing(true)}
                  className="rounded-input p-1.5 text-muted hover:bg-surface-2 hover:text-text"
                  aria-label={t("message.edit")}
                  title={t("message.edit")}
                >
                  <Pencil size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => setConfirming(true)}
                  className="rounded-input p-1.5 text-muted hover:bg-surface-2 hover:text-text"
                  aria-label={t("message.revert")}
                  title={t("message.revert")}
                >
                  <RotateCcw size={14} />
                </button>
              </>
            )}
          </div>
        )}
        {confirming && block.messageID && (
          <ConfirmDialog
            title={t("message.confirm.title")}
            body={t("message.confirm.body")}
            confirmLabel={t("message.confirm.action")}
            onCancel={() => setConfirming(false)}
            onConfirm={() => {
              setConfirming(false);
              onRevert?.(block.messageID!, block.text);
            }}
          />
        )}
      </div>
    </div>
  );
}

export function AgentMessage({
  markdown,
  onOpenArtifact,
}: {
  markdown: string;
  onOpenArtifact?: (a: ArtifactBlock) => void;
}) {
  const { t } = useTranslation(["session", "common"]);
  const shown = useThrottledValue(markdown, 90);
  // Files the agent mentions (e.g. a PDF produced by running code) become clickable.
  // Each mention is resolved to a real workspace path first — prose often names a
  // bare filename ("index.html") whose file lives in a subdirectory; mentions of
  // files that don't exist get no chip.
  const mentioned = onOpenArtifact ? extractArtifactRefs(shown) : [];
  const [refs, setRefs] = useState<string[]>([]);
  const mentionedKey = mentioned.join("\n");
  useEffect(() => {
    let cancelled = false;
    if (!mentionedKey) {
      setRefs([]);
      return;
    }
    void Promise.all(mentionedKey.split("\n").map((p) => resolveArtifactPath(p).catch(() => null))).then(
      (resolved) => {
        if (cancelled) return;
        setRefs([...new Set(resolved.filter((p): p is string => p !== null))]);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [mentionedKey]);
  return (
    <div>
      <MarkdownViewer>{shown}</MarkdownViewer>
      {refs.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {refs.map((path) => (
            <button
              key={path}
              onClick={() => onOpenArtifact?.(refToArtifactBlock(path))}
              className="flex items-center gap-1.5 rounded-input border border-border bg-surface px-2 py-1 text-xs text-text hover:bg-surface-2"
              title={t("agentMessage.previewTitle", { path })}
            >
              <Paperclip size={12} className="text-accent" />
              <span className="font-mono">{path.split(/[\\/]/).pop()}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function DataTable({ block }: { block: DataTableBlock }) {
  return (
    <div className="overflow-x-auto rounded-card border border-border bg-surface shadow-card">
      {block.caption && (
        <div className="border-b border-border px-4 py-2 text-xs text-muted">{block.caption}</div>
      )}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-muted">
            {block.columns.map((c) => (
              <th key={c} className="px-4 py-2 font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, i) => (
            <tr key={i} className="border-b border-border/60 last:border-0">
              {row.map((cell, j) => (
                <td
                  key={j}
                  className={cn(
                    "px-4 py-2 text-text",
                    j === row.length - 1 && "font-mono text-[13px] text-link",
                  )}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RunningJobsOverlay({ block }: { block: RunningJobsBlock }) {
  return (
    <div className="rounded-card border border-border bg-surface shadow-card">
      <div className="border-b border-border px-4 py-2 text-xs font-medium uppercase tracking-wider text-muted">
        {block.title}
      </div>
      <ul className="divide-y divide-border/60">
        {block.jobs.map((j, i) => (
          <li key={i} className="flex items-center gap-2 px-4 py-2 text-sm">
            <Loader2 size={13} className="animate-spin text-accent" />
            <span className="flex-1 truncate text-text">{j.label}</span>
            <span className="text-xs text-muted">{j.elapsed}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const TONE: Record<NonNullable<StatusLineBlock["tone"]>, string> = {
  running: "text-accent",
  done: "text-ok",
  review: "text-muted",
  error: "text-error",
};

export function StatusLine({ block }: { block: StatusLineBlock }) {
  return (
    <div className={cn(block.divider && "border-t border-border pt-4")}>
      <div className={cn("flex items-center gap-2 text-sm", TONE[block.tone ?? "review"])}>
        <Loader2
          size={14}
          className={cn(block.tone === "running" && "animate-spin", block.tone !== "running" && "hidden")}
        />
        <span>{block.text}</span>
      </div>
    </div>
  );
}

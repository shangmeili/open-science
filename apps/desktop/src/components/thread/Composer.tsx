import { useEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUp, Check, ChevronDown, ClipboardList, Folder, Hammer, Hand, ListPlus, Paperclip, Puzzle, Settings2, Square, Terminal, X, Zap } from "lucide-react";
import {
  addBinaryToWorkspace,
  addFilesToWorkspace,
  addPathsToWorkspace,
  addTextToWorkspace,
  isTauri,
  type ApprovalMode,
} from "@/lib/tauri";
import { useUiStore, type ComposerSkillSelection } from "@/lib/store";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/cn";
import type { AgentMode } from "@/lib/runtime";

/** A paste longer than this becomes a workspace file chip instead of raw text. */
const PASTE_AS_FILE_CHARS = 2000;
const PASTE_AS_FILE_LINES = 25;
/** Max composer height before it scrolls internally. */
const MAX_HEIGHT_PX = 160;

function imageExtension(mime: string): string {
  const subtype = mime.split("/")[1]?.split(";")[0]?.replace("+xml", "") ?? "";
  return subtype === "jpeg" ? "jpg" : subtype || "png";
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.readAsDataURL(blob);
  });
}

// Terminal-style input history: every sent input (prompt, "!cmd", "/name args")
// in its typed form, shared across sessions, newest last, ↑/↓ to recall.
const HISTORY_KEY = "ai4s.inputHistory";
const HISTORY_MAX = 100;
function readHistory(): string[] {
  try {
    const arr = JSON.parse(window.localStorage.getItem(HISTORY_KEY) ?? "[]");
    return Array.isArray(arr) ? arr.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}
function recordHistory(entry: string): void {
  if (!entry) return;
  const prev = readHistory();
  if (prev[prev.length - 1] === entry) return; // consecutive duplicate
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify([...prev, entry].slice(-HISTORY_MAX)));
  } catch {
    /* full or unavailable storage never blocks a send */
  }
}

/** A "/" palette entry — the runtime's config commands, skills and MCP prompts. */
export interface ComposerCommand {
  name: string;
  description?: string;
  source?: string;
}

/** The two approval modes the composer can switch between (Codex-style). Copy
 *  (label/description) is translated at render time — see `approvalCopy`. */
const APPROVAL_OPTIONS: { mode: ApprovalMode; icon: typeof Hand }[] = [
  { mode: "approve", icon: Hand },
  { mode: "full", icon: Zap },
];

const AGENT_OPTIONS: { mode: AgentMode; icon: typeof Hammer }[] = [
  { mode: "build", icon: Hammer },
  { mode: "plan", icon: ClipboardList },
];

/**
 * The "Ask anything" composer. Static mock sessions pass no `onSend`; the live
 * OpenCode session passes one to submit prompts to the runtime. Attached
 * workspace files show as removable chips above the input, not as prompt text.
 *
 * Two prefix modes (only when their handler is provided):
 *   `!`  — shell mode: the rest of the line runs directly in the session's
 *          workspace folder (terminal styling, no model turn).
 *   `/`  — command palette: pick a slash command (config command / skill /
 *          MCP prompt) with ↑/↓ + Tab/Enter, then type arguments and send.
 *          A "/name" that matches no known command stays a plain prompt.
 *   `$`  — choose an installed Skill and keep it as a visible chip; the
 *          editable input then contains only the researcher's request.
 */
export function Composer({
  onSend,
  onRunShell,
  onRunCommand,
  commands = [],
  disabled,
  working,
  onStop,
  placeholder,
  approvalMode,
  onApprovalModeChange,
  agentMode,
  onAgentModeChange,
  beforeWorkspaceWrite,
  autoFocus = false,
  contextLabel,
  modelRequired = false,
  onOpenModelSettings,
}: {
  onSend?: (text: string, skill?: ComposerSkillSelection) => void;
  onRunShell?: (command: string) => void;
  onRunCommand?: (name: string, args: string) => void;
  commands?: ComposerCommand[];
  disabled?: boolean;
  /** A turn is running: natural-language messages can still be queued while
   * command, attachment and mode-changing controls stay unavailable. */
  working?: boolean;
  onStop?: () => void;
  /** Defaults to `t("composer.placeholder.default")` ("Ask anything"). */
  placeholder?: string;
  /** The approval switch shows only when the surface provides both (the live
   *  session does; static mock sessions don't). */
  approvalMode?: ApprovalMode;
  onApprovalModeChange?: (mode: ApprovalMode) => void;
  agentMode?: AgentMode;
  onAgentModeChange?: (mode: AgentMode) => void;
  /** Materialize a draft's private workspace before attachments are copied. */
  beforeWorkspaceWrite?: () => Promise<boolean>;
  /** Focus the input when an explicit new-task surface opens. */
  autoFocus?: boolean;
  /** Optional project context shown as a quiet strip above the free input. */
  contextLabel?: string;
  /** The draft remains editable, but a model must be selected before sending. */
  modelRequired?: boolean;
  onOpenModelSettings?: () => void;
}) {
  const { t } = useTranslation(["session", "common"]);
  // Approval-mode copy keyed by mode — APPROVAL_OPTIONS itself stays static
  // (icons only) so it can live at module scope outside the component.
  const approvalCopy: Record<ApprovalMode, { label: string; description: string }> = {
    approve: {
      label: t("composer.approval.approve.label"),
      description: t("composer.approval.approve.description"),
    },
    full: {
      label: t("composer.approval.full.label"),
      description: t("composer.approval.full.description"),
    },
  };
  const agentCopy: Record<AgentMode, { label: string; description: string }> = {
    build: {
      label: t("composer.agent.build.label"),
      description: t("composer.agent.build.description"),
    },
    plan: {
      label: t("composer.agent.plan.label"),
      description: t("composer.agent.plan.description"),
    },
  };
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  /** Highlighted palette row; clamped to the current matches. */
  const [sel, setSel] = useState(0);
  /** Esc closed the palette for the current input; typing reopens it. */
  const [paletteClosed, setPaletteClosed] = useState(false);
  /** A committed slash command: shown as a chip, the input holds arguments. */
  const [command, setCommand] = useState<string | null>(null);
  /** ↑/↓ history navigation; `draft` is what was typed before recalling. */
  const [hist, setHist] = useState<{ index: number; draft: string } | null>(null);
  /** The approval-mode menu is open. */
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState<ComposerSkillSelection | null>(null);
  const approvalRef = useRef<HTMLDivElement>(null);
  const agentRef = useRef<HTMLDivElement>(null);
  const controlsDisabled = !!disabled || !!working;

  // Changing approval mode restarts the bundled runtime. Never leave that
  // control live while a turn is running: a mid-turn restart orphans the
  // current tool call and strands the conversation in a false working state.
  useEffect(() => {
    if (controlsDisabled) setApprovalOpen(false);
    if (controlsDisabled) setAgentOpen(false);
  }, [controlsDisabled]);

  // Dismiss the approval menu on any outside press. (Button blur can't do
  // this: WKWebView never focuses a clicked button, so blur never fires.)
  useEffect(() => {
    if (!approvalOpen) return;
    const onDown = (e: MouseEvent) => {
      if (!approvalRef.current?.contains(e.target as Node)) setApprovalOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [approvalOpen]);
  useEffect(() => {
    if (!agentOpen) return;
    const onDown = (event: MouseEvent) => {
      if (!agentRef.current?.contains(event.target as Node)) setAgentOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [agentOpen]);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const composerDraft = useUiStore((s) => s.composerDraft);
  const composerDraftMode = useUiStore((s) => s.composerDraftMode);
  const setComposerDraft = useUiStore((s) => s.setComposerDraft);
  const composerSkill = useUiStore((s) => s.composerSkill);
  const setComposerSkill = useUiStore((s) => s.setComposerSkill);
  const resolvedPlaceholder = selectedSkill
    ? t("composer.skill.placeholder", { skill: selectedSkill.label })
    : placeholder ?? t("composer.placeholder.default");

  useEffect(() => {
    if (autoFocus) taRef.current?.focus();
  }, [autoFocus]);

  const shellMode = !working && !!onRunShell && !command && value.startsWith("!");
  // The palette is open while the command NAME is being typed ("/na…"); the
  // first space ends name-typing (arguments follow) and closes it.
  const slashTyping = !working && !!onRunCommand && !command && /^\/\S*$/.test(value);
  const skillTyping =
    !working && !!onSend && !command && !selectedSkill && /^\$\S*$/.test(value);
  const paletteKind = slashTyping ? "command" : skillTyping ? "skill" : null;
  const query = paletteKind ? value.slice(1).toLowerCase() : "";
  const matches = paletteKind
    ? commands
        .filter((c) => paletteKind !== "skill" || c.source === "skill")
        .filter((c) => c.name.toLowerCase().includes(query))
        .sort(
          (a, b) =>
            Number(b.name.toLowerCase().startsWith(query)) -
            Number(a.name.toLowerCase().startsWith(query)),
        )
    : [];
  const paletteOpen = matches.length > 0 && !paletteClosed && !controlsDisabled;
  const selIndex = Math.min(sel, Math.max(matches.length - 1, 0));

  // Each edit resets the palette: selection back to the top, Esc-close undone.
  useEffect(() => {
    setSel(0);
    setPaletteClosed(false);
  }, [value]);

  // Committing a command turns it into a chip; the input then holds only the
  // arguments — the "/name" can never degrade into ordinary prompt text.
  const pick = (c: ComposerCommand) => {
    if (paletteKind === "skill") {
      setSelectedSkill({ id: c.name, label: c.name });
      setValue("");
      taRef.current?.focus();
      return;
    }
    setCommand(c.name);
    setValue("");
    taRef.current?.focus();
  };

  const onChange = (v: string) => {
    setHist(null); // an edit leaves history navigation
    // "$skill arguments" commits an installed Skill as a visible chip. An
    // unknown name stays ordinary prompt text instead of silently claiming a
    // capability that is not installed.
    if (!working && onSend && !command && !selectedSkill) {
      const m = /^\$(\S+)\s([\s\S]*)$/.exec(v);
      const skill = m
        ? commands.find((c) => c.source === "skill" && c.name === m[1])
        : undefined;
      if (m && skill) {
        setSelectedSkill({ id: skill.name, label: skill.name });
        setValue(m[2]);
        taRef.current?.focus();
        return;
      }
    }
    // A full known command name followed by whitespace commits it, same as a
    // pick — whether typed ("/init ") or pasted whole ("/init focus\n…"); the
    // remainder becomes the arguments. Unknown names (paths) stay plain text.
    if (!working && onRunCommand && !command) {
      const m = /^\/(\S+)\s([\s\S]*)$/.exec(v);
      if (m && commands.some((c) => c.name === m[1])) {
        setCommand(m[1]);
        setValue(m[2]);
        taRef.current?.focus();
        return;
      }
    }
    setValue(v);
  };

  const unchip = () => {
    if (!command) return;
    setValue(value ? `/${command} ${value}` : `/${command}`);
    setCommand(null);
    taRef.current?.focus();
  };

  // Consume a draft another surface prepared (e.g. provenance "Reproduce") —
  // prefilled, never auto-sent: the user reviews and presses send. Follow-ups
  // append; mutually exclusive task starters replace the previous starter.
  useEffect(() => {
    if (composerDraft === null) return;
    // React StrictMode replays mount effects in development. Consume from the
    // store before changing local state so the replay cannot append the same
    // starter a second time while it still holds the first render's snapshot.
    const draft = useUiStore.getState().composerDraft;
    if (draft === null) return;
    const mode = useUiStore.getState().composerDraftMode;
    setComposerDraft(null);
    setValue((v) =>
      mode === "replace" ? draft : v.trim() ? `${v.trimEnd()}\n\n${draft}` : draft,
    );
    taRef.current?.focus();
  }, [composerDraft, composerDraftMode, setComposerDraft]);

  // The capability catalog passes the runtime id separately from the editable
  // request. Researchers see a localized Skill chip; the id is added only to
  // the runtime prompt when they send the task.
  useEffect(() => {
    if (composerSkill === null) return;
    setSelectedSkill(composerSkill);
    setComposerSkill(null);
    taRef.current?.focus();
  }, [composerSkill, setComposerSkill]);

  // Auto-grow with the content, scroll internally beyond the cap.
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  const submit = () => {
    if (disabled) return;
    const text = value.trim();
    setHist(null);
    // While a turn is active, only plain natural-language messages may enter
    // the queue. This prevents deferred shell, slash-command, attachment or
    // mode-changing actions from executing later without fresh context.
    if (working) {
      if (!text) return;
      if (selectedSkill) onSend?.(text, selectedSkill);
      else onSend?.(text);
      recordHistory(text);
      setValue("");
      setSelectedSkill(null);
      return;
    }
    // A chipped command runs as itself — arguments optional.
    if (command) {
      onRunCommand?.(command, text);
      recordHistory(text ? `/${command} ${text}` : `/${command}`);
      setCommand(null);
      setValue("");
      return;
    }
    // "!" — run the rest of the line as a shell command (no model turn).
    if (shellMode) {
      const line = value.slice(1).trim();
      if (!line) return;
      onRunShell?.(line);
      recordHistory(`!${line}`);
      setValue("");
      return;
    }
    // "/name args" — run a KNOWN slash command; unknown names stay a prompt
    // (a message can legitimately start with a path like "/etc/hosts …").
    if (onRunCommand && text.startsWith("/")) {
      const name = text.slice(1).split(/\s/, 1)[0];
      if (commands.some((c) => c.name === name)) {
        onRunCommand(name, text.slice(1 + name.length).trim());
        recordHistory(text);
        setValue("");
        return;
      }
    }
    if (!text && files.length === 0) return;
    const fileNote =
      files.length > 0 ? `Files added to the workspace: ${files.join(", ")}` : "";
    const payload = text && fileNote ? `${text}\n\n${fileNote}` : text || fileNote;
    if (selectedSkill) onSend?.(payload, selectedSkill);
    else onSend?.(payload);
    if (text) recordHistory(text);
    setValue("");
    setFiles([]);
    setSelectedSkill(null);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // During IME composition (e.g. pinyin), Enter picks a candidate — it must
    // not send. WebKit reports the committing keydown as legacy keyCode 229.
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    // While the palette is open, the keyboard drives it, not the send.
    if (paletteOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSel((i) => Math.min(i + 1, matches.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSel((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setPaletteClosed(true);
        return;
      }
      if (e.key === "Tab" || e.key === "Enter") {
        e.preventDefault();
        pick(matches[selIndex]);
        return;
      }
    }
    // Backspace on an empty input dissolves the command chip back into text.
    if (e.key === "Backspace" && command && value === "") {
      e.preventDefault();
      unchip();
      return;
    }
    if (e.key === "Backspace" && selectedSkill && value === "") {
      e.preventDefault();
      setSelectedSkill(null);
      return;
    }
    // Terminal-style history: ↑ at the very start of the input recalls the
    // previous sent input; while navigating, ↑/↓ walk older/newer and walking
    // past the newest restores the unsent draft. Any edit leaves navigation.
    if (e.key === "ArrowUp" && !command) {
      const el = taRef.current;
      const atStart = !!el && el.selectionStart === 0 && el.selectionEnd === 0;
      if (hist || atStart) {
        const entries = readHistory();
        const index = (hist ? hist.index : entries.length) - 1;
        if (index >= 0) {
          e.preventDefault();
          setHist({ index, draft: hist ? hist.draft : value });
          setValue(entries[index]);
        }
        return;
      }
    }
    if (e.key === "ArrowDown" && hist) {
      e.preventDefault();
      const entries = readHistory();
      const index = hist.index + 1;
      if (index < entries.length) {
        setHist({ ...hist, index });
        setValue(entries[index]);
      } else {
        setValue(hist.draft);
        setHist(null);
      }
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const addWorkspaceFiles = async (write: () => Promise<string | string[]>) => {
    try {
      if (beforeWorkspaceWrite && !(await beforeWorkspaceWrite())) return;
      const result = await write();
      const names = Array.isArray(result) ? result : [result];
      if (names.length > 0) setFiles((current) => [...current, ...names]);
    } catch (err) {
      toast.error(
        t("composer.error.paste", {
          message: err instanceof Error ? err.message : String(err),
        }),
      );
    }
  };

  // Long text and pasted screenshots become local workspace file chips.
  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    if (working || !isTauri || !onSend) return;
    const imageItem = Array.from(e.clipboardData.items ?? []).find((item) =>
      item.type.startsWith("image/"),
    );
    const image = imageItem?.getAsFile();
    if (image) {
      e.preventDefault();
      void addWorkspaceFiles(async () => {
        const base64 = await blobToBase64(image);
        return addBinaryToWorkspace(`pasted.${imageExtension(image.type)}`, base64);
      });
      return;
    }
    const text = e.clipboardData.getData("text/plain");
    if (text.length <= PASTE_AS_FILE_CHARS && text.split("\n").length <= PASTE_AS_FILE_LINES) {
      return; // normal paste
    }
    e.preventDefault();
    void addWorkspaceFiles(() => addTextToWorkspace("pasted.txt", text));
  };

  // Keep the current drop action in a ref so the native Tauri listener can be
  // registered exactly once. Re-subscribing on every render leaks listeners
  // during streaming and can copy one dropped file many times.
  const onDropRef = useRef<((paths: string[]) => void) | null>(null);
  onDropRef.current =
    isTauri && onSend && !working
      ? (paths) => {
          if (paths.length > 0) void addWorkspaceFiles(() => addPathsToWorkspace(paths));
        }
      : null;

  // OS file drops are native Tauri events; DOM drop events do not receive the
  // absolute paths needed to copy files into the local research workspace.
  useEffect(() => {
    if (!isTauri) return;
    let unlisten: (() => void) | undefined;
    let cancelled = false;
    void import("@tauri-apps/api/webview")
      .then(({ getCurrentWebview }) => getCurrentWebview().onDragDropEvent((event) => {
        const payload = event.payload;
        if (payload.type === "enter" || payload.type === "over") setDragOver(true);
        if (payload.type === "leave") setDragOver(false);
        if (payload.type === "drop") {
          setDragOver(false);
          onDropRef.current?.(payload.paths);
        }
      }))
      .then((stop) => {
        if (cancelled) stop();
        else unlisten = stop;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  // Copy local files into the agent workspace; they appear as chips.
  const addFiles = async () => {
    if (working) return;
    setAdding(true);
    try {
      if (beforeWorkspaceWrite && !(await beforeWorkspaceWrite())) return;
      const names = await addFilesToWorkspace();
      if (names.length > 0) setFiles((f) => [...f, ...names]);
    } catch (err) {
      toast.error(
        t("composer.error.addFiles", {
          message: err instanceof Error ? err.message : String(err),
        }),
      );
    } finally {
      setAdding(false);
    }
  };

  const canAttach = isTauri && !!onSend;
  const canSend =
    !disabled &&
    (working
      ? !!value.trim()
      : command
      ? true // a chipped command may run without arguments
      : shellMode
        ? value.slice(1).trim().length > 0
        : !!value.trim() || files.length > 0);

  return (
    <div
      className={cn(
        "relative rounded-[14px] border bg-surface px-3 pb-2.5 pt-3 shadow-card",
        shellMode
          ? "border-warn/60"
          : command
            ? "border-accent/50"
            : agentMode === "plan"
              ? "border-link/60"
              : "border-border",
        dragOver && "border-accent ring-2 ring-accent/40",
      )}
    >
      {contextLabel && (
        <div className="mb-2 flex items-center gap-2 border-b border-faint px-1 pb-2 text-xs text-muted">
          <Folder size={13} className="shrink-0" />
          <span className="truncate">{contextLabel}</span>
        </div>
      )}
      {paletteOpen && (
        <div
          role="listbox"
          aria-label={t("composer.commandsAria")}
          className="absolute bottom-full left-0 right-0 z-20 mb-2 max-h-64 overflow-y-auto rounded-card border border-border bg-surface p-1 shadow-card"
        >
          {matches.map((c, i) => (
            <button
              key={c.name}
              role="option"
              aria-selected={i === selIndex}
              className={cn(
                "flex w-full items-baseline gap-2 rounded-input px-2 py-1.5 text-left",
                i === selIndex ? "bg-surface-2" : "hover:bg-surface-2",
              )}
              // mousedown, not click — a click would blur the textarea first.
              onMouseDown={(e) => {
                e.preventDefault();
                pick(c);
              }}
            >
              <span className="shrink-0 font-mono text-xs text-text">
                {paletteKind === "skill" ? "$" : "/"}{c.name}
              </span>
              {c.description && (
                <span className="min-w-0 flex-1 truncate text-xs text-muted">{c.description}</span>
              )}
              {(c.source === "skill" || c.source === "mcp") && (
                <span className="shrink-0 rounded px-1 py-0.5 text-[10px] uppercase text-muted ring-1 ring-border">
                  {c.source === "skill" ? t("composer.source.skill") : t("composer.source.mcp")}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      {selectedSkill && (
        <div className="flex flex-wrap gap-1.5 px-1 pb-2">
          <span
            className="flex items-center gap-1.5 rounded-input bg-accent/10 py-1 pl-2 pr-1 text-xs font-medium text-text ring-1 ring-accent/20"
            title={t("composer.skill.chipTitle", { skill: selectedSkill.label })}
          >
            <Puzzle size={12} className="shrink-0 text-accent" />
            <span className="max-w-[260px] truncate">{selectedSkill.label}</span>
            <button
              type="button"
              className="rounded p-0.5 text-muted hover:bg-accent/15 hover:text-text"
              aria-label={t("composer.skill.removeAria", { skill: selectedSkill.label })}
              onClick={() => setSelectedSkill(null)}
            >
              <X size={11} />
            </button>
          </span>
        </div>
      )}
      {files.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-1 pb-2">
          {files.map((name) => (
            <span
              key={name}
              className="flex items-center gap-1.5 rounded-input bg-surface-2 py-1 pl-2 pr-1 font-mono text-xs text-text ring-1 ring-border"
            >
              <Paperclip size={11} className="shrink-0 text-muted" />
              <span className="max-w-[220px] truncate">{name}</span>
              <button
                className="rounded p-0.5 text-muted hover:bg-border hover:text-text"
                aria-label={t("composer.file.removeAria", { name })}
                onClick={() => setFiles((f) => f.filter((n) => n !== name))}
              >
                <X size={11} />
              </button>
            </span>
          ))}
        </div>
      )}
      <textarea
        ref={taRef}
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        onPaste={onPaste}
        placeholder={
          command
            ? t("composer.placeholder.arguments")
            : shellMode
              ? t("composer.placeholder.shell")
              : resolvedPlaceholder
        }
        className={cn(
          "max-h-[160px] min-h-[48px] w-full resize-none bg-transparent px-0.5 py-0 text-sm leading-6 text-text outline-none placeholder:text-muted/90",
          (shellMode || command) && "font-mono",
        )}
        aria-label={t("composer.placeholder.default")}
      />
      {/* Codex-style action row: mode controls bottom-left, send bottom-right. */}
      <div className="flex min-h-8 items-center gap-1.5 pt-1.5">
        {command ? (
          <span
            className="flex h-7 shrink-0 items-center gap-1 rounded-input bg-accent/15 pl-2 pr-1 font-mono text-xs text-accent"
            title={t("composer.command.chipTitle")}
          >
            /{command}
            <button
              className="rounded p-0.5 hover:bg-accent/20"
              aria-label={t("composer.command.removeAria")}
              onClick={unchip}
            >
              <X size={11} />
            </button>
          </span>
        ) : shellMode ? (
          <span
            className="flex h-7 shrink-0 items-center gap-1 rounded-input bg-warn/15 px-1.5 font-mono text-xs text-warn"
            title={t("composer.shellMode.title")}
          >
            <Terminal size={13} />
            {t("composer.shellMode.badge")}
          </span>
        ) : (
          canAttach && (
            <button
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-input text-muted hover:bg-surface-2 hover:text-text disabled:opacity-40"
              aria-label={t("composer.attach.addAria")}
              title={t("composer.attach.title")}
              onClick={() => void addFiles()}
              disabled={adding || working}
            >
              <Paperclip size={15} />
            </button>
          )
        )}
        {agentMode && onAgentModeChange && (
          <div className="relative shrink-0" ref={agentRef}>
            {agentOpen && (
              <div
                role="menu"
                aria-label={t("composer.agent.menuAria")}
                className="absolute bottom-full left-0 z-20 mb-2 w-80 rounded-card border border-border bg-surface p-1 shadow-card"
              >
                <div className="px-2 pb-1 pt-1.5 text-xs text-muted">
                  {t("composer.agent.menuTitle")}
                </div>
                {AGENT_OPTIONS.map((option) => (
                  <button
                    key={option.mode}
                    role="menuitemradio"
                    aria-checked={option.mode === agentMode}
                    className="flex w-full items-start gap-2 rounded-input px-2 py-1.5 text-left hover:bg-surface-2"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      setAgentOpen(false);
                      if (option.mode !== agentMode) onAgentModeChange(option.mode);
                    }}
                  >
                    <option.icon size={13} className="mt-0.5 shrink-0 text-muted" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs text-text">{agentCopy[option.mode].label}</span>
                      <span className="block text-xs text-muted">
                        {agentCopy[option.mode].description}
                      </span>
                    </span>
                    {option.mode === agentMode && (
                      <Check size={13} className="mt-0.5 shrink-0 text-accent" />
                    )}
                  </button>
                ))}
              </div>
            )}
            <button
              aria-label={t("composer.agent.aria")}
              title={t("composer.agent.title")}
              className={cn(
                "flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs",
                agentMode === "plan"
                  ? "bg-link/15 text-link hover:bg-link/25"
                  : "text-muted hover:bg-surface-2 hover:text-text",
              )}
              onClick={() => setAgentOpen((open) => !open)}
              disabled={controlsDisabled}
            >
              {agentMode === "plan" ? <ClipboardList size={12} /> : <Hammer size={12} />}
              <span>{agentCopy[agentMode].label}</span>
              <ChevronDown size={11} />
            </button>
          </div>
        )}
        {approvalMode && onApprovalModeChange && (
          <div className="relative shrink-0" ref={approvalRef}>
            {approvalOpen && (
              <div
                role="menu"
                aria-label={t("composer.approval.menuAria")}
                className="absolute bottom-full left-0 z-20 mb-2 w-80 rounded-card border border-border bg-surface p-1 shadow-card"
              >
                <div className="px-2 pb-1 pt-1.5 text-xs text-muted">
                  {t("composer.approval.menuTitle")}
                </div>
                {APPROVAL_OPTIONS.map((opt) => (
                  <button
                    key={opt.mode}
                    role="menuitemradio"
                    aria-checked={opt.mode === approvalMode}
                    disabled={controlsDisabled}
                    className="flex w-full items-start gap-2 rounded-input px-2 py-1.5 text-left hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40"
                    // mousedown, not click — a click would blur the textarea first.
                    onMouseDown={(e) => {
                      e.preventDefault();
                      setApprovalOpen(false);
                      if (opt.mode !== approvalMode) onApprovalModeChange(opt.mode);
                    }}
                  >
                    <opt.icon size={13} className="mt-0.5 shrink-0 text-muted" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs text-text">{approvalCopy[opt.mode].label}</span>
                      <span className="block text-xs text-muted">
                        {approvalCopy[opt.mode].description}
                      </span>
                    </span>
                    {opt.mode === approvalMode && (
                      <Check size={13} className="mt-0.5 shrink-0 text-accent" />
                    )}
                  </button>
                ))}
              </div>
            )}
            <button
              aria-label={t("composer.approval.aria")}
              title={t("composer.approval.title")}
              disabled={controlsDisabled}
              className="flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs text-muted hover:bg-surface-2 hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
              onClick={() => setApprovalOpen((o) => !o)}
            >
              {approvalMode === "full" ? <Zap size={12} /> : <Hand size={12} />}
              <span>{approvalCopy[approvalMode].label}</span>
              <ChevronDown size={11} />
            </button>
          </div>
        )}
        {modelRequired && onOpenModelSettings && (
          <button
            type="button"
            onClick={onOpenModelSettings}
            className="flex h-7 shrink-0 items-center gap-1.5 rounded-full bg-accent/10 px-2.5 text-xs font-medium text-accent hover:bg-accent/15"
            aria-label={t("composer.modelRequired.action")}
            title={t("composer.modelRequired.description")}
          >
            <Settings2 size={12} />
            <span>{t("composer.modelRequired.action")}</span>
          </button>
        )}
        <span className="flex-1" />
        {working ? (
          <>
            <button
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors",
                canSend
                  ? "bg-surface-2 text-text hover:bg-border"
                  : "bg-surface-2 text-muted/40",
              )}
              aria-label={t("composer.queue.addAria")}
              title={t("composer.queue.addTitle")}
              onClick={submit}
              disabled={!canSend}
            >
              <ListPlus size={15} />
            </button>
            {onStop && (
              <button
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-accent-fg hover:opacity-90"
                aria-label={t("composer.stop.aria")}
                title={t("composer.stop.title")}
                onClick={onStop}
              >
                <Square size={11} fill="currentColor" />
              </button>
            )}
          </>
        ) : (
          <button
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors",
              canSend
                ? "bg-accent text-accent-fg hover:opacity-90"
                : "bg-surface-2 text-muted/60",
            )}
            aria-label={t("composer.send.aria")}
            title={modelRequired ? t("composer.modelRequired.sendHint") : undefined}
            onClick={submit}
            disabled={!canSend}
          >
            <ArrowUp size={15} />
          </button>
        )}
      </div>
    </div>
  );
}

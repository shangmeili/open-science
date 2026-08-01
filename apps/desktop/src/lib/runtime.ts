import { create } from "zustand";
import {
  OpenCodeClient,
  DEFAULT_OPENCODE_URL,
  type AgentInfo,
  type AgentRuntime,
  type CommandInfo,
  type HistoryMessage,
  type OpenCodeEvent,
  type PermissionAskedEvent,
  type PermissionReply,
  type QuestionAskedEvent,
  type SessionMeta,
  type SessionRuntimeStatus,
  type SkillInfo,
  type ToolCallStatus,
} from "@ai4s/sdk";
import type { ArtifactBlock, RuntimeStatus, ThreadBlock, ToolVerb } from "@ai4s/shared";
import {
  detectTools as probeTools,
  commitWorkspaceSnapshot,
  createProject as createProjectFolder,
  importProject as importProjectFolder,
  setProjectPinned as setProjectPinnedCmd,
  deleteProject as deleteProjectCmd,
  currentResearchScope,
  getApprovalMode,
  isTauri,
  listProjects,
  logDebug,
  markSession,
  newDatedWorkspace,
  runtimePassword,
  restartRuntime,
  setApprovalMode as persistApprovalMode,
  setProxySetting as persistProxySetting,
  setWorkspace,
  startRuntime,
  workspacePath,
  type ApprovalMode,
  type ProjectInfo,
  type ProxyMode,
  type ToolStatus,
} from "./tauri";
import { kernelReset } from "./kernel";
import { moveScrollMemory } from "./scrollMemory";
import { deriveArtifact } from "./artifacts";
import { provenanceInputsFromEvent, recordProvenance } from "./provenance";
import { recordRun, runInputFromEvent } from "./runs";
import { recordModelCall, recordModelCallsFromHistory } from "./modelCalls";
import { splitReview } from "./review";
import { displayHeorPrompt, heorPromptContext, type HeorPromptContext } from "./heor";
import { fallbackDefaultModel } from "@/components/settings/modelCatalog";
import i18n from "@/i18n";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const URL_KEY = "ai4s.opencodeUrl";
const HIDDEN_KEY = "ai4s.hiddenExamples";

function initialUrl(): string {
  if (typeof window === "undefined") return DEFAULT_OPENCODE_URL;
  return window.localStorage.getItem(URL_KEY) ?? DEFAULT_OPENCODE_URL;
}
function initialHidden(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(window.localStorage.getItem(HIDDEN_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export interface Thread {
  blocks: ThreadBlock[];
  index: Record<string, number>;
  loaded: boolean;
}

/** What a session's right pane shows: an artifact inspector, the Files
 *  browser, the Runs ledger, or nothing. Mutually exclusive — one pane. */
export interface PaneState {
  artifact: ArtifactBlock | null;
  showFiles: boolean;
  showRuns: boolean;
}

export interface QueuedPromptSkill {
  id: string;
  label: string;
}

export interface QueuedPrompt {
  id: string;
  text: string;
  skill?: QueuedPromptSkill;
}

interface RuntimeState {
  status: RuntimeStatus;
  serverUrl: string;
  sessions: SessionMeta[];
  currentId: string | null;
  threads: Record<string, Thread>;
  skills: SkillInfo[];
  agents: AgentInfo[];
  /** Slash commands the runtime can run ("/" palette): config commands,
   *  skills and MCP prompts, one merged list from GET /command. */
  commands: CommandInfo[];
  /** Configured default model ("provider/model"), or null when unset. */
  defaultModel: string | null;
  /** Apply a new default model and transparently reconnect (see impl). */
  setDefaultModel: (model: string) => Promise<void>;
  /** The last failed model switch's error, or null. While set, the Settings
   *  page keeps the model browser on screen (instead of the connect prompt)
   *  so the user can retry. Cleared by any successful reconnect, a successful
   *  switch, a server-URL change, or an explicit disconnect. */
  modelSwitchError: string | null;
  /** The composer's approval switch: "approve" (dangerous commands prompt)
   *  or "full" (everything in-workspace runs). Loaded from OpenCode config. */
  approvalMode: ApprovalMode;
  /** Persist a new approval mode (restarts the sidecar) and reconnect. */
  setApprovalMode: (mode: ApprovalMode) => Promise<void>;
  /** Persist the network-proxy setting (restarts the sidecar) and reconnect. */
  setProxySetting: (mode: ProxyMode, url: string) => Promise<void>;
  tools: ToolStatus[];
  hiddenExamples: string[];
  error: string | null;
  /** Pending interactive requests the agent is blocked on, newest last. */
  questions: QuestionAskedEvent[];
  permissions: PermissionAskedEvent[];
  /** Subagent session → the session whose task tool spawned it, learned from
   *  task tool events (live) and the session list (recovery after reload). */
  sessionParents: Record<string, string>;
  /** Right-pane state per session (DRAFT_KEY for a draft) — each session keeps
   *  its own open artifact / Files browser and gets it back when reopened.
   *  In-memory only: an app restart returns every session to a closed pane. */
  panes: Record<string, PaneState>;
  sessionAgents: Record<string, AgentMode>;
  /** Natural-language messages waiting behind the active turn, isolated by
   * task id (DRAFT_KEY before the first turn creates a real session). */
  promptQueues: Record<string, QueuedPrompt[]>;
  setAgentMode: (mode: AgentMode) => void;
  enqueuePrompt: (text: string, skill?: QueuedPromptSkill) => string;
  removeQueuedPrompt: (id: string) => void;
  moveQueuedPrompt: (id: string, direction: "up" | "down") => void;
  takeNextQueuedPrompt: () => QueuedPrompt | null;
  requeuePromptFront: (prompt: QueuedPrompt) => void;
  openArtifact: (a: ArtifactBlock) => void;
  closeArtifact: () => void;
  setShowFiles: (show: boolean) => void;
  setShowRuns: (show: boolean) => void;
  answerQuestion: (requestId: string, answers: string[][]) => Promise<void>;
  rejectQuestion: (requestId: string) => Promise<void>;
  replyPermission: (requestId: string, reply: PermissionReply) => Promise<void>;
  setServerUrl: (url: string) => void;
  loadCatalog: () => Promise<void>;
  detectTools: () => Promise<void>;
  connect: () => Promise<void>;
  /** Replace the bundled local process, then reconnect on its stable port. */
  restartLocalRuntime: () => Promise<boolean>;
  /** Resolves true once connected, false when the retry window is exhausted. */
  connectRetry: (tries?: number) => Promise<boolean>;
  bootstrap: () => Promise<void>;
  disconnect: () => void;
  refreshSessions: () => Promise<void>;
  /** Increments for every explicit new-task action so draft-only UI state can
   *  reset even when the user is already on the new-task route. */
  draftEpoch: number;
  startDraft: () => void;
  /** Materialize the draft's private local research scope before a file write
   *  or deterministic starter runs. Sending a first message also calls this. */
  ensureStandaloneWorkspace: () => Promise<boolean>;
  startDraftInCurrentWorkspace: () => void;
  /** AI4HEOR projects: typed HEOR workspace folders under the base dir.
   *  Sessions group under a project by `directory`; multiple sessions share the folder. */
  projects: ProjectInfo[];
  /** Active named project or standalone task research scope. */
  researchScope: ProjectInfo | null;
  refreshProjects: () => Promise<void>;
  /** Create an AI4HEOR project and move into it with a fresh pinned draft. */
  createProject: (name: string) => Promise<ProjectInfo | null>;
  /** Copy an existing folder into AI4HEOR, switch to the copy, and start a
   *  clean project task without modifying the selected source folder. */
  importProject: (path: string) => Promise<ProjectInfo | null>;
  setProjectPinned: (id: string, pinned: boolean) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  /** Fresh draft pinned inside `path` (a project folder), so the next new
   *  session lands there. Skips the reconnect when the folder is already active. */
  startDraftInWorkspace: (path: string) => Promise<void>;
  /** Active workspace folder (absolute path); null in the browser. */
  workspace: string | null;
  /** True when the user explicitly picked the active folder for the next new
   *  task; false means a new task gets its own fresh dated folder. */
  workspacePinned: boolean;
  /** A deliberate workspace move is in flight (event-stream reconnect into the
   *  new folder). The UI must not present it as a disconnection — no status
   *  flip, no Connect button, no help card. Real failures surface after the
   *  retry window is exhausted, once this clears. */
  switching: boolean;
  /** A sendPrompt is in flight (click → POST accepted). Locks the composer. */
  sending: boolean;
  /** Sessions with an active turn (send accepted, session.idle not yet seen).
   *  Drives the composer lock and the "Working…" indicator. */
  runningSessions: Record<string, true>;
  /** Honest server-reported phase for each active turn. */
  sessionProgress: Record<string, SessionRuntimeStatus>;
  /** Current model-step number for each running session. A changing step is a
   *  visible liveness signal during long turns with no tool output. */
  stepCounts: Record<string, number>;
  /** Sessions whose current turn is a user-typed "!" shell command. Their bash
   *  output shows inline in the thread — the output IS the result the user
   *  asked for. Agent bash steps stay quiet single-line log entries. */
  shellTurns: Record<string, true>;
  /** Switch to an existing project or legacy session folder. */
  switchWorkspace: (target: { path: string }) => Promise<void>;
  openSession: (id: string) => Promise<void>;
  renameSession: (id: string, title: string) => Promise<void>;
  sendPrompt: (text: string, displayText?: string) => Promise<string | null>;
  /** Run a "!" shell command directly in the session's workspace folder —
   *  no model turn; the output folds into the thread as a bash tool row. */
  runShell: (command: string) => Promise<string | null>;
  /** Run a "/" slash command (config command / skill / MCP prompt). */
  runCommand: (name: string, args?: string) => Promise<string | null>;
  /** Replace a past user message and continue from that point. The runtime
   * restores both conversation and workspace files before the edited turn. */
  editMessage: (messageID: string, runtimeText: string, displayText?: string) => Promise<boolean>;
  /** Return to a past user message, restoring the workspace and leaving that
   * message in the composer so the researcher can revise it deliberately. */
  revertMessage: (messageID: string) => Promise<boolean>;
  /** Interrupt the current session's running turn (Stop button / Esc). */
  interrupt: () => Promise<void>;
  /** Check every session holding a running lock against the server: if its
   *  turn is actually over (idle was missed — SSE reconnect windows, the
   *  directory-scoped event stream), reload the missed history and unlock. */
  reconcileRunning: () => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  hideExample: (id: string) => void;
  /** Open a natural-language industrialization review. The candidate remains
   *  inactive; only the app's locked registry can admit a platform asset. */
  reviewAssetCandidate: (text: string) => Promise<string | null>;
}

// Conversation execution depends only on the model/runtime-neutral contract.
// Settings retains the concrete OpenCode client because provider credentials,
// OAuth, MCP, and catalogs are implementation-specific configuration surfaces.
let client: AgentRuntime | null = null;
let opencodeClient: OpenCodeClient | null = null;
let queuedPromptSequence = 0;
/** HEOR template context for the active turn in each session. It contains only
 * fixed app-owned identifiers and the response language, never user text. */
const pendingPromptContexts = new Map<string, HeorPromptContext>();
/** OpenCode can leave a session executor occupied after a provider error even
 * after emitting session.idle. Abort is its supported executor cleanup; keep
 * the UI running lock until both the idle event and that cleanup have landed. */
const errorRecoveries = new Map<string, Promise<void>>();
const errorRecoveryIdle = new Set<string>();

function nextQueuedPromptId(): string {
  queuedPromptSequence += 1;
  return `queued-${Date.now().toString(36)}-${queuedPromptSequence.toString(36)}`;
}
let openSessionSeq = 0;
/** Increments when the researcher deliberately changes the model. Catalog
 *  requests capture the value they started with, so a stale response cannot
 *  overwrite a newer selection after the switch has completed. */
let modelSelectionSeq = 0;
let lastSwitchModel: string | null = null;
let lastSwitchAt = 0;
const SWITCH_HEAL_GRACE_MS = 15_000;
/** React StrictMode mounts effects twice in development. Share the same boot
 *  promise so duplicate AppShell effects cannot start dueling connect loops. */
let bootstrapInFlight: Promise<void> | null = null;
/** Unhook the current client's status listener BEFORE closing it — teardown
 *  emits "offline", and a reconnect attempt must not flash that at the user. */
let clientStatusUnsub: (() => void) | null = null;
/** The SDK recovers a dropped stream in ~250ms (OpenCode closes /event ~1s
 *  after a config PATCH while rebuilding its instance). Surfacing that blip
 *  repaints every status consumer, so a ready→connecting flip is held this
 *  long and only shown if the stream does not come back. */
const STATUS_BLIP_GRACE_MS = 2000;
let statusBlipTimer: ReturnType<typeof setTimeout> | null = null;
function clearStatusBlip() {
  if (statusBlipTimer !== null) clearTimeout(statusBlipTimer);
  statusBlipTimer = null;
}
function teardownClient() {
  clientStatusUnsub?.();
  clientStatusUnsub = null;
  clearStatusBlip();
  client?.close();
  client = null;
  opencodeClient = null;
  pendingPromptContexts.clear();
  errorRecoveries.clear();
  errorRecoveryIdle.clear();
}
const emptyThread = (): Thread => ({ blocks: [], index: {}, loaded: false });
/** Threads key for the draft conversation — its blocks move to the real
 *  session id once the session exists, so the page never visibly resets. */
export const DRAFT_KEY = "draft";
export type AgentMode = "build" | "plan";
/** One bounded retry for the first POSTs after a sidecar restart — the old
 *  connection occasionally dies mid-handshake ("Load failed"). */
async function withRetry<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch {
    await sleep(600);
    return await fn();
  }
}
/** Remember only the newest keys. Long-running desktop sessions can receive
 *  many repeated SSE events, so deduplication state must not grow forever. */
export function rememberBounded(set: Set<string>, key: string, cap = 4000): void {
  if (set.has(key)) return;
  set.add(key);
  while (set.size > cap) {
    const oldest = set.values().next().value as string | undefined;
    if (oldest === undefined) break;
    set.delete(oldest);
  }
}

function setBoundedMap<K, V>(map: Map<K, V>, key: K, value: V, cap: number): void {
  map.delete(key);
  map.set(key, value);
  while (map.size > cap) {
    const oldest = map.keys().next().value as K | undefined;
    if (oldest === undefined) break;
    map.delete(oldest);
  }
}
/** Tool calls already written to provenance — success events can repeat per callId. */
const recordedProvenance = new Set<string>();
/** Bash calls already written to the run store — terminal events can repeat per callId. */
const recordedRuns = new Set<string>();

/** Sessions the user just interrupted: the thread already shows "Interrupted",
 *  so the abort's own trailing events (an "aborted" error and one or more
 *  session.idle events) must not add a second line. Armed before the abort POST
 *  and held across every trailing event; the next turn clears it (`turn → sid`). */
const interruptedSessions = new Set<string>();

/** Server-side truth for "is this session's turn over": the last message is an
 *  assistant message that has finished streaming (time.completed set). A last
 *  USER message means a turn was accepted but not yet answered — still running. */
export function turnIsOver(messages: HistoryMessage[]): boolean {
  const last = messages[messages.length - 1];
  return !!last && last.role === "assistant" && (!!last.completed || !!last.error);
}

/** OpenCode 1.17.13 can leave an unfinished assistant message after a provider
 * failure or sidecar restart even when its final SSE error never reaches the
 * client. It may be blank, or may contain completed setup steps plus one
 * orphaned running tool. Two inactive server polls are required before the
 * caller treats it as stopped. */
export function turnStoppedWithoutReply(
  messages: HistoryMessage[],
  status: SessionRuntimeStatus | undefined,
): boolean {
  const last = messages[messages.length - 1];
  const active = status?.type === "busy" || status?.type === "retry";
  return !active && !!last && last.role === "assistant" && !last.completed && !last.error;
}

/** Last SSE arrival per session (monotonic sequence, not wall time). Lets a
 *  failed sync POST tell "the connection died but the turn is alive" (events
 *  kept arriving after the POST began) from "the send never took" — WKWebView
 *  kills any fetch at ~60 s, long before a long agent turn finishes. */
let sseSeq = 0;
const sseLast = new Map<string, number>();
/** Require two consecutive inactive polls before declaring a blank turn dead. */
const inactiveTurnPolls = new Map<string, number>();

function friendlyRuntimeError(message: string): string {
  return /rate\s*limit|too many requests|quota|请求过于频繁/i.test(message)
    ? i18n.t("session:live.status.rateLimited")
    : message;
}

/** Coalescing for live bash output: a running tool emits an event per stdout
 *  write (a progress bar redraws dozens of times a second) — fold at most one
 *  partial-output update per interval per call, latest event wins. */
const LIVE_FOLD_MS = 250;
const liveFoldLast = new Map<string, number>();
const liveFoldPending = new Map<
  string,
  { sessionId: string; timer: number; event: Extract<OpenCodeEvent, { type: "tool.updated" }> }
>();

export function buildAssetReviewPrompt(text: string): string {
  return (
    "Evaluate the following external Skill, plugin, MCP server, or calculation package as an " +
    "AI4HEOR asset candidate. Do not install, enable, or copy it into .opencode/skills. Keep it " +
    "inactive. Establish the exact source revision and license; map workspace access, network " +
    "egress, executable dependencies, and authority; identify the smallest first-party derivative " +
    "or isolated adapter; define contract, regression, adversarial, and macOS/Windows/Linux tests; " +
    "and preserve every unresolved blocker. No asset may create human approvals, claim independent " +
    "validation, or produce authoritative HEOR calculations. Write a review package under " +
    "heor/asset-reviews/<safe-name>/ and finish with a natural-language recommendation. Updating the " +
    "app's release registry remains a separate code-reviewed product change.\n\n---\n" +
    text
  );
}

/** Drop a session's queued partial folds — when its turn ends (idle, error,
 *  interrupt) a late timer must not fold a stale "running" event into a
 *  thread the history reload may have rebuilt. */
function clearLiveFolds(sessionId: string) {
  for (const [callId, p] of liveFoldPending) {
    if (p.sessionId !== sessionId) continue;
    window.clearTimeout(p.timer);
    liveFoldPending.delete(callId);
    liveFoldLast.delete(callId);
  }
}

/** Resolve a (possibly nested) subagent session to its top-level session —
 *  a subagent's question/permission belongs to the conversation the user sees. */
export function rootSessionOf(parents: Record<string, string>, sessionId: string): string {
  let cur = sessionId;
  for (let hop = 0; parents[cur] && hop < 10; hop++) cur = parents[cur];
  return cur;
}

type StoreSet = {
  (partial: Partial<RuntimeState>): void;
  (fn: (s: RuntimeState) => Partial<RuntimeState>): void;
};
type StoreGet = () => RuntimeState;

/**
 * The one send lifecycle (new → input → send → response), shared by plain
 * prompts, "!" shell commands and "/" slash commands:
 *   1. `echo` lands in the thread IMMEDIATELY — on a draft under DRAFT_KEY,
 *      grafted onto the real session id later, so the page never resets.
 *   2. `sending` is true from click until the POST is accepted (locks the
 *      composer); the session sits in `runningSessions` while the turn runs.
 *   3. Failures land as a red status line inside the conversation.
 * Every turn arms its running lock BEFORE the POST. SSE events can beat either
 * a long-running shell/command response or the short prompt_async acceptance
 * response; setting the lock afterwards would resurrect a turn that already
 * emitted session.idle.
 * `syncTurn` marks endpoints whose POST resolves only when the turn is OVER
 * (shell/command, unlike prompt_async), so their lock is also cleared when the
 * POST settles if no terminal SSE event did so first.
 * `shell` additionally marks the turn in `shellTurns` for its duration, so
 * the event fold shows the bash output inline.
 */
async function performTurn(
  set: StoreSet,
  get: StoreGet,
  echo: string,
  post: (sid: string) => Promise<void>,
  syncTurn: boolean,
  shell = false,
  promptContext: HeorPromptContext | null = null,
): Promise<string | null> {
  if (!client) {
    set({ error: "Not connected to the AI assistant runtime." });
    return null;
  }
  if (get().sending) return null; // one send at a time
  const echoKey = get().currentId ?? DRAFT_KEY;
  // Keep the turn attached to the task that started it. The researcher may
  // open another task while the provider request is still in flight.
  let turnKey = echoKey;
  set((s) => {
    const cur = s.threads[echoKey] ?? emptyThread();
    return {
      sending: true,
      threads: {
        ...s.threads,
        [echoKey]: { ...cur, loaded: true, blocks: [...cur.blocks, { kind: "user", text: echo }] },
      },
    };
  });
  try {
    let id = get().currentId;
    if (!id) {
      // A standalone task gets its own local research scope. Choosing
      // a project pins the conversation to that project's shared workspace;
      // neither path changes the assistant, skills, files, or HEOR methods the
      // researcher can use.
      if (isTauri && !get().workspacePinned) {
        if (!(await get().ensureStandaloneWorkspace()) || !client) {
          throw new Error(
            get().error ?? "Runtime did not reconnect after creating the conversation workspace.",
          );
        }
      } else if (isTauri && get().workspacePinned) {
        set({ switching: true });
        try {
          await get().connectRetry();
        } finally {
          set({ switching: false });
        }
        if (get().status !== "ready" || !client) {
          throw new Error("Runtime did not reconnect before creating the conversation.");
        }
      }
      id = await withRetry(() => client!.createSession());
      turnKey = id;
      set((s) => {
        // Graft the draft conversation (and its pane) onto the real session id.
        const threads = { ...s.threads, [id!]: s.threads[DRAFT_KEY] ?? emptyThread() };
        delete threads[DRAFT_KEY];
        const panes = { ...s.panes };
        if (panes[DRAFT_KEY]) {
          panes[id!] = panes[DRAFT_KEY];
          delete panes[DRAFT_KEY];
        }
        const promptQueues = { ...s.promptQueues };
        if (promptQueues[DRAFT_KEY]?.length) {
          promptQueues[id!] = promptQueues[DRAFT_KEY];
        }
        delete promptQueues[DRAFT_KEY];
        return { currentId: id, threads, panes, promptQueues };
      });
      moveScrollMemory(`chat:${DRAFT_KEY}`, `chat:${id}`);
      void get().refreshSessions();
    }
    const sid = id;
    interruptedSessions.delete(sid); // a fresh turn folds its events normally
    inactiveTurnPolls.delete(sid); // inactivity evidence never carries into a new turn
    void logDebug(`turn → ${sid}`);
    if (get().stepCounts[sid]) {
      set((s) => {
        const stepCounts = { ...s.stepCounts };
        delete stepCounts[sid];
        return { stepCounts };
      });
    }
    if (promptContext) pendingPromptContexts.set(sid, promptContext);
    if (syncTurn) {
      set((s) => ({
        runningSessions: { ...s.runningSessions, [sid]: true },
        sessionProgress: { ...s.sessionProgress, [sid]: { type: "busy" } },
        ...(shell ? { shellTurns: { ...s.shellTurns, [sid]: true as const } } : {}),
      }));
      const mark = sseSeq;
      try {
        await post(sid);
      } catch (err) {
        // The POST rejected — but shell/command POSTs are held open for the
        // WHOLE turn, and WKWebView kills any fetch at ~60 s. If SSE kept
        // streaming this session since the POST began, the turn is alive
        // server-side: keep the running lock (session.idle or a session error
        // will clear it) and don't report a failure that didn't happen.
        if ((sseLast.get(sid) ?? 0) > mark) {
          void logDebug(`turn POST dropped mid-turn, still running → ${sid}`);
          return sid;
        }
        // A genuinely failed POST produces no events — drop both flags here.
        // (On success the session.idle event clears the shell flag, never the
        // POST settling: SSE frames and the POST response race on separate
        // connections, and the bash-output event may land after the POST
        // resolves.)
        set((s) => {
          const runningSessions = { ...s.runningSessions };
          const shellTurns = { ...s.shellTurns };
          const sessionProgress = { ...s.sessionProgress };
          const stepCounts = { ...s.stepCounts };
          delete runningSessions[sid];
          delete shellTurns[sid];
          delete sessionProgress[sid];
          delete stepCounts[sid];
          return { runningSessions, shellTurns, sessionProgress, stepCounts };
        });
        throw err;
      }
      set((s) => {
        const runningSessions = { ...s.runningSessions };
        const sessionProgress = { ...s.sessionProgress };
        const stepCounts = { ...s.stepCounts };
        delete runningSessions[sid];
        delete sessionProgress[sid];
        delete stepCounts[sid];
        return { runningSessions, sessionProgress, stepCounts };
      });
    } else {
      set((s) => ({
        runningSessions: { ...s.runningSessions, [sid]: true },
        sessionProgress: { ...s.sessionProgress, [sid]: { type: "busy" } },
      }));
      try {
        await post(sid);
      } catch (err) {
        // prompt_async normally returns after accepting the turn. If the
        // request itself fails before any terminal SSE event can arrive, undo
        // the pre-armed lock here; otherwise session.idle owns the unlock.
        set((s) => {
          const runningSessions = { ...s.runningSessions };
          const sessionProgress = { ...s.sessionProgress };
          const stepCounts = { ...s.stepCounts };
          delete runningSessions[sid];
          delete sessionProgress[sid];
          delete stepCounts[sid];
          return { runningSessions, sessionProgress, stepCounts };
        });
        throw err;
      }
    }
    void logDebug("turn OK");
    return sid;
  } catch (err) {
    if (turnKey !== DRAFT_KEY && pendingPromptContexts.get(turnKey) === promptContext) {
      pendingPromptContexts.delete(turnKey);
    }
    const msg = err instanceof Error ? err.message : String(err);
    void logDebug(`turn FAILED: ${msg}`);
    // The failure belongs next to the message that caused it.
    set((s) => {
      const cur = s.threads[turnKey] ?? emptyThread();
      return {
        threads: {
          ...s.threads,
          [turnKey]: {
            ...cur,
            loaded: true,
            blocks: [...cur.blocks, { kind: "status-line", text: `Send failed: ${msg}`, tone: "error" }],
          },
        },
      };
    });
    return turnKey === DRAFT_KEY ? null : turnKey;
  } finally {
    set({ sending: false });
  }
}

/** Restore the task and its local files to immediately before `messageID`.
 *
 * OpenCode may briefly return 404 while its newly accepted message is still
 * being indexed, so the request is retried a few times. The UI truncates only
 * after the runtime confirms the rollback. Pending interaction cards and
 * inspectors belong to the discarded future and must not survive it. */
async function revertToMessage(
  set: StoreSet,
  get: StoreGet,
  messageID: string,
): Promise<boolean> {
  const sid = get().currentId;
  const c = client;
  if (!sid || !c) return false;

  if (get().runningSessions[sid]) await get().interrupt();

  let lastError: unknown;
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      await c.revert(sid, messageID);
      lastError = undefined;
      break;
    } catch (error) {
      lastError = error;
      if (attempt < 4) await sleep(200);
    }
  }
  if (lastError) {
    const message = lastError instanceof Error ? lastError.message : String(lastError);
    set({ error: i18n.t("session:message.revertFailed", { message }) });
    return false;
  }

  clearLiveFolds(sid);
  interruptedSessions.delete(sid);
  inactiveTurnPolls.delete(sid);
  set((s) => {
    const current = s.threads[sid] ?? emptyThread();
    const index = current.blocks.findIndex(
      (block) => block.kind === "user" && block.messageID === messageID,
    );
    const runningSessions = { ...s.runningSessions };
    const shellTurns = { ...s.shellTurns };
    const sessionProgress = { ...s.sessionProgress };
    const stepCounts = { ...s.stepCounts };
    delete runningSessions[sid];
    delete shellTurns[sid];
    delete sessionProgress[sid];
    delete stepCounts[sid];
    return {
      error: null,
      runningSessions,
      shellTurns,
      sessionProgress,
      stepCounts,
      questions: s.questions.filter(
        (question) => rootSessionOf(s.sessionParents, question.sessionId) !== sid,
      ),
      permissions: s.permissions.filter(
        (permission) => rootSessionOf(s.sessionParents, permission.sessionId) !== sid,
      ),
      panes: {
        ...s.panes,
        [sid]: { artifact: null, showFiles: false, showRuns: false },
      },
      threads: {
        ...s.threads,
        [sid]: {
          ...current,
          blocks: index >= 0 ? current.blocks.slice(0, index) : current.blocks,
          index: {},
          loaded: true,
        },
      },
    };
  });
  await commitWorkspaceSnapshot(`Return task ${sid} to an earlier message`).catch(() => false);
  void get().refreshSessions();
  return true;
}

/** The live OpenCode client (Settings talks to the runtime's config API directly). */
export function getClient(): OpenCodeClient | null {
  return opencodeClient;
}

export const useRuntimeStore = create<RuntimeState>((set, get) => ({
  status: "offline",
  serverUrl: initialUrl(),
  sessions: [],
  currentId: null,
  draftEpoch: 0,
  threads: {},
  skills: [],
  agents: [],
  commands: [],
  defaultModel: null,
  modelSwitchError: null,
  approvalMode: "approve",
  tools: [],
  hiddenExamples: initialHidden(),
  error: null,
  questions: [],
  permissions: [],
  sessionParents: {},
  panes: {},
  sessionAgents: {},
  promptQueues: {},
  setAgentMode: (mode) =>
    set((state) => ({
      sessionAgents: { ...state.sessionAgents, [state.currentId ?? DRAFT_KEY]: mode },
    })),
  enqueuePrompt: (text, skill) => {
    const id = nextQueuedPromptId();
    const prompt: QueuedPrompt = { id, text: text.trim(), ...(skill ? { skill } : {}) };
    set((state) => {
      const key = state.currentId ?? DRAFT_KEY;
      return {
        promptQueues: {
          ...state.promptQueues,
          [key]: [...(state.promptQueues[key] ?? []), prompt],
        },
      };
    });
    return id;
  },
  removeQueuedPrompt: (id) =>
    set((state) => {
      const key = state.currentId ?? DRAFT_KEY;
      return {
        promptQueues: {
          ...state.promptQueues,
          [key]: (state.promptQueues[key] ?? []).filter((prompt) => prompt.id !== id),
        },
      };
    }),
  moveQueuedPrompt: (id, direction) =>
    set((state) => {
      const key = state.currentId ?? DRAFT_KEY;
      const queue = [...(state.promptQueues[key] ?? [])];
      const index = queue.findIndex((prompt) => prompt.id === id);
      const target = direction === "up" ? index - 1 : index + 1;
      if (index < 0 || target < 0 || target >= queue.length) return state;
      [queue[index], queue[target]] = [queue[target], queue[index]];
      return { promptQueues: { ...state.promptQueues, [key]: queue } };
    }),
  takeNextQueuedPrompt: () => {
    const state = get();
    const key = state.currentId ?? DRAFT_KEY;
    const queue = state.promptQueues[key] ?? [];
    const prompt = queue[0] ?? null;
    if (!prompt) return null;
    set({ promptQueues: { ...state.promptQueues, [key]: queue.slice(1) } });
    return prompt;
  },
  requeuePromptFront: (prompt) =>
    set((state) => {
      const key = state.currentId ?? DRAFT_KEY;
      return {
        promptQueues: {
          ...state.promptQueues,
          [key]: [prompt, ...(state.promptQueues[key] ?? [])],
        },
      };
    }),
  projects: [],
  researchScope: null,
  workspace: null,
  workspacePinned: false,
  switching: false,
  sending: false,
  runningSessions: {},
  sessionProgress: {},
  stepCounts: {},
  shellTurns: {},

  // These write the CURRENT session's pane (DRAFT_KEY on a draft), keeping the
  // artifact inspector, the Files browser, and the Runs pane mutually exclusive
  // — one pane at a time.
  openArtifact: (artifact) =>
    set((s) => ({
      panes: { ...s.panes, [s.currentId ?? DRAFT_KEY]: { artifact, showFiles: false, showRuns: false } },
    })),
  closeArtifact: () =>
    set((s) => {
      const key = s.currentId ?? DRAFT_KEY;
      const p = s.panes[key];
      return { panes: { ...s.panes, [key]: { artifact: null, showFiles: p?.showFiles ?? false, showRuns: p?.showRuns ?? false } } };
    }),
  setShowFiles: (show) =>
    set((s) => {
      const key = s.currentId ?? DRAFT_KEY;
      const p = s.panes[key];
      return {
        panes: {
          ...s.panes,
          [key]: { artifact: show ? null : (p?.artifact ?? null), showFiles: show, showRuns: show ? false : (p?.showRuns ?? false) },
        },
      };
    }),
  setShowRuns: (show) =>
    set((s) => {
      const key = s.currentId ?? DRAFT_KEY;
      const p = s.panes[key];
      return {
        panes: {
          ...s.panes,
          [key]: { artifact: show ? null : (p?.artifact ?? null), showFiles: show ? false : (p?.showFiles ?? false), showRuns: show },
        },
      };
    }),

  answerQuestion: async (requestId, answers) => {
    const q = get().questions.find((x) => x.requestId === requestId);
    if (!q || !client) return;
    set((s) => ({ questions: s.questions.filter((x) => x.requestId !== requestId) }));
    try {
      await client.answerQuestion(requestId, answers);
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) });
    }
  },
  rejectQuestion: async (requestId) => {
    const q = get().questions.find((x) => x.requestId === requestId);
    if (!q || !client) return;
    set((s) => ({ questions: s.questions.filter((x) => x.requestId !== requestId) }));
    try {
      await client.rejectQuestion(requestId);
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) });
    }
  },
  replyPermission: async (requestId, reply) => {
    const p = get().permissions.find((x) => x.requestId === requestId);
    if (!p || !client) return;
    // Identical pending asks (same session, action and resources — e.g. three
    // parallel reads into one folder) are ONE question to the user: answer
    // them all with one click instead of re-asking for each tool call.
    const sig = (x: PermissionAskedEvent) =>
      `${x.sessionId}|${x.action}|${x.resources.join("|")}`;
    const batch = get().permissions.filter((x) => sig(x) === sig(p));
    set((s) => ({ permissions: s.permissions.filter((x) => sig(x) !== sig(p)) }));
    try {
      await Promise.all(batch.map((x) => client!.replyPermission(x.requestId, reply)));
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) });
    }
  },

  setServerUrl: (serverUrl) => {
    if (typeof window !== "undefined") window.localStorage.setItem(URL_KEY, serverUrl);
    set({ serverUrl, modelSwitchError: null });
  },

  loadCatalog: async () => {
    if (!client) return;
    const selectionSeq = modelSelectionSeq;
    try {
      const [firstSkills, agents, defaultModel, commands, providers] = await Promise.all([
        client.listSkills(),
        client.listAgents(),
        client.getDefaultModel().catch(() => null),
        client.listCommands().catch(() => []),
        client.listProviders().catch(() => []),
      ]);
      // A model switch in flight owns `defaultModel`: this read may predate
      // the switch's config write, and applying it would visibly revert the
      // just-selected model.
      set(
        get().switching || selectionSeq !== modelSelectionSeq
          ? { agents, commands }
          : { agents, defaultModel, commands },
      );
      const justSwitched =
        defaultModel === lastSwitchModel && Date.now() - lastSwitchAt < SWITCH_HEAL_GRACE_MS;
      if (
        !get().switching &&
        selectionSeq === modelSelectionSeq &&
        !justSwitched &&
        defaultModel
      ) {
        const fallback = fallbackDefaultModel(providers, defaultModel);
        if (fallback) {
          try {
            await get().setDefaultModel(fallback);
            void logDebug(`[provider] unavailable model ${defaultModel}; selected ${fallback}`);
          } catch {
            // The existing send-time error remains visible if recovery fails.
          }
        }
      }
      let skills = firstSkills;
      // The first workspace-scoped /api/skill call triggers OpenCode's lazy
      // instance init and can answer before the scan finishes — poll briefly.
      for (let i = 0; skills.length === 0 && i < 4; i++) {
        await sleep(400);
        skills = await client.listSkills();
      }
      set({ skills });
    } catch {
      /* ignore transient failures */
    }
  },

  detectTools: async () => {
    try {
      set({ tools: await probeTools() });
    } catch {
      /* ignore */
    }
  },

  setApprovalMode: async (mode) => {
    // Persisting this setting restarts the sidecar. Refuse the transition while
    // any turn is active so a settings surface can never kill another
    // conversation's in-flight model/tool work. The live composer also disables
    // the control, but this store guard is the authoritative boundary.
    if (get().sending || Object.keys(get().runningSessions).length > 0) {
      void logDebug("approval mode change ignored while a task is running");
      return;
    }
    // A deliberate restart, like switchWorkspace: `switching` keeps the UI
    // rendering as connected — no status flip, no page flash.
    set({ switching: true });
    try {
      await persistApprovalMode(mode); // writes the config; restarts the sidecar
      set({ approvalMode: mode });
      await get().connectRetry();
    } finally {
      set({ switching: false });
    }
  },

  setProxySetting: async (mode, url) => {
    // Same masked restart as setApprovalMode: the proxy env applies at spawn.
    set({ switching: true });
    try {
      await persistProxySetting(mode, url); // persists; restarts the sidecar
      await get().connectRetry();
    } finally {
      set({ switching: false });
    }
  },

  setDefaultModel: async (model) => {
    if (!client) throw new Error("Not connected to the AI assistant runtime.");
    modelSelectionSeq += 1;
    lastSwitchModel = model;
    lastSwitchAt = Date.now();
    // Applying the model PATCHes OpenCode's global config, which closes the
    // event stream server-side. EventSource's own reconnect does not reliably
    // recover from that — it strands the app in "connecting"/disconnected until
    // a manual Connect. So do a deliberate masked reconnect (a fresh stream,
    // exactly what the manual Connect did): `switching` keeps the UI connected,
    // so switching models never flips the status or blocks the composer.
    set({ switching: true });
    try {
      await client.setDefaultModel(model);
      set({ defaultModel: model });
      if (!(await get().connectRetry())) {
        throw new Error(
          get().error ?? "Runtime did not reconnect after setting the default model.",
        );
      }
      set({ modelSwitchError: null });
    } catch (err) {
      set({ modelSwitchError: err instanceof Error ? err.message : String(err) });
      throw err;
    } finally {
      set({ switching: false });
    }
  },

  connect: async () => {
    // Quiet teardown of any previous connection: within a (re)connect the
    // status must never pass through "offline" — on first boot the retry loop
    // runs for minutes (macOS TCC) and each flip repaints the whole page.
    teardownClient();
    // Scope skill discovery to the sidecar's workspace (null in browser dev).
    const directory = await workspacePath();
    set({ workspace: directory, approvalMode: await getApprovalMode() });
    // The bundled sidecar requires per-run Basic auth; browser dev (no Tauri)
    // gets null and connects to a user-run passwordless server.
    const password = await runtimePassword();
    const c = new OpenCodeClient({
      baseUrl: get().serverUrl,
      directory: directory ?? undefined,
      password: password ?? undefined,
    });
    opencodeClient = c;
    client = c;
    clientStatusUnsub = c.onStatus((status) => {
      void logDebug(`status → ${status}`);
      if (status === "connecting" && get().status === "ready") {
        // Hold the flip for STATUS_BLIP_GRACE_MS: if the SDK's own reconnect
        // lands first ("ready" clears the timer), the UI never sees the blip.
        if (statusBlipTimer === null)
          statusBlipTimer = setTimeout(() => {
            statusBlipTimer = null;
            set({ status: "connecting" });
          }, STATUS_BLIP_GRACE_MS);
        return;
      }
      clearStatusBlip();
      set({ status });
    });
    c.onEvent((event) => {
      // text.updated fires per streamed token, and a running bash tool fires
      // per stdout write (tqdm redraws dozens of times a second) — logging
      // each one would flood debug.log with an IPC call per event.
      if (
        event.type !== "text.updated" &&
        event.type !== "reasoning.updated" &&
        !(event.type === "tool.updated" && event.status === "running")
      )
        void logDebug(`event ← ${event.type}${"sessionId" in event ? " " + event.sessionId : ""}`);
      if ("sessionId" in event && event.sessionId)
        setBoundedMap(sseLast, event.sessionId, ++sseSeq, 500);
      if (event.type === "message.usage") {
        void recordModelCall(event, pendingPromptContexts.get(event.sessionId));
        return;
      }
      if (event.type === "error") {
        // A session-scoped error belongs IN the conversation (a red status
        // line where the user is looking). Keep the running lock until the
        // server's trailing session.idle: sending the next queued turn in the
        // error/idle gap can persist its user message without running a model.
        // If idle is lost, reconcileRunning clears the lock from history.
        // Errors without a session keep the banner.
        const sid = event.sessionId;
        if (sid) pendingPromptContexts.delete(sid);
        // After a user interrupt the abort's own "aborted" error is expected —
        // the thread already says "Interrupted"; don't add a second red line.
        if (sid) clearLiveFolds(sid);
        if (sid && interruptedSessions.has(sid)) return;
        if (sid) {
          if (client && !errorRecoveries.has(sid)) {
            const recovery = Promise.resolve()
              .then(() => client?.abortSession(sid))
              .then(() => undefined)
              .catch((error) => {
                void logDebug(`provider error recovery failed for ${sid}: ${String(error)}`);
              })
              .finally(() => {
                errorRecoveries.delete(sid);
                if (!errorRecoveryIdle.delete(sid)) return;
                set((s) => {
                  const runningSessions = { ...s.runningSessions };
                  const shellTurns = { ...s.shellTurns };
                  const sessionProgress = { ...s.sessionProgress };
                  const stepCounts = { ...s.stepCounts };
                  delete runningSessions[sid];
                  delete shellTurns[sid];
                  delete sessionProgress[sid];
                  delete stepCounts[sid];
                  inactiveTurnPolls.delete(sid);
                  return { runningSessions, shellTurns, sessionProgress, stepCounts };
                });
              });
            errorRecoveries.set(sid, recovery);
          }
          set((s) => {
            const cur = s.threads[sid] ?? emptyThread();
            const sessionProgress = { ...s.sessionProgress };
            const stepCounts = { ...s.stepCounts };
            delete sessionProgress[sid];
            delete stepCounts[sid];
            return {
              sessionProgress,
              stepCounts,
              threads: {
                ...s.threads,
                [sid]: {
                  ...cur,
                  loaded: true,
                  blocks: [...cur.blocks, {
                    kind: "status-line",
                    text: friendlyRuntimeError(event.message),
                    tone: "error",
                  }],
                },
              },
            };
          });
        } else {
          set({ error: event.message });
        }
        return;
      }
      if (event.type === "session.status") {
        set((s) => ({
          sessionProgress: {
            ...s.sessionProgress,
            [event.sessionId]: {
              type: event.status,
              attempt: event.attempt,
              message: event.message,
              next: event.next,
            },
          },
        }));
        return;
      }
      // Interactive requests live outside the thread blocks (transient UI).
      switch (event.type) {
        case "message.user":
          set((s) => {
            const current = s.threads[event.sessionId] ?? emptyThread();
            const blocks = [...current.blocks];
            for (let index = blocks.length - 1; index >= 0; index--) {
              const block = blocks[index];
              if (block.kind === "user" && !block.messageID) {
                blocks[index] = { ...block, messageID: event.messageID };
                break;
              }
            }
            return {
              threads: {
                ...s.threads,
                [event.sessionId]: { ...current, blocks, loaded: true },
              },
            };
          });
          return;
        case "question.asked":
          set((s) => ({
            questions: [...s.questions.filter((q) => q.requestId !== event.requestId), event],
          }));
          return;
        case "question.resolved":
          set((s) => ({ questions: s.questions.filter((q) => q.requestId !== event.requestId) }));
          return;
        case "permission.asked":
          set((s) => ({
            permissions: [
              ...s.permissions.filter((p) => p.requestId !== event.requestId),
              event,
            ],
          }));
          return;
        case "permission.resolved":
          set((s) => ({ permissions: s.permissions.filter((p) => p.requestId !== event.requestId) }));
          return;
        case "step.updated":
          set((s) => ({ stepCounts: { ...s.stepCounts, [event.sessionId]: event.step } }));
          return;
      }
      const sid = event.sessionId;
      if (!sid) return;
      if (event.type === "session.idle") pendingPromptContexts.delete(sid);
      if (event.type === "session.idle") clearLiveFolds(sid);
      // Idle after a user interrupt: the thread already ends with "Interrupted"
      // — keep the locks clear and skip the fold. An abort can emit MORE than
      // one idle, so the guard must survive every trailing idle (`.has`, not
      // `.delete`); it is cleared when the next turn starts (see `turn → sid`).
      if (event.type === "session.idle" && interruptedSessions.has(sid)) {
        set((s) => {
          const runningSessions = { ...s.runningSessions };
          const shellTurns = { ...s.shellTurns };
          const sessionProgress = { ...s.sessionProgress };
          const stepCounts = { ...s.stepCounts };
          delete runningSessions[sid];
          delete shellTurns[sid];
          delete sessionProgress[sid];
          delete stepCounts[sid];
          inactiveTurnPolls.delete(sid);
          return { runningSessions, shellTurns, sessionProgress, stepCounts };
        });
        void get().refreshSessions();
        return;
      }
      // A task tool names the subagent session it spawned — remember the
      // parent link so the child's permission/question asks surface in THIS
      // conversation, and refresh the list so the child's title is known.
      if (
        event.type === "tool.updated" &&
        event.childSessionId &&
        get().sessionParents[event.childSessionId] !== sid
      ) {
        const child = event.childSessionId;
        set((s) => ({ sessionParents: { ...s.sessionParents, [child]: sid } }));
        void get().refreshSessions();
      }
      const applyFold = (ev: typeof event) =>
        set((s) => {
          const cur = s.threads[sid] ?? emptyThread();
          const folded = foldEvent(
            { blocks: cur.blocks, index: cur.index },
            ev,
            { shellTurn: !!s.shellTurns[sid] },
          );
          // The turn is over — unlock the composer and drop the "Working…" row.
          // The shell flag clears HERE (not when the POST settles): within the
          // SSE stream the bash-output event always precedes session.idle.
          const runningSessions = { ...s.runningSessions };
          const shellTurns = { ...s.shellTurns };
          const sessionProgress = { ...s.sessionProgress };
          const stepCounts = { ...s.stepCounts };
          if (ev.type === "session.idle") {
            if (errorRecoveries.has(sid)) {
              errorRecoveryIdle.add(sid);
            } else {
              delete runningSessions[sid];
              delete shellTurns[sid];
              delete sessionProgress[sid];
              delete stepCounts[sid];
              inactiveTurnPolls.delete(sid);
            }
          }
          return {
            runningSessions,
            shellTurns,
            sessionProgress,
            stepCounts,
            threads: { ...s.threads, [sid]: { ...cur, ...folded, loaded: true } },
          };
        });
      // A running bash tool streams its stdout tail on every write — dozens
      // of events per second under a progress bar. Fold at most one partial
      // update per LIVE_FOLD_MS per call (latest wins); everything else
      // (status changes, completion) folds immediately and supersedes.
      if (event.type === "tool.updated") {
        if (event.status === "running" && event.partialOutput !== undefined) {
          const now = Date.now();
          const last = liveFoldLast.get(event.callId) ?? 0;
          if (now - last < LIVE_FOLD_MS) {
            const pending = liveFoldPending.get(event.callId);
            if (pending) pending.event = event;
            else {
              const callId = event.callId;
              const timer = window.setTimeout(() => {
                const p = liveFoldPending.get(callId);
                liveFoldPending.delete(callId);
                if (!p) return;
                liveFoldLast.set(callId, Date.now());
                applyFold(p.event);
              }, LIVE_FOLD_MS - (now - last));
              liveFoldPending.set(event.callId, { sessionId: sid, timer, event });
            }
            return;
          }
          liveFoldLast.set(event.callId, now);
        } else {
          const pending = liveFoldPending.get(event.callId);
          if (pending) {
            window.clearTimeout(pending.timer);
            liveFoldPending.delete(event.callId);
          }
          liveFoldLast.delete(event.callId);
        }
      }
      applyFold(event);
      // apply_patch can update several files in one call. Record and dedupe
      // every resulting artifact independently so the audit trail is complete.
      if (event.type === "tool.updated") {
        for (const input of provenanceInputsFromEvent(event)) {
          const key = `${event.callId}:${input.path}`;
          if (recordedProvenance.has(key)) continue;
          rememberBounded(recordedProvenance, key);
          void recordProvenance(input, sid, get().defaultModel);
        }
      }
      // A completed experiment execution (bash running code) becomes a run —
      // its reproducibility recipe (once per call).
      if (event.type === "tool.updated" && !recordedRuns.has(event.callId)) {
        const run = runInputFromEvent(event);
        if (run) {
          rememberBounded(recordedRuns, event.callId);
          void recordRun(run, sid, get().defaultModel);
        }
      }
      if (event.type === "session.idle") {
        void get().refreshSessions();
        // Name the session in the snapshot: a project folder is shared by many
        // sessions, and its git history must say which one made each change.
        const sessionName = get().sessions.find((s) => s.id === sid)?.title || sid;
        void commitWorkspaceSnapshot(`Snapshot session changes (${sessionName})`)
          .then((committed) => {
            if (committed) void logDebug(`git snapshot ✓ ${sid}`);
          })
          .catch((err) =>
            logDebug(`git snapshot skipped for ${sid}: ${err instanceof Error ? err.message : String(err)}`),
          );
      }
    });
    try {
      void logDebug(`connect → ${get().serverUrl}`);
      await c.connect();
      void logDebug("connect OK");
      set({ error: null });
      await get().refreshSessions();
      // Await the local project scan so the sidebar and active-scope label are
      // coherent when connect() resolves. Standalone tasks do not
      // depend on this list.
      await get().refreshProjects();
      // Catalog (skills/agents/commands) fills in behind the page — a session
      // switch must not wait on it to show the conversation.
      void get().loadCatalog();
      // Every reconnect is a window where session.idle can have been missed
      // (the event stream is directory-scoped and torn down on purpose) —
      // check any session still holding a running lock against the server.
      void get().reconcileRunning();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      void logDebug(`connect FAILED: ${msg}`);
      set({ error: msg, status: "error" });
    }
  },

  // First boot can be slow far beyond the process spawn: on a fresh install
  // macOS TCC ("access Documents") blocks the sidecar until the user answers,
  // so the window must cover minutes, not seconds — giving up early strands
  // the user on an error screen that a single manual Connect would fix.
  // Failed attempts are masked (status AND error): workspace switches
  // reconnect the event stream on purpose, and flashing "could not open the
  // event stream" at the user mid-switch reads as breakage. The last error is
  // surfaced only if the whole retry window is exhausted.
  connectRetry: async (tries = 120) => {
    set({ status: "connecting" });
    let lastError: string | null = null;
    for (let i = 0; i < tries; i++) {
      await get().connect();
      if (get().status === "ready") {
        set({ modelSwitchError: null });
        return true;
      }
      lastError = get().error ?? lastError;
      set({ status: "connecting", error: null });
      // Quick retries first — the server is usually up within a second (a
      // reconnect finds it already listening); back off to 1 s for the long
      // tail (first boot blocked on macOS TCC can take minutes).
      await sleep(i < 8 ? 250 : 1000);
    }
    set({ status: "error", error: lastError });
    return false;
  },

  restartLocalRuntime: async () => {
    if (!isTauri) {
      await get().connect();
      return get().status === "ready";
    }
    set({ switching: true, status: "connecting", error: null });
    try {
      const url = await restartRuntime();
      if (!url) throw new Error("The local AI assistant did not return an endpoint.");
      set({ serverUrl: url });
      const connected = await get().connectRetry(30);
      if (!connected) {
        throw new Error(get().error ?? "The local AI assistant did not restart.");
      }
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      void logDebug(`runtime recovery FAILED: ${message}`);
      set({ status: "error", error: message });
      return false;
    } finally {
      set({ switching: false });
    }
  },

  bootstrap: () => {
    if (bootstrapInFlight) return bootstrapInFlight;
    const run = (async () => {
      void get().detectTools();
      if (!isTauri) return;
      void logDebug("bootstrap: starting bundled runtime");
      try {
        const url = await startRuntime();
        void logDebug(`bootstrap: runtime at ${url}`);
        if (url) set({ serverUrl: url });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        void logDebug(`bootstrap FAILED: ${msg}`);
        set({ error: msg });
        return;
      }
      await get().connectRetry();
    })();
    bootstrapInFlight = run;
    const clear = () => {
      if (bootstrapInFlight === run) bootstrapInFlight = null;
    };
    void run.then(clear, clear);
    return run;
  },

  disconnect: () => {
    teardownClient();
    set({ status: "offline", modelSwitchError: null });
  },

  refreshSessions: async () => {
    if (!client) return;
    try {
      const sessions = await client.listSessions();
      set((s) => {
        // The list also names each subagent session's parent — the recovery
        // path for parent links after a reload (no live task event to learn from).
        const sessionParents = { ...s.sessionParents };
        for (const m of sessions) if (m.parentId) sessionParents[m.id] = m.parentId;
        return { sessions, sessionParents };
      });
    } catch {
      /* ignore transient list failures */
    }
  },

  // The global "New task" action starts a standalone task.
  // A project row has its own + action and uses startDraftInWorkspace instead.
  startDraft: () =>
    set((s) => {
      const threads = { ...s.threads };
      delete threads[DRAFT_KEY]; // leftovers from an aborted first message
      const panes = { ...s.panes };
      delete panes[DRAFT_KEY]; // a fresh draft starts with a closed pane
      const promptQueues = { ...s.promptQueues };
      delete promptQueues[DRAFT_KEY];
      return {
        currentId: null,
        draftEpoch: s.draftEpoch + 1,
        workspacePinned: false,
        threads,
        panes,
        promptQueues,
      };
    }),

  ensureStandaloneWorkspace: async () => {
    if (!isTauri || get().currentId || get().workspacePinned) return true;
    set({ switching: true });
    try {
      await newDatedWorkspace(datedWorkspaceName());
      await kernelReset().catch(() => {});
      const connected = await get().connectRetry();
      if (!connected) return false;
      set({ workspacePinned: true });
      return true;
    } catch (error) {
      set({ error: error instanceof Error ? error.message : String(error) });
      return false;
    } finally {
      set({ switching: false });
    }
  },

  // Local /new and /clear: clear the visible chat context, but keep the active
  // folder. The first next message creates a new OpenCode session in that same
  // folder; no session, database row, or file is deleted here.
  startDraftInCurrentWorkspace: () =>
    set((s) => {
      const threads = { ...s.threads };
      threads[DRAFT_KEY] = {
        ...emptyThread(),
        loaded: true,
        blocks: [
          {
            kind: "status-line",
            text: i18n.t("session:localCommand.cleared"),
            tone: "review",
            divider: true,
          },
        ],
      };
      const panes = { ...s.panes };
      delete panes[DRAFT_KEY];
      const promptQueues = { ...s.promptQueues };
      delete promptQueues[DRAFT_KEY];
      return { currentId: null, workspacePinned: true, threads, panes, promptQueues };
    }),

  refreshProjects: async () => {
    if (!isTauri) return;
    try {
      const [projects, researchScope] = await Promise.all([
        listProjects(),
        currentResearchScope(),
      ]);
      set({ projects, researchScope });
    } catch {
      /* ignore transient scan failures */
    }
  },

  createProject: async (name) => {
    try {
      const project = await createProjectFolder(name);
      set((s) => ({
        projects: [...s.projects.filter((candidate) => candidate.id !== project.id), project]
          .sort((left, right) => left.name.localeCompare(right.name)),
      }));
      await get().switchWorkspace({ path: project.path });
      return project;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) });
      return null;
    }
  },

  importProject: async (path) => {
    try {
      const project = await importProjectFolder(path);
      set((state) => ({
        projects: [...state.projects.filter((candidate) => candidate.id !== project.id), project]
          .sort((left, right) => left.name.localeCompare(right.name)),
      }));
      await get().switchWorkspace({ path: project.path });
      return project;
    } catch (error) {
      set({ error: error instanceof Error ? error.message : String(error) });
      return null;
    }
  },

  setProjectPinned: async (id, pinned) => {
    set((state) => ({
      projects: state.projects.map((project) =>
        project.id === id ? { ...project, pinned } : project,
      ),
    }));
    try {
      await setProjectPinnedCmd(id, pinned);
    } catch (error) {
      set({ error: error instanceof Error ? error.message : String(error) });
    }
    void get().refreshProjects();
  },

  deleteProject: async (id) => {
    try {
      await deleteProjectCmd(id);
    } catch (error) {
      set({ error: error instanceof Error ? error.message : String(error) });
    }
    void get().refreshProjects();
  },

  startDraftInWorkspace: async (path) => {
    if (get().workspace === path) {
      // Already inside the project — a clean pinned draft, no reconnect.
      set((s) => {
        const threads = { ...s.threads };
        delete threads[DRAFT_KEY];
        const panes = { ...s.panes };
        delete panes[DRAFT_KEY];
        const promptQueues = { ...s.promptQueues };
        delete promptQueues[DRAFT_KEY];
        return { currentId: null, workspacePinned: true, threads, panes, promptQueues };
      });
      return;
    }
    await get().switchWorkspace({ path });
  },

  switchWorkspace: async (target) => {
    set({ switching: true });
    try {
      await setWorkspace(target.path);
      // Reset the local kernel so it respawns in the new folder, then reconnect
      // the event stream scoped to it (connect() re-reads the active folder —
      // the sidecar itself keeps running). An explicit switch pins the folder,
      // so the next new task lands exactly there.
      await kernelReset().catch(() => {});
      set((s) => {
        // Back to a draft in the new folder — the draft pane must not carry
        // files from the previous folder. Session panes keep their memory.
        const panes = { ...s.panes };
        delete panes[DRAFT_KEY];
        const promptQueues = { ...s.promptQueues };
        delete promptQueues[DRAFT_KEY];
        return { currentId: null, panes, promptQueues, workspacePinned: true };
      });
      await get().connectRetry();
      await Promise.all([get().refreshSessions(), get().loadCatalog()]);
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) });
    } finally {
      set({ switching: false });
    }
  },

  openSession: async (id) => {
    const seq = ++openSessionSeq;
    set({ currentId: id });
    if (!client) return;
    // Follow the session into its own workspace folder: record it as active and
    // reconnect the event stream scoped to it, so the agent, kernel and Files
    // all operate where the session's files live. Sessions with no recorded
    // folder, or that already match the active folder, skip this.
    const dir = get().sessions.find((s) => s.id === id)?.directory;
    if (dir && dir !== get().workspace) {
      set({ switching: true });
      try {
        await setWorkspace(dir).catch(() => {});
        // A newer openSession has superseded this one — stop before starting a
        // second, dueling connectRetry. Two reconnect loops tear down each
        // other's in-flight EventSource, leaking half-open sockets until the
        // webview's per-host connection pool is exhausted and every later
        // session hangs on load. The winner (latest seq) does the reconnect.
        if (seq !== openSessionSeq) return;
        await kernelReset().catch(() => {});
        if (seq !== openSessionSeq) return;
        await get().connectRetry();
      } finally {
        // Only the still-current open clears `switching`; a superseded one must
        // not flip it off while the winner is mid-reconnect.
        if (seq === openSessionSeq) set({ switching: false });
      }
    }
    // Stamp the (now-active) workspace with this session's id so skill-recorded
    // remote runs attach to the session, not just the global Runs view.
    if (dir) void markSession(id).catch(() => {});
    if (!client) return;
    // Recover any request the agent is blocked on (asked before connect/reload).
    void (async () => {
      try {
        const [qs, ps] = await Promise.all([
          client!.listQuestions(id),
          client!.listPermissions(id),
        ]);
        // Both lists are workspace-scoped (they include subagent sessions'
        // asks) — replace by requestId so live SSE copies don't duplicate.
        set((s) => {
          const qIds = new Set(qs.map((q) => q.requestId));
          const pIds = new Set(ps.map((p) => p.requestId));
          return {
            questions: [...s.questions.filter((q) => !qIds.has(q.requestId)), ...qs],
            permissions: [...s.permissions.filter((p) => !pIds.has(p.requestId)), ...ps],
          };
        });
      } catch {
        /* pending-request recovery is best-effort */
      }
    })();
    // A session reopened while "Working…" may have finished behind our back.
    void get().reconcileRunning();
    if (get().threads[id]?.loaded) return;
    try {
      const messages = await client.getMessages(id);
      if (seq !== openSessionSeq || get().currentId !== id) return;
      await recordModelCallsFromHistory(messages);
      if (seq !== openSessionSeq || get().currentId !== id) return;
      set((s) => ({
        threads: {
          ...s.threads,
          [id]: { ...historyToThread(messages, s.commands), loaded: true },
        },
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (seq !== openSessionSeq || get().currentId !== id) return;
      set((s) => ({
        error: msg,
        threads: {
          ...s.threads,
          [id]: {
            ...emptyThread(),
            loaded: true,
            blocks: [{ kind: "status-line", text: `Failed to load messages: ${msg}`, tone: "error" }],
          },
        },
      }));
    }
  },

  renameSession: async (id, title) => {
    const trimmed = title.trim();
    if (!trimmed) return;
    const previous = get().sessions.find((session) => session.id === id)?.title;
    set((state) => ({
      sessions: state.sessions.map((session) =>
        session.id === id ? { ...session, title: trimmed } : session,
      ),
    }));
    if (!client) return;
    try {
      await client.renameSession(id, trimmed);
    } catch (error) {
      set((state) => ({
        sessions: state.sessions.map((session) =>
          session.id === id && previous !== undefined
            ? { ...session, title: previous }
            : session,
        ),
        error: error instanceof Error ? error.message : String(error),
      }));
    }
  },

  // The send lifecycle (new → input → send → response) is shared by plain
  // prompts, "!" shell commands and "/" slash commands — see performTurn.
  sendPrompt: (text, displayText) =>
    performTurn(
      set,
      get,
      displayText ?? text,
      // Pin every turn to the model currently selected by the researcher.
      // OpenCode otherwise retains the model attached when an older session
      // was created, even after the global provider/model is changed.
      (sid) =>
        withRetry(() =>
          client!.sendPrompt(
            sid,
            text,
            get().sessionAgents[sid] ?? "build",
            get().defaultModel,
          ),
        ),
      false,
      false,
      heorPromptContext(text),
    ),

  // No retry for shell/command: re-POSTing would run the command twice.
  runShell: (command) => {
    const agent = get().agents.find((a) => a.mode === "primary")?.name ?? "build";
    return performTurn(
      set,
      get,
      `! ${command}`,
      (sid) => client!.runShell(sid, command, agent),
      true,
      true,
    );
  },

  runCommand: async (name, args) => {
    if (name === "new" || name === "clear") {
      get().startDraftInCurrentWorkspace();
      return null;
    }
    return performTurn(
      set,
      get,
      args ? `/${name} ${args}` : `/${name}`,
      (sid) => client!.runCommand(sid, name, args),
      true,
    );
  },

  editMessage: async (messageID, runtimeText, displayText) => {
    if (!(await revertToMessage(set, get, messageID))) return false;
    await get().sendPrompt(runtimeText, displayText);
    return true;
  },

  revertMessage: (messageID) => revertToMessage(set, get, messageID),

  interrupt: async () => {
    const sid = get().currentId;
    if (!sid || !client || !get().runningSessions[sid]) return;
    // Arm the guard BEFORE the abort POST: the server answers an abort with its
    // own SSE burst (an "aborted" error and one or more session.idle events)
    // that streams back WHILE this POST is still awaited. If we armed it after
    // the await, those events would race in ahead and litter the thread with
    // "Aborted" / "done" lines before "Interrupted".
    interruptedSessions.add(sid);
    try {
      await client.abortSession(sid);
    } catch {
      // The abort POST failing usually means the turn is already dead —
      // fall through: unlock locally either way so the user is never stuck.
    }
    set((s) => {
      const runningSessions = { ...s.runningSessions };
      const shellTurns = { ...s.shellTurns };
      const sessionProgress = { ...s.sessionProgress };
      const stepCounts = { ...s.stepCounts };
      delete runningSessions[sid];
      delete shellTurns[sid];
      delete sessionProgress[sid];
      delete stepCounts[sid];
      inactiveTurnPolls.delete(sid);
      const cur = s.threads[sid] ?? emptyThread();
      return {
        runningSessions,
        shellTurns,
        sessionProgress,
        stepCounts,
        threads: {
          ...s.threads,
          [sid]: {
            ...cur,
            loaded: true,
            blocks: [...cur.blocks, { kind: "status-line", text: "Interrupted", tone: "error" }],
          },
        },
      };
    });
  },

  reconcileRunning: async () => {
    const c = client;
    const running = Object.keys(get().runningSessions);
    if (!c || running.length === 0) return;
    let statuses: Record<string, SessionRuntimeStatus> = {};
    let statusesKnown = false;
    try {
      statuses = await c.getSessionStatuses();
      statusesKnown = true;
      set((s) => ({ sessionProgress: { ...s.sessionProgress, ...statuses } }));
    } catch {
      // History still provides the normal completed/error recovery path.
    }
    for (const sid of running) {
      try {
        const messages = await c.getMessages(sid);
        const sessionDirectory = get().sessions.find((session) => session.id === sid)?.directory;
        // The status endpoint is scoped to the currently active workspace.
        // Absence means "idle" only for a task in that workspace; for another
        // task it means "not observable here" and must never be turned into a
        // false provider failure while the researcher is viewing elsewhere.
        const statusCoversSession = !sessionDirectory || sessionDirectory === get().workspace;
        const stopped = statusesKnown
          && statusCoversSession
          && turnStoppedWithoutReply(messages, statuses[sid]);
        const inactiveCount = stopped ? (inactiveTurnPolls.get(sid) ?? 0) + 1 : 0;
        if (stopped) inactiveTurnPolls.set(sid, inactiveCount);
        else inactiveTurnPolls.delete(sid);
        // Still ours to answer for? The lock may have cleared while we fetched.
        if ((!turnIsOver(messages) && inactiveCount < 2) || !get().runningSessions[sid]) continue;
        void logDebug(`reconcile: missed idle for ${sid} — unlocking`);
        set((s) => {
          const runningSessions = { ...s.runningSessions };
          const shellTurns = { ...s.shellTurns };
          const sessionProgress = { ...s.sessionProgress };
          const stepCounts = { ...s.stepCounts };
          delete runningSessions[sid];
          delete shellTurns[sid];
          delete sessionProgress[sid];
          delete stepCounts[sid];
          inactiveTurnPolls.delete(sid);
          const recovered = historyToThread(messages, s.commands);
          const recoveredTail = recovered.blocks[recovered.blocks.length - 1];
          const alreadyShowsFailure = recoveredTail?.kind === "status-line"
            && recoveredTail.tone === "error";
          if (inactiveCount >= 2 && !alreadyShowsFailure) {
            recovered.blocks.push({
              kind: "status-line",
              text: i18n.t("session:live.status.stoppedBeforeReply"),
              tone: "error",
            });
          }
          return {
            runningSessions,
            shellTurns,
            sessionProgress,
            stepCounts,
            // The idle was missed, so the tail of the turn was too — replace
            // the thread with the full history rather than leave it stale.
            threads: {
              ...s.threads,
              [sid]: { ...recovered, loaded: true },
            },
          };
        });
      } catch {
        /* best-effort — the next reconnect or poll tries again */
      }
    }
  },

  deleteSession: async (id) => {
    if (client) {
      try {
        await client.deleteSession(id);
      } catch (err) {
        set({ error: err instanceof Error ? err.message : String(err) });
      }
    }
    set((s) => {
      const threads = { ...s.threads };
      delete threads[id];
      const runningSessions = { ...s.runningSessions };
      delete runningSessions[id];
      const sessionProgress = { ...s.sessionProgress };
      delete sessionProgress[id];
      const stepCounts = { ...s.stepCounts };
      delete stepCounts[id];
      inactiveTurnPolls.delete(id);
      const panes = { ...s.panes };
      delete panes[id];
      const promptQueues = { ...s.promptQueues };
      delete promptQueues[id];
      return {
        sessions: s.sessions.filter((x) => x.id !== id),
        threads,
        runningSessions,
        sessionProgress,
        stepCounts,
        panes,
        promptQueues,
        currentId: s.currentId === id ? null : s.currentId,
      };
    });
  },

  hideExample: (id) => {
    const next = Array.from(new Set([...get().hiddenExamples, id]));
    if (typeof window !== "undefined") window.localStorage.setItem(HIDDEN_KEY, JSON.stringify(next));
    set({ hiddenExamples: next });
  },

  // Start a review, never an active install. Workspace skills remain a separate,
  // user-managed mechanism and cannot enter the bundled platform inventory.
  reviewAssetCandidate: async (text) => {
    if (!client) {
      set({ error: "Connect the runtime first to review an external asset." });
      return null;
    }
    try {
      const id = await client.createSession();
      set((s) => ({ currentId: id, threads: { ...s.threads, [id]: { ...emptyThread(), loaded: true } } }));
      await get().refreshSessions();
      const prompt = buildAssetReviewPrompt(text);
      set((s) => {
        const cur = s.threads[id];
        return {
          threads: {
            ...s.threads,
            [id]: { ...cur, blocks: [...cur.blocks, { kind: "user", text: `Review asset candidate:\n${text}` }] },
          },
        };
      });
      await client.sendPrompt(id, prompt, undefined, get().defaultModel);
      return id;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) });
      return null;
    }
  },
}));

/** Dated local folder for a standalone task. The folder is an
 * independent research scope, not an AI4HEOR project. */
export function datedWorkspaceName(now = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}`;
}

const DEFAULT_SESSION_TITLE = /^(?:new session|untitled)(?:\s*-\s*.*)?$/i;

/** Keep OpenCode's useful generated titles, but never expose its English
 *  timestamp placeholder. While a task is new, its first visible request is a
 *  clearer local title and works in every locale. */
export function displaySessionTitle(
  serverTitle: string | undefined,
  blocks: ThreadBlock[] | undefined,
  fallback: string,
): string {
  const title = serverTitle?.trim();
  if (title && !DEFAULT_SESSION_TITLE.test(title)) return title;
  const request = blocks?.find(
    (block): block is Extract<ThreadBlock, { kind: "user" }> => block.kind === "user",
  )?.text;
  const compact = request?.replace(/\s+/g, " ").trim();
  if (!compact) return fallback;
  return compact.length > 30 ? `${compact.slice(0, 30)}…` : compact;
}

export interface FoldState {
  blocks: ThreadBlock[];
  index: Record<string, number>;
}

/** Pure reducer: fold one normalized OpenCode event into a thread's blocks. */
/**
 * Tidy a tool-call title for the conversation: show workspace files by their
 * relative path (`demo/analyze.py`), not the full `/Users/.../AI4HEOR/...`
 * absolute path, so the thread reads like a researcher's log, not a shell trace.
 * The workspace path never contains spaces (by design), so a space-free run
 * ending in the current `AI4HEOR/` or legacy `OpenScience/` root matches it
 * whether or not it has a leading slash (OpenCode's write-tool titles drop it).
 */
export function tidyToolTitle(title: string): string {
  return title.replace(/[^\s]*(?:AI4HEOR|OpenScience)\//g, "").trim() || title;
}

/**
 * De-noise a bash command for the one-line title: collapse whitespace and
 * strip leading `cd <dir> &&` / `cd <dir>;` hops (repeatedly), so the step
 * reads `python train.py --mode teacher`, not `cd output/very/long/path && …`.
 * The full command stays available in the expanded detail.
 */
export function humanizeCommand(command: string): string {
  let c = command.replace(/\s+/g, " ").trim();
  for (;;) {
    const m = /^cd\s+(?:"[^"]*"|'[^']*'|[^\s;&|]+)\s*(?:&&|;)\s*/.exec(c);
    if (!m) break;
    c = c.slice(m[0].length);
  }
  return c || command.trim();
}

/**
 * Progress bars (tqdm, pip, curl) redraw lines with `\r` — keep only what
 * each line last drew so live output shows one updating line, not hundreds.
 */
export function foldCarriageReturns(text: string): string {
  return text
    .split("\n")
    .map((line) => line.slice(line.lastIndexOf("\r") + 1))
    .join("\n");
}

/** Live-tail cap: enough for a handful of lines, tiny in the store. */
const LIVE_TAIL_MAX = 4_000;
/** Expanded-detail cap: plenty to read inline, never megabytes in the store. */
const DETAIL_MAX = 64_000;
const capTail = (t: string, max: number) => (t.length > max ? "…" + t.slice(-max) : t);
const capHead = (t: string, max: number) => (t.length > max ? t.slice(0, max) + "\n…" : t);

const str = (v: unknown) => (typeof v === "string" ? v : "");
const EDIT_TOOLS = new Set(["edit", "str_replace_editor", "apply_patch"]);

/**
 * Verb + subject for a tool step ("Ran" + `python train.py …`, "Created" +
 * `demo/analyze.py`) — recognizable at a glance, Codex-style. Tools without
 * a natural verb keep the old title fallback chain (server title → command →
 * file path → tool name).
 */
export function toolPresentation(
  tool: string,
  title: string | undefined,
  input?: Record<string, unknown>,
): { verb?: ToolVerb; title: string } {
  const command = str(input?.command);
  const filePath = str(input?.filePath) || str(input?.path);
  const fallback = tidyToolTitle(title?.trim() || command || filePath || tool || "tool");
  const loadedSkill = /^loaded skill:\s*(.+)$/i.exec(fallback);
  if (loadedSkill) {
    return {
      title: i18n.t("session:live.status.loadedSkill", { skill: loadedSkill[1] }),
    };
  }
  const file = filePath ? tidyToolTitle(filePath) : "";
  switch (tool) {
    case "bash":
      return { verb: "Ran", title: command ? humanizeCommand(tidyToolTitle(command)) : fallback };
    case "write":
    case "create":
      return { verb: "Created", title: file || fallback };
    case "edit":
    case "str_replace_editor":
    case "apply_patch":
      return { verb: "Edited", title: file || fallback };
    case "read":
      return { verb: "Read", title: file || fallback };
    case "grep":
    case "glob":
      return { verb: "Searched", title: str(input?.pattern) || fallback };
    case "list":
      return { verb: "Listed", title: file || fallback };
    case "webfetch":
      return { verb: "Fetched", title: str(input?.url) || fallback };
    default:
      return { title: fallback };
  }
}

export function foldEvent(
  state: FoldState,
  event: OpenCodeEvent,
  opts?: { shellTurn?: boolean },
): FoldState {
  const blocks = [...state.blocks];
  const index = { ...state.index };
  switch (event.type) {
    case "text.updated": {
      // A ```review fence in the agent's text becomes a structured reviewer card.
      const { clean, review } = splitReview(event.text);
      const key = `text:${event.partId}`;
      if (key in index) blocks[index[key]] = { kind: "agent", markdown: clean };
      else {
        blocks.push({ kind: "agent", markdown: clean });
        index[key] = blocks.length - 1;
      }
      if (review) {
        const rkey = `review:${event.partId}`;
        if (rkey in index) blocks[index[rkey]] = review;
        else {
          blocks.push(review);
          index[rkey] = blocks.length - 1;
        }
      }
      return { blocks, index };
    }
    case "reasoning.updated": {
      const key = `reasoning:${event.partId}`;
      if (key in index) blocks[index[key]] = { kind: "reasoning", text: event.text };
      else {
        blocks.push({ kind: "reasoning", text: event.text });
        index[key] = blocks.length - 1;
      }
      return { blocks, index };
    }
    case "tool.updated": {
      // The interactive `question`/`permission` tools render as their own
      // answerable card (InteractionPrompt), not as a blank thread row. `todo*`
      // tools only report an opaque "N todos" count with no useful content —
      // pure noise in the conversation, so drop them.
      if (/question|permission|^ask$|todo/i.test(event.tool)) return { blocks, index };
      const key = `tool:${event.callId}`;
      const command = str(event.input?.command);
      const filePath = str(event.input?.filePath) || str(event.input?.path);
      const content = str(event.input?.content);
      // Some updates omit fields earlier ones carried (a task tool names its
      // subagent session once; time.start only rides the first events) —
      // carry them over from the previous version of the block.
      const prev = key in index ? blocks[index[key]] : undefined;
      const prevTool = prev?.kind === "tool-call" ? prev : undefined;
      const childSessionId = event.childSessionId ?? prevTool?.childSessionId;
      const startedAt = event.startedAt ?? prevTool?.startedAt;
      const endedAt = event.endedAt ?? prevTool?.endedAt;
      // Edit tools report a proper unified diff in metadata on completion;
      // until (or without) that, synthesize a minimal old→new view.
      const diff =
        event.diff ??
        prevTool?.diff ??
        (EDIT_TOOLS.has(event.tool) && (str(event.input?.oldString) || str(event.input?.newString))
          ? [
              ...str(event.input?.oldString).split("\n").map((l) => `- ${l}`),
              ...str(event.input?.newString).split("\n").map((l) => `+ ${l}`),
            ].join("\n")
          : undefined);
      const { verb, title } = toolPresentation(event.tool, event.title, event.input);
      const block: ThreadBlock = {
        kind: "tool-call",
        title,
        status: event.status,
        tool: event.tool,
        ...(verb ? { verb } : {}),
        ...(command ? { command } : {}),
        ...(filePath ? { filePath: tidyToolTitle(filePath) } : {}),
        ...(content ? { content: capHead(content, DETAIL_MAX) } : {}),
        ...(diff ? { diff: capHead(diff, DETAIL_MAX) } : {}),
        // Live stdout tail while running — the "is it alive?" signal.
        ...(event.status === "running" && event.partialOutput
          ? { partialOutput: capTail(foldCarriageReturns(event.partialOutput), LIVE_TAIL_MAX) }
          : {}),
        ...(event.output?.trim()
          ? { output: capTail(foldCarriageReturns(event.output), DETAIL_MAX).replace(/\s+$/, "") }
          : {}),
        ...(startedAt ? { startedAt } : {}),
        ...(endedAt ? { endedAt } : {}),
        ...(childSessionId ? { childSessionId } : {}),
        // A user-typed "!" command ran for its output — its detail opens by
        // default. Agent bash steps stay quiet one-liners until expanded.
        ...(opts?.shellTurn && event.tool === "bash" && event.output?.trim()
          ? { outputSummary: event.output.replace(/\s+$/, "") }
          : {}),
      };
      if (key in index) blocks[index[key]] = block;
      else {
        blocks.push(block);
        index[key] = blocks.length - 1;
      }
      // Surface a file the agent wrote as a traceable artifact (deduped by path).
      const artifact = deriveArtifact(event);
      if (artifact) {
        const akey = `artifact:${artifact.path}`;
        if (akey in index) blocks[index[akey]] = artifact;
        else {
          blocks.push(artifact);
          index[akey] = blocks.length - 1;
        }
      }
      return { blocks, index };
    }
    case "session.idle": {
      // Idle closes the live activity indicator; it is not evidence that a
      // scientific step or the task itself is complete. Normal completion is
      // intentionally silent in the conversation, while stopped/error/waiting
      // states remain visible because they require interpretation or action.
      return { blocks, index };
    }
    default:
      return state;
  }
}

/**
 * One-line live activity of a subagent, derived from its folded thread:
 * the latest tool step's title, "Writing…" while it streams text, and
 * "Working…" before anything is known (e.g. right after an app reload).
 */
export function subagentActivity(blocks?: ThreadBlock[]): string {
  for (let i = (blocks?.length ?? 0) - 1; i >= 0; i--) {
    const b = blocks![i];
    if (b.kind === "tool-call") return b.title;
    if (b.kind === "agent") return "Writing…";
    if (b.kind === "reasoning") return i18n.t("session:reasoning.thinking");
  }
  return "Working…";
}

function mapToolStatus(status?: string): ToolCallStatus {
  switch (status) {
    case "running":
      return "running";
    case "completed":
      return "success";
    case "error":
      return "failed";
    default:
      return "pending";
  }
}

/** Convert loaded message history into thread blocks. */
export function historyToThread(messages: HistoryMessage[], commands?: CommandInfo[]): FoldState {
  const blocks: ThreadBlock[] = [];
  // OpenCode stores a slash command's EXPANDED template as the user message,
  // with any typed arguments appended after it (no marker) — show the
  // "/name args" the user actually typed instead. Longest template first, so
  // one template being a prefix of another's expansion can't mis-attribute.
  const templates = (commands ?? [])
    .filter((c) => c.template?.trim())
    .map((c) => ({ name: c.name, template: c.template!.trim() }))
    .sort((a, b) => b.template.length - a.template.length);
  const asTypedCommand = (text: string): string | undefined => {
    const hit = templates.find((t) => text.startsWith(t.template));
    if (!hit) return undefined;
    const args = text.slice(hit.template.length).trim();
    return args ? `/${hit.name} ${args}` : `/${hit.name}`;
  };
  // A step frozen mid-run (the runtime restarted or the turn was killed before
  // it finished) must not spin forever in history — render it quietly and say
  // once, at the end, that the turn was interrupted.
  let interrupted = false;
  // A user-typed "!" command is recorded as a synthetic user text plus a bash
  // tool part on the next assistant message. Render it like the live path:
  // the "! cmd" echo and the output inline — never the synthetic marker text.
  let shellTurn = false;
  for (const m of messages) {
    if (m.role === "user") {
      shellTurn = m.parts.some((p) => p.type === "text" && p.synthetic);
      if (shellTurn) continue;
      const text = m.parts
        .filter((p) => p.type === "text")
        .map((p) => p.text ?? "")
        .join("")
        .trim();
      const visibleText = displayHeorPrompt(text);
      const command = asTypedCommand(visibleText);
      if (command) blocks.push({ kind: "user", text: command, messageID: m.id });
      else if (visibleText) blocks.push({ kind: "user", text: visibleText, messageID: m.id });
    } else {
      for (const p of m.parts) {
        if (p.type === "text" && p.text?.trim()) {
          const { clean, review } = splitReview(p.text);
          if (clean) blocks.push({ kind: "agent", markdown: clean });
          if (review) blocks.push(review);
        }
        else if (p.type === "reasoning" && p.text?.trim()) {
          blocks.push({ kind: "reasoning", text: p.text });
        }
        else if (p.type === "tool") {
          // Interactive tools are surfaced by InteractionPrompt, not the thread;
          // `todo*` tools are opaque "N todos" noise — skip both.
          if (/question|permission|^ask$|todo/i.test(p.tool ?? "")) continue;
          const status = mapToolStatus(p.state?.status);
          const frozen = status === "running" || status === "pending";
          if (frozen) interrupted = true;
          const command = str(p.state?.input?.command);
          const filePath = str(p.state?.input?.filePath) || str(p.state?.input?.path);
          const content = str(p.state?.input?.content);
          const diff =
            str(p.state?.metadata?.diff) ||
            (EDIT_TOOLS.has(p.tool ?? "") &&
            (str(p.state?.input?.oldString) || str(p.state?.input?.newString))
              ? [
                  ...str(p.state?.input?.oldString).split("\n").map((l) => `- ${l}`),
                  ...str(p.state?.input?.newString).split("\n").map((l) => `+ ${l}`),
                ].join("\n")
              : "");
          const userShell = shellTurn && p.tool === "bash";
          if (userShell) blocks.push({ kind: "user", text: `! ${command}` });
          const { verb, title } = toolPresentation(p.tool ?? "", p.state?.title, p.state?.input);
          blocks.push({
            kind: "tool-call",
            title,
            status: frozen ? "failed" : status,
            tool: p.tool,
            ...(verb ? { verb } : {}),
            ...(command ? { command } : {}),
            ...(filePath ? { filePath: tidyToolTitle(filePath) } : {}),
            ...(content ? { content: capHead(content, DETAIL_MAX) } : {}),
            ...(diff ? { diff: capHead(diff, DETAIL_MAX) } : {}),
            ...(p.state?.output?.trim()
              ? { output: capTail(foldCarriageReturns(p.state.output), DETAIL_MAX).replace(/\s+$/, "") }
              : {}),
            ...(typeof p.state?.time?.start === "number" ? { startedAt: p.state.time.start } : {}),
            ...(typeof p.state?.time?.end === "number" ? { endedAt: p.state.time.end } : {}),
            ...(userShell && p.state?.output?.trim()
              ? { outputSummary: p.state.output.replace(/\s+$/, "") }
              : {}),
          });
          const artifact = deriveArtifact({
            type: "tool.updated",
            sessionId: "",
            callId: "",
            tool: p.tool ?? "",
            status,
            input: p.state?.input,
            output: p.state?.output,
          });
          if (artifact) blocks.push(artifact);
        }
      }
      if (m.error) {
        blocks.push({ kind: "status-line", text: friendlyRuntimeError(m.error), tone: "error" });
        interrupted = false;
      }
      shellTurn = false;
    }
  }
  if (interrupted) {
    blocks.push({
      kind: "status-line",
      text: i18n.t("session:live.status.stoppedBeforeReply"),
      tone: "error",
    });
  }
  return { blocks, index: {} };
}

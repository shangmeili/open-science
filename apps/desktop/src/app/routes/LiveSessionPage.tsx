import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Activity, FlaskConical, FolderOpen, Loader2, NotebookPen, PanelLeft, PlugZap } from "lucide-react";
import type { RuntimeStatus } from "@ai4s/shared";
import { DRAFT_KEY, rootSessionOf, subagentActivity, useRuntimeStore } from "@/lib/runtime";
import { queryRuns } from "@/lib/runs";
import { useOverlayTitlebar, useUiStore } from "@/lib/store";
import { fileInspectorFromBlock } from "@/lib/artifacts";
import { useScrollMemory } from "@/lib/scrollMemory";
import { BlockList, type BlockHandlers } from "@/components/thread/BlockList";
import { Elapsed } from "@/components/thread/ToolGroup";
import { Composer } from "@/components/thread/Composer";
import { baseName } from "@/components/thread/WorkspaceChip";
import { HeorStarters } from "@/components/heor/HeorStarters";
import { FirstRunGuide } from "@/components/heor/FirstRunGuide";
import { HeorReviewPane } from "@/components/heor/HeorReviewPane";
import { InteractionPrompt } from "@/components/thread/InteractionPrompt";
import { InspectorShell } from "@/components/inspector/InspectorShell";
import { MaximizePaneButton, RightPane } from "@/components/inspector/RightPane";
import { SessionFilesPane } from "./FilesPage";
import { RunsPane } from "./RunsPage";
import { cn } from "@/lib/cn";
import { buildHeorPrompt } from "@/lib/heor";
import { isTauri } from "@/lib/tauri";

/** AI4HEOR research conversation backed by the local assistant runtime. The
 * session is created lazily on the first message, then the URL gains its id. */
export function LiveSessionPage() {
  const { t } = useTranslation(["session", "common", "heor"]);
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const {
    status,
    switching,
    sending,
    runningSessions,
    sessions,
    projects,
    currentId,
    threads,
    error,
    questions,
    permissions,
    sessionParents,
    workspace,
    panes,
    commands,
    defaultModel,
    connect,
    openSession,
    startDraft,
    sendPrompt,
    runShell,
    runCommand,
    openArtifact,
    closeArtifact,
    setShowFiles,
    setShowRuns,
    answerQuestion,
    rejectQuestion,
    replyPermission,
    interrupt,
    reconcileRunning,
    approvalMode,
    setApprovalMode,
  } = useRuntimeStore();
  const clearingLocalCommand = useRef(false);
  const [showHeorReview, setShowHeorReview] = useState(false);

  // A deliberate workspace move restarts the sidecar — expected and brief, so
  // the UI stays "connected" (no badge flip, no Connect button, no help card).
  // Only a real failure (retry window exhausted, switching cleared) surfaces.
  const connected = status === "ready" || switching;
  const connecting = status === "connecting" && !switching;
  const displayStatus = switching ? "ready" : status;

  useEffect(() => {
    if (sessionId) {
      if (!clearingLocalCommand.current) void openSession(sessionId);
    } else {
      clearingLocalCommand.current = false;
      // Read currentId from the store, NOT as an effect dependency: openSession
      // sets currentId, so depending on it here re-fires this effect and opens
      // the session a SECOND time — two concurrent connectRetry loops then leak
      // EventSockets until the connection pool is exhausted and sessions hang.
      if (useRuntimeStore.getState().currentId) startDraft(); // blank draft (#3)
    }
  }, [sessionId, openSession, startDraft]);

  // All three composer paths reflect a freshly-created session in the URL.
  const afterTurn = (id: string | null) => {
    if (id && !sessionId) navigate(`/heor/${id}`);
  };
  const onSend = async (text: string) => {
    if (!defaultModel) {
      useUiStore.getState().setComposerDraft(text);
      return;
    }
    afterTurn(await sendPrompt(buildHeorPrompt(text)));
  };
  const onRunShell = async (command: string) => afterTurn(await runShell(command));
  const onRunCommand = async (name: string, args: string) => {
    const localClear = name === "new" || name === "clear";
    // Only arm the guard when a real session is open. From a draft, the URL is
    // already a blank draft and no route/currentId change follows — arming here would
    // strand the flag at true (the reset lives in the effect's else branch,
    // which never re-runs) and silently block the next openSession.
    if (localClear && sessionId) clearingLocalCommand.current = true;
    const id = await runCommand(name, args);
    if (localClear) navigate("/heor", { replace: true });
    else afterTurn(id);
  };
  const composerCommands = useMemo(() => {
    const local = [
      { name: "new", description: t("localCommand.newDescription"), source: "local" },
      { name: "clear", description: t("localCommand.clearDescription"), source: "local" },
    ];
    const localNames = new Set(local.map((c) => c.name));
    return [...local, ...commands.filter((c) => !localNames.has(c.name))];
  }, [commands, t]);

  // Interactions from the thread/inspector fold back into the conversation as follow-up prompts.
  const handlers: BlockHandlers = {
    onArtifactOpen: openArtifact,
    onFigureComment: (a, title) =>
      void sendPrompt(t("figure.commentPrompt", {
        title,
        x: a.x.toFixed(0),
        y: a.y.toFixed(0),
        note: a.note,
      })),
    // Subagent events fold into their own thread; a running task row reads
    // its child's latest step from there.
    subagentActivity: (childId) => subagentActivity(threads[childId]?.blocks),
  };
  const onEvaluate = (expr: string) => void sendPrompt(t("live.notebook.evaluatePrompt", { expr }));

  // A draft shows its local thread (the first message echoes there instantly,
  // before any session exists) — it is grafted onto the session id on create.
  const thread = currentId ? threads[currentId] : threads[DRAFT_KEY];
  // Opening a session fetches its history (cross-folder opens also restart the
  // sidecar) — show skeleton shapes meanwhile, never a blank page.
  const historyLoading = connected && !!sessionId && !thread?.loaded;
  const title = sessions.find((s) => s.id === currentId)?.title;
  const isEmpty = !thread || thread.blocks.length === 0;
  // The turn lifecycle: `sending` covers click → POST accepted (incl. the
  // dated-folder setup on a first message); `running` covers the agent
  // working until session.idle. Together they lock the composer and show the
  // working indicator, so a sent message is never silently "nowhere".
  const running = !!(currentId && runningSessions[currentId]);
  const working = sending || running;
  // What the agent is doing right now — the newest still-running tool call.
  const currentTool = working
    ? [...(thread?.blocks ?? [])]
        .reverse()
        .find((b): b is Extract<typeof b, { kind: "tool-call" }> =>
          b.kind === "tool-call" && b.status === "running",
        )
    : undefined;

  // Esc interrupts the running turn (like a terminal agent). Modals own Esc
  // while open; the composer's palette marks its Esc as handled.
  useEffect(() => {
    if (!running) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (document.querySelector('[role="dialog"], [role="alertdialog"]')) return;
      void interrupt();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [running, interrupt]);

  // Backstop while "Working…": if session.idle got lost (SSE reconnect
  // windows), a slow poll re-checks the server so the spinner can never
  // outlive the turn.
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => void reconcileRunning(), 15_000);
    return () => window.clearInterval(timer);
  }, [running, reconcileRunning]);

  // The oldest unanswered request blocks the run — surface it. Requests from
  // subagents carry their CHILD session id; resolve through the parent chain
  // so they still land in the conversation the user is looking at.
  const belongsHere = (sid: string) =>
    !!currentId && (sid === currentId || rootSessionOf(sessionParents, sid) === currentId);
  const activeQuestion = questions.find((q) => belongsHere(q.sessionId));
  const activePermission = permissions.find((p) => belongsHere(p.sessionId));
  const activeRequest = activeQuestion ?? activePermission;
  // Name the subagent on the card when the ask isn't from the main agent.
  const requestOrigin =
    activeRequest && activeRequest.sessionId !== currentId
      ? (sessions.find((s) => s.id === activeRequest.sessionId)?.title ?? t("live.subagentFallback"))
      : undefined;

  // Notebooks the agent touched in THIS session — the conversation ↔ notebook map.
  const sessionNotebooks = (thread?.blocks ?? []).filter(
    (b): b is Extract<typeof b, { kind: "artifact" }> =>
      b.kind === "artifact" && b.filename.endsWith(".ipynb"),
  );
  const uniqueNotebooks = [...new Map(sessionNotebooks.map((b) => [b.path, b])).values()];

  // The right pane belongs to the session: each one remembers its own open
  // artifact or Files browser (mutually exclusive, enforced by the store) and
  // gets it back when the user returns.
  const pane = panes[currentId ?? DRAFT_KEY];
  const activeArtifact = pane?.artifact ?? null;
  const showFiles = !activeArtifact && !!pane?.showFiles;
  const showRuns = !activeArtifact && !showFiles && !!pane?.showRuns;
  const activeProject =
    projects.find((candidate) => candidate.path === workspace) ??
    (!isTauri ? { id: "ai4heor-demo", name: "First-line NSCLC" } : null);

  // Show the Runs toggle only when this session has runs (like the Files/folder
  // affordance — present when there's content). Cheap count query on open.
  const [hasRuns, setHasRuns] = useState(false);
  useEffect(() => {
    if (!sessionId) return setHasRuns(false);
    let cancelled = false;
    void queryRuns({ sessionId, limit: 1 }).then((p) => !cancelled && setHasRuns(p.total > 0));
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // Conversation scroll position, per session — restored once history is in.
  const chatRef = useRef<HTMLDivElement>(null);
  const onChatScroll = useScrollMemory(chatRef, `chat:${currentId ?? DRAFT_KEY}`, !historyLoading);

  // When the agent starts working a notebook (Jupyter MCP), open it beside the
  // chat automatically — once per notebook, so a manual close stays closed.
  const autoOpened = useRef(new Set<string>());
  useEffect(() => {
    const agentNb = uniqueNotebooks.find(
      (b) => b.tool.toLowerCase().includes("jupyter") && !autoOpened.current.has(b.path),
    );
    if (agentNb) {
      autoOpened.current.add(agentNb.path);
      openArtifact(agentNb);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uniqueNotebooks.length]);

  // With the sidebar collapsed this header doubles as the titlebar (macOS
  // overlay): it clears the traffic lights, hosts the sidebar expand button,
  // and empty stretches drag the window — one row, never two.
  const { sidebarCollapsed, setSidebarCollapsed } = useUiStore();
  const isMac = navigator.userAgent.includes("Mac");
  const overlayTitlebar = useOverlayTitlebar();

  return (
    <div className="flex h-full min-w-0">
      <div className="flex h-full min-w-0 flex-1 flex-col">
        <div
          data-tauri-drag-region={overlayTitlebar || undefined}
          className={cn(
            "flex h-12 shrink-0 items-center gap-2 px-6",
            // A draft is a clean page — no separator; an open session gets a
            // faint one so the title row reads as part of the conversation.
            sessionId && "border-b border-faint",
            sidebarCollapsed && overlayTitlebar && "pl-[78px]",
          )}
        >
          {sidebarCollapsed && (
            <button
              onClick={() => setSidebarCollapsed(false)}
              aria-label={t("live.header.expandSidebarAria")}
              title={t("live.header.expandSidebarTitle", { shortcut: isMac ? "⌘B" : "Ctrl+B" })}
              className="fade-in rounded p-1 text-text hover:bg-surface-2"
            >
              <PanelLeft size={14} strokeWidth={1.5} />
            </button>
          )}
          {/* Left: the session title is the identity anchor. A draft shows no
              title — the workspace picker lives in the composer until the
              session exists. min-w-0 lets it truncate instead of shoving the
              right-side controls off the bar. */}
          <div className="flex min-w-0 items-center gap-2">
            <Activity size={14} className="shrink-0 text-accent" />
            <h1 className="truncate font-serif text-[15px] font-semibold text-text">
              {t("heor:brand")}
            </h1>
            {sessionId && title && <span className="truncate text-xs text-muted">/ {title}</span>}
          </div>
          <div data-tauri-drag-region={overlayTitlebar || undefined} className="flex-1" />
          {/* Right: quiet ghost controls — no border or fill until hovered or
              active, so the row stays flat and editorial (one visual language
              across the Files toggle and every notebook chip). The Files toggle
              names this session's folder; a draft has none yet. */}
          {sessionId && (
            <button
              onClick={() => setShowFiles(!showFiles)}
              className={cn(
                "flex items-center gap-1 rounded-md px-1.5 py-1 text-xs transition-colors hover:bg-surface-2",
                showFiles ? "bg-surface-2 text-text" : "text-muted",
              )}
              title={`${t("live.filesToggle.title")}${workspace ? ` — ${workspace}` : ""}`}
              aria-pressed={showFiles}
            >
              <FolderOpen size={13} />
              <span className="max-w-[160px] truncate">
                {workspace ? baseName(workspace) : t("live.filesToggle.default")}
              </span>
            </button>
          )}
          {sessionId && hasRuns && (
            <button
              onClick={() => setShowRuns(!showRuns)}
              className={cn(
                "flex items-center gap-1 rounded-md px-1.5 py-1 text-xs transition-colors hover:bg-surface-2",
                showRuns ? "bg-surface-2 text-text" : "text-muted",
              )}
              title={t("live.runsToggle.title")}
              aria-pressed={showRuns}
            >
              <FlaskConical size={13} />
              <span>{t("live.runsToggle.label")}</span>
            </button>
          )}
          <button
            onClick={() => setShowHeorReview((open) => !open)}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors hover:bg-surface-2",
              showHeorReview ? "bg-surface-2 text-text" : "text-muted",
            )}
            aria-pressed={showHeorReview}
            title={t("heor:review")}
          >
            <Activity size={13} />
            <span>{t("heor:review")}</span>
          </button>
          <ConnBadge status={displayStatus} />
          {uniqueNotebooks.map((nb) => (
            <button
              key={nb.path}
              onClick={() => openArtifact(nb)}
              className={cn(
                "flex items-center gap-1 rounded-md px-1.5 py-1 font-mono text-xs transition-colors hover:bg-surface-2",
                activeArtifact?.path === nb.path ? "bg-surface-2 text-text" : "text-muted",
              )}
              title={t("live.notebook.openTitle", { path: nb.path })}
            >
              <NotebookPen size={12} />
              <span className="max-w-[180px] truncate">{nb.filename}</span>
            </button>
          ))}
          {!connected && (
            <button
              onClick={connect}
              disabled={connecting}
              className="flex items-center gap-1.5 rounded-input bg-accent px-2.5 py-0.5 text-xs font-medium text-accent-fg hover:opacity-90 disabled:opacity-50"
            >
              {connecting ? <Loader2 size={13} className="animate-spin" /> : <PlugZap size={13} />}
              {t("live.connect")}
            </button>
          )}
        </div>

        <div ref={chatRef} onScroll={onChatScroll} className="flex-1 overflow-y-auto">
          <div className="mx-auto flex max-w-[760px] flex-col gap-4 px-8 py-6">
            {isEmpty && !sessionId && (
              <>
                <FirstRunGuide onOpenSettings={() => navigate("/settings")} />
                <HeorStarters
                  onPick={(prompt) => useUiStore.getState().setComposerDraft(prompt)}
                />
              </>
            )}
            {/* Deliberate workspace switches don't render anything at all (they're
                masked as connected); a genuine boot/reconnect shows only the
                header badge's pulsing dot — anything appearing and disappearing
                in the content flow makes the page jump. The help card is for
                real error/offline states. */}
            {!connected && !connecting && (
              <div className="rounded-card border border-border bg-surface p-5 shadow-card">
                <div className="text-sm font-medium text-text">{t("live.runtime.title")}</div>
                <p className="mt-1 text-sm text-muted">{t("live.runtime.body")}</p>
              </div>
            )}
            {error && (
              <div className="rounded-input border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
                {error}
              </div>
            )}
            {historyLoading && <ThreadSkeleton />}
            {!historyLoading && thread && <BlockList blocks={thread.blocks} handlers={handlers} />}
            {working && (
              // Typing-indicator at the bottom of the conversation: the message
              // just echoed above it, so the user always sees the send is alive.
              <div className="flex min-w-0 items-center gap-2 text-sm text-muted">
                <Loader2 size={14} className="shrink-0 animate-spin" />
                <span className="shrink-0">
                  {activeRequest
                    ? t("live.status.paused")
                    : sending && !currentId
                      ? t("live.status.startingSession")
                      : t("live.status.working")}
                </span>
                {!activeRequest && currentTool && (
                  <>
                    <span
                      className="truncate font-mono text-xs"
                      title={currentTool.command ?? currentTool.title}
                    >
                      {currentTool.title}
                    </span>
                    {currentTool.startedAt !== undefined && (
                      <Elapsed start={currentTool.startedAt} />
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="px-8 pb-5 pt-2">
          <div className="mx-auto max-w-[760px] space-y-3">
            {connected && !defaultModel && (
              <div
                role="status"
                className="flex items-center justify-between gap-4 rounded-card border border-warn/30 bg-warn/10 px-4 py-3"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium text-text">{t("heor:modelRequired.title")}</div>
                  <p className="mt-0.5 text-xs leading-5 text-muted">{t("heor:modelRequired.body")}</p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate("/settings")}
                  className="shrink-0 rounded-input border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text hover:bg-surface-2"
                >
                  {t("heor:modelRequired.action")}
                </button>
              </div>
            )}
            {activeRequest && (
              <InteractionPrompt
                question={activeQuestion}
                permission={activeQuestion ? undefined : activePermission}
                origin={requestOrigin}
                onAnswer={(id, answers) => void answerQuestion(id, answers)}
                onReject={(id) => void rejectQuestion(id)}
                onPermission={(id, reply) => void replyPermission(id, reply)}
              />
            )}
            <Composer
              onSend={onSend}
              onRunShell={(c) => void onRunShell(c)}
              onRunCommand={(n, a) => void onRunCommand(n, a)}
              commands={composerCommands}
              disabled={!connected || working || !defaultModel}
              working={running}
              onStop={() => void interrupt()}
              placeholder={
                working
                  ? t("live.placeholder.waiting")
                  : connected && !defaultModel
                    ? t("heor:modelRequired.placeholder")
                  : connected
                    ? t("heor:placeholder")
                    : t("live.placeholder.disconnected")
              }
              approvalMode={approvalMode}
              onApprovalModeChange={(mode) => void setApprovalMode(mode)}
            />
          </div>
        </div>
      </div>

      {(showHeorReview || activeArtifact || showFiles || showRuns) && (
        <RightPane
          onClose={showHeorReview ? () => setShowHeorReview(false) : activeArtifact ? closeArtifact : showRuns ? () => setShowRuns(false) : () => setShowFiles(false)}
        >
          {showHeorReview ? (
            <HeorReviewPane
              project={activeProject}
              onClose={() => setShowHeorReview(false)}
              onRequestRevision={(prompt) => {
                useUiStore.getState().setComposerDraft(prompt);
                setShowHeorReview(false);
              }}
            />
          ) : activeArtifact ? (
            <InspectorShell
              inspector={fileInspectorFromBlock(activeArtifact)}
              onClose={closeArtifact}
              onEvaluate={onEvaluate}
              controls={<MaximizePaneButton />}
            />
          ) : showRuns ? (
            <RunsPane
              sessionId={sessionId!}
              onClose={() => setShowRuns(false)}
              controls={<MaximizePaneButton />}
            />
          ) : (
            <div className="h-full border-l border-border bg-surface">
              <SessionFilesPane
                onClose={() => setShowFiles(false)}
                controls={<MaximizePaneButton />}
              />
            </div>
          )}
        </RightPane>
      )}
    </div>
  );
}

/** Loading placeholder mirroring the thread's real shapes: a user card, agent
 *  text lines, a quiet tool row — so the page never sits blank while history
 *  loads and nothing jumps when the content arrives. */
function ThreadSkeleton() {
  return (
    <div className="animate-pulse space-y-4" aria-hidden>
      <div className="h-11 rounded-card bg-surface-2" />
      <div className="space-y-2.5 px-1 pt-1">
        <div className="h-3.5 w-11/12 rounded bg-surface-2" />
        <div className="h-3.5 w-4/5 rounded bg-surface-2" />
        <div className="h-3.5 w-2/3 rounded bg-surface-2" />
      </div>
      <div className="ml-2 h-4 w-2/5 rounded bg-surface-2 opacity-60" />
      <div className="h-11 rounded-card bg-surface-2" />
      <div className="space-y-2.5 px-1 pt-1">
        <div className="h-3.5 w-5/6 rounded bg-surface-2" />
        <div className="h-3.5 w-3/5 rounded bg-surface-2" />
      </div>
    </div>
  );
}

function ConnBadge({ status }: { status: RuntimeStatus }) {
  const { t } = useTranslation(["session", "common"]);
  const tone = status === "ready" ? "text-ok" : status === "error" ? "text-error" : "text-muted";
  return (
    <span
      className={cn("flex items-center gap-1.5 text-xs", tone)}
      title={t("live.connBadge.title", { status: t(`live.connBadge.status.${status}`) })}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          status === "ready" ? "bg-ok" : status === "error" ? "bg-error" : "bg-muted",
          status === "connecting" && "animate-pulse",
        )}
      />
      {/* Ready is the norm — a green dot says it all (hover for detail). Text
          appears only for states that need attention. */}
      {status !== "ready" && t(`live.connBadge.status.${status}`)}
    </span>
  );
}

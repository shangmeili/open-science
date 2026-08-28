// Project/session behavior: a standalone conversation gets its own local
// research scope; choosing a project pins the conversation to shared context.
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  activePath: "/ws/base",
  projects: [
    {
      id: "project-1",
      name: "Test HEOR project",
      createdAt: 1,
      kind: "heor" as const,
      path: "/ws/base",
    },
  ],
  setWorkspace: vi.fn(async (path: string) => {
    mocks.activePath = path;
    return path;
  }),
  newDatedWorkspace: vi.fn(async (name: string) => {
    mocks.activePath = `/ws/${name}`;
    return mocks.activePath;
  }),
  createProject: vi.fn(async (name: string) => {
    const project = {
      id: "created-project",
      name,
      createdAt: 2,
      kind: "heor" as const,
      path: "/ws/Created-Project",
    };
    mocks.projects.push(project);
    return project;
  }),
  importProject: vi.fn(async (path: string) => {
    const project = {
      id: "imported-project",
      name: "Imported Study",
      createdAt: 4,
      kind: "heor" as const,
      path: "/ws/Imported-Study",
      imported: true,
      importedFrom: path,
    };
    mocks.projects.push(project);
    return project;
  }),
  commitWorkspaceSnapshot: vi.fn(async () => false),
  kernelReset: vi.fn(async () => {}),
  /** Number of connect() attempts that fail before one succeeds. */
  failConnects: 0,
  /** Number of createSession() attempts that fail before one succeeds. */
  failCreates: 0,
  /** Fire a normalized event into the store, as the SSE stream would. */
  fireEvent: (_e: unknown) => {},
  /** Fire a client status flip into the store, as the SDK's reconnect would. */
  fireStatus: (_s: string) => {},
  runShell: vi.fn(),
  runCommand: vi.fn(),
  sendPrompt: vi.fn(),
  sendPromptDeferred: null as Promise<void> | null,
  sendPromptEvents: [] as unknown[],
  replyPermission: vi.fn(),
  abortSession: vi.fn(),
  abortSessionDeferred: null as Promise<void> | null,
  renameSession: vi.fn(),
  revert: vi.fn(),
  failReverts: 0,
  /** SSE events the real server streams back DURING an abort POST's await — an
   *  "aborted" error and one or more session.idle events. Empty by default. */
  abortTrailing: [] as unknown[],
  getMessages: vi.fn(),
  statuses: {} as Record<string, { type: "busy" | "retry" | "idle"; attempt?: number }>,
  /** Records setDefaultModel calls; `currentModel` is what getDefaultModel returns. */
  setDefaultModelSpy: vi.fn(),
  currentModel: null as string | null,
  providers: [] as Array<{
    id: string;
    name: string;
    models: Array<{ id: string; name: string }>;
  }>,
  /** Optional delayed catalog read used to reproduce a stale response race. */
  getDefaultModelDeferred: null as Promise<string | null> | null,
  /** Next setDefaultModel PATCH throws (server unreachable). */
  failSetModel: false,
  /** History the mock server returns for any session. */
  messages: [] as unknown[],
  /** Next getMessages call throws. */
  failMessages: false,
  /** Next runShell call throws (HTTP-level failure). */
  failShell: false,
  /** Next runCommand call throws before any event (HTTP-level failure). */
  failCommand: false,
  /** Next runCommand call streams an event, then throws — the WKWebView
   *  ~60 s fetch kill on a long sync turn ("Load failed"). */
  dropCommandPost: false,
  /** Approval mode the Rust config currently holds. */
  approvalMode: "approve" as string,
  setApprovalMode: vi.fn(async (mode: string) => {
    mocks.approvalMode = mode;
    return "http://127.0.0.1:1";
  }),
  startRuntime: vi.fn(async () => "http://127.0.0.1:1"),
  restartRuntime: vi.fn(async () => "http://127.0.0.1:1"),
  /** Constructor options every OpenCodeClient was created with. */
  clientOpts: [] as Record<string, unknown>[],
  recordModelCall: vi.fn(async (_event: unknown, _context?: unknown) => {}),
  recordRun: vi.fn(async (_input: unknown, _sessionId?: string, _model?: string | null) => {}),
}));

vi.mock("./tauri", () => ({
  isTauri: true,
  logDebug: async () => {},
  detectTools: async () => [],
  startRuntime: mocks.startRuntime,
  restartRuntime: mocks.restartRuntime,
  workspacePath: async () => mocks.activePath,
  setWorkspace: mocks.setWorkspace,
  newDatedWorkspace: mocks.newDatedWorkspace,
  createProject: mocks.createProject,
  importProject: mocks.importProject,
  listProjects: async () => mocks.projects,
  currentResearchScope: async () =>
    mocks.projects.find((project) => project.path === mocks.activePath) ?? {
      id: "standalone-scope",
      name: mocks.activePath.split("/").pop() ?? "conversation",
      createdAt: 3,
      kind: "session" as const,
      path: mocks.activePath,
    },
  markSession: async () => {},
  commitWorkspaceSnapshot: mocks.commitWorkspaceSnapshot,
  getApprovalMode: async () => mocks.approvalMode,
  setApprovalMode: mocks.setApprovalMode,
  runtimePassword: async () => "pw-test",
}));
vi.mock("./kernel", () => ({ kernelReset: mocks.kernelReset }));
vi.mock("./modelCalls", () => ({
  recordModelCall: mocks.recordModelCall,
  recordModelCallsFromHistory: vi.fn(async () => {}),
}));
vi.mock("./runs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./runs")>()),
  recordRun: mocks.recordRun,
}));
vi.mock("@ai4s/sdk", () => {
  class OpenCodeClient {
    private statusCb: (s: string) => void = () => {};
    constructor(opts: Record<string, unknown>) {
      mocks.clientOpts.push(opts);
    }
    onStatus(cb: (s: string) => void) {
      this.statusCb = cb;
      mocks.fireStatus = cb;
      return () => {
        this.statusCb = () => {};
      };
    }
    onEvent(cb: (e: unknown) => void) {
      mocks.fireEvent = cb;
    }
    async connect() {
      this.statusCb("connecting");
      if (mocks.failConnects > 0) {
        mocks.failConnects--;
        this.statusCb("error");
        throw new Error("Could not open OpenCode event stream");
      }
      this.statusCb("ready");
    }
    async listSessions() {
      return [];
    }
    async listSkills() {
      return [{ name: "stub" }];
    }
    async listAgents() {
      return [];
    }
    async getDefaultModel() {
      if (mocks.getDefaultModelDeferred) return mocks.getDefaultModelDeferred;
      return mocks.currentModel;
    }
    async setDefaultModel(model: string) {
      mocks.setDefaultModelSpy(model);
      if (mocks.failSetModel) throw new Error("Load failed");
      mocks.currentModel = model;
    }
    async listProviders() {
      return mocks.providers;
    }
    async createSession() {
      if (mocks.failCreates > 0) {
        mocks.failCreates--;
        throw new Error("Load failed");
      }
      return "ses_new";
    }
    async sendPrompt(sid: string, text: string, agent?: string, model?: string | null) {
      mocks.sendPrompt(sid, text, agent, model);
      for (const event of mocks.sendPromptEvents.splice(0)) mocks.fireEvent(event);
      if (mocks.sendPromptDeferred) await mocks.sendPromptDeferred;
    }
    async listCommands() {
      return [{ name: "init", description: "guided AGENTS.md setup", source: "command" }];
    }
    // Like the real endpoints, shell/command resolve only when the turn is
    // over — and session.idle fires BEFORE the POST resolves.
    async runShell(sid: string, command: string, agent: string) {
      mocks.runShell(sid, command, agent);
      if (mocks.failShell) throw new Error("shell exploded");
      mocks.fireEvent({
        type: "tool.updated",
        sessionId: sid,
        callId: "csh",
        tool: "bash",
        status: "success",
        title: "",
        input: { command },
        output: "/ws/mock\n",
      });
      mocks.fireEvent({ type: "session.idle", sessionId: sid });
    }
    async runCommand(sid: string, name: string, args?: string) {
      mocks.runCommand(sid, name, args);
      if (mocks.failCommand) throw new Error("command exploded");
      if (mocks.dropCommandPost) {
        mocks.fireEvent({ type: "text.updated", sessionId: sid, partId: "t1", text: "working…" });
        throw new Error("Load failed");
      }
      mocks.fireEvent({ type: "session.idle", sessionId: sid });
    }
    async replyPermission(requestId: string, reply: string) {
      mocks.replyPermission(requestId, reply);
    }
    async abortSession(sid: string) {
      mocks.abortSession(sid);
      // The real server answers an abort with its own SSE burst that streams
      // back while this POST is still being awaited — reproduce that timing so
      // the guard must already be set before the await, not after it.
      for (const e of mocks.abortTrailing) mocks.fireEvent(e);
      if (mocks.abortSessionDeferred) await mocks.abortSessionDeferred;
    }
    async renameSession(sid: string, title: string) {
      mocks.renameSession(sid, title);
    }
    async revert(sid: string, messageID: string) {
      mocks.revert(sid, messageID);
      if (mocks.failReverts > 0) {
        mocks.failReverts--;
        throw new Error("message not ready");
      }
    }
    async unrevert() {}
    async getMessages(sid: string) {
      mocks.getMessages(sid);
      if (mocks.failMessages) throw new Error("history hung");
      return mocks.messages;
    }
    async getSessionStatuses() {
      return mocks.statuses;
    }
    async listQuestions() {
      return [];
    }
    async listPermissions() {
      return [];
    }
    // The real client emits "offline" on teardown — the store must keep that
    // away from the UI while reconnecting (first-boot flicker regression).
    close() {
      this.statusCb("offline");
    }
  }
  return { OpenCodeClient, DEFAULT_OPENCODE_URL: "http://127.0.0.1:4096" };
});

import type { ArtifactBlock } from "@ai4s/shared";
import { buildHeorPrompt, heorPromptContext } from "./heor";
import { DRAFT_KEY, rememberBounded, rootSessionOf, useRuntimeStore } from "./runtime";

const PROJECT = {
  id: "project-1",
  name: "Test HEOR project",
  createdAt: 1,
  kind: "heor" as const,
  path: "/ws/base",
};

beforeEach(async () => {
  vi.clearAllMocks();
  mocks.activePath = PROJECT.path;
  mocks.projects = [PROJECT];
  mocks.failConnects = 0;
  mocks.failCreates = 0;
  mocks.failShell = false;
  mocks.failCommand = false;
  mocks.dropCommandPost = false;
  mocks.abortTrailing = [];
  mocks.abortSessionDeferred = null;
  mocks.failReverts = 0;
  mocks.messages = [];
  mocks.statuses = {};
  mocks.failMessages = false;
  mocks.approvalMode = "approve";
  mocks.currentModel = null;
  mocks.providers = [];
  mocks.getDefaultModelDeferred = null;
  mocks.failSetModel = false;
  mocks.sendPromptDeferred = null;
  mocks.sendPromptEvents = [];
  useRuntimeStore.setState({
    currentId: null,
    workspace: PROJECT.path,
    workspacePinned: false,
    projects: [PROJECT],
    sessions: [],
    researchScope: PROJECT,
    threads: {},
    error: null,
    sending: false,
    runningSessions: {},
    sessionProgress: {},
    permissions: [],
    sessionParents: {},
    panes: {},
    promptQueues: {},
    runsRevision: 0,
  });
  await useRuntimeStore.getState().connect();
  expect(useRuntimeStore.getState().status).toBe("ready");
});

describe("runtime authentication", () => {
  it("publishes a run-ledger revision only after the completed run is persisted", async () => {
    let release = () => {};
    mocks.recordRun.mockImplementationOnce(() => new Promise<void>((resolve) => {
      release = resolve;
    }));
    const before = useRuntimeStore.getState().runsRevision;

    mocks.fireEvent({
      type: "tool.updated",
      sessionId: "ses_new",
      messageId: "msg_run_revision",
      callId: "toolu_run_revision",
      tool: "bash",
      status: "success",
      input: { command: "python cea.py" },
      output: "done",
    });

    expect(useRuntimeStore.getState().runsRevision).toBe(before);
    release();
    await vi.waitFor(() => {
      expect(useRuntimeStore.getState().runsRevision).toBe(before + 1);
    });
  });

  it("associates a completed model call with only the active HEOR template context", async () => {
    const runtimePrompt = buildHeorPrompt("研究者问题", "zh-Hans");
    const sessionId = await useRuntimeStore.getState().sendPrompt(runtimePrompt);
    const event = {
      type: "message.usage" as const,
      sessionId: sessionId!,
      messageId: "msg_assistant_1",
      parentMessageId: "msg_user_1",
      providerId: "mock-provider",
      modelId: "mock-model",
      agent: "build",
      createdAt: 1_000,
      completedAt: 1_250,
      runtimeReportedCost: 0.0123,
      tokens: { input: 1, output: 2, reasoning: 0, cacheRead: 0, cacheWrite: 0 },
    };

    mocks.fireEvent(event);

    expect(mocks.recordModelCall).toHaveBeenCalledWith(event, heorPromptContext(runtimePrompt));
    expect(JSON.stringify(mocks.recordModelCall.mock.calls[0][1])).not.toContain("研究者问题");
  });

  it("discards HEOR template context when a new-session send fails", async () => {
    mocks.sendPromptDeferred = new Promise<void>((_resolve, reject) => {
      setTimeout(() => reject(new Error("Load failed")), 0);
    });
    await useRuntimeStore.getState().sendPrompt(buildHeorPrompt("会失败的研究者问题", "zh-Hans"));
    mocks.recordModelCall.mockClear();
    const event = {
      type: "message.usage" as const,
      sessionId: "ses_new",
      messageId: "msg_unrelated",
      parentMessageId: "msg_unrelated_user",
      providerId: "mock-provider",
      modelId: "mock-model",
      agent: "build",
      createdAt: 2_000,
      completedAt: 2_250,
      runtimeReportedCost: 0,
      tokens: { input: 1, output: 1, reasoning: 0, cacheRead: 0, cacheWrite: 0 },
    };

    mocks.fireEvent(event);

    expect(mocks.recordModelCall).toHaveBeenCalledWith(event, undefined);
  });

  it("bounds long-lived SSE deduplication memory", () => {
    const seen = new Set<string>();
    rememberBounded(seen, "first", 2);
    rememberBounded(seen, "second", 2);
    rememberBounded(seen, "third", 2);
    expect([...seen]).toEqual(["second", "third"]);
  });

  it("deduplicates concurrent bootstrap calls", async () => {
    const first = useRuntimeStore.getState().bootstrap();
    const second = useRuntimeStore.getState().bootstrap();

    expect(second).toBe(first);
    await Promise.all([first, second]);
    expect(mocks.startRuntime).toHaveBeenCalledTimes(1);
  });

  it("connect() passes the per-run runtime password to the SDK client", async () => {
    // The sidecar requires Basic auth (OPENCODE_SERVER_PASSWORD); an
    // unauthenticated client would 401 on every call.
    mocks.clientOpts.length = 0;
    await useRuntimeStore.getState().connect();
    expect(mocks.clientOpts[mocks.clientOpts.length - 1]).toMatchObject({
      password: "pw-test",
    });
  });

  it("replaces the local runtime process before reconnecting during recovery", async () => {
    useRuntimeStore.setState({ status: "error", error: "runtime stopped" });

    const recovered = await useRuntimeStore.getState().restartLocalRuntime();

    expect(recovered).toBe(true);
    expect(mocks.restartRuntime).toHaveBeenCalledTimes(1);
    expect(useRuntimeStore.getState()).toMatchObject({
      status: "ready",
      error: null,
      switching: false,
      serverUrl: "http://127.0.0.1:1",
    });
  });
});

describe("project and standalone conversations", () => {
  it("renames a task through the runtime and updates its sidebar metadata", async () => {
    useRuntimeStore.setState({
      sessions: [{ id: "ses_1", title: "Old title", directory: PROJECT.path }],
    });

    await useRuntimeStore.getState().renameSession("ses_1", "Updated CEA review");

    expect(mocks.renameSession).toHaveBeenCalledWith("ses_1", "Updated CEA review");
    expect(useRuntimeStore.getState().sessions).toContainEqual({
      id: "ses_1",
      title: "Updated CEA review",
      directory: PROJECT.path,
    });
  });

  it("adds a newly created project before switching into it", async () => {
    useRuntimeStore.setState({ projects: [], workspacePinned: false });
    const created = await useRuntimeStore.getState().createProject("Created Project");
    expect(created?.id).toBe("created-project");
    expect(useRuntimeStore.getState().projects).toContainEqual(created);
    expect(mocks.setWorkspace).toHaveBeenCalledWith("/ws/Created-Project");
    expect(useRuntimeStore.getState().workspacePinned).toBe(true);
  });

  it("imports an existing folder as an isolated project copy before switching into it", async () => {
    useRuntimeStore.setState({ projects: [], workspacePinned: false });

    const imported = await useRuntimeStore.getState().importProject("/external/Study");

    expect(mocks.importProject).toHaveBeenCalledWith("/external/Study");
    expect(imported).toMatchObject({
      id: "imported-project",
      imported: true,
      importedFrom: "/external/Study",
      path: "/ws/Imported-Study",
    });
    expect(useRuntimeStore.getState().projects).toContainEqual(imported);
    expect(mocks.setWorkspace).toHaveBeenCalledWith("/ws/Imported-Study");
    expect(useRuntimeStore.getState().workspacePinned).toBe(true);
  });

  it("creates a standalone conversation in its own dated research scope", async () => {
    useRuntimeStore.setState({ projects: [], workspacePinned: false });
    const id = await useRuntimeStore.getState().sendPrompt("hello");
    expect(id).toBe("ses_new");
    expect(mocks.newDatedWorkspace).toHaveBeenCalledTimes(1);
    expect(mocks.newDatedWorkspace.mock.calls[0][0]).toMatch(/^\d{4}-\d{2}-\d{2}-\d{4}$/);
    expect(mocks.kernelReset).toHaveBeenCalled();
    expect(useRuntimeStore.getState().researchScope?.kind).toBe("session");
  });

  it("can keep runtime-only Skill syntax out of the visible researcher message", async () => {
    useRuntimeStore.setState({ projects: [], workspacePinned: false });
    const id = await useRuntimeStore.getState().sendPrompt(
      "$heor-model-calibration\n\nCheck this model",
      "Skill: Model calibration\n\nCheck this model",
    );

    expect(mocks.sendPrompt).toHaveBeenCalledWith(
      "ses_new",
      "$heor-model-calibration\n\nCheck this model",
      "build",
      null,
    );
    expect(useRuntimeStore.getState().threads[id!].blocks).toContainEqual({
      kind: "user",
      text: "Skill: Model calibration\n\nCheck this model",
    });
  });

  it("materializes a standalone scope before a starter or attachment writes files", async () => {
    useRuntimeStore.setState({ projects: [], workspacePinned: false });
    expect(await useRuntimeStore.getState().ensureStandaloneWorkspace()).toBe(true);
    expect(useRuntimeStore.getState().workspacePinned).toBe(true);
    expect(mocks.newDatedWorkspace).toHaveBeenCalledTimes(1);

    await useRuntimeStore.getState().sendPrompt("continue with the prepared files");
    expect(mocks.newDatedWorkspace).toHaveBeenCalledTimes(1);
  });

  it("creates a conversation in the selected project without a dated scope", async () => {
    useRuntimeStore.setState({ workspacePinned: true });
    const id = await useRuntimeStore.getState().sendPrompt("hello");
    expect(id).toBe("ses_new");
    expect(mocks.newDatedWorkspace).not.toHaveBeenCalled();
  });

  it("uses the current model for an existing session instead of its stale creation model", async () => {
    useRuntimeStore.setState({
      currentId: "ses_existing",
      defaultModel: "minimax-cn-token-plan/MiniMax-M3",
      threads: {
        ses_existing: { blocks: [], index: {}, loaded: true },
      },
    });

    await useRuntimeStore.getState().sendPrompt("continue");

    expect(mocks.sendPrompt).toHaveBeenCalledWith(
      "ses_existing",
      "continue",
      "build",
      "minimax-cn-token-plan/MiniMax-M3",
    );
  });

  it("does not create another scope for later messages in the same conversation", async () => {
    await useRuntimeStore.getState().sendPrompt("first");
    await useRuntimeStore.getState().sendPrompt("second");
    expect(mocks.newDatedWorkspace).toHaveBeenCalledTimes(1);
  });

  it("masks transient connect errors while deliberately reconnecting", async () => {
    mocks.failConnects = 1;
    const done = useRuntimeStore.getState().connectRetry(3);
    await new Promise((r) => setTimeout(r, 50)); // after the first failed attempt
    expect(useRuntimeStore.getState().status).toBe("connecting");
    expect(useRuntimeStore.getState().error).toBe(null);
    await done;
    expect(useRuntimeStore.getState().status).toBe("ready");
    expect(useRuntimeStore.getState().error).toBe(null);
  });

  it("never passes through 'offline' while retrying (first-boot page flicker)", async () => {
    // On a fresh install the retry loop runs for minutes (macOS TCC dialog);
    // each attempt tears down the previous client, whose close() emits
    // "offline" — if that reaches the store, the page flips between the
    // offline help card and the connecting screen once per attempt.
    mocks.failConnects = 1;
    const seen: string[] = [];
    const unsub = useRuntimeStore.subscribe((s, prev) => {
      if (s.status !== prev.status) seen.push(s.status);
    });
    await useRuntimeStore.getState().connectRetry(3);
    unsub();
    expect(useRuntimeStore.getState().status).toBe("ready");
    expect(seen).not.toContain("offline");
  });

  it("surfaces the last error only when the retry window is exhausted", async () => {
    mocks.failConnects = 99;
    await useRuntimeStore.getState().connectRetry(1);
    expect(useRuntimeStore.getState().status).toBe("error");
    expect(useRuntimeStore.getState().error).toContain("event stream");
  });

  it("a superseded openSession does not start a second, dueling reconnect", async () => {
    // Opening a folder-scoped session reconnects the SSE stream. If a newer
    // open (rapid switching, or an effect that fires twice) overlaps an older
    // one, TWO connectRetry loops must NOT run: they tear down each other's
    // in-flight EventSource and leak half-open sockets until the webview's
    // per-host connection pool is exhausted and every later session hangs.
    useRuntimeStore.setState({
      sessions: [
        { id: "A", title: "A", directory: "/ws/A" },
        { id: "B", title: "B", directory: "/ws/B" },
      ] as never,
    });
    const before = mocks.clientOpts.length;

    // Fire both without awaiting the first — the exact overlap seen in the wild.
    await Promise.all([
      useRuntimeStore.getState().openSession("A"),
      useRuntimeStore.getState().openSession("B"),
    ]);

    // Only the winner reconnects (one new client), and only its history loads.
    expect(mocks.clientOpts.length - before).toBe(1);
    expect(useRuntimeStore.getState().currentId).toBe("B");
    expect(mocks.getMessages).toHaveBeenLastCalledWith("B");
  });

  it("does not reconnect an open session when Windows paths identify the same workspace", async () => {
    useRuntimeStore.setState({
      workspace: "C:\\Users\\Researcher\\Documents\\AI4HEOR\\Project-A",
      sessions: [{
        id: "A",
        title: "A",
        directory: "c:/users/researcher/documents/AI4HEOR/Project-A/",
      }] as never,
    });
    mocks.setWorkspace.mockClear();
    mocks.kernelReset.mockClear();

    await useRuntimeStore.getState().openSession("A");

    expect(mocks.setWorkspace).not.toHaveBeenCalled();
    expect(mocks.kernelReset).not.toHaveBeenCalled();
    expect(mocks.getMessages).toHaveBeenLastCalledWith("A");
  });

  it("echoes the first message instantly into the draft, then grafts it onto the session", async () => {
    const p = useRuntimeStore.getState().sendPrompt("hi");
    // Synchronously (before any await resolves): the message is visible and
    // the composer is locked — the user is never staring at an unchanged page.
    expect(useRuntimeStore.getState().sending).toBe(true);
    expect(useRuntimeStore.getState().threads[DRAFT_KEY]?.blocks).toEqual([
      { kind: "user", text: "hi" },
    ]);
    await p;
    const s = useRuntimeStore.getState();
    expect(s.currentId).toBe("ses_new");
    expect(s.threads[DRAFT_KEY]).toBeUndefined();
    expect(s.threads["ses_new"].blocks).toEqual([{ kind: "user", text: "hi" }]);
    expect(s.sending).toBe(false);
    expect(s.runningSessions["ses_new"]).toBe(true); // turn active until idle
  });

  it("ignores a second send while one is in flight", async () => {
    const p = useRuntimeStore.getState().sendPrompt("hi");
    const second = await useRuntimeStore.getState().sendPrompt("hi again");
    expect(second).toBe(null);
    await p;
    expect(useRuntimeStore.getState().threads[DRAFT_KEY] ?? undefined).toBeUndefined();
    expect(useRuntimeStore.getState().threads["ses_new"].blocks).toHaveLength(1);
  });

  it("session.idle ends the turn without claiming that the research is complete", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    expect(useRuntimeStore.getState().runningSessions["ses_new"]).toBe(true);
    mocks.fireEvent({ type: "session.idle", sessionId: "ses_new" });
    const s = useRuntimeStore.getState();
    expect(s.runningSessions["ses_new"]).toBeUndefined();
    expect(s.threads["ses_new"].blocks).toEqual([{ kind: "user", text: "hi" }]);
  });

  it("a session error is visible and waits for idle plus executor cleanup before unlocking", async () => {
    let releaseAbort!: () => void;
    mocks.abortSessionDeferred = new Promise<void>((resolve) => {
      releaseAbort = resolve;
    });
    await useRuntimeStore.getState().sendPrompt("hi");
    mocks.fireEvent({ type: "error", sessionId: "ses_new", message: "model unavailable" });
    let state = useRuntimeStore.getState();
    expect(state.runningSessions["ses_new"]).toBe(true);
    expect(state.threads["ses_new"].blocks.slice(-1)[0]).toEqual({
      kind: "status-line",
      text: "model unavailable",
      tone: "error",
    });
    mocks.fireEvent({ type: "session.idle", sessionId: "ses_new" });
    state = useRuntimeStore.getState();
    expect(state.runningSessions["ses_new"]).toBe(true);
    await vi.waitFor(() => expect(mocks.abortSession).toHaveBeenCalledWith("ses_new"));
    releaseAbort();
    await vi.waitFor(() => {
      expect(useRuntimeStore.getState().runningSessions["ses_new"]).toBeUndefined();
    });
    state = useRuntimeStore.getState();
    expect(state.runningSessions["ses_new"]).toBeUndefined();
  });

  it("does not resurrect a turn when provider error and idle beat prompt_async", async () => {
    mocks.sendPromptEvents = [
      { type: "error", sessionId: "ses_new", message: "model unavailable" },
      { type: "session.idle", sessionId: "ses_new" },
    ];
    await useRuntimeStore.getState().sendPrompt("hi");
    await vi.waitFor(() => {
      expect(useRuntimeStore.getState().runningSessions["ses_new"]).toBeUndefined();
    });
    const state = useRuntimeStore.getState();
    expect(state.sessionProgress["ses_new"]).toBeUndefined();
    expect(state.threads["ses_new"].blocks.slice(-1)[0]).toMatchObject({
      kind: "status-line",
      text: "model unavailable",
      tone: "error",
    });
  });

  it("retries a failed createSession once (transient 'Load failed')", async () => {
    mocks.failCreates = 1;
    const id = await useRuntimeStore.getState().sendPrompt("hi");
    expect(id).toBe("ses_new");
    expect(useRuntimeStore.getState().error).toBe(null);
  });

  it("a hard create failure shows a red line in the draft and unlocks the composer", async () => {
    mocks.failCreates = 99;
    const id = await useRuntimeStore.getState().sendPrompt("hi");
    expect(id).toBe(null);
    const s = useRuntimeStore.getState();
    expect(s.sending).toBe(false);
    expect(s.threads[DRAFT_KEY].blocks.slice(-1)[0]).toMatchObject({
      kind: "status-line",
      tone: "error",
    });
  });

  it("keeps a delayed send failure on the task that started the request", async () => {
    let rejectSend!: (error: Error) => void;
    mocks.sendPromptDeferred = new Promise<void>((_resolve, reject) => {
      rejectSend = reject;
    });
    useRuntimeStore.setState({
      currentId: "ses_a",
      sessions: [
        { id: "ses_a", title: "A", directory: PROJECT.path },
        { id: "ses_b", title: "B", directory: PROJECT.path },
      ] as never,
      threads: {
        ses_a: { blocks: [], index: {}, loaded: true },
        ses_b: { blocks: [{ kind: "user", text: "existing B" }], index: {}, loaded: true },
      },
    });

    const pending = useRuntimeStore.getState().sendPrompt("request from A");
    useRuntimeStore.setState({ currentId: "ses_b" });
    rejectSend(new Error("provider stopped"));
    await pending;

    const state = useRuntimeStore.getState();
    expect(state.error).toBe(null);
    expect(state.threads.ses_a.blocks[state.threads.ses_a.blocks.length - 1]).toMatchObject({
      kind: "status-line",
      text: "Send failed: provider stopped",
      tone: "error",
    });
    expect(state.threads.ses_b.blocks).toEqual([{ kind: "user", text: "existing B" }]);
  });

  it("marks a deliberate switch as `switching` for its whole duration", async () => {
    mocks.failConnects = 1; // keep the reconnect in flight for one retry beat
    const done = useRuntimeStore.getState().switchWorkspace({ path: "/ws/mine" });
    await new Promise((r) => setTimeout(r, 50));
    expect(useRuntimeStore.getState().switching).toBe(true);
    await done;
    expect(useRuntimeStore.getState().switching).toBe(false);
    expect(useRuntimeStore.getState().status).toBe("ready");
  });

  it("runShell: echoes `! cmd`, runs it, and ends the turn even though idle beat the POST", async () => {
    const id = await useRuntimeStore.getState().runShell("pwd");
    expect(id).toBe("ses_new");
    expect(mocks.runShell).toHaveBeenCalledWith("ses_new", "pwd", "build");
    const s = useRuntimeStore.getState();
    expect(s.threads["ses_new"].blocks[0]).toEqual({ kind: "user", text: "! pwd" });
    // The sync endpoint resolves after session.idle already fired — the
    // running lock must not stick (it was set before the POST, cleared after).
    expect(s.runningSessions["ses_new"]).toBeUndefined();
    expect(s.shellTurns["ses_new"]).toBeUndefined();
    expect(s.sending).toBe(false);
  });

  it("runShell: the bash row carries the command as title and the output inline", async () => {
    await useRuntimeStore.getState().runShell("pwd");
    const bash = useRuntimeStore
      .getState()
      .threads["ses_new"].blocks.find((b) => b.kind === "tool-call");
    // The shell endpoint reports an empty title — the command line stands in,
    // and the output shows inline (it IS the result the user asked for).
    expect(bash).toMatchObject({ title: "pwd", status: "success", outputSummary: "/ws/mock" });
  });

  it("an agent bash step (no shell turn) stays a quiet line without inline output", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    mocks.fireEvent({
      type: "tool.updated",
      sessionId: "ses_new",
      callId: "c9",
      tool: "bash",
      status: "success",
      title: "install deps",
      input: { command: "pip install numpy" },
      output: "lots of pip noise",
    });
    const bash = useRuntimeStore
      .getState()
      .threads["ses_new"].blocks.find((b) => b.kind === "tool-call");
    // A bash step is titled by its (de-noised) command — the honest record —
    // not the model's free-text description.
    expect(bash).toMatchObject({ title: "pip install numpy", verb: "Ran", status: "success" });
    expect((bash as { outputSummary?: string }).outputSummary).toBeUndefined();
  });

  it("runShell failure lands as a red line and unlocks the composer", async () => {
    mocks.failShell = true;
    await useRuntimeStore.getState().runShell("pwd");
    const s = useRuntimeStore.getState();
    expect(s.threads["ses_new"].blocks.slice(-1)[0]).toMatchObject({
      kind: "status-line",
      tone: "error",
    });
    expect(s.runningSessions["ses_new"]).toBeUndefined();
    expect(s.shellTurns["ses_new"]).toBeUndefined(); // no events will clear it
    expect(s.sending).toBe(false);
  });

  it("runCommand: echoes `/name args` and posts the command with its arguments", async () => {
    const id = await useRuntimeStore.getState().runCommand("init", "focus on tests");
    expect(id).toBe("ses_new");
    expect(mocks.runCommand).toHaveBeenCalledWith("ses_new", "init", "focus on tests");
    const s = useRuntimeStore.getState();
    expect(s.threads["ses_new"].blocks[0]).toEqual({ kind: "user", text: "/init focus on tests" });
    expect(s.runningSessions["ses_new"]).toBeUndefined();
  });

  it("/clear starts a new draft in the same folder without calling OpenCode command", async () => {
    useRuntimeStore.setState({
      currentId: "ses_old",
      workspacePinned: false,
      threads: {
        ses_old: { blocks: [{ kind: "user", text: "old context" }], index: {}, loaded: true },
      },
    });
    const id = await useRuntimeStore.getState().runCommand("clear");
    expect(id).toBe(null);
    expect(mocks.runCommand).not.toHaveBeenCalled();

    const cleared = useRuntimeStore.getState();
    expect(cleared.currentId).toBe(null);
    expect(cleared.workspacePinned).toBe(true);
    expect(cleared.threads.ses_old.blocks).toEqual([{ kind: "user", text: "old context" }]);
    expect(cleared.threads[DRAFT_KEY].blocks).toEqual([
      {
        kind: "status-line",
        text: "Chat context cleared. Files stay in the same folder.",
        tone: "review",
        divider: true,
      },
    ]);

    const connectsBeforeNextTurn = mocks.clientOpts.length;
    await useRuntimeStore.getState().sendPrompt("next");
    expect(mocks.clientOpts.length).toBeGreaterThan(connectsBeforeNextTurn);
  });

  it("openSession stops the loading skeleton when history fails to load", async () => {
    mocks.failMessages = true;
    useRuntimeStore.setState({
      sessions: [{ id: "ses_bad", title: "Bad session", directory: "/ws/base" }],
      currentId: null,
      threads: {},
    });

    await useRuntimeStore.getState().openSession("ses_bad");

    const thread = useRuntimeStore.getState().threads.ses_bad;
    expect(thread.loaded).toBe(true);
    expect(thread.blocks).toEqual([
      { kind: "status-line", text: "Failed to load messages: history hung", tone: "error" },
    ]);
  });

  it("global startDraft starts standalone; a project can still pin its own draft", async () => {
    await useRuntimeStore.getState().switchWorkspace({ path: PROJECT.path });
    expect(useRuntimeStore.getState().workspacePinned).toBe(true);
    const before = useRuntimeStore.getState().draftEpoch;
    useRuntimeStore.getState().startDraft();
    expect(useRuntimeStore.getState().workspacePinned).toBe(false);
    expect(useRuntimeStore.getState().draftEpoch).toBe(before + 1);
  });
});

// A task tool spawns a subagent in a CHILD session; its permission asks carry
// the child's id, and a sync POST held open for a long turn is killed by
// WKWebView at ~60 s. Both must not strand the conversation.
describe("subagent permission asks and long sync turns", () => {
  it("shows model-step progress during a long turn and clears it on idle", async () => {
    const id = await useRuntimeStore.getState().sendPrompt("review the evidence");
    expect(id).toBe("ses_new");
    if (!id) throw new Error("expected a session id");
    mocks.fireEvent({ type: "step.updated", sessionId: id, step: 1 });
    mocks.fireEvent({ type: "step.updated", sessionId: id, step: 2 });
    expect(useRuntimeStore.getState().stepCounts[id]).toBe(2);
    mocks.fireEvent({ type: "session.idle", sessionId: id });
    expect(useRuntimeStore.getState().stepCounts[id]).toBeUndefined();
  });

  it("maps a task tool's child session to the parent conversation", async () => {
    const id = await useRuntimeStore.getState().sendPrompt("explore the repo");
    mocks.fireEvent({
      type: "tool.updated",
      sessionId: id,
      callId: "c1",
      tool: "task",
      status: "running",
      title: "Explore repo",
      childSessionId: "ses_child",
    });
    mocks.fireEvent({
      type: "permission.asked",
      sessionId: "ses_child",
      requestId: "per_1",
      action: "external_directory",
      resources: ["/repo/*"],
    });
    const s = useRuntimeStore.getState();
    expect(s.sessionParents["ses_child"]).toBe(id);
    expect(rootSessionOf(s.sessionParents, "ses_child")).toBe(id);
    expect(s.permissions).toHaveLength(1);
  });

  it("keeps the turn alive when a sync POST dies mid-turn but SSE kept streaming", async () => {
    mocks.dropCommandPost = true;
    const id = await useRuntimeStore.getState().runCommand("growth-marketing");
    expect(id).toBe("ses_new");
    const s = useRuntimeStore.getState();
    expect(
      s.threads["ses_new"].blocks.some((b) => b.kind === "status-line" && b.tone === "error"),
    ).toBe(false);
    expect(s.runningSessions["ses_new"]).toBe(true); // still working server-side
    expect(s.sending).toBe(false); // composer input unlocked for the queue
    mocks.fireEvent({ type: "session.idle", sessionId: "ses_new" });
    expect(useRuntimeStore.getState().runningSessions["ses_new"]).toBeUndefined();
  });

  it("a command POST that fails before any event still shows the red line", async () => {
    mocks.failCommand = true;
    await useRuntimeStore.getState().runCommand("init");
    const s = useRuntimeStore.getState();
    const blocks = s.threads["ses_new"].blocks;
    expect(blocks[blocks.length - 1]).toMatchObject({ kind: "status-line", tone: "error" });
    expect(s.runningSessions["ses_new"]).toBeUndefined();
    expect(s.sending).toBe(false);
  });

  it("one reply answers all identical pending asks (same session, action, resources)", async () => {
    await useRuntimeStore.getState().sendPrompt("go");
    const ask = (requestId: string) =>
      mocks.fireEvent({
        type: "permission.asked",
        sessionId: "ses_child",
        requestId,
        action: "external_directory",
        resources: ["/repo/*"],
      });
    ask("per_a");
    ask("per_b");
    ask("per_c");
    expect(useRuntimeStore.getState().permissions).toHaveLength(3);
    await useRuntimeStore.getState().replyPermission("per_a", "always");
    expect(mocks.replyPermission).toHaveBeenCalledTimes(3);
    expect(mocks.replyPermission).toHaveBeenCalledWith("per_b", "always");
    expect(useRuntimeStore.getState().permissions).toHaveLength(0);
  });
});

// A missed session.idle (SSE reconnect window, directory-scoped event stream)
// must not spin "Working…" forever: the store reconciles its running locks
// against the server's truth, and the user can always interrupt a turn.
describe("stale running locks and interrupt", () => {
  const doneHistory = [
    { role: "user", parts: [{ type: "text", text: "hi" }] },
    { role: "assistant", completed: 1783301200079, parts: [{ type: "text", text: "all done" }] },
  ];

  it("reconcileRunning clears a stale lock and reloads the missed history", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    expect(useRuntimeStore.getState().runningSessions["ses_new"]).toBe(true);
    mocks.messages = doneHistory; // the turn ended server-side; idle was missed
    await useRuntimeStore.getState().reconcileRunning();
    const s = useRuntimeStore.getState();
    expect(s.runningSessions["ses_new"]).toBeUndefined();
    expect(
      s.threads["ses_new"].blocks.some((b) => b.kind === "agent" && b.markdown === "all done"),
    ).toBe(true);
  });

  it("reconcileRunning keeps the lock while the turn is genuinely running", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    mocks.messages = [
      { role: "user", parts: [{ type: "text", text: "hi" }] },
      { role: "assistant", parts: [{ type: "text", text: "thinking…" }] }, // no `completed`
    ];
    await useRuntimeStore.getState().reconcileRunning();
    expect(useRuntimeStore.getState().runningSessions["ses_new"]).toBe(true);
  });

  it("does not mark a running task in another workspace as stopped", async () => {
    useRuntimeStore.setState({
      workspace: "/ws/B",
      sessions: [{ id: "ses_a", title: "A", directory: "/ws/A" }] as never,
      runningSessions: { ses_a: true },
      threads: { ses_a: { blocks: [], index: {}, loaded: true } },
    });
    mocks.messages = [
      { role: "user", parts: [{ type: "text", text: "continue" }] },
      { role: "assistant", parts: [{ type: "text", text: "working" }] },
    ];
    mocks.statuses = {};

    await useRuntimeStore.getState().reconcileRunning();
    await useRuntimeStore.getState().reconcileRunning();

    expect(useRuntimeStore.getState().runningSessions.ses_a).toBe(true);
    expect(useRuntimeStore.getState().threads.ses_a.blocks).toEqual([]);
  });

  it("reconciles a stopped Windows task when equivalent paths describe its active workspace", async () => {
    useRuntimeStore.setState({
      workspace: "C:\\Users\\Researcher\\Documents\\AI4HEOR\\Project-A",
      sessions: [{
        id: "ses_a",
        title: "A",
        directory: "c:/users/researcher/documents/AI4HEOR/Project-A/",
      }] as never,
      runningSessions: { ses_a: true },
      threads: { ses_a: { blocks: [], index: {}, loaded: true } },
    });
    mocks.messages = [
      { role: "user", parts: [{ type: "text", text: "continue" }] },
      { role: "assistant", parts: [] },
    ];
    mocks.statuses = {};

    await useRuntimeStore.getState().reconcileRunning();
    await useRuntimeStore.getState().reconcileRunning();

    expect(useRuntimeStore.getState().runningSessions.ses_a).toBeUndefined();
    expect(useRuntimeStore.getState().threads.ses_a.blocks.slice(-1)[0]).toMatchObject({
      kind: "status-line",
      tone: "error",
    });
  });

  it("reconcileRunning unlocks a blank provider failure after two inactive checks", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    mocks.messages = [
      { role: "user", parts: [{ type: "text", text: "hi" }] },
      { role: "assistant", parts: [] },
    ];
    await useRuntimeStore.getState().reconcileRunning();
    expect(useRuntimeStore.getState().runningSessions["ses_new"]).toBe(true);
    await useRuntimeStore.getState().reconcileRunning();
    const state = useRuntimeStore.getState();
    expect(state.runningSessions["ses_new"]).toBeUndefined();
    expect(state.threads.ses_new.blocks.slice(-1)[0]).toMatchObject({
      kind: "status-line",
      tone: "error",
    });
  });

  it("reconcileRunning unlocks an orphaned nonblank tool turn after a runtime restart", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    mocks.messages = [
      { role: "user", parts: [{ type: "text", text: "hi" }] },
      {
        role: "assistant",
        parts: [
          { type: "reasoning", text: "Inspecting the workspace" },
          {
            type: "tool",
            tool: "bash",
            state: { status: "running", input: { command: "cat .gitignore" } },
          },
        ],
      },
    ];
    mocks.statuses = {};
    await useRuntimeStore.getState().reconcileRunning();
    expect(useRuntimeStore.getState().runningSessions["ses_new"]).toBe(true);
    await useRuntimeStore.getState().reconcileRunning();
    const state = useRuntimeStore.getState();
    expect(state.runningSessions["ses_new"]).toBeUndefined();
    expect(state.threads.ses_new.blocks.slice(-1)[0]).toMatchObject({
      kind: "status-line",
      tone: "error",
    });
    expect(state.threads.ses_new.blocks.filter((block) => block.kind === "status-line")).toHaveLength(1);
    expect(state.threads.ses_new.blocks.some(
      (block) => block.kind === "tool-call" && block.status === "pending",
    )).toBe(false);
  });

  it("shows the server retry phase without unlocking the task", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    mocks.fireEvent({
      type: "session.status",
      sessionId: "ses_new",
      status: "retry",
      attempt: 2,
      message: "Rate Limited",
    });
    const state = useRuntimeStore.getState();
    expect(state.runningSessions.ses_new).toBe(true);
    expect(state.sessionProgress.ses_new).toMatchObject({ type: "retry", attempt: 2 });
  });

  it("connect() reconciles running locks left over from before the reconnect", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    mocks.messages = doneHistory;
    await useRuntimeStore.getState().connect(); // e.g. a workspace switch
    await new Promise((r) => setTimeout(r, 10)); // reconcile runs behind connect
    expect(useRuntimeStore.getState().runningSessions["ses_new"]).toBeUndefined();
  });

  it("interrupt aborts the turn, unlocks the composer and marks the thread", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    await useRuntimeStore.getState().interrupt();
    expect(mocks.abortSession).toHaveBeenCalledWith("ses_new");
    const s = useRuntimeStore.getState();
    expect(s.runningSessions["ses_new"]).toBeUndefined();
    expect(s.sending).toBe(false);
    expect(s.threads["ses_new"].blocks.slice(-1)[0]).toEqual({
      kind: "status-line",
      text: "Interrupted",
      tone: "error",
    });
  });

  it("the abort's own error/idle events add no noise after an interrupt", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    await useRuntimeStore.getState().interrupt();
    const before = useRuntimeStore.getState().threads["ses_new"].blocks;
    mocks.fireEvent({ type: "error", sessionId: "ses_new", message: "The message was aborted" });
    mocks.fireEvent({ type: "session.idle", sessionId: "ses_new" });
    expect(useRuntimeStore.getState().threads["ses_new"].blocks).toEqual(before);
  });

  it("swallows the abort's trailing error and BOTH idle events (only 'Interrupted' shows)", async () => {
    // Regression: the abort's SSE burst (an "aborted" error + two session.idle
    // events) arrives DURING the abort POST's await. If the guard is set after
    // the await, or consumed by the first idle, the thread grows a stray
    // "Aborted" and one or two "done" lines before "Interrupted".
    await useRuntimeStore.getState().sendPrompt("hi");
    mocks.abortTrailing = [
      { type: "error", sessionId: "ses_new", message: "The message was aborted" },
      { type: "session.idle", sessionId: "ses_new" },
      { type: "session.idle", sessionId: "ses_new" },
    ];
    await useRuntimeStore.getState().interrupt();
    const statusLines = useRuntimeStore
      .getState()
      .threads["ses_new"].blocks.filter((b) => b.kind === "status-line");
    expect(statusLines).toEqual([{ kind: "status-line", text: "Interrupted", tone: "error" }]);
  });

  it("a new turn after an interrupt folds its events normally again", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    await useRuntimeStore.getState().interrupt();
    mocks.fireEvent({ type: "session.idle", sessionId: "ses_new" }); // suppressed; guard clears on the next turn
    await useRuntimeStore.getState().sendPrompt("again");
    mocks.fireEvent({ type: "session.idle", sessionId: "ses_new" });
    const s = useRuntimeStore.getState();
    expect(s.runningSessions["ses_new"]).toBeUndefined();
    expect(s.threads["ses_new"].blocks.slice(-1)[0]).toEqual({ kind: "user", text: "again" });
  });

  it("interrupt does nothing when no turn is running", async () => {
    await useRuntimeStore.getState().interrupt();
    expect(mocks.abortSession).not.toHaveBeenCalled();
  });
});

describe("edit and return to a past message", () => {
  async function acceptedTurn(text: string, messageID: string) {
    await useRuntimeStore.getState().sendPrompt(text);
    mocks.fireEvent({ type: "message.user", sessionId: "ses_new", messageID });
    mocks.fireEvent({ type: "text.updated", sessionId: "ses_new", partId: `${messageID}-a`, text: "answer" });
    mocks.fireEvent({ type: "session.idle", sessionId: "ses_new" });
  }

  it("binds the runtime message id to the visible user message", async () => {
    await acceptedTurn("original", "msg-1");
    expect(useRuntimeStore.getState().threads.ses_new.blocks[0]).toMatchObject({
      kind: "user",
      text: "original",
      messageID: "msg-1",
    });
  });

  it("restores the workspace before resending an edited HEOR prompt", async () => {
    await acceptedTurn("original", "msg-1");
    mocks.sendPrompt.mockClear();

    const changed = await useRuntimeStore
      .getState()
      .editMessage("msg-1", "runtime HEOR prompt", "revised question");

    expect(changed).toBe(true);
    expect(mocks.revert).toHaveBeenCalledWith("ses_new", "msg-1");
    expect(mocks.sendPrompt).toHaveBeenCalledWith(
      "ses_new",
      "runtime HEOR prompt",
      "build",
      null,
    );
    expect(useRuntimeStore.getState().threads.ses_new.blocks).toContainEqual({
      kind: "user",
      text: "revised question",
    });
  });

  it("retries a newly indexed message and clears discarded interaction and pane state", async () => {
    await acceptedTurn("original", "msg-1");
    mocks.failReverts = 2;
    useRuntimeStore.setState({
      questions: [{ type: "question.asked", sessionId: "ses_new", requestId: "q1", questions: [] }],
      permissions: [{ type: "permission.asked", sessionId: "ses_new", requestId: "p1", action: "write", resources: [] }],
      panes: { ses_new: { artifact: { kind: "artifact", path: "old.pdf", filename: "old.pdf", artifact: "report", tool: "write" }, showFiles: false, showRuns: false } },
    });

    expect(await useRuntimeStore.getState().revertMessage("msg-1")).toBe(true);
    expect(mocks.revert).toHaveBeenCalledTimes(3);
    const state = useRuntimeStore.getState();
    expect(state.threads.ses_new.blocks).toEqual([]);
    expect(state.questions).toEqual([]);
    expect(state.permissions).toEqual([]);
    expect(state.panes.ses_new).toEqual({ artifact: null, showFiles: false, showRuns: false });
  });

  it("keeps the conversation unchanged when the runtime rollback fails", async () => {
    await acceptedTurn("original", "msg-1");
    const before = useRuntimeStore.getState().threads.ses_new.blocks;
    mocks.failReverts = 5;

    expect(await useRuntimeStore.getState().editMessage("msg-1", "new")).toBe(false);
    expect(mocks.sendPrompt).toHaveBeenCalledTimes(1);
    expect(useRuntimeStore.getState().threads.ses_new.blocks).toEqual(before);
    expect(useRuntimeStore.getState().error).toContain("message not ready");
  });
});

// The right pane belongs to a session: each one keeps its own open artifact /
// Files browser and gets it back when reopened — never another session's.
describe("per-session right pane", () => {
  const artifact = (path: string): ArtifactBlock => ({
    kind: "artifact",
    path,
    filename: path.split("/").pop()!,
    artifact: "report",
    tool: "write",
  });

  it("remembers each session's pane and restores it on switch-back", () => {
    useRuntimeStore.setState({ currentId: "ses_1" });
    useRuntimeStore.getState().openArtifact(artifact("report.pdf"));
    // Session 2 has nothing open; session 1's pdf must not leak into it.
    useRuntimeStore.setState({ currentId: "ses_2" });
    expect(useRuntimeStore.getState().panes["ses_2"]).toBeUndefined();
    useRuntimeStore.getState().openArtifact(artifact("analysis.ipynb"));
    // Back to session 1: the pdf is there again, untouched.
    useRuntimeStore.setState({ currentId: "ses_1" });
    expect(useRuntimeStore.getState().panes["ses_1"]?.artifact?.path).toBe("report.pdf");
    expect(useRuntimeStore.getState().panes["ses_2"]?.artifact?.path).toBe("analysis.ipynb");
  });

  it("a closed pane stays closed after switching away and back", () => {
    useRuntimeStore.setState({ currentId: "ses_1" });
    useRuntimeStore.getState().openArtifact(artifact("report.pdf"));
    useRuntimeStore.getState().closeArtifact();
    useRuntimeStore.setState({ currentId: "ses_2" });
    useRuntimeStore.setState({ currentId: "ses_1" });
    expect(useRuntimeStore.getState().panes["ses_1"]?.artifact).toBe(null);
  });

  it("the artifact inspector, Files browser, and Runs pane are mutually exclusive", () => {
    useRuntimeStore.setState({ currentId: "ses_1" });
    useRuntimeStore.getState().openArtifact(artifact("report.pdf"));
    useRuntimeStore.getState().setShowFiles(true);
    expect(useRuntimeStore.getState().panes["ses_1"]).toEqual({ artifact: null, showFiles: true, showRuns: false });
    // Opening Runs closes Files; opening an artifact closes Runs.
    useRuntimeStore.getState().setShowRuns(true);
    expect(useRuntimeStore.getState().panes["ses_1"]).toEqual({ artifact: null, showFiles: false, showRuns: true });
    useRuntimeStore.getState().openArtifact(artifact("report.pdf"));
    const p = useRuntimeStore.getState().panes["ses_1"];
    expect(p?.showFiles).toBe(false);
    expect(p?.showRuns).toBe(false);
  });

  it("grafts the draft's pane onto the session created by the first message", async () => {
    useRuntimeStore.getState().openArtifact(artifact("notes.md"));
    expect(useRuntimeStore.getState().panes[DRAFT_KEY]?.artifact?.path).toBe("notes.md");
    await useRuntimeStore.getState().sendPrompt("hi");
    const s = useRuntimeStore.getState();
    expect(s.panes[DRAFT_KEY]).toBeUndefined();
    expect(s.panes["ses_new"]?.artifact?.path).toBe("notes.md");
  });

  it("keeps queued prompts ordered and isolated by task", () => {
    const store = useRuntimeStore.getState();
    const first = store.enqueuePrompt("first follow-up");
    const second = store.enqueuePrompt("second follow-up", { id: "audit", label: "Audit" });
    expect(useRuntimeStore.getState().promptQueues[DRAFT_KEY].map((item) => item.id))
      .toEqual([first, second]);

    useRuntimeStore.getState().moveQueuedPrompt(second, "up");
    expect(useRuntimeStore.getState().promptQueues[DRAFT_KEY].map((item) => item.text))
      .toEqual(["second follow-up", "first follow-up"]);
    expect(useRuntimeStore.getState().takeNextQueuedPrompt()).toMatchObject({
      id: second,
      skill: { id: "audit", label: "Audit" },
    });

    useRuntimeStore.setState({ currentId: "ses_other" });
    useRuntimeStore.getState().enqueuePrompt("other task");
    expect(useRuntimeStore.getState().promptQueues[DRAFT_KEY]).toHaveLength(1);
    expect(useRuntimeStore.getState().promptQueues.ses_other).toHaveLength(1);
  });

  it("grafts messages queued during first-session creation onto the real task", async () => {
    useRuntimeStore.getState().enqueuePrompt("send after the first reply");
    await useRuntimeStore.getState().sendPrompt("start the task");
    const state = useRuntimeStore.getState();
    expect(state.promptQueues[DRAFT_KEY]).toBeUndefined();
    expect(state.promptQueues.ses_new?.map((item) => item.text))
      .toEqual(["send after the first reply"]);
  });

  it("startDraft resets the draft pane; session panes keep their memory", () => {
    useRuntimeStore.setState({ currentId: "ses_1" });
    useRuntimeStore.getState().openArtifact(artifact("report.pdf"));
    useRuntimeStore.setState({ currentId: null });
    useRuntimeStore.getState().openArtifact(artifact("stale.md"));
    useRuntimeStore.getState().startDraft();
    const s = useRuntimeStore.getState();
    expect(s.panes[DRAFT_KEY]).toBeUndefined();
    expect(s.panes["ses_1"]?.artifact?.path).toBe("report.pdf");
  });

  it("switchWorkspace drops the draft pane (old folder's files) but not session panes", async () => {
    useRuntimeStore.setState({ currentId: "ses_1" });
    useRuntimeStore.getState().openArtifact(artifact("report.pdf"));
    useRuntimeStore.setState({ currentId: null });
    useRuntimeStore.getState().openArtifact(artifact("old-folder.md"));
    await useRuntimeStore.getState().switchWorkspace({ path: "/ws/other" });
    const s = useRuntimeStore.getState();
    expect(s.panes[DRAFT_KEY]).toBeUndefined();
    expect(s.panes["ses_1"]?.artifact?.path).toBe("report.pdf");
  });

  it("deleteSession forgets the session's pane and queued messages", async () => {
    useRuntimeStore.setState({ currentId: "ses_1" });
    useRuntimeStore.getState().openArtifact(artifact("report.pdf"));
    useRuntimeStore.getState().enqueuePrompt("stale follow-up");
    await useRuntimeStore.getState().deleteSession("ses_1");
    expect(useRuntimeStore.getState().panes["ses_1"]).toBeUndefined();
    expect(useRuntimeStore.getState().promptQueues["ses_1"]).toBeUndefined();
  });
});


describe("approval mode", () => {
  it("loads the configured mode when connecting", async () => {
    expect(useRuntimeStore.getState().approvalMode).toBe("approve");
    mocks.approvalMode = "full";
    await useRuntimeStore.getState().connect();
    expect(useRuntimeStore.getState().approvalMode).toBe("full");
  });

  it("setApprovalMode persists the choice and reconnects to the restarted sidecar", async () => {
    await useRuntimeStore.getState().setApprovalMode("full");
    expect(mocks.setApprovalMode).toHaveBeenCalledWith("full");
    const s = useRuntimeStore.getState();
    expect(s.approvalMode).toBe("full");
    expect(s.status).toBe("ready"); // reconnected after the restart
  });

  it("setApprovalMode is a deliberate restart: `switching` masks the reconnect (no UI flash)", async () => {
    const p = useRuntimeStore.getState().setApprovalMode("full");
    // Synchronously flagged, like switchWorkspace — the page must not render
    // the restart as a disconnection.
    expect(useRuntimeStore.getState().switching).toBe(true);
    await p;
    const s = useRuntimeStore.getState();
    expect(s.switching).toBe(false);
    expect(s.status).toBe("ready");
  });

  it("does not restart the runtime when a task is active", async () => {
    await useRuntimeStore.getState().sendPrompt("hi");
    mocks.setApprovalMode.mockClear();
    await useRuntimeStore.getState().setApprovalMode("full");
    expect(mocks.setApprovalMode).not.toHaveBeenCalled();
    expect(useRuntimeStore.getState().approvalMode).toBe("approve");
  });

  it("repairs a configured model that is no longer available", async () => {
    mocks.providers = [
      {
        id: "minimax",
        name: "MiniMax",
        models: [{ id: "MiniMax-M3", name: "MiniMax M3" }],
      },
    ];
    mocks.currentModel = "retired/provider-model";
    useRuntimeStore.setState({ defaultModel: mocks.currentModel, switching: false });

    await useRuntimeStore.getState().loadCatalog();

    expect(mocks.setDefaultModelSpy).toHaveBeenCalledWith("minimax/MiniMax-M3");
    expect(useRuntimeStore.getState().defaultModel).toBe("minimax/MiniMax-M3");
  });

  it("leaves an available configured model unchanged", async () => {
    mocks.providers = [
      {
        id: "minimax",
        name: "MiniMax",
        models: [{ id: "MiniMax-M3", name: "MiniMax M3" }],
      },
    ];
    mocks.currentModel = "minimax/MiniMax-M3";
    useRuntimeStore.setState({ defaultModel: mocks.currentModel, switching: false });

    await useRuntimeStore.getState().loadCatalog();

    expect(mocks.setDefaultModelSpy).not.toHaveBeenCalled();
    expect(useRuntimeStore.getState().defaultModel).toBe("minimax/MiniMax-M3");
  });

  it("setDefaultModel applies the model and reconnects seamlessly (no manual Connect)", async () => {
    const before = mocks.clientOpts.length;
    await useRuntimeStore.getState().setDefaultModel("anthropic/claude-sonnet-5");
    expect(mocks.setDefaultModelSpy).toHaveBeenCalledWith("anthropic/claude-sonnet-5");
    // A fresh client/event stream replaces the one the config change closed —
    // exactly one reconnect, so switching models never strands the app offline.
    expect(mocks.clientOpts.length - before).toBe(1);
    const s = useRuntimeStore.getState();
    expect(s.status).toBe("ready");
    expect(s.switching).toBe(false);
    expect(s.defaultModel).toBe("anthropic/claude-sonnet-5");
  });

  it("setDefaultModel masks the reconnect with `switching` (no disconnect flash)", async () => {
    const p = useRuntimeStore.getState().setDefaultModel("anthropic/claude-sonnet-5");
    expect(useRuntimeStore.getState().switching).toBe(true);
    await p;
    expect(useRuntimeStore.getState().switching).toBe(false);
    expect(useRuntimeStore.getState().status).toBe("ready");
  });

  it("setDefaultModel rejects an exhausted reconnect without rolling back the persisted model", async () => {
    const originalConnectRetry = useRuntimeStore.getState().connectRetry;
    useRuntimeStore.setState({
      connectRetry: vi.fn(async () => {
        useRuntimeStore.setState({
          status: "error",
          error: "Could not open OpenCode event stream",
        });
        return false;
      }),
    });

    try {
      await expect(
        useRuntimeStore.getState().setDefaultModel("anthropic/claude-sonnet-5"),
      ).rejects.toThrow("Could not open OpenCode event stream");
      const state = useRuntimeStore.getState();
      expect(state.status).toBe("error");
      expect(state.defaultModel).toBe("anthropic/claude-sonnet-5");
      expect(state.switching).toBe(false);
    } finally {
      useRuntimeStore.setState({ connectRetry: originalConnectRetry });
    }
  });

  it("setDefaultModel uses a stable error when exhausted reconnect has no message", async () => {
    const originalConnectRetry = useRuntimeStore.getState().connectRetry;
    useRuntimeStore.setState({
      connectRetry: vi.fn(async () => {
        useRuntimeStore.setState({ status: "error", error: null });
        return false;
      }),
    });

    try {
      await expect(
        useRuntimeStore.getState().setDefaultModel("anthropic/claude-sonnet-5"),
      ).rejects.toThrow("Runtime did not reconnect after setting the default model.");
    } finally {
      useRuntimeStore.setState({ connectRetry: originalConnectRetry });
    }
  });

  it("holds a ready→connecting blip so a self-recovering stream never repaints the page", async () => {
    // OpenCode closes /event ~1s after a config PATCH while rebuilding its
    // instance; the SDK reconnects in ~250ms. That blip must not reach the UI.
    vi.useFakeTimers();
    try {
      mocks.fireStatus("connecting");
      expect(useRuntimeStore.getState().status).toBe("ready"); // held
      mocks.fireStatus("ready");
      await vi.advanceTimersByTimeAsync(5000);
      expect(useRuntimeStore.getState().status).toBe("ready"); // never flipped
    } finally {
      vi.useRealTimers();
    }
  });

  it("surfaces connecting when the stream does not recover within the grace window", async () => {
    vi.useFakeTimers();
    try {
      mocks.fireStatus("connecting");
      expect(useRuntimeStore.getState().status).toBe("ready");
      await vi.advanceTimersByTimeAsync(2000);
      expect(useRuntimeStore.getState().status).toBe("connecting");
    } finally {
      vi.useRealTimers();
    }
  });

  it("an error during the hold surfaces immediately", () => {
    mocks.fireStatus("connecting");
    mocks.fireStatus("error");
    expect(useRuntimeStore.getState().status).toBe("error");
  });

  it("loadCatalog never clobbers defaultModel while a switch is in flight", async () => {
    // The switch's reconnect fires loadCatalog, whose config read can still
    // answer with the pre-switch model while OpenCode rebuilds its instance —
    // applying it would visibly bounce the UI back to the previous model.
    try {
      useRuntimeStore.setState({ defaultModel: "moonshot/kimi-k2-thinking", switching: true });
      mocks.currentModel = "moonshot/kimi-k2.7-code"; // stale read-back
      await useRuntimeStore.getState().loadCatalog();
      expect(useRuntimeStore.getState().defaultModel).toBe("moonshot/kimi-k2-thinking");
      // Outside a switch the server value is authoritative again.
      useRuntimeStore.setState({ switching: false });
      await useRuntimeStore.getState().loadCatalog();
      expect(useRuntimeStore.getState().defaultModel).toBe("moonshot/kimi-k2.7-code");
    } finally {
      useRuntimeStore.setState({ switching: false });
    }
  });

  it("ignores a catalog model read that started before a completed switch", async () => {
    let resolveStale: (model: string | null) => void = () => {};
    mocks.getDefaultModelDeferred = new Promise((resolve) => {
      resolveStale = resolve;
    });
    const staleCatalog = useRuntimeStore.getState().loadCatalog();

    mocks.getDefaultModelDeferred = null;
    await useRuntimeStore.getState().setDefaultModel("moonshot/kimi-k2-thinking");
    resolveStale("moonshot/kimi-k2.7-code");
    await staleCatalog;

    expect(useRuntimeStore.getState().defaultModel).toBe("moonshot/kimi-k2-thinking");
  });
});

// The store — not the Settings page — owns the fact "a model switch failed":
// the page derives its whole model surface from `connected || switching ||
// modelSwitchError`, so the browser stays on screen for a retry no matter how
// the attempt failed, and clears wherever the failure stops being true.
describe("model switch failure state", () => {
  const failReconnect = () =>
    vi.fn(async () => {
      useRuntimeStore.setState({ status: "error", error: "Could not open OpenCode event stream" });
      return false;
    });

  it("connectRetry resolves true on success and false when exhausted", async () => {
    await expect(useRuntimeStore.getState().connectRetry(1)).resolves.toBe(true);
    mocks.failConnects = 99;
    await expect(useRuntimeStore.getState().connectRetry(1)).resolves.toBe(false);
  });

  it("an exhausted reconnect records modelSwitchError", async () => {
    const original = useRuntimeStore.getState().connectRetry;
    useRuntimeStore.setState({ connectRetry: failReconnect() });
    try {
      await expect(
        useRuntimeStore.getState().setDefaultModel("anthropic/claude-sonnet-5"),
      ).rejects.toThrow();
      expect(useRuntimeStore.getState().modelSwitchError).toBe(
        "Could not open OpenCode event stream",
      );
    } finally {
      useRuntimeStore.setState({ connectRetry: original });
    }
  });

  it("a rejected model PATCH records modelSwitchError (retry keeps the browser up)", async () => {
    // The likely retry path: the server is still down, so the PATCH itself
    // rejects before any reconnect. The failure state must re-arm — this is
    // exactly the case where the old page-local flag silently dropped it.
    mocks.failSetModel = true;
    await expect(
      useRuntimeStore.getState().setDefaultModel("anthropic/claude-sonnet-5"),
    ).rejects.toThrow("Load failed");
    expect(useRuntimeStore.getState().modelSwitchError).toBe("Load failed");
    expect(useRuntimeStore.getState().defaultModel).toBe(null); // PATCH never landed
  });

  it("a later successful model switch clears modelSwitchError", async () => {
    useRuntimeStore.setState({ modelSwitchError: "stale" });
    await useRuntimeStore.getState().setDefaultModel("anthropic/claude-sonnet-5");
    expect(useRuntimeStore.getState().modelSwitchError).toBe(null);
  });

  it("a later successful reconnect clears modelSwitchError", async () => {
    useRuntimeStore.setState({ modelSwitchError: "stale" });
    await useRuntimeStore.getState().connectRetry(1);
    expect(useRuntimeStore.getState().modelSwitchError).toBe(null);
  });

  it("changing the server URL clears modelSwitchError", () => {
    useRuntimeStore.setState({ modelSwitchError: "stale" });
    useRuntimeStore.getState().setServerUrl("http://127.0.0.1:9999");
    expect(useRuntimeStore.getState().modelSwitchError).toBe(null);
  });

  it("disconnect clears modelSwitchError (offline shows the connect prompt again)", () => {
    useRuntimeStore.setState({ modelSwitchError: "stale" });
    useRuntimeStore.getState().disconnect();
    expect(useRuntimeStore.getState().modelSwitchError).toBe(null);
  });
});

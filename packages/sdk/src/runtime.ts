import type {
  AgentInfo,
  CommandInfo,
  HistoryMessage,
  OpenCodeEvent,
  PermissionAskedEvent,
  PermissionReply,
  SavedPermission,
  ProviderInfo,
  QuestionAskedEvent,
  RuntimeStatus,
  SessionMeta,
  SessionRuntimeStatus,
  SkillInfo,
} from "./types";

/**
 * Runtime-independent contract used by the desktop research surface.
 *
 * OpenCode is the bundled implementation today, but the UI-facing lifecycle,
 * session, capability, model, execution, and Human-interaction APIs must not
 * depend on OpenCode-specific transport details. Provider authentication, MCP
 * configuration, and provider catalogs remain concrete-runtime concerns.
 */
export interface AgentRuntime {
  connect(): Promise<void>;
  close(): void;
  getStatus(): RuntimeStatus;
  onStatus(listener: (status: RuntimeStatus) => void): () => void;
  onEvent(listener: (event: OpenCodeEvent) => void): () => void;

  createSession(): Promise<string>;
  listSessions(): Promise<SessionMeta[]>;
  renameSession(sessionId: string, title: string): Promise<void>;
  deleteSession(sessionId: string): Promise<void>;
  getMessages(sessionId: string): Promise<HistoryMessage[]>;
  getSessionStatuses(): Promise<Record<string, SessionRuntimeStatus>>;
  sendPrompt(
    sessionId: string,
    text: string,
    agent?: string,
    model?: string | null,
  ): Promise<void>;
  abortSession(sessionId: string): Promise<void>;
  /** Return the task to this message, removing it and later messages while
   * restoring workspace files to their earlier state. */
  revert(sessionId: string, messageID: string, partID?: string): Promise<void>;
  /** Restore the most recent runtime revert. Kept at the runtime boundary even
   * though the desktop UI currently exposes only confirmed forward actions. */
  unrevert(sessionId: string): Promise<void>;

  listSkills(): Promise<SkillInfo[]>;
  listAgents(): Promise<AgentInfo[]>;
  listCommands(): Promise<CommandInfo[]>;

  getDefaultModel(): Promise<string | null>;
  setDefaultModel(model: string): Promise<void>;
  listProviders(): Promise<ProviderInfo[]>;

  runShell(sessionId: string, command: string, agent?: string): Promise<void>;
  runCommand(sessionId: string, command: string, args?: string): Promise<void>;

  listQuestions(sessionId?: string): Promise<QuestionAskedEvent[]>;
  listPermissions(sessionId?: string): Promise<PermissionAskedEvent[]>;
  answerQuestion(requestId: string, answers: string[][]): Promise<void>;
  rejectQuestion(requestId: string): Promise<void>;
  replyPermission(requestId: string, reply: PermissionReply): Promise<void>;
  listSavedPermissions(directory?: string): Promise<SavedPermission[]>;
  removeSavedPermission(id: string, directory?: string): Promise<void>;
}

// Thin bridge to the Tauri Rust side. In a plain browser these are no-ops so the
// app still runs in `pnpm dev`; in the packaged desktop app they invoke Rust commands.

export const isTauri =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export interface OpenCodeCredentials {
  provider: string;
  apiKey: string;
  model: string;
  baseUrl?: string;
}

export type ConfigureResult =
  | { ok: true; path: string }
  | { ok: false; reason: "not-desktop" }
  | { ok: false; reason: "error"; message: string };

/** Start the bundled OpenCode sidecar (desktop only). Returns its base URL. */
export async function startRuntime(): Promise<string | null> {
  if (!isTauri) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("start_runtime");
}

/** Replace the bundled local runtime process and return its stable endpoint. */
export async function restartRuntime(): Promise<string | null> {
  if (!isTauri) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("restart_runtime");
}

export interface StartupEnvironmentCheck {
  id: "workspace" | "skills" | "heorCore" | "harness" | string;
  ready: boolean;
  detail: string;
}

export interface StartupEnvironmentAudit {
  desktop: boolean;
  requiredReady: boolean;
  workspacePath: string | null;
  checks: StartupEnvironmentCheck[];
}

/**
 * Check only the local files required to start AI4HEOR. Model providers,
 * Python, Jupyter, network access, and scientific validity are deliberately
 * outside this audit.
 */
export async function auditStartupEnvironment(): Promise<StartupEnvironmentAudit> {
  if (!isTauri) {
    return {
      desktop: false,
      requiredReady: true,
      workspacePath: null,
      checks: [],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<StartupEnvironmentAudit>("audit_startup_environment");
}

export interface AssetAdmissionRecord {
  assetId: string;
  displayName: string;
  kind: "skill" | "mcp" | "package" | string;
  status: "validated-adapter" | "quarantined" | "rejected" | string;
  releaseEligible: boolean;
  repository: string;
  revision: string;
  licenseSpdx: string;
  licenseCompatible: boolean;
  networkEgress: string;
  execution: string;
  blockers: string[];
}

export interface AssetAdmissionAudit {
  complete: boolean;
  failClosed: boolean;
  schemaVersion: string;
  policyRevision: string;
  totalCount: number;
  admittedCount: number;
  quarantinedCount: number;
  rejectedCount: number;
  assets: AssetAdmissionRecord[];
  errors: string[];
}

export type SkillCandidateReviewAction = "activate" | "reject" | "revoke";

export interface LocalizedCandidateCopy {
  displayName: string;
  description: string;
  licenseNote: string;
  limitations: string[];
  acceptanceChecks: string[];
}

export interface SkillCandidateSummary {
  candidateId: string;
  createdAt: string;
  request: string;
  localized: Record<string, LocalizedCandidateCopy>;
  provider: string;
  model: string;
  licenseSpdx: string;
  licenseNote: string;
  acceptanceChecksSha256: string;
  decisionSha256: string;
  activeTreeSha256: string;
  valid: boolean;
  validationErrors: string[];
  status: string;
  canActivate: boolean;
  canReject: boolean;
  canRevoke: boolean;
  lastAction?: SkillCandidateReviewAction;
  lastActorLabel?: string;
  lastRationale?: string;
  lastTimestamp?: number;
}

export interface SkillCandidateAudit {
  projectAvailable: boolean;
  projectId?: string;
  complete: boolean;
  candidates: SkillCandidateSummary[];
  chainHead?: string;
  integrity: string;
  identityAssurance: string;
  errors: string[];
}

export interface SkillCandidateReviewRequest {
  projectId: string;
  candidateId: string;
  decisionSha256: string;
  acceptanceChecksSha256: string;
  action: SkillCandidateReviewAction;
  actorLabel: string;
  rationale: string;
}

export interface SkillCandidateReviewEvent extends SkillCandidateReviewRequest {
  schemaVersion: number;
  sequence: number;
  reviewId: string;
  activeTreeSha256: string;
  timestamp: number;
  recordPath: string;
  recordSha256: string;
  assurance: string;
  previousHash?: string;
  eventHash: string;
}

export type PreferenceReviewAction = "accept" | "update" | "enable" | "disable" | "delete";

export interface PreferenceEvidenceSummary {
  interactionRef: string;
  observedAt: string;
  summary: string;
}

export interface PreferenceProposalSummary {
  proposalId: string;
  createdAt: string;
  scope: "language" | "presentation" | "workflow" | "audit" | string;
  proposedRule: string;
  evidence: PreferenceEvidenceSummary[];
  counterexamples: string[];
  reviewCondition: string;
  expiresAt?: string;
  proposalSha256: string;
  valid: boolean;
  validationErrors: string[];
  accepted: boolean;
}

export interface AcceptedPreferenceSummary {
  id: string;
  scope: "language" | "presentation" | "workflow" | "audit" | string;
  rule: string;
  sourceProposalSha256: string;
  acceptedAt: number;
  updatedAt: number;
  enabled: boolean;
  reviewCondition: string;
  expiresAt?: string;
}

export interface PreferenceAudit {
  projectAvailable: boolean;
  projectId?: string;
  complete: boolean;
  storeSha256: string;
  proposals: PreferenceProposalSummary[];
  preferences: AcceptedPreferenceSummary[];
  chainHead?: string;
  integrity: string;
  identityAssurance: string;
  errors: string[];
}

export interface PreferenceReviewRequest {
  projectId: string;
  preferenceId: string;
  proposalSha256: string;
  storeSha256: string;
  action: PreferenceReviewAction;
  rule: string;
  actorLabel: string;
  rationale: string;
}

export interface PreferenceReviewEvent extends PreferenceReviewRequest {
  schemaVersion: number;
  sequence: number;
  reviewId: string;
  beforeStoreSha256: string;
  afterStoreSha256: string;
  timestamp: number;
  recordPath: string;
  recordSha256: string;
  assurance: string;
  previousHash?: string;
  eventHash: string;
}

/** Audit the packaged third-party asset registry. Missing or invalid registry
 *  data is returned as a fail-closed audit by the native service. */
export async function auditAssetAdmission(): Promise<AssetAdmissionAudit> {
  if (!isTauri) throw new Error("The packaged admission registry is available only in the desktop app.");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<AssetAdmissionAudit>("audit_asset_admission");
}

/** Independently revalidate current-project Skill candidates and their
 *  app-owned Human review chain. Browser development has no project filesystem. */
export async function auditSkillCandidates(): Promise<SkillCandidateAudit> {
  if (!isTauri) {
    return {
      projectAvailable: false,
      complete: true,
      candidates: [],
      integrity: "not_applicable",
      identityAssurance: "app_owned_local_human_assertion",
      errors: [],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<SkillCandidateAudit>("audit_skill_candidates");
}

/** Record a Human activation/rejection/revocation for exact candidate bytes.
 *  Activation and revocation are performed only by the native app. */
export async function appendSkillCandidateReview(
  request: SkillCandidateReviewRequest,
): Promise<SkillCandidateReviewEvent> {
  if (!isTauri) throw new Error("Skill candidate review is available in the desktop app only.");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<SkillCandidateReviewEvent>("append_skill_candidate_review", { request });
}

/** Read repeated-observation preference proposals and the exact Human-reviewed
 * local preference store for the current project. */
export async function auditLocalPreferences(): Promise<PreferenceAudit> {
  if (!isTauri) {
    return {
      projectAvailable: false,
      complete: true,
      storeSha256: "",
      proposals: [],
      preferences: [],
      integrity: "not_applicable",
      identityAssurance: "app_owned_local_human_assertion",
      errors: [],
    };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<PreferenceAudit>("audit_local_preferences");
}

/** Apply one explicit Human acceptance, edit, state change, or deletion to the
 * exact current proposal and preference-store bytes. */
export async function appendLocalPreferenceReview(
  request: PreferenceReviewRequest,
): Promise<PreferenceReviewEvent> {
  if (!isTauri) throw new Error("Preference review is available in the desktop app only.");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<PreferenceReviewEvent>("append_local_preference_review", { request });
}

/**
 * Per-run password the sidecar requires on every request (desktop only —
 * browser dev talks to a user-run, passwordless `opencode serve`). Held in
 * memory on both sides; never persisted.
 */
export async function runtimePassword(): Promise<string | null> {
  if (!isTauri) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("runtime_password");
}

/**
 * Pick local files via the native dialog and copy them into the agent
 * workspace (desktop only). Returns the workspace file names; [] on cancel.
 */
export async function addFilesToWorkspace(): Promise<string[]> {
  if (!isTauri) return [];
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string[]>("add_files_to_workspace");
}

/**
 * Write text into the workspace as a file (desktop only), deduplicating the
 * name on collision. Returns the actual file name written.
 */
export async function addTextToWorkspace(filename: string, content: string): Promise<string> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("add_text_to_workspace", { filename, content });
}

/**
 * Explicitly import the user's OpenCode CLI login into the app's private
 * runtime (desktop only). Returns false when no CLI login exists; the sidecar
 * is restarted on success.
 */
export async function importOpenCodeLogin(): Promise<boolean> {
  if (!isTauri) return false;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("import_opencode_login");
}

/** How agent actions get approved — the composer's Codex-style switch.
 *  "approve": dangerous shell commands (delete / install / remote / privilege)
 *  and web fetches prompt first. "full": everything in-workspace just runs. */
export type ApprovalMode = "approve" | "full";

/** The approval mode OpenCode's config currently holds ("approve" until changed). */
export async function getApprovalMode(): Promise<ApprovalMode> {
  if (!isTauri) return "approve";
  const { invoke } = await import("@tauri-apps/api/core");
  const mode = await invoke<string>("get_approval_mode");
  return mode === "full" ? "full" : "approve";
}

/** Switch the approval mode; the sidecar restarts — the caller must reconnect. */
export async function setApprovalMode(mode: ApprovalMode): Promise<void> {
  if (!isTauri) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("set_approval_mode", { mode });
}

/** Network proxy for the sidecar: follow the OS, a fixed URL, or direct. */
export type ProxyMode = "system" | "custom" | "none";
export interface ProxySetting {
  mode: ProxyMode;
  /** The custom URL (empty unless mode is "custom"). */
  url: string;
  /** The proxy the sidecar would use right now; null ⇒ direct. */
  effective: string | null;
}

/** The persisted proxy setting (desktop only; null in browser). */
export async function getProxySetting(): Promise<ProxySetting | null> {
  if (!isTauri) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return await invoke<ProxySetting>("get_proxy_setting");
}

/** Persist the proxy setting; the sidecar restarts — the caller must reconnect. */
export async function setProxySetting(mode: ProxyMode, url: string): Promise<void> {
  if (!isTauri) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("set_proxy_setting", { mode, url });
}

/** uv download mirrors used only when provisioning Python tools (empty ⇒ default). */
export interface MirrorSetting {
  /** PyPI index URL (UV_DEFAULT_INDEX). */
  pypi: string;
  /** Python-download mirror (UV_PYTHON_INSTALL_MIRROR). */
  python: string;
}

/** The persisted uv mirrors (desktop only; null in browser). */
export async function getMirrorSetting(): Promise<MirrorSetting | null> {
  if (!isTauri) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return await invoke<MirrorSetting>("get_mirror_setting");
}

/** Persist the uv mirrors; blank fields clear. No sidecar restart. */
export async function setMirrorSetting(pypi: string, python: string): Promise<void> {
  if (!isTauri) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("set_mirror_setting", { pypi, python });
}

/** Remove a provider/mcp entry from the global OpenCode config (restarts the sidecar). */
export async function removeConfigEntry(section: "provider" | "mcp", key: string): Promise<void> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("remove_config_entry", { section, key });
}

export interface JupyterStatus {
  installed: boolean;
  running: boolean;
  url: string | null;
  token: string | null;
  mcp_command: string | null;
}

/** State of the app-managed Jupyter environment (desktop only). */
export async function jupyterStatus(): Promise<JupyterStatus | null> {
  if (!isTauri) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<JupyterStatus>("jupyter_status");
}

/** Provision the isolated Jupyter env via bundled uv (first run: minutes, ~hundreds of MB). */
export async function setupJupyter(): Promise<void> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("setup_jupyter");
}

/** Start the managed headless jupyter-lab (idempotent). */
export async function startJupyter(): Promise<JupyterStatus> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<JupyterStatus>("start_jupyter");
}

/** Open the app-managed JupyterLab in the system browser, starting the server
 *  if needed. Returns false when Jupyter has not been set up yet (the caller
 *  should point the user at Settings). Same env the agent drives, same files.
 *
 *  `notebook` is a path RELATIVE TO THE LAB ROOT (the active workspace) — pass
 *  it to open that file directly (`/lab/tree/<path>`); omit to land on the lab
 *  home. Only pass a path you know is under the workspace root. */
export async function openJupyterLab(notebook?: string): Promise<boolean> {
  if (!isTauri) return false;
  const st = await jupyterStatus();
  if (!st?.installed) return false;
  const s = await startJupyter(); // idempotent; yields the fixed url + token
  if (!s.url || !s.token) return false;
  const rel = notebook?.trim().replace(/^\/+/, "");
  // Encode each segment but keep the "/" separators so nested paths resolve.
  const tree = rel ? "/tree/" + rel.split("/").map(encodeURIComponent).join("/") : "";
  await openExternal(`${s.url}/lab${tree}?token=${encodeURIComponent(s.token)}`);
  return true;
}

/** The interpreter local Python kernels resolve to, and where it came from. */
export interface PythonInterpreter {
  /** The manual override, if one is set (even when it no longer runs). */
  configured: string | null;
  /** What cells would actually run on right now. */
  resolved: string | null;
  source: "manual" | "system" | "jupyter-env" | null;
  error: string | null;
}

export async function pythonInterpreter(): Promise<PythonInterpreter | null> {
  if (!isTauri) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<PythonInterpreter>("python_interpreter");
}

/** Set (empty clears) the manual Python interpreter override. Validated on save. */
export async function setPythonPath(path: string): Promise<void> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("set_python_path", { path });
}

/** One live output line from the Jupyter uv provisioning run. */
export interface SetupProgress {
  task: "jupyter";
  line: string;
}

/** Subscribe to setup progress lines; returns the unlisten function. */
export async function watchSetupProgress(
  cb: (p: SetupProgress) => void,
): Promise<() => void> {
  if (!isTauri) return () => {};
  const { listen } = await import("@tauri-apps/api/event");
  return listen<SetupProgress>("setup-progress", (e) => cb(e.payload));
}

/** Auto-start Jupyter on launch when it was enabled before. Silent no-op otherwise. */
export async function ensureJupyter(): Promise<void> {
  try {
    const s = await jupyterStatus();
    if (s?.installed && !s.running) await startJupyter();
  } catch {
    /* Jupyter is optional — never block the app on it */
  }
}

/** Open an http(s) URL in the system browser (never navigates the webview). */
export async function openExternal(url: string): Promise<void> {
  if (!/^https?:\/\//i.test(url)) return;
  if (isTauri) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("open_url", { url });
    } catch {
      /* opening a link must never break the app */
    }
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

export type SaveResult =
  | { kind: "saved"; path: string }
  | { kind: "canceled" }
  | { kind: "not-desktop" };

/** Save text via the native "Save As" dialog (desktop only). Throws on write failure. */
export async function saveTextFile(filename: string, content: string): Promise<SaveResult> {
  if (!isTauri) return { kind: "not-desktop" };
  const { invoke } = await import("@tauri-apps/api/core");
  const path = await invoke<string | null>("save_text_file", { filename, content });
  return path ? { kind: "saved", path } : { kind: "canceled" };
}

/** The active workspace directory (desktop only; null in browser). */
export async function workspacePath(): Promise<string | null> {
  if (!isTauri) return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<string>("workspace_path");
  } catch {
    return null;
  }
}

/** The base folder new dated workspaces are created under (desktop only). */
export async function workspaceBase(): Promise<string | null> {
  if (!isTauri) return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<string>("workspace_base");
  } catch {
    return null;
  }
}

/** Choose the base folder new session workspaces are created under.
 *  Returns the canonical path. Throws in the browser. */
export async function setWorkspaceBase(path: string): Promise<string> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("set_workspace_base", { path });
}

/** Reveal the base workspace folder in the OS file manager. */
export async function openWorkspaceBase(): Promise<void> {
  if (!isTauri) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("open_workspace_base");
}

/** Switch the active workspace folder (creates it if needed; the runtime
 *  rescopes via `?directory=` — no restart). Returns the canonical path.
 *  Throws in the browser. */
export async function setWorkspace(path: string): Promise<string> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("set_workspace", { path });
}

/** Record which session owns the active workspace (written to
 *  `.openscience/session.txt`) so skill helpers can attribute remote runs. */
export async function markSession(sessionId: string): Promise<void> {
  if (!isTauri) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("mark_session", { sessionId });
}

/** Best-effort local git checkpoint for the active workspace. Returns false
 *  when there were no changes. Never configures a remote or pushes. */
export async function commitWorkspaceSnapshot(message: string): Promise<boolean> {
  if (!isTauri) return false;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("commit_workspace_snapshot", { message });
}

/** Create a new dated folder under the base workspace and switch to it. */
export async function newDatedWorkspace(name: string): Promise<string> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("new_dated_workspace", { name });
}

/** An AI4HEOR project: a named workspace folder under the base dir, marked by
 *  the historical `.openscience/project.json` compatibility path. Sessions
 *  group under it by `directory`. */
export interface ProjectInfo {
  id: string;
  name: string;
  description?: string;
  createdAt: number;
  kind: "heor";
  /** Absolute workspace folder (canonical, matches session `directory`). */
  path: string;
}

/** Create a project folder (with metadata, harness and an initial git
 *  snapshot). Does not switch the active workspace. */
export async function createProject(name: string): Promise<ProjectInfo> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ProjectInfo>("create_project", { name });
}

/** Every project under the base dir, sorted by name. */
export async function listProjects(): Promise<ProjectInfo[]> {
  if (!isTauri) return [];
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ProjectInfo[]>("list_projects");
}

/** Rename a project's display name (the folder never moves). */
export async function renameProject(path: string, name: string): Promise<void> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("rename_project", { path, name });
}

/** Native folder picker; null on cancel or in the browser. */
export async function pickFolder(): Promise<string | null> {
  if (!isTauri) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string | null>("pick_folder");
}

export interface ToolStatus {
  name: string;
  found: boolean;
  version?: string | null;
}

/** Detect scientific/runtime tools on the user's system (desktop only). */
export async function detectTools(): Promise<ToolStatus[]> {
  if (!isTauri) return [];
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ToolStatus[]>("detect_tools");
}

/** Host aliases from the user's ~/.ssh/config (desktop only). */
export async function listSshHosts(): Promise<string[]> {
  if (!isTauri) return [];
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string[]>("list_ssh_hosts");
}

export interface GpuInfo {
  name: string;
  mem_total_mib: number;
  mem_used_mib: number;
  util_pct: number;
}

/** One live SSH probe of a remote machine (capabilities + usage snapshot). */
export interface ComputeProbe {
  reachable: boolean;
  message: string | null;
  os: string | null;
  cores: number | null;
  load1: number | null;
  mem_total_bytes: number | null;
  mem_avail_bytes: number | null;
  disk_total_bytes: number | null;
  disk_free_bytes: number | null;
  gpus: GpuInfo[];
  slurm: string | null;
}

/** Static capability cache the agent reads to pick a machine. */
export interface MachineCaps {
  cores: number | null;
  mem_total_bytes: number | null;
  gpus: string[];
  slurm: string | null;
}

export interface Machine {
  host: string;
  label: string | null;
  caps: MachineCaps | null;
}

/** A Slurm queue entry. */
export interface ComputeJob {
  id: string;
  state: string;
  time: string;
  partition: string;
  name: string;
}

/** Saved remote machines (migrates a legacy hpc.json on first read). */
export async function computeMachines(): Promise<Machine[]> {
  if (!isTauri) return [];
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<Machine[]>("compute_machines");
}

/** Save (or update the label of) a remote machine. */
export async function addComputeMachine(host: string, label?: string): Promise<void> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("add_compute_machine", { host, label: label ?? null });
}

export async function removeComputeMachine(host: string): Promise<void> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("remove_compute_machine", { host });
}

/** Probe a machine over SSH; also caches its static caps for the agent. */
export async function computeProbe(host: string): Promise<ComputeProbe> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ComputeProbe>("compute_probe", { host });
}

/** A Slurm host's queue. */
export async function computeJobs(host: string): Promise<ComputeJob[]> {
  if (!isTauri) return [];
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ComputeJob[]>("compute_jobs", { host });
}

export async function computeCancel(host: string, jobId: string): Promise<void> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("compute_cancel", { host, jobId });
}

export interface ModalStatus {
  installed: boolean;
  version: string | null;
  authenticated: boolean;
  hint: string | null;
}

/** Detect whether the user's Modal CLI is installed and authenticated. */
export async function modalStatus(): Promise<ModalStatus | null> {
  if (!isTauri) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<ModalStatus>("modal_status");
}

/** Copy a bundled example project into the workspace (idempotent; never
 *  overwrites user edits). Returns the workspace directory name. */
export async function installExample(name: string): Promise<string> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("install_example", { name });
}

export interface TeachingExampleOutput {
  path: string;
  sha256: string;
  scenario: "base_case" | "one_way_sensitivity";
  scenarioValue: number | null;
  incrementalCostPerPerson: number;
  incrementalQalysPerPerson: number;
  icerPerQaly: number | null;
  incrementalNetMonetaryBenefitPerPerson: number;
}

export interface TeachingExampleRunResult {
  schema: "ai4heor-teaching-cea-desktop-run/v1";
  runId: string;
  interpreterSource: "manual" | "jupyter-env" | "system";
  expectedResultSha256: string;
  baseCase: TeachingExampleOutput;
  sensitivityLow: TeachingExampleOutput;
  sensitivityHigh: TeachingExampleOutput;
  limitations: string[];
}

/** Run the exact installed synthetic teaching case locally after the auxiliary
 * Human confirmation. No model provider receives project content. */
export async function runHeorTeachingExample(): Promise<TeachingExampleRunResult> {
  if (!isTauri) throw new Error("not running in the desktop app");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<TeachingExampleRunResult>("run_heor_teaching_example", {
    confirmedTeachingAssumptions: true,
  });
}

/** Append a diagnostic line to <app-data>/debug.log (desktop only; no-op in browser). */
export async function logDebug(message: string): Promise<void> {
  if (!isTauri) return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("log_debug", { message });
  } catch {
    /* never let diagnostics break the app */
  }
}

/** True when the current UA is macOS (traffic lights live in the window chrome). */
export function isMacUA(): boolean {
  return typeof navigator !== "undefined" && navigator.userAgent.includes("Mac");
}

/** Whether the macOS traffic lights overlap our content and need a left inset.
 *  Only in the packaged macOS webview (overlay titlebar) AND when not fullscreen
 *  — native fullscreen slides the lights away, so the inset would be an empty
 *  gap (the sidebar/expand buttons floated oddly indented in fullscreen). */
export function trafficLightsPresent(tauri: boolean, mac: boolean, fullscreen: boolean): boolean {
  return tauri && mac && !fullscreen;
}

/** Watch the window's fullscreen state (desktop only). Reports the current
 *  value immediately and on every enter/leave — fullscreen resizes the window,
 *  so a resize listener catches it. Returns an unlisten fn; in a plain browser
 *  it reports `false` once and unlisten is a no-op. */
export async function watchFullscreen(cb: (fullscreen: boolean) => void): Promise<() => void> {
  if (!isTauri) {
    cb(false);
    return () => {};
  }
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  const win = getCurrentWindow();
  const sync = async () => {
    try {
      cb(await win.isFullscreen());
    } catch {
      // Window gone or API unavailable — keep the last known value.
    }
  };
  await sync();
  return win.onResized(() => void sync());
}

/** Write the provider key/model into OpenCode's config via the Rust command. */
export async function configureOpenCode(
  creds: OpenCodeCredentials,
): Promise<ConfigureResult> {
  if (!isTauri) return { ok: false, reason: "not-desktop" };
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const path = await invoke<string>("configure_opencode", {
      provider: creds.provider,
      apiKey: creds.apiKey,
      model: creds.model,
      baseUrl: creds.baseUrl ?? null,
    });
    return { ok: true, path };
  } catch (e) {
    return { ok: false, reason: "error", message: e instanceof Error ? e.message : String(e) };
  }
}

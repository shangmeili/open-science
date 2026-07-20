// Run provenance: turn the agent's experiment executions (bash) into run
// records in `.openscience/runs.jsonl`. Unlike file provenance (which records
// an authored file's text), a *run* is the reproducibility recipe — the
// command, code version, environment, hardware, inputs, and outputs of an
// execution. Pure derivation lives here; the Tauri bridge is separate so this
// can be unit-tested without a desktop shell.
import type { RunArtifact, RunRecord } from "@ai4s/shared";
import type { ToolUpdatedEvent } from "@ai4s/sdk";
import i18n from "@/i18n";
import { isTauri, logDebug } from "./tauri";

/** The compute surface a run targeted. Only "local" runs produce workspace
 *  files we can hash; remote surfaces are recorded honestly with their command
 *  and the submitting machine's env, but their outputs live elsewhere. */
export type RunSurface = "local" | "hpc" | "modal" | "jupyter" | "ssh";

export interface RunInput {
  /** The exact command the agent ran, e.g. "python train.py --lr 3e-4". */
  command: string;
  /** Captured stdout/stderr, when the event carried it. */
  log?: string;
  /** Epoch ms the command started / finished (used to attribute outputs). */
  startedAt?: number;
  endedAt?: number;
  /** Terminal outcome of the command. */
  status: "ok" | "failed";
  /** The compute surface the command targeted. */
  surface: RunSurface;
}

/** Local interpreter/build commands, anchored at a segment head. A conservative
 *  allowlist: recording only what we confidently recognize keeps `runs.jsonl`
 *  meaningful and low-noise (reads/housekeeping are not runs). */
const EXECUTION_HEAD =
  /^(python[0-9.]*|Rscript|julia|matlab|octave|make|snakemake|nextflow|torchrun|mpirun|accelerate|dvc|luigi)\b|^(bash|sh)\s+\S*\.sh\b|^\.?\/\S*\.sh\b/;

// Remote/batch markers, anchored at a segment head (NOT matched inside quoted
// args, so `git commit -m "…sbatch…"` is not mistaken for a run).
const HPC_HEAD = /^(sbatch|srun|salloc|sacct)\b/;
const MODAL_HEAD = /^modal\s+(run|deploy|serve)\b/;
const JUPYTER_HEAD = /^papermill\b|^jupyter\s+.*\bnbconvert\b/;

/** Strip leading `VAR=val` env assignments and `cd X &&/;` hops from a command
 *  segment, exposing the operative command (e.g. `CUDA_VISIBLE_DEVICES=0 cd x
 *  && python …` → `python …`). */
function stripPrefixes(segment: string): string {
  let c = segment.trim();
  const cd = /^cd\s+(?:"[^"]*"|'[^']*'|[^\s&;]+)\s*(?:&&|;)\s*/;
  const env = /^\w+=(?:"[^"]*"|'[^']*'|\S*)\s+/;
  // Launch wrappers are transparent for detection. The original command is
  // still stored verbatim so a later reproduction keeps every flag/redirect.
  const wrap = /^(?:nohup|time|timeout\s+\S+|stdbuf(?:\s+-\S+)+)\s+/;
  let changed = true;
  while (changed) {
    changed = false;
    if (cd.test(c)) {
      c = c.replace(cd, "").trim();
      changed = true;
    }
    if (env.test(c)) {
      c = c.replace(env, "").trim();
      changed = true;
    }
    if (wrap.test(c)) {
      c = c.replace(wrap, "").trim();
      changed = true;
    }
  }
  return c;
}

/** The operative command heads of each `&&`/`;`/`|`-separated segment, with env
 *  and cd prefixes stripped and a leading `ssh <host>` unwrapped to the remote
 *  command. Markers are matched against these, never inside quoted arguments. */
function commandSegments(command: string): string[] {
  return command
    .split(/&&|;|\||\n/)
    .map((seg) => {
      let s = stripPrefixes(seg);
      // `ssh host "sbatch job.sh"` → the remote command is what runs.
      const ssh = s.match(/^ssh\s+\S+\s+(.+)$/);
      if (ssh) s = ssh[1].trim().replace(/^['"]|['"]$/g, "");
      return s;
    })
    .filter(Boolean);
}

/** The compute surface a command targets — remote surfaces are still runs
 *  (recorded honestly), just without locally-captured outputs. */
export function surfaceForCommand(command: string): RunSurface {
  const segs = commandSegments(command);
  if (segs.some((s) => HPC_HEAD.test(s))) return "hpc";
  if (segs.some((s) => MODAL_HEAD.test(s))) return "modal";
  if (segs.some((s) => JUPYTER_HEAD.test(s))) return "jupyter";
  return "local";
}

export function looksLikeExecution(command: string): boolean {
  // A recognized local interpreter/build head in any segment, OR a remote/batch
  // marker at a segment head.
  return commandSegments(command).some((s) => EXECUTION_HEAD.test(s)) || surfaceForCommand(command) !== "local";
}

/**
 * Derive a run record input from a completed tool call, or `null` when the
 * event is not a recordable experiment execution (non-bash, still running,
 * no command, or a read-only/housekeeping command).
 */
export function runInputFromEvent(event: ToolUpdatedEvent): RunInput | null {
  if ((event.tool ?? "").toLowerCase() !== "bash") return null;
  if (event.status !== "success" && event.status !== "failed") return null;
  const command = typeof event.input?.command === "string" ? event.input.command.trim() : "";
  if (!command) return null;
  // Remote runs (HPC/Modal) execute off-box — their env, hardware, and outputs
  // live on the cluster/cloud, invisible here. Recording them from the laptop
  // would stamp the wrong environment, so the remote-compute / modal-run skills
  // record them instead (into .openscience/remote-runs.jsonl) with real remote
  // facts. The passive capture handles local runs only.
  if (surfaceForCommand(command) !== "local") return null;
  if (!looksLikeExecution(command)) return null;
  return {
    command,
    log: event.output,
    startedAt: event.startedAt,
    endedAt: event.endedAt,
    status: event.status === "success" ? "ok" : "failed",
    surface: "local",
  };
}

/** The prompt the Reproduce action drafts for a run — prefilled, reviewed, and
 *  user-sent (human in the loop, never auto-run). Unlike reproducing a file,
 *  this re-runs the recorded COMMAND in the recorded environment and compares
 *  the regenerated OUTPUTS — real reproducibility, not re-authoring source. */
export function reproduceRunPrompt(r: RunRecord): string {
  const env = r.env;
  const hw = env?.hardware;
  const zh = (i18n.resolvedLanguage ?? i18n.language).startsWith("zh");
  const parts: string[] = [];
  if (env) {
    const bits = [
      env.python && `Python ${env.python}`,
      env.platform,
      hw?.gpu?.length ? hw.gpu.join(", ") : hw?.accelerator,
      hw?.cpu,
    ].filter(Boolean);
    if (bits.length) parts.push(zh ? `原运行环境：${bits.join(" · ")}。` : `Original environment: ${bits.join(" · ")}.`);
    if (env.packages)
      parts.push(
        zh
          ? `平台保存了 ${env.packages.count} 个 Python 包的环境快照（编号 ${env.packages.hash}）；如果结果不一致，先对照该快照检查依赖版本。`
          : `AI4HEOR saved an environment snapshot with ${env.packages.count} Python packages (ID ${env.packages.hash}); if the result differs, compare dependency versions with that snapshot.`,
      );
  }
  const code = fileList(r.code ?? []);
  if (code)
    parts.push(
      zh
        ? `相关代码已按文件哈希记录：${code}；再次运行前请确认代码是否发生变化。`
        : `Related code is recorded by file hash: ${code}; check whether it has changed before running again.`,
    );
  const remote = r.surface === "hpc" || r.surface === "modal" || r.surface === "ssh";
  if (remote)
    parts.push(
      zh
        ? `这项分析在${r.surface === "hpc" ? "高性能计算集群" : r.surface === "modal" ? "云计算环境" : "远程计算机"}上运行，输出未保存在本机。`
        : `This analysis ran on ${
            r.surface === "hpc" ? "an HPC cluster" : r.surface === "modal" ? "a cloud environment" : "a remote computer"
          }, so its outputs were not saved on this computer.`,
    );
  const outputs = fileList(r.outputs ?? []);
  if (zh) {
    const compare = outputs
      ? `按相同条件再次运行，并将新结果（${outputs}）与原记录逐项比较；如有差异，请说明差异和可能原因。`
      : remote
        ? "重新提交任务，取回远程输出后与原结果比较。"
        : "按相同条件再次运行并检查结果；本次记录没有可直接比较的输出文件。";
    return (
      `请再次运行分析记录 \`${r.runId}\`。原命令为：\n\n    ${r.command}\n\n` +
      `${parts.join(" ")}${parts.length ? " " : ""}${compare}`
    );
  }

  const compare = outputs
    ? `run it again under the same conditions, then compare the new outputs (${outputs}) with the recorded outputs and explain any differences.`
    : remote
      ? "submit it again, retrieve the remote outputs, and compare them with the original results."
      : "run it again under the same conditions and check the result; this record has no output files available for direct comparison.";
  return (
    `Run analysis record \`${r.runId}\` again. The original command was:\n\n    ${r.command}\n\n` +
    `${parts.join(" ")}${parts.length ? " " : ""}${compare}`
  );
}

/** "a, b, c (+N more)" for a capped list of run files, or "" when empty. */
function fileList(files: RunArtifact[], cap = 6): string {
  if (files.length === 0) return "";
  const shown = files.slice(0, cap).map((f) => `\`${f.path}\``);
  const more = files.length > cap ? ` (+${files.length - cap} more)` : "";
  return shown.join(", ") + more;
}

/** Append a run record (desktop only). Recording must never break the chat flow. */
export async function recordRun(
  input: RunInput,
  sessionId: string | undefined,
  model: string | null,
): Promise<void> {
  if (!isTauri) return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("record_run", {
      command: input.command,
      log: input.log ?? null,
      startedAt: input.startedAt ?? null,
      endedAt: input.endedAt ?? null,
      status: input.status,
      surface: input.surface,
      sessionId: sessionId ?? null,
      model: model ?? null,
    });
    void logDebug(`run ✓ ${input.command.slice(0, 60)}`);
  } catch (e) {
    void logDebug(`run FAILED for ${input.command.slice(0, 60)}: ${e instanceof Error ? e.message : String(e)}`);
  }
}

/** All recorded runs, newest first ([] in browser dev). */
export async function listRuns(): Promise<RunRecord[]> {
  if (!isTauri) return [];
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<RunRecord[]>("list_runs", {});
  } catch {
    return [];
  }
}

/** A keyset-paginated, faceted query over the runs index. */
export interface RunQuery {
  search?: string;
  status?: string;
  surface?: string;
  sessionId?: string;
  /** Time filter: only runs at or after this epoch-seconds instant. */
  sinceTs?: number;
  /** Keyset cursor from a previous page's `next`. */
  beforeTs?: number;
  beforeRowid?: number;
  limit?: number;
}

export interface RunFacet {
  value: string;
  count: number;
}

export interface RunPage {
  rows: RunRecord[];
  /** Total matching the full filter (for the header count). */
  total: number;
  facets: { status: RunFacet[]; surface: RunFacet[] };
  /** Cursor for the next (older) page; absent at the end. */
  next?: { ts: number; rowid: number };
}

const EMPTY_PAGE: RunPage = { rows: [], total: 0, facets: { status: [], surface: [] } };

/** Query the runs index (indexed, paginated, faceted). Empty page in browser dev. */
export async function queryRuns(query: RunQuery): Promise<RunPage> {
  if (!isTauri) return EMPTY_PAGE;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<RunPage>("query_runs_cmd", { query });
  } catch {
    return EMPTY_PAGE;
  }
}

/** A run's captured stdout/stderr by its log hash (null if unreadable). */
export async function readRunLog(hash: string): Promise<string | null> {
  if (!isTauri) return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<string>("read_run_log", { hash });
  } catch {
    return null;
  }
}

// App-lifetime owner of the long-running uv provisioning flows (isolated
// Jupyter env). This state lived inside SettingsPage
// before, so navigating away — clicking a chat or a history session —
// unmounted the page, discarded the "setting up…" flags, and (worse) severed
// the setup-progress listener, making a still-running download look frozen and
// inviting a second click that collided on the same env dir. Owning it here
// means the download is unaffected by which page is open.
import { create } from "zustand";
import { getClient, useRuntimeStore } from "./runtime";
import {
  agentBrowserBin,
  detectChrome,
  getProxySetting,
  removeConfigEntry,
  setupJupyter,
  startJupyter,
  watchSetupProgress,
} from "./tauri";
import { BROWSER_MCP_ID, buildBrowserMcpConfig } from "./browser";
import { toast } from "./toast";
import i18n from "../i18n";

interface SetupState {
  /** True while the isolated Jupyter env is being provisioned. */
  jupyterBusy: boolean;
  browserBusy: boolean;
  /** Latest live uv output line — reassurance during a hundreds-of-MB download. */
  line: string | null;
  /** Bumped when any provisioning run finishes, so open pages re-read status. */
  generation: number;
  installManagedPython: () => Promise<void>;
  enableJupyter: () => Promise<void>;
  enableBrowser: (opts: EnableBrowserOptions) => Promise<void>;
}

export interface EnableBrowserOptions {
  profileDir?: string;
  headed?: boolean;
  tools?: string;
  allowedDomains?: string[];
  useSystemChrome?: boolean;
}

export const useSetupStore = create<SetupState>((set, get) => ({
  jupyterBusy: false,
  browserBusy: false,
  line: null,
  generation: 0,

  installManagedPython: async () => {
    if (get().jupyterBusy) return;
    set({ jupyterBusy: true, line: null });
    try {
      toast.success(i18n.t("settings:python.installStarting"));
      await setupJupyter();
      toast.success(i18n.t("settings:python.installComplete"));
    } catch (e) {
      toast.error(
        `${i18n.t("settings:python.installFailed")}: ${e instanceof Error ? e.message : String(e)}`,
      );
    } finally {
      set((st) => ({ jupyterBusy: false, line: null, generation: st.generation + 1 }));
    }
  },

  enableJupyter: async () => {
    // One provisioning run at a time: a second `uv venv` / `pip install` into
    // the same env dir races the first and fails.
    if (get().jupyterBusy) return;
    set({ jupyterBusy: true, line: null });
    try {
      toast.success(i18n.t("settings:mcp.setupStarting"));
      await setupJupyter();
      const s = await startJupyter();
      if (!s.url || !s.token || !s.mcp_command) {
        throw new Error(i18n.t("settings:mcp.setupIncomplete"));
      }
      await getClient()!.addMcpServer("jupyter", {
        type: "local",
        command: [s.mcp_command],
        enabled: true,
        environment: { JUPYTER_URL: s.url, JUPYTER_TOKEN: s.token, ALLOW_IMG_OUTPUT: "true" },
      });
      toast.success(i18n.t("settings:mcp.setupComplete"));
      await useRuntimeStore.getState().loadCatalog();
    } catch (e) {
      toast.error(
        `${i18n.t("settings:mcp.setupFailed")}: ${e instanceof Error ? e.message : String(e)}`,
      );
    } finally {
      set((st) => ({ jupyterBusy: false, line: null, generation: st.generation + 1 }));
    }
  },

  enableBrowser: async (opts) => {
    if (get().browserBusy) return;
    set({ browserBusy: true, line: null });
    try {
      const bin = await agentBrowserBin();
      const chrome = opts.useSystemChrome === false ? null : await detectChrome();
      const proxy = (await getProxySetting())?.effective ?? null;
      const config = buildBrowserMcpConfig({
        bin,
        profileDir: opts.profileDir,
        executablePath: chrome?.path,
        headed: opts.headed,
        proxy,
        tools: opts.tools,
        allowedDomains: opts.allowedDomains,
      });
      const hadEntry = await removeConfigEntry("mcp", BROWSER_MCP_ID)
        .then(() => true)
        .catch(() => false);
      if (hadEntry) await useRuntimeStore.getState().connectRetry();
      await getClient()!.addMcpServer(BROWSER_MCP_ID, config);
      toast.success(i18n.t("settings:browser.enabledStatus"));
      await useRuntimeStore.getState().loadCatalog();
    } catch (e) {
      toast.error(
        `${i18n.t("settings:browser.label")}: ${e instanceof Error ? e.message : String(e)}`,
      );
    } finally {
      set((st) => ({ browserBusy: false, line: null, generation: st.generation + 1 }));
    }
  },

}));

// A SINGLE app-lifetime uv-progress listener. Registered once from AppShell so
// a page unmount can never sever it — the old per-page listener died with
// SettingsPage and made a running download look frozen.
let progressUnlisten: (() => void) | null = null;

/** Start the shared uv-progress listener (idempotent). Call once from AppShell. */
export function ensureSetupProgressListener(): void {
  if (progressUnlisten) return;
  progressUnlisten = () => {}; // claim the slot synchronously against a double call
  void watchSetupProgress((p) => useSetupStore.setState({ line: p.line })).then((u) => {
    progressUnlisten = u;
  });
}

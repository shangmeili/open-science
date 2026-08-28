import { useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { McpServer } from "@ai4s/sdk";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Row, Section, Switch } from "./Section";
import { selectCls } from "./inputCls";
import { getClient, useRuntimeStore } from "@/lib/runtime";
import { useSetupStore } from "@/lib/setup";
import {
  agentBrowserProfiles,
  detectChrome,
  removeConfigEntry,
  setupBrowserChrome,
  type BrowserProfile,
  type ChromeInfo,
} from "@/lib/tauri";
import {
  BROWSER_DISPLAY_NAMES,
  BROWSER_MCP_ID,
  PRIVATE_BROWSER,
} from "@/lib/browser";
import { cn } from "@/lib/cn";
import { toast } from "@/lib/toast";
import { sameLocalPath } from "@/lib/localPath";

export function BrowserSettingsCard({ connected }: { connected: boolean }) {
  const { t } = useTranslation(["settings", "common"]);
  const generation = useSetupStore((s) => s.generation);
  const browserBusy = useSetupStore((s) => s.browserBusy);
  const setupLine = useSetupStore((s) => s.line);
  const [profiles, setProfiles] = useState<BrowserProfile[]>([]);
  const [chrome, setChrome] = useState<ChromeInfo | null>(null);
  const [servers, setServers] = useState<McpServer[]>([]);
  const [profile, setProfile] = useState("");
  const [headed, setHeaded] = useState(false);
  const [tools, setTools] = useState("core");
  const [domains, setDomains] = useState("");
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [confirmHeadedOff, setConfirmHeadedOff] = useState(false);

  useEffect(() => {
    if (!connected) return;
    void Promise.all([
      agentBrowserProfiles(),
      detectChrome(),
      getClient()?.listMcpServers().catch(() => []) ?? Promise.resolve([]),
    ]).then(([nextProfiles, nextChrome, nextServers]) => {
      setProfiles(nextProfiles);
      setChrome(nextChrome);
      setServers(nextServers);
      if (!nextChrome) setProfile((current) => current || PRIVATE_BROWSER);
    });
  }, [connected, generation]);

  const server = servers.find((entry) => entry.name === BROWSER_MCP_ID) ?? null;
  const enabled = server !== null;
  const configSignature = JSON.stringify(server?.config ?? null);
  useEffect(() => {
    const config = server?.config;
    if (!config || config.type !== "local") return;
    const environment = config.environment ?? {};
    setProfile(
      environment.AGENT_BROWSER_EXECUTABLE_PATH
        ? (environment.AGENT_BROWSER_PROFILE ?? "")
        : PRIVATE_BROWSER,
    );
    setHeaded(environment.AGENT_BROWSER_HEADED === "true");
    setDomains(
      (environment.AGENT_BROWSER_ALLOWED_DOMAINS ?? "")
        .split(",")
        .map((domain) => domain.trim())
        .filter(Boolean)
        .join("\n"),
    );
    const toolsIndex = config.command.indexOf("--tools");
    setTools(toolsIndex >= 0 && config.command[toolsIndex + 1] ? config.command[toolsIndex + 1] : "core");
    // configSignature deliberately captures nested MCP config changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configSignature]);

  const apply = () => {
    const useSystemChrome = profile !== PRIVATE_BROWSER;
    void useSetupStore.getState().enableBrowser({
      profileDir: useSystemChrome && profile ? profile : undefined,
      headed,
      tools,
      useSystemChrome,
      allowedDomains: domains
        .split(/[\n,]/)
        .map((domain) => domain.trim())
        .filter(Boolean),
    });
  };

  const disable = async () => {
    try {
      await removeConfigEntry("mcp", BROWSER_MCP_ID);
      await useRuntimeStore.getState().connectRetry();
      setServers((current) => current.filter((entry) => entry.name !== BROWSER_MCP_ID));
      toast.success(t("toast.mcpRemoved", { name: t("browser.label") }));
    } catch (error) {
      toast.error(`${t("toast.couldNotRemoveMcp")}: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const download = async () => {
    setDownloadBusy(true);
    try {
      await setupBrowserChrome();
      setChrome(await detectChrome());
      toast.success(t("browser.downloaded"));
    } catch (error) {
      toast.error(`${t("browser.couldNotDownload")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setDownloadBusy(false);
    }
  };

  return (
    <Section title={t("browser.title")} hint={t("browser.hint")} flush>
      {!connected ? (
        <p className="px-4 py-3 text-[13px] text-muted">{t("mcp.connectPrompt")}</p>
      ) : (
        <div className="divide-y divide-faint">
          <Row
            title={t("browser.browseAs")}
            hint={
              <>
                {profile === PRIVATE_BROWSER
                  ? t("browser.privateNote")
                  : profile
                    ? t("browser.reuseNote", {
                        name: profiles.find((item) => sameLocalPath(item.directory, profile))?.name ?? profile,
                      })
                    : t("browser.isolatedNote")}
                <span className="mt-1 block">
                  {chrome
                    ? `${t("browser.detected")}: ${BROWSER_DISPLAY_NAMES[chrome.kind] ?? chrome.kind}`
                    : t("browser.noChromeWillDownload")}
                </span>
              </>
            }
          >
            <div className="mt-2.5 flex flex-col gap-2 sm:flex-row">
              <select
                value={profile}
                onChange={(event) => setProfile(event.target.value)}
                aria-label={t("browser.browseAs")}
                className={selectCls("min-w-0 flex-1")}
              >
                {chrome && <option value="">{t("browser.isolated")}</option>}
                {chrome && profiles.map((item) => (
                  <option key={item.directory} value={item.directory}>
                    {item.name} · {item.directory}
                  </option>
                ))}
                <option value={PRIVATE_BROWSER}>{t("browser.privateBrowser")}</option>
              </select>
              {profile === PRIVATE_BROWSER && (
                <button
                  className={buttonGhost}
                  onClick={() => void download()}
                  disabled={downloadBusy || browserBusy}
                >
                  {downloadBusy ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                  {t("browser.download")}
                </button>
              )}
            </div>
          </Row>

          <Row title={t("browser.capabilities")}>
            <select
              value={tools}
              onChange={(event) => setTools(event.target.value)}
              aria-label={t("browser.capabilities")}
              className={selectCls("mt-2.5 w-full")}
            >
              <option value="core">{t("browser.capCore")}</option>
              <option value="core,network">{t("browser.capNetwork")}</option>
              <option value="all">{t("browser.capAll")}</option>
            </select>
          </Row>

          <Row title={t("browser.allowedDomains")} hint={t("browser.allowedDomainsHint")}>
            <textarea
              value={domains}
              onChange={(event) => setDomains(event.target.value)}
              rows={3}
              placeholder={t("browser.allowedDomainsPlaceholder")}
              aria-label={t("browser.allowedDomains")}
              className="mt-2.5 w-full rounded-input border border-transparent bg-surface-2 px-3 py-2 font-mono text-[12px] text-text outline-none placeholder:text-muted/50 focus:border-accent/55 focus:bg-surface"
            />
          </Row>

          <Row
            title={t("browser.showWindow")}
            control={
              <Switch
                checked={headed}
                onChange={(next) => {
                  const reusesLogin = profile !== PRIVATE_BROWSER && profile.trim() !== "";
                  if (!next && reusesLogin) setConfirmHeadedOff(true);
                  else setHeaded(next);
                }}
                label={t("browser.showWindow")}
              />
            }
          />

          <div className="flex flex-wrap items-center gap-2 px-4 py-3">
            <span className={cn("inline-flex items-center gap-1.5 text-xs", enabled ? "text-ok" : "text-muted")}>
              <span className={cn("h-1.5 w-1.5 rounded-full", enabled ? "bg-ok" : "bg-muted")} />
              {enabled ? t("browser.enabledStatus") : t("browser.disabledStatus")}
            </span>
            {browserBusy && setupLine && (
              <span className="inline-flex min-w-0 items-center gap-1.5 text-muted">
                <Loader2 size={11} className="shrink-0 animate-spin" />
                <span className="truncate font-mono text-[11px]">{setupLine}</span>
              </span>
            )}
            <div className="flex-1" />
            {enabled && (
              <button className={buttonGhost} onClick={() => void disable()} disabled={browserBusy}>
                {t("browser.disable")}
              </button>
            )}
            <button className={buttonAccent} onClick={apply} disabled={browserBusy || downloadBusy}>
              {browserBusy ? (
                <><Loader2 size={12} className="animate-spin" /> {t("mcp.settingUp")}</>
              ) : enabled ? t("browser.apply") : t("mcp.enable")}
            </button>
          </div>
        </div>
      )}

      {confirmHeadedOff && (
        <ConfirmDialog
          title={t("browser.headedOffTitle")}
          body={t("browser.headedOffBody", {
            profile: profiles.find((item) => sameLocalPath(item.directory, profile))?.name ?? profile,
          })}
          confirmLabel={t("browser.headedOffConfirm")}
          onConfirm={() => {
            setHeaded(false);
            setConfirmHeadedOff(false);
          }}
          onCancel={() => setConfirmHeadedOff(false)}
        />
      )}
    </Section>
  );
}

const buttonGhost = cn(
  "flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-input border border-border bg-surface px-3.5",
  "text-[13px] text-text transition-colors hover:bg-surface-2 disabled:text-muted",
);

const buttonAccent = cn(
  "flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-input bg-accent px-3.5 text-[13px] font-medium",
  "text-accent-fg transition-colors hover:bg-accent/90 disabled:bg-accent/50",
);

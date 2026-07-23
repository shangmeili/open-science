import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation } from "react-router-dom";
import { PanelLeft } from "lucide-react";
import { cn } from "@/lib/cn";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { CommandPalette } from "@/components/command-palette/CommandPalette";
import { Toaster } from "@/components/ui/Toaster";
import { useRuntimeStore } from "@/lib/runtime";
import { ensureSetupProgressListener } from "@/lib/setup";
import { useOverlayTitlebar, useUiStore } from "@/lib/store";
import { ensureJupyter, isTauri, openExternal, watchFullscreen } from "@/lib/tauri";
import { useUpdateStore } from "@/lib/update";

export function AppShell() {
  const { t } = useTranslation("nav");
  const { sidebarCollapsed, setSidebarCollapsed } = useUiStore();

  // Cmd/Ctrl+B toggles the sidebar, matching the button's tooltip.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        useUiStore.getState().toggleSidebar();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  // In the packaged desktop app, auto-start the bundled OpenCode and connect,
  // and bring the Jupyter server back up if the user enabled it before.
  useEffect(() => {
    void useRuntimeStore.getState().bootstrap();
    void ensureJupyter();
    // One app-lifetime listener for uv provisioning progress, so a running
    // download's live output survives navigating between pages.
    ensureSetupProgressListener();
    if (!import.meta.env.TEST) {
      void useUpdateStore.getState().maybeAutoCheck();
    }
  }, []);

  // Track native fullscreen: macOS hides the traffic lights there, so headers
  // must drop their traffic-light inset (see useOverlayTitlebar).
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let cancelled = false;
    void watchFullscreen((fs) => useUiStore.getState().setIsFullscreen(fs)).then((u) => {
      if (cancelled) u();
      else unlisten = u;
    });
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  // External links open in the system browser. Navigating the webview away
  // from the app would strand the user — there is no back button.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const anchor = (e.target as HTMLElement).closest?.("a[href]");
      const href = anchor?.getAttribute("href") ?? "";
      if (/^https?:\/\//i.test(href)) {
        e.preventDefault();
        void openExternal(href);
      }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  // The packaged app is a desktop workspace, not a web page. Suppress the
  // host webview's Back/Reload/Open Link menu everywhere; component-owned
  // Radix menus still receive the event and provide the app's real actions.
  useEffect(() => {
    if (!isTauri) return;
    const onContextMenu = (event: MouseEvent) => event.preventDefault();
    document.addEventListener("contextmenu", onContextMenu);
    return () => document.removeEventListener("contextmenu", onContextMenu);
  }, []);

  // The live session page's own header doubles as the titlebar when the
  // sidebar is collapsed; every other route gets this fallback strip so the
  // macOS traffic lights don't overlap content, the window stays draggable,
  // and the sidebar can be re-expanded.
  const isMac = navigator.userAgent.includes("Mac");
  const overlayTitlebar = useOverlayTitlebar();
  const pathname = useLocation().pathname;
  const pageOwnsTitlebar = pathname.startsWith("/live") || pathname.startsWith("/heor");

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg text-text">
      <a
        href="#ai4heor-main"
        className="fixed left-3 top-3 z-[100] -translate-y-24 rounded-input bg-text px-3 py-2 text-sm font-medium text-bg shadow-card transition-transform focus:translate-y-0"
      >
        {t("accessibility.skipToMain")}
      </a>
      <Sidebar />
      <main id="ai4heor-main" tabIndex={-1} className="flex min-w-0 flex-1 flex-col">
        {sidebarCollapsed && !pageOwnsTitlebar && (
          <div
            data-tauri-drag-region={overlayTitlebar || undefined}
            className={cn(
              "flex h-12 shrink-0 items-center",
              overlayTitlebar ? "pl-[78px]" : "pl-2",
            )}
          >
            <button
              onClick={() => setSidebarCollapsed(false)}
              aria-label={t("sidebar.expand")}
              title={t("sidebar.expandTitle", { shortcut: isMac ? "⌘B" : "Ctrl+B" })}
              className="fade-in rounded p-1 text-text hover:bg-surface-2"
            >
              <PanelLeft size={14} strokeWidth={1.5} />
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1">
          <Outlet />
        </div>
      </main>
      <CommandPalette />
      <Toaster />
    </div>
  );
}

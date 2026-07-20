import { create } from "zustand";
import { detectInitialLocale, LOCALE_KEY } from "@/i18n/config";
import { isMacUA, isTauri, trafficLightsPresent } from "./tauri";

export type Theme = "light" | "dark";

const THEME_KEY = "ai4s.theme";
const SIDEBAR_WIDTH_KEY = "ai4s.sidebar.width";
const SIDEBAR_COLLAPSED_KEY = "ai4s.sidebar.collapsed";
const INSPECTOR_WIDTH_KEY = "ai4s.inspector.width";

export const SIDEBAR_MIN = 184;
export const SIDEBAR_MAX = 340;
export const SIDEBAR_DEFAULT = 232;

export const INSPECTOR_MIN = 360;
export const INSPECTOR_MAX = 960;
export const INSPECTOR_DEFAULT = 560;

function initialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const saved = window.localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") return saved;
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  return prefersDark ? "dark" : "light";
}

function initialSidebarWidth(): number {
  if (typeof window === "undefined") return SIDEBAR_DEFAULT;
  const saved = Number(window.localStorage.getItem(SIDEBAR_WIDTH_KEY));
  if (!Number.isFinite(saved) || saved === 0) return SIDEBAR_DEFAULT;
  return Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, saved));
}

function initialInspectorWidth(): number {
  if (typeof window === "undefined") return INSPECTOR_DEFAULT;
  const saved = Number(window.localStorage.getItem(INSPECTOR_WIDTH_KEY));
  if (!Number.isFinite(saved) || saved === 0) return INSPECTOR_DEFAULT;
  return Math.min(INSPECTOR_MAX, Math.max(INSPECTOR_MIN, saved));
}

interface UiState {
  theme: Theme;
  /** Active UI locale (BCP-47). Persisted; mirrors the `theme` pattern. */
  locale: string;
  inspectorOpen: boolean;
  /** Right-pane width in px (persisted); the pane can also be maximized to
   *  cover the whole window (session-ephemeral, reset when the pane closes). */
  inspectorWidth: number;
  inspectorMaximized: boolean;
  sidebarCollapsed: boolean;
  sidebarWidth: number;
  /** macOS native fullscreen: the traffic lights slide away, so headers must
   *  drop their traffic-light inset. Synced from the Tauri window in AppShell. */
  isFullscreen: boolean;
  paletteOpen: boolean;
  /** One-shot text placed into the composer by another surface (e.g. the
   *  provenance Reproduce action) — consumed on the next composer render. */
  composerDraft: string | null;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  setLocale: (locale: string) => void;
  setInspectorOpen: (open: boolean) => void;
  setInspectorWidth: (width: number) => void;
  setInspectorMaximized: (maximized: boolean) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setSidebarWidth: (width: number) => void;
  setIsFullscreen: (fullscreen: boolean) => void;
  setPaletteOpen: (open: boolean) => void;
  setComposerDraft: (draft: string | null) => void;
}

export const useUiStore = create<UiState>((set, get) => ({
  theme: initialTheme(),
  locale: detectInitialLocale(),
  inspectorOpen: true,
  sidebarCollapsed:
    typeof window !== "undefined" && window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1",
  sidebarWidth: initialSidebarWidth(),
  isFullscreen: false,
  paletteOpen: false,
  setTheme: (theme) => {
    if (typeof window !== "undefined") window.localStorage.setItem(THEME_KEY, theme);
    set({ theme });
  },
  toggleTheme: () => get().setTheme(get().theme === "light" ? "dark" : "light"),
  setLocale: (locale) => {
    if (typeof window !== "undefined") window.localStorage.setItem(LOCALE_KEY, locale);
    set({ locale });
  },
  setInspectorOpen: (inspectorOpen) => set({ inspectorOpen }),
  inspectorWidth: initialInspectorWidth(),
  inspectorMaximized: false,
  setInspectorWidth: (width) => {
    const inspectorWidth = Math.min(INSPECTOR_MAX, Math.max(INSPECTOR_MIN, Math.round(width)));
    if (typeof window !== "undefined")
      window.localStorage.setItem(INSPECTOR_WIDTH_KEY, String(inspectorWidth));
    set({ inspectorWidth });
  },
  setInspectorMaximized: (inspectorMaximized) => set({ inspectorMaximized }),
  setSidebarCollapsed: (sidebarCollapsed) => {
    if (typeof window !== "undefined")
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed ? "1" : "0");
    set({ sidebarCollapsed });
  },
  toggleSidebar: () => get().setSidebarCollapsed(!get().sidebarCollapsed),
  setIsFullscreen: (isFullscreen) => set({ isFullscreen }),
  setSidebarWidth: (width) => {
    const sidebarWidth = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, Math.round(width)));
    if (typeof window !== "undefined")
      window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth));
    set({ sidebarWidth });
  },
  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
  composerDraft: null,
  setComposerDraft: (composerDraft) => set({ composerDraft }),
}));

/** Whether headers should inset for the macOS overlay-titlebar traffic lights.
 *  False in a browser, on non-mac, and in fullscreen (the lights hide). The one
 *  source of truth for every titlebar/header that clears the lights. */
export function useOverlayTitlebar(): boolean {
  const isFullscreen = useUiStore((s) => s.isFullscreen);
  return trafficLightsPresent(isTauri, isMacUA(), isFullscreen);
}

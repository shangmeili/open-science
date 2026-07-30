import { create } from "zustand";
import { detectInitialLocale, LOCALE_KEY } from "@/i18n/config";
import { isMacUA, isTauri, trafficLightsPresent } from "./tauri";

export type Theme = "light" | "warm" | "dark";

export const THEMES: readonly Theme[] = ["light", "warm", "dark"];

export interface ComposerSkillSelection {
  id: string;
  label: string;
}

export type ComposerDraftMode = "append" | "replace";
export const REPLACE_COMPOSER_DRAFT: ComposerDraftMode = "replace";

const THEME_KEY = "ai4s.theme.v2";
const LEGACY_THEME_KEY = "ai4s.theme";
const SIDEBAR_WIDTH_KEY = "ai4s.sidebar.width";
const SIDEBAR_COLLAPSED_KEY = "ai4s.sidebar.collapsed";
const INSPECTOR_WIDTH_KEY = "ai4s.inspector.width";
const ZOOM_KEY = "ai4s.zoom";
const TASK_PROJECT_PLACEMENT_KEY = "ai4s.taskProjectPlacement";

export const ZOOM_MIN = 0.5;
export const ZOOM_MAX = 3;
export const ZOOM_STEP = 0.1;

export const SIDEBAR_MIN = 184;
export const SIDEBAR_MAX = 340;
export const SIDEBAR_DEFAULT = 232;

export const INSPECTOR_MIN = 360;
export const INSPECTOR_MAX = 960;
export const INSPECTOR_DEFAULT = 560;

function initialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const saved = window.localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "warm" || saved === "dark") return saved;
  const legacy = window.localStorage.getItem(LEGACY_THEME_KEY);
  if (legacy === "dark") return "dark";
  if (legacy === "light") return "warm";
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  return prefersDark ? "dark" : "light";
}

function clampZoom(value: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(value * 100) / 100));
}

function initialZoom(): number {
  if (typeof window === "undefined") return 1;
  const saved = Number(window.localStorage.getItem(ZOOM_KEY));
  if (!Number.isFinite(saved) || saved <= 0) return 1;
  return clampZoom(saved);
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

export type TaskProjectPlacement = Record<string, string | null>;

function initialTaskProjectPlacement(): TaskProjectPlacement {
  if (typeof window === "undefined") return {};
  try {
    const parsed = JSON.parse(
      window.localStorage.getItem(TASK_PROJECT_PLACEMENT_KEY) ?? "{}",
    );
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]) =>
        typeof value === "string" || value === null,
      ),
    ) as TaskProjectPlacement;
  } catch {
    return {};
  }
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
  zoom: number;
  /** One-shot text placed into the composer by another surface (e.g. the
   *  provenance Reproduce action) — consumed on the next composer render. */
  composerDraft: string | null;
  /** Prepared task starters replace one another; provenance and review
   *  follow-ups keep the historical append behavior. */
  composerDraftMode: ComposerDraftMode;
  /** One-shot Skill selection prepared by the capability catalog. The
   *  composer renders the localized label while keeping the runtime id out of
   *  the editable research request. */
  composerSkill: ComposerSkillSelection | null;
  /** Explicit sidebar project placement. null means deliberately standalone;
   *  absence falls back to the session's original workspace directory. */
  taskProjectPlacement: TaskProjectPlacement;
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
  setZoom: (zoom: number) => void;
  zoomBy: (steps: number) => void;
  resetZoom: () => void;
  setComposerDraft: (draft: string | null, mode?: ComposerDraftMode) => void;
  setComposerSkill: (skill: ComposerSkillSelection | null) => void;
  moveTaskToProject: (taskId: string, projectId: string | null) => void;
  forgetTaskProjectPlacement: (taskId: string) => void;
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
  zoom: initialZoom(),
  setTheme: (theme) => {
    if (typeof window !== "undefined") window.localStorage.setItem(THEME_KEY, theme);
    set({ theme });
  },
  toggleTheme: () => get().setTheme(THEMES[(THEMES.indexOf(get().theme) + 1) % THEMES.length]),
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
  setZoom: (value) => {
    const zoom = clampZoom(value);
    if (typeof window !== "undefined") window.localStorage.setItem(ZOOM_KEY, String(zoom));
    set({ zoom });
  },
  zoomBy: (steps) => get().setZoom(get().zoom + steps * ZOOM_STEP),
  resetZoom: () => get().setZoom(1),
  composerDraft: null,
  composerDraftMode: "append",
  setComposerDraft: (composerDraft, composerDraftMode = "append") =>
    set({ composerDraft, composerDraftMode }),
  composerSkill: null,
  setComposerSkill: (composerSkill) => set({ composerSkill }),
  taskProjectPlacement: initialTaskProjectPlacement(),
  moveTaskToProject: (taskId, projectId) => {
    const taskProjectPlacement = { ...get().taskProjectPlacement, [taskId]: projectId };
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        TASK_PROJECT_PLACEMENT_KEY,
        JSON.stringify(taskProjectPlacement),
      );
    }
    set({ taskProjectPlacement });
  },
  forgetTaskProjectPlacement: (taskId) => {
    const taskProjectPlacement = { ...get().taskProjectPlacement };
    if (!Object.prototype.hasOwnProperty.call(taskProjectPlacement, taskId)) return;
    delete taskProjectPlacement[taskId];
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        TASK_PROJECT_PLACEMENT_KEY,
        JSON.stringify(taskProjectPlacement),
      );
    }
    set({ taskProjectPlacement });
  },
}));

/** Whether headers should inset for the macOS overlay-titlebar traffic lights.
 *  False in a browser, on non-mac, and in fullscreen (the lights hide). The one
 *  source of truth for every titlebar/header that clears the lights. */
export function useOverlayTitlebar(): boolean {
  const isFullscreen = useUiStore((s) => s.isFullscreen);
  return trafficLightsPresent(isTauri, isMacUA(), isFullscreen);
}

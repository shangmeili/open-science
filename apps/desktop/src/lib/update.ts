import { create } from "zustand";

const CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;
export const UPDATE_SOURCE_CONFIGURED = false;

export interface UpdateInfo {
  version: string;
  url: string;
  name: string | null;
  publishedAt: string | null;
}

type CheckStatus = "idle" | "checking" | "ready" | "error" | "unavailable";

interface UpdateState {
  sourceConfigured: boolean;
  enabled: boolean;
  badgeEnabled: boolean;
  dismissedVersion: string | null;
  lastCheckedAt: number | null;
  latest: UpdateInfo | null;
  status: CheckStatus;
  error: string | null;
  currentVersion: string;
  hasUpdate: boolean;
  showBadge: boolean;
  setEnabled: (enabled: boolean) => void;
  setBadgeEnabled: (enabled: boolean) => void;
  dismissBadge: () => void;
  check: (opts?: { manual?: boolean; now?: number }) => Promise<void>;
  maybeAutoCheck: () => Promise<void>;
}

export function normalizeVersion(version: string): string {
  return version.trim().replace(/^v/i, "").split(/[+-]/)[0] ?? "";
}

export function compareVersions(a: string, b: string): number {
  const pa = normalizeVersion(a).split(".").map((x) => Number.parseInt(x, 10));
  const pb = normalizeVersion(b).split(".").map((x) => Number.parseInt(x, 10));
  for (let i = 0; i < Math.max(pa.length, pb.length, 3); i++) {
    const da = Number.isFinite(pa[i]) ? pa[i] : 0;
    const db = Number.isFinite(pb[i]) ? pb[i] : 0;
    if (da > db) return 1;
    if (da < db) return -1;
  }
  return 0;
}

export function isNewerVersion(candidate: string, current: string): boolean {
  return compareVersions(candidate, current) > 0;
}

export function shouldAutoCheck(lastCheckedAt: number | null, now: number): boolean {
  return !lastCheckedAt || now - lastCheckedAt >= CHECK_INTERVAL_MS;
}

export function shouldShowUpdateBadge(args: {
  enabled: boolean;
  badgeEnabled: boolean;
  latest: UpdateInfo | null;
  currentVersion: string;
  dismissedVersion: string | null;
}): boolean {
  if (!args.enabled || !args.badgeEnabled || !args.latest) return false;
  if (!isNewerVersion(args.latest.version, args.currentVersion)) return false;
  return normalizeVersion(args.latest.version) !== normalizeVersion(args.dismissedVersion ?? "");
}

function derive(base: Pick<UpdateState, "enabled" | "badgeEnabled" | "latest" | "currentVersion" | "dismissedVersion">) {
  const hasUpdate = Boolean(base.latest && isNewerVersion(base.latest.version, base.currentVersion));
  const showBadge = shouldShowUpdateBadge(base);
  return { hasUpdate, showBadge };
}

const initial = {
  sourceConfigured: UPDATE_SOURCE_CONFIGURED,
  enabled: false,
  badgeEnabled: false,
  dismissedVersion: null,
  lastCheckedAt: null,
  latest: null,
  currentVersion: __APP_VERSION__,
};

export const useUpdateStore = create<UpdateState>((set, get) => ({
  ...initial,
  status: "unavailable",
  error: null,
  ...derive(initial),
  setEnabled: () => set({ enabled: false, hasUpdate: false, showBadge: false }),
  setBadgeEnabled: () => set({ badgeEnabled: false, showBadge: false }),
  dismissBadge: () => set({ dismissedVersion: null, showBadge: false }),
  check: async () => {
    set({
      enabled: false,
      badgeEnabled: false,
      latest: null,
      lastCheckedAt: null,
      status: "unavailable",
      error: null,
      hasUpdate: false,
      showBadge: false,
    });
  },
  maybeAutoCheck: () => get().check({ manual: false }),
}));

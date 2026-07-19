import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  compareVersions,
  isNewerVersion,
  shouldAutoCheck,
  shouldShowUpdateBadge,
  UPDATE_SOURCE_CONFIGURED,
  useUpdateStore,
  type UpdateInfo,
} from "./update";

const latest: UpdateInfo = {
  version: "v0.1.8",
  url: "https://example.invalid/ai4heor/releases/tag/v0.1.8",
  name: "v0.1.8",
  publishedAt: "2026-07-09T00:00:00Z",
};

describe("version comparison", () => {
  it("compares v-prefixed semver versions", () => {
    expect(compareVersions("v0.1.8", "0.1.7")).toBe(1);
    expect(compareVersions("0.1.7", "v0.1.7")).toBe(0);
    expect(compareVersions("0.2.0", "0.10.0")).toBe(-1);
  });

  it("detects newer versions only", () => {
    expect(isNewerVersion("v0.1.8", "0.1.7")).toBe(true);
    expect(isNewerVersion("v0.1.7", "0.1.7")).toBe(false);
    expect(isNewerVersion("v0.1.6", "0.1.7")).toBe(false);
  });
});

describe("update check policy", () => {
  it("checks automatically at most once per 24 hours", () => {
    const now = 1_000_000_000;
    expect(shouldAutoCheck(null, now)).toBe(true);
    expect(shouldAutoCheck(now - 23 * 60 * 60 * 1000, now)).toBe(false);
    expect(shouldAutoCheck(now - 24 * 60 * 60 * 1000, now)).toBe(true);
  });

  it("allows update badge suppression without disabling checks", () => {
    expect(
      shouldShowUpdateBadge({
        enabled: true,
        badgeEnabled: true,
        latest,
        currentVersion: "0.1.7",
        dismissedVersion: null,
      }),
    ).toBe(true);
    expect(
      shouldShowUpdateBadge({
        enabled: true,
        badgeEnabled: false,
        latest,
        currentVersion: "0.1.7",
        dismissedVersion: null,
      }),
    ).toBe(false);
    expect(
      shouldShowUpdateBadge({
        enabled: true,
        badgeEnabled: true,
        latest,
        currentVersion: "0.1.7",
        dismissedVersion: "0.1.8",
      }),
    ).toBe(false);
  });
});

describe("update store", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    useUpdateStore.setState({
      sourceConfigured: false,
      enabled: false,
      badgeEnabled: false,
      dismissedVersion: null,
      lastCheckedAt: null,
      latest: null,
      status: "unavailable",
      error: null,
      currentVersion: "0.1.7",
      hasUpdate: false,
      showBadge: false,
    });
  });

  it("does not contact the network before an AI4HEOR release source is configured", async () => {
    expect(UPDATE_SOURCE_CONFIGURED).toBe(false);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    useUpdateStore.setState({ lastCheckedAt: 1000 });
    await useUpdateStore.getState().check({ manual: true, now: 2000 });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(useUpdateStore.getState()).toMatchObject({
      sourceConfigured: false,
      enabled: false,
      badgeEnabled: false,
      latest: null,
      lastCheckedAt: null,
      status: "unavailable",
      hasUpdate: false,
      showBadge: false,
    });
  });
});

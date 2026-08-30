import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  invoke: vi.fn(),
  gatewayToken: vi.fn(() => "gateway-secret"),
  gatewayOrigin: vi.fn(() => "http://127.0.0.1:4098"),
}));

vi.mock("./tauri", () => ({ isTauri: true }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));
vi.mock("./webMode", () => ({
  isGatewayWeb: true,
  gatewayToken: mocks.gatewayToken,
  gatewayOrigin: mocks.gatewayOrigin,
}));

import {
  clearResolvedArtifactPaths,
  previewUrl,
  readArtifact,
  resolveArtifactPath,
} from "./artifactFile";

describe("workspace artifact reads", () => {
  beforeEach(() => {
    mocks.invoke.mockReset();
    clearResolvedArtifactPaths();
    vi.restoreAllMocks();
  });

  it("treats an artifact that has not been created as missing", async () => {
    mocks.invoke.mockRejectedValueOnce(new Error("file not found"));
    await expect(readArtifact("heor/analysis-plan.json")).resolves.toBeNull();
  });

  it("preserves real read failures", async () => {
    mocks.invoke.mockRejectedValueOnce(new Error("path escapes the workspace"));
    await expect(readArtifact("../secret.json")).rejects.toThrow("path escapes the workspace");
  });

  it("exchanges the bearer token for a single-file preview ticket", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ ticket: "file-ticket" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(
      previewUrl("reports/result.html", "workspace", "/research/session-1"),
    ).resolves.toBe("http://127.0.0.1:4098/v1/fs/read?ticket=file-ticket");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:4098/v1/fs/ticket?path=reports%2Fresult.html&root=workspace&dir=%2Fresearch%2Fsession-1",
      { headers: { Authorization: "Bearer gateway-secret" } },
    );
    expect(fetchMock.mock.calls.flat().join(" ")).not.toContain("gateway-secret");
  });

  it("deduplicates artifact path resolution within one workspace", async () => {
    mocks.invoke.mockResolvedValue("reports/result.html");

    await expect(resolveArtifactPath("result.html")).resolves.toBe("reports/result.html");
    await expect(resolveArtifactPath("result.html")).resolves.toBe("reports/result.html");
    expect(mocks.invoke).toHaveBeenCalledTimes(1);

    clearResolvedArtifactPaths();
    await expect(resolveArtifactPath("result.html")).resolves.toBe("reports/result.html");
    expect(mocks.invoke).toHaveBeenCalledTimes(2);
  });

  it("does not retain a failed artifact path resolution", async () => {
    mocks.invoke.mockRejectedValueOnce(new Error("temporary IPC failure"));
    mocks.invoke.mockResolvedValueOnce("reports/result.html");

    await expect(resolveArtifactPath("result.html")).rejects.toThrow("temporary IPC failure");
    await expect(resolveArtifactPath("result.html")).resolves.toBe("reports/result.html");
    expect(mocks.invoke).toHaveBeenCalledTimes(2);
  });
});

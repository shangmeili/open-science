import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("./tauri", () => ({ isTauri: true }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));

import { readArtifact } from "./artifactFile";

describe("workspace artifact reads", () => {
  beforeEach(() => mocks.invoke.mockReset());

  it("treats an artifact that has not been created as missing", async () => {
    mocks.invoke.mockRejectedValueOnce(new Error("file not found"));
    await expect(readArtifact("heor/analysis-plan.json")).resolves.toBeNull();
  });

  it("preserves real read failures", async () => {
    mocks.invoke.mockRejectedValueOnce(new Error("path escapes the workspace"));
    await expect(readArtifact("../secret.json")).rejects.toThrow("path escapes the workspace");
  });
});

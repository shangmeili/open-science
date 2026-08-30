import { describe, expect, it } from "vitest";
import { customProviderId } from "./customProviderId";

describe("customProviderId", () => {
  it("preserves existing ASCII endpoint ids", () => {
    expect(customProviderId("OpenRouter")).toBe("openrouter");
    expect(customProviderId("Local research gateway")).toBe("local-research-gateway");
  });

  it("creates a stable id for a Chinese endpoint name", () => {
    const id = customProviderId("本地研究模型");
    expect(id).toMatch(/^custom-[0-9a-f]{8}$/);
    expect(customProviderId("本地研究模型")).toBe(id);
  });

  it("does not collapse different non-Latin names onto the same ASCII skeleton", () => {
    expect(customProviderId("本地 API")).not.toBe(customProviderId("院内 API"));
  });

  it("returns an empty id only when the name is blank", () => {
    expect(customProviderId("   ")).toBe("");
    expect(customProviderId("!!!")).toMatch(/^custom-[0-9a-f]{8}$/);
  });
});

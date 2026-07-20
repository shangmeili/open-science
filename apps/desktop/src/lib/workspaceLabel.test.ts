import { describe, expect, it } from "vitest";
import { workspaceLabel } from "./workspaceLabel";

describe("workspaceLabel", () => {
  it("turns internal dated task folders into readable labels", () => {
    expect(workspaceLabel("2026-07-20-1408", "zh-Hans")).toBe("7月20日 14:08 的任务");
    expect(workspaceLabel("2026-07-05-0319", "en")).toBe("Jul 5, 03:19 task");
  });

  it("keeps user-named project folders unchanged", () => {
    expect(workspaceLabel("糖尿病成本效果研究", "zh-Hans")).toBe("糖尿病成本效果研究");
  });
});

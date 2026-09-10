import { describe, expect, it } from "vitest";
import { buildHeorPrompt, displayHeorPrompt } from "./heor";

describe("bundled product help", () => {
  it("grounds configuration questions in bundled user instructions", () => {
    const prompt = buildHeorPrompt("AI4HEOR 如何配置模型和 Jupyter？", "zh-Hans");
    expect(prompt).toContain("设置 → 模型");
    expect(prompt).toContain("安装本地环境");
    expect(prompt).toContain("待发送");
    expect(prompt).toContain("research-presentation");
    expect(prompt).toContain("APP_PRODUCT_HELP");
    expect(displayHeorPrompt(prompt)).toBe("AI4HEOR 如何配置模型和 Jupyter？");
  });

  it("supports English product questions and leaves ordinary research prompts unchanged", () => {
    expect(buildHeorPrompt("How do I configure AI4HEOR?", "en")).toContain("APP_PRODUCT_HELP");
    expect(buildHeorPrompt("比较两种治疗的成本与QALY", "zh-Hans")).not.toContain("APP_PRODUCT_HELP");
    expect(buildHeorPrompt("使用技能分析这份数据", "zh-Hans")).not.toContain("APP_PRODUCT_HELP");
  });
});

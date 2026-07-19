import { describe, expect, it } from "vitest";
import i18n, { NAMESPACES } from "./index";

function strings(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (!value || typeof value !== "object") return [];
  return Object.values(value as Record<string, unknown>).flatMap(strings);
}

describe("Simplified Chinese product copy", () => {
  const copy = NAMESPACES.flatMap((namespace) =>
    strings(i18n.getResourceBundle("zh-Hans", namespace)),
  );

  it("does not expose internal English role names or broken mixed-language phrases", () => {
    const joined = copy.join("\n");
    expect(joined).not.toMatch(/\b(?:Agent|Human)\b/);
    expect(joined).not.toContain("代理");
    expect(joined).not.toContain("让 助手");
    expect(joined).not.toContain("助手 ");
  });

  it("uses the pharmacoeconomic terms adopted by the Chinese knowledge base", () => {
    expect(i18n.t("heor:starter.scope.title", { lng: "zh-Hans" })).toBe("设计成本-效果分析");
    expect(i18n.t("session:starters.example-cea.title", { lng: "zh-Hans" })).toBe(
      "查看成本-效用分析示例",
    );
    expect(i18n.t("heor:snapshot.perspective", { lng: "zh-Hans" })).toBe("评价视角");
    expect(copy.join("\n")).not.toMatch(/风险比值（HR）/);
  });

  it("keeps the first-use boundary direct and researcher-led", () => {
    expect(i18n.t("heor:starter.title", { lng: "zh-Hans" })).toBe("从研究问题开始");
    expect(i18n.t("heor:starter.body", { lng: "zh-Hans" })).toContain(
      "AI4HEOR 会在你的指导下检索和整理证据、开展分析并检查结果",
    );
    expect(i18n.t("heor:starter.body", { lng: "zh-Hans" })).toContain(
      "由你审阅确认",
    );
    expect(i18n.t("session:firstRun.title", { lng: "zh-Hans" })).toBe(
      "开始前，请先了解这四点",
    );
    expect(i18n.t("session:firstRun.points.human.title", { lng: "zh-Hans" })).toBe(
      "关键研究决策由你把关",
    );
    expect(copy.join("\n")).not.toContain("资料整理、分析记录和结果检查可以交给助手");
  });
});

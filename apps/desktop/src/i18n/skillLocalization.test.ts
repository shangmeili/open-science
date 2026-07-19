import { afterEach, describe, expect, it } from "vitest";
import i18n from "./index";
import { shippedLocales } from "./config";
import { localizeSkill } from "./skillLocalization";

describe("localizeSkill", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("uses the current language for app-owned HEOR Skills", async () => {
    await i18n.changeLanguage("zh-Hans");
    const copy = localizeSkill("heor-workbench", "English runtime description", i18n.resolvedLanguage);
    expect(copy).toEqual({
      displayName: "AI4HEOR 药物经济学工作台",
      description: "帮助研究者完成药物经济学与 HEOR 项目的设计、分析、复核和报告。",
      localized: true,
    });
  });

  it("falls back to exact runtime metadata for unknown or third-party Skills", () => {
    expect(localizeSkill("my-project-skill", "Project-provided description", "zh-Hans")).toEqual({
      displayName: "my-project-skill",
      description: "Project-provided description",
      localized: false,
    });
  });

  it.each(shippedLocales())("provides first-party Skill copy in $nativeName", ({ code }) => {
    const copy = localizeSkill("heor-workbench", "English runtime description", code);
    expect(copy.localized).toBe(true);
    expect(copy.displayName).not.toBe("heor-workbench");
    expect(copy.description).not.toBe("English runtime description");
  });
});

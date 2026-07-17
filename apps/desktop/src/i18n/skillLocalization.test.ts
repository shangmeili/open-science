import { afterEach, describe, expect, it } from "vitest";
import i18n from "./index";
import { localizeSkill } from "./skillLocalization";

describe("localizeSkill", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("uses the current language for app-owned HEOR Skills", async () => {
    await i18n.changeLanguage("zh-Hans");
    const copy = localizeSkill("heor-workbench", "English runtime description", i18n.resolvedLanguage);
    expect(copy).toEqual({
      displayName: "AI4HEOR 科研工作台",
      description: "辅助由研究者主导、可审计的药物经济学与 HEOR 工作。",
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
});

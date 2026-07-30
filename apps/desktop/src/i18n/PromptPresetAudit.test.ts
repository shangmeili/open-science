import { describe, expect, it } from "vitest";
import deSession from "./locales/de/session.json";
import enHeor from "./locales/en/heor.json";
import enSession from "./locales/en/session.json";
import esSession from "./locales/es/session.json";
import frSession from "./locales/fr/session.json";
import jaSession from "./locales/ja/session.json";
import koSession from "./locales/ko/session.json";
import zhHeor from "./locales/zh-Hans/heor.json";
import zhSession from "./locales/zh-Hans/session.json";

const sessions = { de: deSession, en: enSession, es: esSession, fr: frSession, ja: jaSession, ko: koSession, zh: zhSession };
const visibleInternalToken = /\$[\w-]+|(?:heor|deliverables|references)\/[\w./-]+|\.json|\.md|SHA-256|\b(?:Git|README|OpenCode|permission mode|full access)\b/i;
const debugResidue = /do not begin with git|authorization handoff|permission mode|full[- ]?access|localhost|127\.0\.0\.1|调试遗留|权限模式|授权面板/i;

function promptValues(value: unknown, key = ""): string[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  return Object.entries(value).flatMap(([childKey, child]) => {
    if (typeof child === "string" && /prompt/i.test(childKey)) return [child];
    return promptValues(child, childKey || key);
  });
}

describe("researcher-facing prompt presets", () => {
  it("keeps entry presets in natural language across every bundled UI locale", () => {
    for (const [locale, session] of Object.entries(sessions)) {
      const prompts = [
        session.starters.analyze.prompt,
        session.starters.audit.prompt,
        session.starters.design.prompt,
        session.starters["example-cea"].prompt,
        ...Object.values(session.newTask.suggestions).map((suggestion) => suggestion.prompt),
      ];
      for (const prompt of prompts) {
        expect(prompt, `${locale}: ${prompt}`).not.toMatch(visibleInternalToken);
      }
    }
  });

  it("contains no known development or authorization-handoff residue in any preset prompt", () => {
    for (const prompt of [
      ...Object.values(sessions).flatMap((session) => promptValues(session)),
      ...promptValues(enHeor),
      ...promptValues(zhHeor),
    ]) {
      expect(prompt).not.toMatch(debugResidue);
    }
  });
});

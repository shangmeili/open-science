import i18n from "./index";
import { resolveLocale } from "./config";

interface SkillCatalogEntry {
  displayName: string;
  description: string;
}

interface SkillCatalogBundle {
  catalog?: Record<string, SkillCatalogEntry>;
}

export interface LocalizedSkillCopy {
  displayName: string;
  description: string;
  localized: boolean;
}

/**
 * Localize app-owned Skills and the exact hash-locked adapters shipped by the
 * product. Unknown runtime and project Skills keep the metadata supplied by
 * OpenCode, so the app never invents or mistranslates unreviewed capabilities.
 */
export function localizeSkill(
  name: string,
  runtimeDescription: string,
  locale: string | null | undefined,
): LocalizedSkillCopy {
  const resolved = resolveLocale(locale);
  const bundle = i18n.getResourceBundle(resolved, "skills") as SkillCatalogBundle | undefined;
  const entry = bundle?.catalog?.[name];
  if (!entry?.displayName?.trim() || !entry.description?.trim()) {
    return { displayName: name, description: runtimeDescription, localized: false };
  }
  return {
    displayName: entry.displayName,
    description: entry.description,
    localized: true,
  };
}

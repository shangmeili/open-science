import i18n from "@/i18n";

/** Last path segment of a project folder, or the localized fallback. */
export function baseName(path: string | null): string {
  const fallback = i18n.t("session:workspaceChip.fallbackName");
  if (!path) return fallback;
  return path.replace(/[/\\]+$/, "").split(/[/\\]/).pop() || fallback;
}

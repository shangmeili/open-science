// OpenCode uses this id as a JSON key and inside "provider/model" strings, so
// it remains ASCII even when the researcher-facing endpoint name is not.

function isAscii(value: string): boolean {
  for (const char of value) if (char.codePointAt(0)! > 0x7f) return false;
  return true;
}

/** Stable FNV-1a digest over Unicode code points; no crypto dependency needed. */
function digest(value: string): string {
  let hash = 0x811c9dc5;
  for (const char of value) {
    hash ^= char.codePointAt(0)!;
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

/**
 * Derive a stable ASCII config id from the endpoint display name. Existing
 * ASCII names retain their historical slug. Non-ASCII names include a digest
 * so distinct names cannot silently overwrite the same provider entry.
 */
export function customProviderId(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "";
  const slug = trimmed
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  if (!slug) return `custom-${digest(trimmed)}`;
  if (isAscii(trimmed)) return slug;
  return `${slug}-${digest(trimmed)}`;
}

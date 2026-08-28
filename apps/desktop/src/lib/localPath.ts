/** Compare canonical local paths across platform-specific string formats.
 *
 * Windows APIs may return the same directory with either slash style, a
 * differently-cased drive/path, a trailing separator, or an extended-length
 * prefix. POSIX paths remain case-sensitive. This intentionally does not
 * resolve `.`/`..`: callers compare paths already canonicalized by Tauri or
 * the runtime, and resolving untrusted strings in the frontend would hide a
 * real scope mismatch.
 */
export function sameLocalPath(left: string | null | undefined, right: string | null | undefined) {
  if (!left || !right) return false;
  const leftWindows = isWindowsPath(left);
  const rightWindows = isWindowsPath(right);
  if (leftWindows !== rightWindows) return false;
  return comparablePath(left, leftWindows) === comparablePath(right, rightWindows);
}

function isWindowsPath(path: string) {
  return /^[A-Za-z]:[\\/]/.test(path)
    || /^\\\\/.test(path)
    || /^\/\//.test(path);
}

function comparablePath(path: string, windows: boolean) {
  let normalized = path.replace(/\\/g, "/");
  if (windows) {
    if (/^\/\/\?\/unc\//i.test(normalized)) normalized = `//${normalized.slice(8)}`;
    else if (/^\/\/\?\//.test(normalized)) normalized = normalized.slice(4);
  }
  while (
    normalized.length > 1
    && normalized.endsWith("/")
    && !/^[A-Za-z]:\/$/.test(normalized)
  ) {
    normalized = normalized.slice(0, -1);
  }
  return windows ? normalized.toLocaleLowerCase("en-US") : normalized;
}

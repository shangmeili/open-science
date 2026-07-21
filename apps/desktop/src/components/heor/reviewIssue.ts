/** Keep native file-system and schema-presence diagnostics in debug logs. The
 * assessment title and its recovery action already identify the missing HEOR
 * artifact, so the product UI only needs a stable research status. */
export function formatHeorReviewIssue(issue: string, artifactPending: string): string {
  return /(?:no such file(?: or directory)?|file not found|os error\s*2|\bunavailable\b|\bis required\b)/i.test(issue)
    ? artifactPending
    : issue;
}

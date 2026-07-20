const STANDALONE_TASK = /^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})$/;

/**
 * Standalone tasks are stored in timestamp folders so names never collide.
 * Keep that storage detail out of the product UI while preserving real project
 * names exactly as the researcher chose them.
 */
export function workspaceLabel(name: string, locale?: string): string {
  const match = STANDALONE_TASK.exec(name);
  if (!match) return name;

  const [, year, month, day, hour, minute] = match;
  const date = new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
  );
  if (
    date.getFullYear() !== Number(year) ||
    date.getMonth() !== Number(month) - 1 ||
    date.getDate() !== Number(day) ||
    date.getHours() !== Number(hour) ||
    date.getMinutes() !== Number(minute)
  ) {
    return name;
  }

  const language = locale || "en";
  const time = new Intl.DateTimeFormat(language, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
  if (language.toLowerCase().startsWith("zh")) {
    return `${Number(month)}月${Number(day)}日 ${time} 的任务`;
  }
  const calendarDate = new Intl.DateTimeFormat(language, {
    month: "short",
    day: "numeric",
  }).format(date);
  return `${calendarDate}, ${time} task`;
}

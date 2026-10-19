import type { OpenCodeEvent } from "@ai4s/sdk";

export const STREAM_COALESCE_MS = 120;

export type CoalescibleEvent = Extract<OpenCodeEvent, { type: "text.updated" | "reasoning.updated" }>;
export type CoalescedEntry = { key: string; event: CoalescibleEvent };

export function coalesceKey(event: OpenCodeEvent): string | null {
  if (event.type === "text.updated") return `text:${event.partId}`;
  if (event.type === "reasoning.updated") return `reasoning:${event.partId}`;
  return null;
}

export function upsertCoalesced(queue: CoalescedEntry[], key: string, event: CoalescibleEvent): void {
  for (const entry of queue) {
    if (entry.key === key) {
      entry.event = event;
      return;
    }
  }
  queue.push({ key, event });
}

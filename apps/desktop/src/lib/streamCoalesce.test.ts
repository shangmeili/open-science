import { describe, expect, it } from "vitest";
import type { OpenCodeEvent } from "@ai4s/sdk";
import { coalesceKey, upsertCoalesced, type CoalescedEntry, type CoalescibleEvent } from "./streamCoalesce";

const text = (partId: string, value: string) =>
  ({ type: "text.updated", sessionId: "s", partId, text: value }) as unknown as CoalescibleEvent;
const reasoning = (partId: string, value: string) =>
  ({ type: "reasoning.updated", sessionId: "s", partId, text: value }) as unknown as CoalescibleEvent;

describe("coalesceKey", () => {
  it("keys text and reasoning snapshots independently", () => {
    expect(coalesceKey(text("p1", "a"))).toBe("text:p1");
    expect(coalesceKey(reasoning("p1", "a"))).toBe("reasoning:p1");
  });

  it("does not defer non-snapshot or terminal events", () => {
    expect(coalesceKey({ type: "tool.updated" } as OpenCodeEvent)).toBeNull();
    expect(coalesceKey({ type: "session.idle" } as OpenCodeEvent)).toBeNull();
    expect(coalesceKey({ type: "error" } as OpenCodeEvent)).toBeNull();
  });
});

describe("upsertCoalesced", () => {
  it("keeps the latest snapshot while preserving first-arrival order", () => {
    const queue: CoalescedEntry[] = [];
    upsertCoalesced(queue, "text:p1", text("p1", "a"));
    upsertCoalesced(queue, "reasoning:r1", reasoning("r1", "thinking"));
    upsertCoalesced(queue, "text:p1", text("p1", "answer"));
    expect(queue.map((entry) => entry.key)).toEqual(["text:p1", "reasoning:r1"]);
    expect((queue[0].event as { text: string }).text).toBe("answer");
  });
});

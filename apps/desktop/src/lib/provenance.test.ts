import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ToolUpdatedEvent } from "@ai4s/sdk";
import { provenanceInputFromEvent, provenanceInputsFromEvent, recordProvenance } from "./provenance";

const mocks = vi.hoisted(() => ({ invoke: vi.fn(), logDebug: vi.fn() }));
vi.mock("./tauri", () => ({ isTauri: true, logDebug: mocks.logDebug }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));

beforeEach(() => {
  mocks.invoke.mockReset();
  mocks.logDebug.mockReset();
});

const write = (over: Partial<ToolUpdatedEvent> = {}): ToolUpdatedEvent => ({
  type: "tool.updated",
  sessionId: "ses_1",
  messageId: "msg_assistant_1",
  callId: "call_1",
  tool: "write",
  status: "success",
  input: { filePath: "fig/plot.py", content: "print(1)" },
  ...over,
});

describe("provenanceInputFromEvent", () => {
  it("derives a record from a successful write with its content", () => {
    const r = provenanceInputFromEvent(write({ title: "Rewrote the plotting helper" }));
    expect(r).toEqual({
      path: "fig/plot.py",
      tool: "write",
      content: "print(1)",
      log: "Rewrote the plotting helper",
      assistantMessageId: "msg_assistant_1",
      toolCallId: "call_1",
    });
  });

  it("replaces path-only or empty titles with a compact tool → path log", () => {
    // OpenCode write titles are usually just the file path — redundant.
    const paths = provenanceInputFromEvent(write({ title: "Users/x/AI4HEOR/fig/plot.py" }));
    expect(paths?.log).toBe("write → fig/plot.py");
    const empty = provenanceInputFromEvent(write({ title: "" }));
    expect(empty?.log).toBe("write → fig/plot.py");
  });

  it("captures an edit's diff for lineage when full content isn't available", () => {
    // OpenCode's edit tool carries oldString/newString (not `content`), so the
    // full file text isn't in the event — but its unified diff is.
    const edit = provenanceInputFromEvent(
      write({
        tool: "edit",
        input: { filePath: "fig/plot.py", oldString: "print(1)", newString: "print(2)" },
        diff: "--- a/fig/plot.py\n+++ b/fig/plot.py\n@@ -1 +1 @@\n-print(1)\n+print(2)",
      }),
    );
    expect(edit?.content).toBeUndefined();
    expect(edit?.diff).toContain("+print(2)");
  });

  it("ignores non-success, non-write, and pathless events", () => {
    expect(provenanceInputFromEvent(write({ status: "running" }))).toBeNull();
    expect(provenanceInputFromEvent(write({ tool: "bash" }))).toBeNull();
    expect(provenanceInputFromEvent(write({ input: {} }))).toBeNull();
  });

  it("records every add and update in a multi-file apply_patch call", () => {
    const patchText = [
      "*** Begin Patch",
      "*** Add File: reports/result.md",
      "+Result",
      "*** Update File: analysis/model.R",
      "@@ -1 +1 @@",
      "-print(1)",
      "+print(2)",
      "*** Delete File: scratch.tmp",
      "*** End Patch",
    ].join("\n");
    const records = provenanceInputsFromEvent(
      write({ tool: "apply_patch", input: { patchText } }),
    );
    expect(records.map((record) => record.path)).toEqual([
      "reports/result.md",
      "analysis/model.R",
    ]);
    expect(records[0].content).toBe("Result");
    expect(records[1].diff).toContain("+print(2)");
    expect(records.every((record) => record.assistantMessageId === "msg_assistant_1")).toBe(true);
    expect(records.every((record) => record.toolCallId === "call_1")).toBe(true);
  });

  it("wraps one ordinary write and excludes non-writing events", () => {
    expect(provenanceInputsFromEvent(write()).map((record) => record.path)).toEqual([
      "fig/plot.py",
    ]);
    expect(provenanceInputsFromEvent(write({ tool: "bash" }))).toEqual([]);
  });

  it("records mutating jupyter tools but not reads", () => {
    const jupyter = (tool: string) =>
      write({ tool, input: { notebook_path: "analysis.ipynb" } });
    expect(provenanceInputFromEvent(jupyter("jupyter_insert_cell"))?.path).toBe("analysis.ipynb");
    expect(provenanceInputFromEvent(jupyter("jupyter_execute_cell"))?.path).toBe("analysis.ipynb");
    expect(provenanceInputFromEvent(jupyter("jupyter_read_cells"))).toBeNull();
    expect(provenanceInputFromEvent(jupyter("jupyter_list_files"))).toBeNull();
  });

  it("passes exact assistant-message and tool-call ids to the native provenance store", async () => {
    mocks.invoke.mockResolvedValue({ version: 1 });
    const input = provenanceInputFromEvent(write())!;
    await recordProvenance(input, "ses_1", "mock/model");

    expect(mocks.invoke).toHaveBeenCalledWith("record_provenance", {
      path: "fig/plot.py",
      tool: "write",
      content: "print(1)",
      diff: null,
      log: "write → fig/plot.py",
      sessionId: "ses_1",
      model: "mock/model",
      assistantMessageId: "msg_assistant_1",
      toolCallId: "call_1",
    });
  });
});

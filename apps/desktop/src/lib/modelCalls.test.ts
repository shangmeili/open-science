import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MessageUsageEvent } from "@ai4s/sdk";
import { listModelCalls, modelCallInput, recordModelCall, recordModelCallsFromHistory } from "./modelCalls";
import type { HeorPromptContext } from "./heor";
import { buildHeorPrompt, heorPromptContext } from "./heor";

const mocks = vi.hoisted(() => ({ invoke: vi.fn(), logDebug: vi.fn() }));
vi.mock("./tauri", () => ({ isTauri: true, logDebug: mocks.logDebug }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));

beforeEach(() => {
  mocks.invoke.mockReset();
  mocks.logDebug.mockReset();
});

describe("model-call audit boundary", () => {
  it("keeps only content-free completed-call metadata", () => {
    const event: MessageUsageEvent = {
      type: "message.usage",
      sessionId: "ses_1",
      messageId: "msg_assistant_1",
      parentMessageId: "msg_user_1",
      providerId: "mock-provider",
      modelId: "mock-model",
      agent: "build",
      systemContextContract: "ai4heor.system-context/v1",
      systemContextSha256: "b".repeat(64),
      systemContextBlockCount: 2,
      createdAt: 1_000,
      completedAt: 1_250,
      runtimeReportedCost: 0.0123,
      tokens: {
        input: 120,
        output: 45,
        reasoning: 8,
        cacheRead: 30,
        cacheWrite: 4,
      },
      finish: "stop",
    };

    const input = modelCallInput(event);
    expect(input).toEqual({
      runtime: "opencode",
      runtimeVersion: "1.17.13-ai4heor.2",
      sessionId: "ses_1",
      messageId: "msg_assistant_1",
      parentMessageId: "msg_user_1",
      providerId: "mock-provider",
      modelId: "mock-model",
      agent: "build",
      systemContextContract: "ai4heor.system-context/v1",
      systemContextSha256: "b".repeat(64),
      systemContextBlockCount: 2,
      createdAt: 1_000,
      completedAt: 1_250,
      runtimeReportedCost: 0.0123,
      tokens: {
        input: 120,
        output: 45,
        reasoning: 8,
        cacheRead: 30,
        cacheWrite: 4,
      },
      finish: "stop",
    });
    expect(JSON.stringify(input)).not.toMatch(/prompt|response|content|apiKey|requestUrl/);
    expect(JSON.stringify(input)).not.toContain("research-secret");
  });

  it("adds only the fixed prompt-template fingerprint when one is known", () => {
    const event: MessageUsageEvent = {
      type: "message.usage",
      sessionId: "ses_1",
      messageId: "msg_assistant_1",
      parentMessageId: "msg_user_1",
      providerId: "mock-provider",
      modelId: "mock-model",
      agent: "build",
      systemContextContract: "ai4heor.system-context/v1",
      systemContextSha256: "c".repeat(64),
      systemContextBlockCount: 1,
      createdAt: 1_000,
      completedAt: 1_250,
      runtimeReportedCost: 0.0123,
      tokens: { input: 1, output: 2, reasoning: 0, cacheRead: 0, cacheWrite: 0 },
    };
    const context: HeorPromptContext = {
      promptTemplateId: "ai4heor/heor-workbench-preamble",
      promptTemplateSha256: "a".repeat(64),
      responseLanguage: "Simplified Chinese",
    };

    expect(modelCallInput(event, context)).toMatchObject(context);
  });

  it("persists live and replayed usage through the same idempotent native command", async () => {
    mocks.invoke.mockResolvedValue({ callId: "call_1" });
    const event: MessageUsageEvent = {
      type: "message.usage",
      sessionId: "ses_1",
      messageId: "msg_assistant_1",
      parentMessageId: "msg_user_1",
      providerId: "mock-provider",
      modelId: "mock-model",
      agent: "build",
      systemContextContract: "ai4heor.system-context/v1",
      systemContextSha256: "d".repeat(64),
      systemContextBlockCount: 3,
      createdAt: 1_000,
      completedAt: 1_250,
      runtimeReportedCost: 0.0123,
      tokens: { input: 120, output: 45, reasoning: 8, cacheRead: 30, cacheWrite: 4 },
      finish: "stop",
    };
    const usage = {
      sessionId: event.sessionId,
      messageId: event.messageId,
      parentMessageId: event.parentMessageId,
      providerId: event.providerId,
      modelId: event.modelId,
      agent: event.agent,
      systemContextContract: event.systemContextContract,
      systemContextSha256: event.systemContextSha256,
      systemContextBlockCount: event.systemContextBlockCount,
      createdAt: event.createdAt,
      completedAt: event.completedAt,
      runtimeReportedCost: event.runtimeReportedCost,
      tokens: event.tokens,
      finish: event.finish,
    };

    await recordModelCall(event);
    const storedPrompt = buildHeorPrompt("研究者问题", "zh-Hans");
    const context = heorPromptContext(storedPrompt)!;
    await recordModelCallsFromHistory([
      { role: "assistant", usage, parts: [] },
      { role: "user", id: "msg_user_1", parts: [{ type: "text", text: storedPrompt }] },
    ]);

    expect(mocks.invoke).toHaveBeenCalledTimes(2);
    expect(mocks.invoke).toHaveBeenNthCalledWith(1, "record_model_call", {
      input: modelCallInput(event),
    });
    expect(mocks.invoke).toHaveBeenNthCalledWith(2, "record_model_calls", {
      inputs: [modelCallInput(event, context)],
    });
  });

  it("reads the verified local ledger for researcher-facing audit details", async () => {
    const records = [{ callId: "call_1", messageId: "msg_assistant_1" }];
    mocks.invoke.mockResolvedValue(records);

    await expect(listModelCalls()).resolves.toEqual(records);
    expect(mocks.invoke).toHaveBeenCalledWith("list_model_calls");
  });

  it("propagates native ledger verification failures to the audit UI", async () => {
    mocks.invoke.mockRejectedValue(new Error("hash chain mismatch"));

    await expect(listModelCalls()).rejects.toThrow("hash chain mismatch");
    expect(mocks.invoke).toHaveBeenCalledWith("list_model_calls");
  });
});

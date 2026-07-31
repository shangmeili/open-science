import {
  OPENCODE_VERSION,
  type HistoryMessage,
  type MessageUsageEvent,
} from "@ai4s/sdk";
import { isTauri, logDebug } from "./tauri";

export interface ModelCallInput extends Omit<MessageUsageEvent, "type"> {
  runtime: "opencode";
  runtimeVersion: string;
}

/** Convert the SDK's content-free completed-call event to the native ledger
 * contract. Keeping this pure makes the privacy boundary directly testable. */
export function modelCallInput(event: MessageUsageEvent): ModelCallInput {
  return {
    runtime: "opencode",
    runtimeVersion: OPENCODE_VERSION,
    sessionId: event.sessionId,
    messageId: event.messageId,
    parentMessageId: event.parentMessageId,
    providerId: event.providerId,
    modelId: event.modelId,
    agent: event.agent,
    createdAt: event.createdAt,
    completedAt: event.completedAt,
    runtimeReportedCost: event.runtimeReportedCost,
    tokens: event.tokens,
    ...(event.finish ? { finish: event.finish } : {}),
  };
}

/** Best-effort audit persistence must never interrupt a conversation. */
export async function recordModelCall(event: MessageUsageEvent): Promise<void> {
  if (!isTauri) return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("record_model_call", { input: modelCallInput(event) });
    void logDebug("model-call ledger ✓");
  } catch (error) {
    void logDebug(
      `model-call ledger FAILED: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

/** Backfill completed calls from history after a task is opened, covering a
 * transiently missed SSE event. Native idempotency makes replay safe. */
export async function recordModelCallsFromHistory(
  messages: HistoryMessage[],
): Promise<void> {
  if (!isTauri) return;
  const inputs = messages
    .filter(
      (message): message is HistoryMessage & { usage: NonNullable<HistoryMessage["usage"]> } =>
        !!message.usage,
    )
    .map((message) => modelCallInput({ type: "message.usage", ...message.usage }));
  if (inputs.length === 0) return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("record_model_calls", { inputs });
    void logDebug("model-call history ledger ✓");
  } catch (error) {
    void logDebug(
      `model-call history ledger FAILED: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

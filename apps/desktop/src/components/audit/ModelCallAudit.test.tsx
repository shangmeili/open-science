import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ModelCallAudit } from "./ModelCallAudit";

const mocks = vi.hoisted(() => ({ listModelCalls: vi.fn() }));
vi.mock("@/lib/modelCalls", () => ({
  listModelCalls: (...args: unknown[]) => mocks.listModelCalls(...args),
}));

const record = {
  schemaVersion: 1,
  callId: "call_internal_1",
  recordedAt: 1_751_500_001_000,
  runtime: "opencode",
  runtimeVersion: "1.17.13-ai4heor.2",
  sessionId: "ses_1",
  messageId: "msg_assistant_1",
  parentMessageId: "msg_user_1",
  providerId: "minimax-cn",
  modelId: "MiniMax-M3",
  agent: "build",
  createdAt: 1_751_500_000_000,
  completedAt: 1_751_500_001_250,
  runtimeReportedCost: 0.0123,
  tokens: { input: 120, output: 45, reasoning: 8, cacheRead: 30, cacheWrite: 4 },
  finish: "stop",
  systemContextContract: "ai4heor.system-context/v1",
  systemContextSha256: "b".repeat(64),
  systemContextBlockCount: 2,
  promptTemplateId: "ai4heor/heor-workbench-preamble",
  promptTemplateSha256: "a".repeat(64),
  responseLanguage: "Simplified Chinese",
  eventHash: "c".repeat(64),
};

describe("ModelCallAudit", () => {
  beforeEach(() => mocks.listModelCalls.mockReset());

  it("shows content-free details for the exact linked assistant call", async () => {
    mocks.listModelCalls.mockResolvedValue([record]);
    render(<ModelCallAudit assistantMessageId="msg_assistant_1" sessionId="ses_1" />);

    await userEvent.click(screen.getByRole("button", { name: "Model call record" }));
    expect(await screen.findByText("minimax-cn / MiniMax-M3")).toBeInTheDocument();
    expect(screen.getByText("Input 120")).toBeInTheDocument();
    expect(screen.getByText("Output 45")).toBeInTheDocument();
    expect(screen.getByText("ai4heor/heor-workbench-preamble")).toBeInTheDocument();
    expect(screen.getByText("Research constraints recorded")).toBeInTheDocument();
    expect(screen.getByText("Simplified Chinese")).toBeInTheDocument();
    expect(screen.getByText(/0\.0123/)).toBeInTheDocument();
    expect(screen.queryByText("msg_assistant_1")).not.toBeInTheDocument();
    expect(screen.queryByText("call_internal_1")).not.toBeInTheDocument();
    expect(screen.queryByText("b".repeat(64))).not.toBeInTheDocument();
  });

  it("does not guess when the linked call is absent", async () => {
    mocks.listModelCalls.mockResolvedValue([]);
    render(<ModelCallAudit assistantMessageId="msg_missing" sessionId="ses_1" />);

    await userEvent.click(screen.getByRole("button", { name: "Model call record" }));
    expect(await screen.findByText("No matching model-call record was found.")).toBeInTheDocument();
  });

  it("reports an unreadable ledger instead of hiding the failure", async () => {
    mocks.listModelCalls.mockResolvedValue({
      find: () => {
        throw new Error("hash chain mismatch");
      },
    });
    render(<ModelCallAudit assistantMessageId="msg_assistant_1" sessionId="ses_1" />);

    await userEvent.click(screen.getByRole("button", { name: "Model call record" }));
    expect(mocks.listModelCalls).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Model-call record could not be read.")).toBeInTheDocument();
  });
});

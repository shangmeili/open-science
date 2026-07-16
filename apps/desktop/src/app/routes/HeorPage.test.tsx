import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { renderAt } from "@/test/render";
import { useRuntimeStore } from "@/lib/runtime";
import { useUiStore } from "@/lib/store";

const defaults = {
  status: useRuntimeStore.getState().status,
  currentId: useRuntimeStore.getState().currentId,
  defaultModel: useRuntimeStore.getState().defaultModel,
  sendPrompt: useRuntimeStore.getState().sendPrompt,
};

afterEach(() => {
  useRuntimeStore.setState(defaults);
  useUiStore.getState().setComposerDraft(null);
  useUiStore.getState().setLocale("en");
});

describe("AI4HEOR conversation route", () => {
  it("makes natural-language research the primary empty state", async () => {
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: "openai/gpt-5.2",
    });
    renderAt("/heor");

    expect(
      await screen.findByRole("heading", { name: "Start with the research question" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/forms stay secondary/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Describe the decision problem/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review analysis" })).toBeInTheDocument();
  });

  it("keeps starter requests as Human-reviewed drafts", async () => {
    const sendPrompt = vi.fn().mockResolvedValue("session-1");
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: "openai/gpt-5.2",
      sendPrompt,
    });
    renderAt("/heor");

    await userEvent.click(
      await screen.findByRole("button", { name: /Frame a cost-effectiveness study/i }),
    );

    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain(
      "Help me frame a cost-effectiveness study",
    );
    expect(sendPrompt).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("blocks agent turns until a model is explicitly selected", async () => {
    const sendPrompt = vi.fn().mockResolvedValue("session-1");
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: null,
      sendPrompt,
    });
    renderAt("/heor");

    expect(await screen.findByText("Choose a model before sending")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Frame a cost-effectiveness study/i }));

    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain(
      "Help me frame a cost-effectiveness study",
    );
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(sendPrompt).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Open model settings" })).toBeInTheDocument();
  });
});

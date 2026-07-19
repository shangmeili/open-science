import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { renderAt } from "@/test/render";
import { useRuntimeStore } from "@/lib/runtime";
import { useUiStore } from "@/lib/store";
import { AI4HEOR_FIRST_RUN_KEY } from "@/components/heor/FirstRunGuide";

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
  window.localStorage.removeItem(AI4HEOR_FIRST_RUN_KEY);
});

describe("AI4HEOR conversation route", () => {
  it("explains the first-run local, model, approval, and Human boundaries without a form", async () => {
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: null,
    });
    renderAt("/heor");

    expect(await screen.findByRole("heading", { name: "Begin with you in control" }))
      .toBeInTheDocument();
    expect(screen.getByText("Local by default")).toBeInTheDocument();
    expect(screen.getByText("Your choice of model")).toBeInTheDocument();
    expect(screen.getByText("Actions remain reviewable")).toBeInTheDocument();
    expect(screen.getByText("Human scientific authority")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /provider|api key|workspace/i }))
      .not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Enter the HEOR workspace" }));

    expect(screen.queryByRole("heading", { name: "Begin with you in control" }))
      .not.toBeInTheDocument();
    expect(window.localStorage.getItem(AI4HEOR_FIRST_RUN_KEY)).toBe("complete");
    expect(screen.getByRole("heading", { name: "Start with the research question" }))
      .toBeInTheDocument();
  });

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
    expect(screen.getByText(/You frame the question and make scientific choices/i))
      .toBeInTheDocument();
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

  it("starts local-library learning as a Human-reviewed natural-language draft", async () => {
    const sendPrompt = vi.fn().mockResolvedValue("session-1");
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: "openai/gpt-5.2",
      sendPrompt,
    });
    renderAt("/heor");

    await userEvent.click(
      await screen.findByRole("button", { name: /Learn from my local HEOR library/i }),
    );

    const draft = (screen.getByRole("textbox") as HTMLTextAreaElement).value;
    expect(draft).toContain("$heor-local-evidence");
    expect(draft).toContain("First ask what I want to learn and my current level");
    expect(draft).toContain("Do not use the network");
    expect(sendPrompt).not.toHaveBeenCalled();
  });

  it("prepares the deterministic teaching example without starting an agent turn", async () => {
    const sendPrompt = vi.fn().mockResolvedValue("session-1");
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: "openai/gpt-5.2",
      sendPrompt,
    });
    renderAt("/heor");

    await userEvent.click(
      await screen.findByRole("button", {
        name: /Run the cost-effectiveness teaching example/i,
      }),
    );

    const draft = (screen.getByRole("textbox") as HTMLTextAreaElement).value;
    expect(draft).toContain("python run_analysis.py --check expected/base-case-result.json");
    expect(draft).toContain("ask me whether to continue");
    expect(sendPrompt).not.toHaveBeenCalled();
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

import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { renderAt, renderNavigableAt } from "@/test/render";
import { useRuntimeStore } from "@/lib/runtime";
import { useUiStore } from "@/lib/store";
import { AI4HEOR_FIRST_RUN_KEY } from "@/components/heor/FirstRunGuide";

const defaults = {
  status: useRuntimeStore.getState().status,
  currentId: useRuntimeStore.getState().currentId,
  draftEpoch: useRuntimeStore.getState().draftEpoch,
  defaultModel: useRuntimeStore.getState().defaultModel,
  sendPrompt: useRuntimeStore.getState().sendPrompt,
  workspacePinned: useRuntimeStore.getState().workspacePinned,
  workspace: useRuntimeStore.getState().workspace,
  projects: useRuntimeStore.getState().projects,
  researchScope: useRuntimeStore.getState().researchScope,
  openSession: useRuntimeStore.getState().openSession,
  threads: useRuntimeStore.getState().threads,
  runningSessions: useRuntimeStore.getState().runningSessions,
};

afterEach(() => {
  useRuntimeStore.setState(defaults);
  useUiStore.getState().setComposerDraft(null);
  useUiStore.getState().setLocale("en");
  useUiStore.setState({ taskProjectPlacement: {} });
  window.localStorage.removeItem("ai4s.taskProjectPlacement");
  window.localStorage.removeItem(AI4HEOR_FIRST_RUN_KEY);
});

describe("AI4HEOR conversation route", () => {
  it("explains the first-run local, model, approval, and Human boundaries without a form", async () => {
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: null,
    });
    renderNavigableAt("/heor");

    expect(await screen.findByRole("heading", { name: "Before you begin" }))
      .toBeInTheDocument();
    expect(screen.getByText("Local by default")).toBeInTheDocument();
    expect(screen.getByText("Your choice of model")).toBeInTheDocument();
    expect(screen.getByText("Actions remain reviewable")).toBeInTheDocument();
    expect(screen.getByText("You review key research decisions")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /provider|api key|workspace/i }))
      .not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Enter the HEOR workspace" }));

    expect(screen.queryByRole("heading", { name: "Before you begin" }))
      .not.toBeInTheDocument();
    expect(window.localStorage.getItem(AI4HEOR_FIRST_RUN_KEY)).toBe("complete");
    expect(screen.getByRole("heading", { name: "What are you working on?" }))
      .toBeInTheDocument();
  });

  it("keeps the workbench as a guided HEOR starting surface, not a second blank task", async () => {
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: "openai/gpt-5.2",
    });
    renderNavigableAt("/heor");

    expect(
      await screen.findByRole("heading", { name: "What are you working on?" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Describe the pharmacoeconomic or HEOR task in your own words/i))
      .toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Research & analysis" })).not.toBeInTheDocument();
  });

  it("keeps a new task unconstrained while HEOR suggestions only prefill the draft", async () => {
    const sendPrompt = vi.fn().mockResolvedValue("session-1");
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: "openai/gpt-5.2",
      sendPrompt,
      workspacePinned: false,
    });
    renderNavigableAt("/heor/new");

    expect(
      await screen.findByRole("heading", { name: "What HEOR work would you like to tackle today?" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("ai4heor-new-task-wordmark")).toHaveAttribute(
      "src",
      expect.stringContaining("ai4heor-wordmark-light.png"),
    );
    expect(screen.getByRole("button", { name: "Frame the research question" }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Find and organize evidence" }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Design or review a model" }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze data or prepare a briefing" }))
      .toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Learn pharmacoeconomics fundamentals" }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open the complete cost–utility teaching case" }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Research & analysis" }))
      .not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Find and organize evidence" }));
    const input = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(input.value).toContain("Help me find and organize the evidence needed");
    expect(sendPrompt).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Design or review a model" }));
    expect(input.value).toContain("Help me design or review this health economic model");
    expect(input.value).not.toContain("Help me find and organize the evidence needed");

    await userEvent.clear(input);
    await userEvent.type(input, "A completely different task");
    expect(input.value).toBe("A completely different task");
    expect(sendPrompt).not.toHaveBeenCalled();
  });

  it("does not carry the previous project label into a standalone new task", async () => {
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: "openai/gpt-5.2",
      workspace: "/research/dapagliflozin",
      workspacePinned: false,
      projects: [{
        id: "project-dapagliflozin",
        name: "Dapagliflozin",
        path: "/research/dapagliflozin",
        createdAt: 1,
        pinned: true,
      }],
      researchScope: {
        id: "project-dapagliflozin",
        name: "Dapagliflozin",
        path: "/research/dapagliflozin",
        createdAt: 1,
        kind: "heor",
      },
    });
    renderNavigableAt("/heor/new");

    const input = await screen.findByRole("textbox");
    expect(within(input.parentElement!).queryByText("Dapagliflozin"))
      .not.toBeInTheDocument();

    useRuntimeStore.setState({ workspacePinned: true });
    expect(await within(input.parentElement!).findByText("Dapagliflozin"))
      .toBeInTheDocument();
  });

  it("uses explicit task placement instead of a stale session directory for project context", async () => {
    useRuntimeStore.setState({
      status: "ready",
      currentId: "session-1",
      defaultModel: "openai/gpt-5.2",
      workspace: "/research/project-a",
      workspacePinned: true,
      sessions: [{ id: "session-1", title: "CEA", directory: "/research/project-a" }],
      projects: [{
        id: "project-a",
        name: "Project A",
        path: "/research/project-a",
        createdAt: 1,
        pinned: true,
      }],
      openSession: vi.fn().mockResolvedValue(undefined),
      threads: {
        "session-1": { loaded: true, blocks: [], index: {} },
      },
    });
    useUiStore.setState({ taskProjectPlacement: { "session-1": null } });
    renderNavigableAt("/heor/session-1");

    const input = await screen.findByRole("textbox");
    expect(within(input.parentElement!).queryByText("Project A")).not.toBeInTheDocument();

    useUiStore.getState().moveTaskToProject("session-1", "project-a");
    expect(await within(input.parentElement!).findByText("Project A")).toBeInTheDocument();
  });

  it("sends the HEOR contract privately while echoing only the researcher's words", async () => {
    const sendPrompt = vi.fn().mockResolvedValue("session-1");
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: "openai/gpt-5.2",
      sendPrompt,
      workspacePinned: true,
    });
    renderNavigableAt("/heor/new");

    const input = await screen.findByRole("textbox");
    await userEvent.type(input, "评价达格列净的成本效果");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(sendPrompt).toHaveBeenCalledTimes(1);
    expect(sendPrompt.mock.calls[0][0]).toContain("Use $heor-workbench");
    expect(sendPrompt.mock.calls[0][0]).toContain("评价达格列净的成本效果");
    expect(sendPrompt.mock.calls[0][1]).toBe("评价达格列净的成本效果");
  });

  it("shows research tools after a task has an actual session scope", async () => {
    useRuntimeStore.setState({
      status: "ready",
      currentId: "session-1",
      defaultModel: "openai/gpt-5.2",
      openSession: vi.fn().mockResolvedValue(undefined),
      threads: {
        "session-1": { loaded: true, blocks: [], index: {} },
      },
    });
    renderNavigableAt("/heor/session-1");

    expect(await screen.findByRole("button", { name: "Research & analysis" }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run history" })).toBeInTheDocument();
  });

  it("surfaces the HEOR pane when an active task creates a structured search request", async () => {
    useRuntimeStore.setState({
      status: "ready",
      currentId: "session-search",
      defaultModel: "openai/gpt-5.2",
      workspacePinned: true,
      openSession: vi.fn().mockResolvedValue(undefined),
      runningSessions: { "session-search": true },
      threads: {
        "session-search": {
          loaded: true,
          index: {},
          blocks: [{
            kind: "artifact",
            path: "heor/evidence-search-request.json",
            filename: "evidence-search-request.json",
            artifact: "data",
            tool: "write",
          }],
        },
      },
    });
    renderNavigableAt("/heor/session-search");

    expect(await screen.findByRole("button", { name: "Research & analysis" }))
      .toHaveAttribute("aria-pressed", "true");
  });

  it("uses the AI4HEOR research surface for legacy live links", async () => {
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: "openai/gpt-5.2",
    });
    renderAt("/live");

    expect(await screen.findByRole("heading", { name: "What are you working on?" }))
      .toBeInTheDocument();
    expect(screen.getByText("Learn pharmacoeconomics fundamentals")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/climate trends|end-to-end demo/i)).not.toBeInTheDocument();
  });

  it("keeps starter requests as Human-reviewed drafts", async () => {
    const sendPrompt = vi.fn().mockResolvedValue("session-1");
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: "openai/gpt-5.2",
      sendPrompt,
    });
    renderNavigableAt("/heor");

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
    renderNavigableAt("/heor");

    await userEvent.click(
      await screen.findByRole("button", { name: /Learn pharmacoeconomics fundamentals/i }),
    );

    const draft = (screen.getByRole("textbox") as HTMLTextAreaElement).value;
    expect(draft).toContain("prepared AI4HEOR learning library");
    expect(draft).toContain(
      "First ask about the topic I want to study, what I already know, and the time I have available",
    );
    expect(draft).toContain("instead of offering uncited model knowledge");
    expect(draft).not.toContain("SHA-256");
    expect(sendPrompt).not.toHaveBeenCalled();
  });

  it("previews the teaching example in place without claiming a desktop install", async () => {
    const sendPrompt = vi.fn().mockResolvedValue("session-1");
    useRuntimeStore.setState({
      status: "ready",
      currentId: null,
      defaultModel: "openai/gpt-5.2",
      sendPrompt,
    });
    renderNavigableAt("/heor");

    await userEvent.click(
      await screen.findByRole("button", {
        name: /Open the complete cost–utility teaching case/i,
      }),
    );

    expect(
      await screen.findByText("Preview of the complete teaching case"),
    ).toBeInTheDocument();
    expect(screen.getByText(/hypothetical population/i)).toBeInTheDocument();
    expect(screen.getByText("Available in the desktop app")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run the complete case" }))
      .not.toBeInTheDocument();
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
    renderNavigableAt("/heor");

    await userEvent.click(screen.getByRole("button", { name: /Frame a cost-effectiveness study/i }));

    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain(
      "Help me frame a cost-effectiveness study",
    );
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(sendPrompt).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText("Describe the research question or work you want to address…"))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose a model" })).toBeInTheDocument();
  });
});

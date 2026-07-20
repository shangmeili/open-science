import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRuntimeStore } from "@/lib/runtime";
import { useUiStore } from "@/lib/store";
import { renderAt, renderNavigableAt } from "@/test/render";

const PROJECT = {
  id: "p1",
  name: "Cost Effectiveness Study",
  createdAt: 1,
  kind: "heor" as const,
  path: "/base/Cost-Effectiveness-Study",
};

const defaults = {
  status: useRuntimeStore.getState().status,
  defaultModel: useRuntimeStore.getState().defaultModel,
  draftEpoch: useRuntimeStore.getState().draftEpoch,
  workspacePinned: useRuntimeStore.getState().workspacePinned,
  researchScope: useRuntimeStore.getState().researchScope,
  createProject: useRuntimeStore.getState().createProject,
  startDraft: useRuntimeStore.getState().startDraft,
};

afterEach(() => {
  useRuntimeStore.setState({
    ...defaults,
    projects: [],
    sessions: [],
    workspace: null,
    workspacePinned: false,
    researchScope: null,
  });
  useUiStore.getState().setComposerDraft(null);
});

describe("Sidebar projects", () => {
  it("groups sessions into their project and keeps the rest loose", async () => {
    useRuntimeStore.setState({
      projects: [PROJECT],
      sessions: [
        { id: "in", title: "paper search", directory: PROJECT.path },
        { id: "out", title: "quick question", directory: "/base/2026-07-01-0900" },
        // Subagent sessions never get a row, project or not.
        { id: "child", title: "subtask", directory: PROJECT.path, parentId: "in" },
      ],
    });
    renderAt("/files");

    expect(await screen.findByText("Cost Effectiveness Study")).toBeInTheDocument();
    // Both groups render their sessions; the child session does not appear.
    expect(screen.getByText("paper search")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /paper search/i })).toHaveAttribute(
      "href",
      "/heor/in",
    );
    expect(screen.getByText("quick question")).toBeInTheDocument();
    expect(screen.getByText("Tasks")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /quick question/i })).toHaveAttribute(
      "href",
      "/heor/out",
    );
    expect(screen.queryByText("subtask")).not.toBeInTheDocument();
    // The project offers its own new-task entry point.
    expect(
      screen.getByRole("button", { name: "New task in Cost Effectiveness Study" }),
    ).toBeInTheDocument();
  });

  it("offers a new-project entry when no projects exist yet", async () => {
    renderAt("/files");
    // Header [+] plus the ghost row — both open the inline name input.
    expect((await screen.findAllByRole("button", { name: "New project" })).length).toBeGreaterThan(0);
    expect(screen.queryByText("Cross-species atlas figure")).not.toBeInTheDocument();
    expect(screen.queryByText("SCVI Hyperparameter Screen")).not.toBeInTheDocument();
    expect(screen.getByText("Tasks")).toBeInTheDocument();
  });

  it("opens a visible clean task, focuses it, and resets it on every click", async () => {
    const createProject = vi.fn().mockResolvedValue(PROJECT);
    const startDraft = vi.fn(() => defaults.startDraft());
    useRuntimeStore.setState({
      projects: [],
      sessions: [],
      workspace: null,
      status: "ready",
      defaultModel: "openai/gpt-5.2",
      createProject,
      startDraft,
    });
    renderNavigableAt("/heor");

    await userEvent.click(
      await screen.findByRole("button", { name: "New task" }),
    );

    expect(startDraft).toHaveBeenCalledTimes(1);
    expect(createProject).not.toHaveBeenCalled();
    expect(await screen.findByRole("heading", { name: "What HEOR work would you like to tackle today?" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "What are you working on?" })).not.toBeInTheDocument();

    const firstInput = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(firstInput).toHaveFocus();
    await userEvent.type(firstInput, "draft that must be cleared");
    expect(firstInput.value).toBe("draft that must be cleared");

    await userEvent.click(screen.getByRole("button", { name: "New task" }));
    const resetInput = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(startDraft).toHaveBeenCalledTimes(2);
    expect(resetInput.value).toBe("");
    expect(resetInput).toHaveFocus();
  });

  it("uses the AI4HEOR brand as the only research-workspace home entry", async () => {
    useRuntimeStore.setState({
      projects: [],
      sessions: [],
      workspace: null,
      status: "ready",
      defaultModel: "openai/gpt-5.2",
    });
    renderNavigableAt("/heor/new");

    expect(await screen.findByRole("heading", { name: "What HEOR work would you like to tackle today?" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Research workspace" }));
    expect(await screen.findByRole("heading", { name: "What are you working on?" })).toBeInTheDocument();
  });

  it("keeps an explicit project flow for work that should share context", async () => {
    const createProject = vi.fn().mockResolvedValue(PROJECT);
    useRuntimeStore.setState({
      projects: [],
      sessions: [],
      workspace: null,
      createProject,
    });
    renderNavigableAt("/heor");

    await userEvent.click((await screen.findAllByRole("button", { name: "New project" }))[0]);
    const input = screen.getByPlaceholderText("Project name");
    await userEvent.type(input, `${PROJECT.name}{Enter}`);

    expect(createProject).toHaveBeenCalledWith(PROJECT.name);
    const draft = (screen.getByRole("textbox") as HTMLTextAreaElement).value;
    expect(draft).toContain("Help me start this HEOR project");
  });
});

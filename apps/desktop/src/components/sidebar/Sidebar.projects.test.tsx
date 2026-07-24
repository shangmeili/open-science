import { fireEvent, screen } from "@testing-library/react";
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
  currentId: useRuntimeStore.getState().currentId,
  draftEpoch: useRuntimeStore.getState().draftEpoch,
  panes: useRuntimeStore.getState().panes,
  workspacePinned: useRuntimeStore.getState().workspacePinned,
  researchScope: useRuntimeStore.getState().researchScope,
  createProject: useRuntimeStore.getState().createProject,
  importProject: useRuntimeStore.getState().importProject,
  startDraft: useRuntimeStore.getState().startDraft,
  openSession: useRuntimeStore.getState().openSession,
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
    expect(
      screen.getByRole("button", { name: "More: Cost Effectiveness Study" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More: paper search" })).toBeInTheDocument();
  });

  it("uses the Codex-style task actions instead of the browser link menu", async () => {
    const renameSession = vi.fn(async () => {});
    useRuntimeStore.setState({
      projects: [],
      sessions: [{ id: "task-1", title: "CEA review", directory: "/base/task-1" }],
      renameSession,
    });
    renderAt("/files");

    const task = await screen.findByRole("link", { name: /CEA review/i });
    fireEvent.contextMenu(task);

    expect(await screen.findByRole("menuitem", { name: "Rename task" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete task" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Open task" })).not.toBeInTheDocument();
    expect(screen.queryByText("Open link in new window")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("menuitem", { name: "Rename task" }));
    const input = screen.getByDisplayValue("CEA review");
    await userEvent.clear(input);
    await userEvent.type(input, "Updated CEA review{Enter}");
    expect(renameSession).toHaveBeenCalledWith("task-1", "Updated CEA review");
  });

  it("opens a task action menu at the visible more button instead of the window origin", async () => {
    useRuntimeStore.setState({
      projects: [],
      sessions: [{ id: "task-1", title: "CEA review", directory: "/base/task-1" }],
    });
    renderAt("/files");

    const button = await screen.findByRole("button", { name: "More: CEA review" });
    vi.spyOn(button, "getBoundingClientRect").mockReturnValue({
      x: 190,
      y: 260,
      left: 190,
      top: 260,
      right: 214,
      bottom: 284,
      width: 24,
      height: 24,
      toJSON: () => ({}),
    });
    const anchor = button.closest("[data-sidebar-context-anchor]");
    const contextEvent = vi.fn();
    anchor?.addEventListener("contextmenu", contextEvent);

    await userEvent.click(button);

    expect(contextEvent).toHaveBeenCalledTimes(1);
    expect(contextEvent.mock.calls[0][0]).toMatchObject({ clientX: 214, clientY: 284 });
    expect(await screen.findByRole("menuitem", { name: "Rename task" })).toBeInTheDocument();
  });

  it("uses a Codex-style project menu instead of the host browser menu", async () => {
    useRuntimeStore.setState({ projects: [PROJECT], sessions: [] });
    renderAt("/files");

    const projectButton = (await screen.findByText(PROJECT.name)).closest("button");
    expect(projectButton).not.toBeNull();
    fireEvent.contextMenu(projectButton!);

    expect(await screen.findByRole("menuitem", { name: "New task" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Rename" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Show in file manager" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Remove" })).toBeInTheDocument();
    expect(screen.queryByText("Back")).not.toBeInTheDocument();
    expect(screen.queryByText("Reload")).not.toBeInTheDocument();
  });

  it("opens a project action menu at the visible more button instead of the window origin", async () => {
    useRuntimeStore.setState({ projects: [PROJECT], sessions: [] });
    renderAt("/files");

    const button = await screen.findByRole("button", { name: `More: ${PROJECT.name}` });
    vi.spyOn(button, "getBoundingClientRect").mockReturnValue({
      x: 188,
      y: 206,
      left: 188,
      top: 206,
      right: 212,
      bottom: 230,
      width: 24,
      height: 24,
      toJSON: () => ({}),
    });
    const anchor = button.closest("[data-sidebar-context-anchor]");
    const contextEvent = vi.fn();
    anchor?.addEventListener("contextmenu", contextEvent);

    await userEvent.click(button);

    expect(contextEvent).toHaveBeenCalledTimes(1);
    expect(contextEvent.mock.calls[0][0]).toMatchObject({ clientX: 212, clientY: 230 });
    expect(await screen.findByRole("menuitem", { name: "Rename" })).toBeInTheDocument();
  });

  it("switches the single task side pane between research review and analysis history", async () => {
    const openSession = vi.fn(async () => {});
    useRuntimeStore.setState({
      status: "ready",
      currentId: "task-1",
      workspace: "/base/task-1",
      sessions: [{ id: "task-1", title: "CEA review", directory: "/base/task-1" }],
      panes: {
        "task-1": { artifact: null, showFiles: false, showRuns: false },
      },
      openSession,
    });
    renderNavigableAt("/heor/task-1");

    const review = await screen.findByRole("button", { name: "Research & analysis" });
    await userEvent.click(review);
    expect(review).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("Research materials, analysis records, and decisions awaiting your review")).toBeInTheDocument();

    const runs = screen.getByRole("button", { name: "Run history" });
    await userEvent.click(runs);
    expect(runs).toHaveAttribute("aria-pressed", "true");
    expect(review).toHaveAttribute("aria-pressed", "false");
    expect((await screen.findAllByText("Run history")).length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("Research materials, analysis records, and decisions awaiting your review")).not.toBeInTheDocument();
  });

  it("offers a new-project entry when no projects exist yet", async () => {
    renderAt("/files");
    // Header [+] plus the ghost row — both open the inline name input.
    expect((await screen.findAllByRole("button", { name: "New project" })).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "More" }));
    expect(await screen.findByRole("menuitem", { name: "Import existing project" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByText("Cross-species atlas figure")).not.toBeInTheDocument();
    expect(screen.queryByText("SCVI Hyperparameter Screen")).not.toBeInTheDocument();
    expect(screen.getByText("Tasks")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More: Tasks" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "New task" }).length).toBeGreaterThan(1);
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

    await userEvent.click((await screen.findAllByRole("button", { name: "New task" }))[0]);

    expect(startDraft).toHaveBeenCalledTimes(1);
    expect(createProject).not.toHaveBeenCalled();
    expect(await screen.findByRole("heading", { name: "What HEOR work would you like to tackle today?" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "What are you working on?" })).not.toBeInTheDocument();

    const firstInput = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(firstInput).toHaveFocus();
    await userEvent.type(firstInput, "draft that must be cleared");
    expect(firstInput.value).toBe("draft that must be cleared");

    await userEvent.click(screen.getAllByRole("button", { name: "New task" })[0]);
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
    expect(screen.getByTestId("ai4heor-brand-wordmark")).toHaveAttribute(
      "src",
      expect.stringContaining("ai4heor-wordmark-light.svg"),
    );
    expect(screen.getByTestId("ai4heor-brand-wordmark")).toHaveClass("w-[100px]");
    await userEvent.click(screen.getByRole("button", { name: "Research workspace" }));
    expect(await screen.findByRole("heading", { name: "What are you working on?" })).toBeInTheDocument();
    expect(screen.queryByText("Beta")).not.toBeInTheDocument();
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
    expect(input).not.toHaveAttribute("data-focus-style");
    expect(input).toHaveClass("border-border");
    expect(input).not.toHaveClass(
      "border-accent/50",
      "focus:border-accent",
      "focus:border-muted",
      "focus:ring-border",
    );
    await userEvent.type(input, `${PROJECT.name}{Enter}`);

    expect(createProject).toHaveBeenCalledWith(PROJECT.name);
    const draft = (screen.getByRole("textbox") as HTMLTextAreaElement).value;
    expect(draft).toContain("Help me start this HEOR project");
  });
});

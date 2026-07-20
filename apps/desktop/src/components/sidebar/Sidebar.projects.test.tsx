import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRuntimeStore } from "@/lib/runtime";
import { useUiStore } from "@/lib/store";
import { renderAt } from "@/test/render";

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
  createProject: useRuntimeStore.getState().createProject,
  startDraft: useRuntimeStore.getState().startDraft,
};

afterEach(() => {
  useRuntimeStore.setState({
    ...defaults,
    projects: [],
    sessions: [],
    workspace: null,
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
    expect(screen.getByText("Standalone conversations")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /quick question/i })).toHaveAttribute(
      "href",
      "/heor/out",
    );
    expect(screen.queryByText("subtask")).not.toBeInTheDocument();
    // The project offers its own "new session" entry point.
    expect(
      screen.getByRole("button", { name: "New session in Cost Effectiveness Study" }),
    ).toBeInTheDocument();
  });

  it("offers a new-project entry when no projects exist yet", async () => {
    renderAt("/files");
    // Header [+] plus the ghost row — both open the inline name input.
    expect((await screen.findAllByRole("button", { name: "New project" })).length).toBeGreaterThan(0);
    expect(screen.queryByText("Cross-species atlas figure")).not.toBeInTheDocument();
    expect(screen.queryByText("SCVI Hyperparameter Screen")).not.toBeInTheDocument();
    expect(screen.getByText("Standalone conversations")).toBeInTheDocument();
  });

  it("starts a standalone conversation without creating or selecting a project", async () => {
    const createProject = vi.fn().mockResolvedValue(PROJECT);
    const startDraft = vi.fn();
    useRuntimeStore.setState({
      projects: [],
      sessions: [],
      workspace: null,
      status: "ready",
      defaultModel: "openai/gpt-5.2",
      createProject,
      startDraft,
    });
    renderAt("/heor");

    await userEvent.click(
      await screen.findByRole("button", { name: "New conversation" }),
    );

    expect(startDraft).toHaveBeenCalledTimes(1);
    expect(createProject).not.toHaveBeenCalled();
  });

  it("keeps an explicit project flow for work that should share context", async () => {
    const createProject = vi.fn().mockResolvedValue(PROJECT);
    useRuntimeStore.setState({
      projects: [],
      sessions: [],
      workspace: null,
      createProject,
    });
    renderAt("/heor");

    await userEvent.click((await screen.findAllByRole("button", { name: "New project" }))[0]);
    const input = screen.getByPlaceholderText("Project name");
    await userEvent.type(input, `${PROJECT.name}{Enter}`);

    expect(createProject).toHaveBeenCalledWith(PROJECT.name);
    const draft = (screen.getByRole("textbox") as HTMLTextAreaElement).value;
    expect(draft).toContain("Help me start this HEOR project");
  });
});

import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useRuntimeStore } from "@/lib/runtime";
import { renderAt } from "@/test/render";

const PROJECT = {
  id: "p1",
  name: "Cost Effectiveness Study",
  createdAt: 1,
  path: "/base/Cost-Effectiveness-Study",
};

afterEach(() =>
  useRuntimeStore.setState({ projects: [], sessions: [], workspace: null }),
);

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
    expect(screen.getByText("quick question")).toBeInTheDocument();
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
  });
});

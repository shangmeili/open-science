import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { renderAt, renderNavigableAt } from "@/test/render";
import { useUiStore } from "@/lib/store";
import { useRuntimeStore } from "@/lib/runtime";

// COPYCAT RULE: useUiStore is module-global; reset the locale after each test
// so this suite never bleeds a non-English locale into other test files.
afterEach(() => {
  useUiStore.getState().setLocale("en");
  useUiStore.getState().setComposerDraft(null);
  useUiStore.getState().setComposerSkill(null);
});

// COPYCAT RULE: useRuntimeStore is also module-global — restore the
// disconnected default after any test that fakes a "ready" runtime.
const RUNTIME_DEFAULTS = {
  status: useRuntimeStore.getState().status,
  agents: useRuntimeStore.getState().agents,
  skills: useRuntimeStore.getState().skills,
  currentId: useRuntimeStore.getState().currentId,
  draftEpoch: useRuntimeStore.getState().draftEpoch,
  workspace: useRuntimeStore.getState().workspace,
  workspacePinned: useRuntimeStore.getState().workspacePinned,
  projects: useRuntimeStore.getState().projects,
  researchScope: useRuntimeStore.getState().researchScope,
};
afterEach(() => useRuntimeStore.setState(RUNTIME_DEFAULTS));

describe("NotebooksPage strings (i18n)", () => {
  it("renders the page heading and the desktop-only empty state in English", async () => {
    renderAt("/notebooks");
    expect(await screen.findByRole("heading", { level: 1, name: "Analysis notes" })).toBeInTheDocument();
    expect(screen.getByText("Notebooks are available in the desktop app.")).toBeInTheDocument();
    expect(screen.getByText("New notebook")).toBeInTheDocument();
  });
});

describe("FilesPage strings (i18n)", () => {
  it("renders the desktop-only explorer message and the preview prompt in English", async () => {
    renderAt("/files");
    expect(await screen.findByText("The file explorer is available in the desktop app.")).toBeInTheDocument();
    expect(screen.getByText("Select a file to preview it here.")).toBeInTheDocument();
  });
});

describe("SkillsPage strings (i18n)", () => {
  it("uses research-facing copy and hides implementation paths in English", async () => {
    renderAt("/skills");
    expect(await screen.findByRole("heading", { level: 1, name: "Plugins & skills" })).toBeInTheDocument();
    expect(screen.getByText("Add a research capability")).toBeInTheDocument();
    expect(screen.queryByText(/\.opencode\/skills/)).not.toBeInTheDocument();
    expect(screen.queryByText("Node.js")).not.toBeInTheDocument();
    expect(
      await screen.findByText(
        "External tools could not be checked, so none were enabled.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Connect the local assistant to view available research capabilities."),
    ).toBeInTheDocument();
  });

  it("translates the known agent-mode badge and falls back to the raw value for an unknown mode", async () => {
    useRuntimeStore.setState({
      status: "ready",
      agents: [
        { name: "build", description: "Primary build agent", mode: "primary" },
        { name: "custom-thing", description: "Some external agent", mode: "future-mode" },
      ],
    });
    renderAt("/skills");
    expect(await screen.findByText("build")).toBeInTheDocument();
    expect(screen.getByText("primary")).toBeInTheDocument();
    // Unknown mode values (outside the closed set OpenCode emits) render raw, unmodified.
    expect(screen.getByText("future-mode")).toBeInTheDocument();
  });

  it("shows only user-facing AI4HEOR skills and opens a ready-to-edit task when Use is clicked", async () => {
    useRuntimeStore.setState({
      status: "ready",
      skills: [
        {
          name: "customize-opencode",
          description: "Edit OpenCode configuration.",
          location: "/runtime/builtin/customize-opencode/SKILL.md",
        },
        {
          name: "heor-workbench",
          description: "Support HEOR research work.",
          location: "/app/skills/heor-workbench/SKILL.md",
        },
      ],
      workspace: "/research/2026-07-20-1408",
      workspacePinned: true,
      projects: [],
      researchScope: {
        id: "standalone-task",
        name: "2026-07-20-1408",
        createdAt: 1,
        kind: "session",
        path: "/research/2026-07-20-1408",
      },
    });

    renderNavigableAt("/skills");
    expect(await screen.findByText("AI4HEOR Research Workbench")).toBeInTheDocument();
    expect(screen.queryByText("customize-opencode")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use" }));
    expect(await screen.findByLabelText("Ask anything")).toHaveValue("");
    expect(screen.getByPlaceholderText("Describe what you want AI4HEOR Research Workbench to help with"))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove AI4HEOR Research Workbench" }))
      .toBeInTheDocument();
    expect(screen.queryByText("2026-07-20-1408")).not.toBeInTheDocument();
    expect(useRuntimeStore.getState().workspacePinned).toBe(false);
  });
});

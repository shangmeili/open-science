import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRuntimeStore } from "@/lib/runtime";

const mocks = vi.hoisted(() => ({
  audit: vi.fn(),
}));

vi.mock("@/lib/tauri", async () => {
  const actual = await vi.importActual<typeof import("@/lib/tauri")>("@/lib/tauri");
  return {
    ...actual,
    isTauri: true,
    auditStartupEnvironment: mocks.audit,
  };
});

import { StartupReadiness } from "./StartupReadiness";

const original = {
  status: useRuntimeStore.getState().status,
  defaultModel: useRuntimeStore.getState().defaultModel,
  restartLocalRuntime: useRuntimeStore.getState().restartLocalRuntime,
};

const readyAudit = {
  desktop: true,
  requiredReady: true,
  workspacePath: "/Users/researcher/Documents/AI4HEOR",
  checks: [
    { id: "workspace", ready: true, detail: "/Users/researcher/Documents/AI4HEOR" },
    { id: "skills", ready: true, detail: "48" },
    { id: "heorCore", ready: true, detail: "3/3" },
    { id: "harness", ready: true, detail: "4/4" },
  ],
};

beforeEach(() => {
  mocks.audit.mockReset();
  mocks.audit.mockResolvedValue(readyAudit);
  useRuntimeStore.setState({
    status: "ready",
    defaultModel: null,
    restartLocalRuntime: original.restartLocalRuntime,
  });
});

afterEach(() => {
  cleanup();
  useRuntimeStore.setState(original);
});

describe("StartupReadiness", () => {
  it("separates required local readiness from an optional model", async () => {
    render(<StartupReadiness />);

    expect(await screen.findByText("Ready to work")).toBeInTheDocument();
    expect(screen.getByText("48 Skills available")).toBeInTheDocument();
    expect(screen.getByText("Model (optional)")).toBeInTheDocument();
    expect(screen.getByText("Not connected — local calculations still work")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restart local assistant" })).not.toBeInTheDocument();
  });

  it("shows a real process-restart action when the local assistant needs attention", async () => {
    const restart = vi.fn(async () => {
      useRuntimeStore.setState({ status: "ready", error: null });
      return true;
    });
    useRuntimeStore.setState({
      status: "error",
      error: "runtime stopped",
      restartLocalRuntime: restart,
    });

    render(<StartupReadiness />);

    const button = await screen.findByRole("button", { name: "Restart local assistant" });
    await userEvent.click(button);

    expect(restart).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Ready to work")).toBeInTheDocument();
  });

  it("keeps native resource failures visible without claiming readiness", async () => {
    mocks.audit.mockResolvedValue({
      ...readyAudit,
      requiredReady: false,
      checks: [
        ...readyAudit.checks.slice(0, 1),
        { id: "skills", ready: false, detail: "required Skill is unavailable: heor-workbench" },
        ...readyAudit.checks.slice(2),
      ],
    });

    render(<StartupReadiness />);

    expect(await screen.findByText("One item needs attention")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Technical details"));
    expect(screen.getByText("required Skill is unavailable: heor-workbench")).toBeInTheDocument();
  });
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HeorStarters } from "./HeorStarters";

const toastState = vi.hoisted(() => ({ errors: [] as string[], successes: [] as string[] }));
const installCalls: string[] = [];
const knowledgeInstallCalls: string[] = [];
let failInstall = false;
let runCalls = 0;
let failRun = false;
const runResult = {
  schema: "ai4heor-teaching-cea-desktop-run/v1" as const,
  runId: "run_local_1",
  interpreterSource: "system" as const,
  expectedResultSha256: "8daa00",
  baseCase: {
    path: "heor-cost-effectiveness/outputs/base-case-result.json",
    sha256: "8daa00",
    scenario: "base_case" as const,
    scenarioValue: null,
    incrementalCostPerPerson: 28241.078662,
    incrementalQalysPerPerson: 0.403709,
    icerPerQaly: 69954.047747,
    incrementalNetMonetaryBenefitPerPerson: 32315.271338,
  },
  sensitivityLow: {
    path: "heor-cost-effectiveness/outputs/stable-cost-low-result.json",
    sha256: "low00",
    scenario: "one_way_sensitivity" as const,
    scenarioValue: 14400,
    incrementalCostPerPerson: 24916.77344,
    incrementalQalysPerPerson: 0.403709,
    icerPerQaly: 61719.64,
    incrementalNetMonetaryBenefitPerPerson: 35639.57,
  },
  sensitivityHigh: {
    path: "heor-cost-effectiveness/outputs/stable-cost-high-result.json",
    sha256: "high00",
    scenario: "one_way_sensitivity" as const,
    scenarioValue: 21600,
    incrementalCostPerPerson: 31565.383884,
    incrementalQalysPerPerson: 0.403709,
    icerPerQaly: 78188.46,
    incrementalNetMonetaryBenefitPerPerson: 28990.97,
  },
  limitations: ["Synthetic teaching assumptions only."],
};
vi.mock("@/lib/tauri", () => ({
  isTauri: true,
  currentResearchScope: async () => ({
    id: "scope-1",
    name: "Learning task",
    path: "/tmp/learning-task",
  }),
  installExample: async (name: string) => {
    installCalls.push(name);
    if (failInstall) throw new Error("resource missing");
    return name;
  },
  runHeorTeachingExample: async () => {
    runCalls += 1;
    if (failRun) throw new Error("model-inputs.csv differs from the bundled teaching example");
    return runResult;
  },
}));
vi.mock("@/lib/heor", () => ({
  installBundledHeorKnowledgeBase: async (projectId: string) => {
    knowledgeInstallCalls.push(projectId);
    return { alreadyInstalled: false };
  },
}));
vi.mock("@/lib/toast", () => ({
  toast: {
    error: (message: string) => toastState.errors.push(message),
    success: (message: string) => toastState.successes.push(message),
  },
}));

describe("HeorStarters", () => {
  beforeEach(() => {
    installCalls.length = 0;
    knowledgeInstallCalls.length = 0;
    failInstall = false;
    runCalls = 0;
    failRun = false;
    toastState.errors.length = 0;
    toastState.successes.length = 0;
  });

  it("shows the model-independent HEOR teaching example on the default surface", () => {
    render(<HeorStarters onPick={() => {}} />);
    expect(screen.getAllByRole("button")).toHaveLength(6);
    expect(screen.getByText("Open the cost–utility teaching case")).toBeInTheDocument();
    expect(screen.getByText(/three-state model and its teaching assumptions/i))
      .toBeInTheDocument();
    expect(screen.queryByText(/climate|materials|weather/i)).not.toBeInTheDocument();
  });

  it("keeps ordinary public evidence retrieval in the conversation", async () => {
    const onPick = vi.fn();
    render(<HeorStarters onPick={onPick} />);
    await userEvent.click(screen.getByRole("button", { name: /Find public evidence/i }));
    expect(onPick).toHaveBeenCalledTimes(1);
    const prompt = onPick.mock.calls[0][0] as string;
    expect(prompt).toContain("available public retrieval tools");
    expect(prompt).toContain("full-access mode proceeds");
    expect(prompt).toContain("Do not inspect Git by default");
    expect(prompt).not.toContain("create heor/evidence-search-request.json for the current");
    expect(prompt).toContain("Do not inspect Git by default, create heor/evidence-search-request.json, tell me to find a panel");
  });

  it("prepares the bundled library before drafting a learning task", async () => {
    const onPick = vi.fn();
    const ensureWorkspace = vi.fn().mockResolvedValue(true);
    render(<HeorStarters onPick={onPick} ensureWorkspace={ensureWorkspace} />);

    await userEvent.click(
      screen.getByRole("button", { name: /Learn pharmacoeconomics fundamentals/i }),
    );

    await waitFor(() => expect(knowledgeInstallCalls).toEqual(["scope-1"]));
    expect(ensureWorkspace).toHaveBeenCalledTimes(1);
    expect(onPick).toHaveBeenCalledTimes(1);
    const prompt = onPick.mock.calls[0][0] as string;
    expect(prompt).toContain("prepared AI4HEOR learning library");
    expect(prompt).toContain("state the gap");
    expect(prompt).not.toContain("$heor-local-evidence");
    expect(prompt).not.toContain("SHA-256");
  });

  it("installs the example without hiding its local runner behind an agent turn", async () => {
    const onPick = vi.fn();
    const ensureWorkspace = vi.fn().mockResolvedValue(true);
    render(<HeorStarters onPick={onPick} ensureWorkspace={ensureWorkspace} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Open the cost–utility teaching case/i }),
    );
    await waitFor(() => expect(installCalls).toEqual(["heor-cost-effectiveness"]));
    expect(ensureWorkspace).toHaveBeenCalledTimes(1);
    expect(onPick).not.toHaveBeenCalled();
    expect(screen.getByText("The local teaching case is ready")).toBeInTheDocument();
    expect(screen.getByText(/hypothetical population/i)).toBeInTheDocument();
    expect(screen.getByText("Stable")).toBeInTheDocument();
    expect(screen.getByText("Progressed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run and view results" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask the assistant to explain" }))
      .toBeInTheDocument();
    expect(runCalls).toBe(0);

    await userEvent.click(screen.getByRole("button", { name: "Ask the assistant to explain" }));
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick.mock.calls[0][0]).toContain("three health states");
    expect(onPick.mock.calls[0][0]).toContain("plain language");
    expect(onPick.mock.calls[0][0]).not.toContain("run_analysis.py");
    expect(onPick.mock.calls[0][0]).not.toContain("SHA-256");
  });

  it("runs from the explicit local action and keeps technical details collapsed", async () => {
    render(<HeorStarters onPick={() => {}} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Open the cost–utility teaching case/i }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Run and view results" }));

    expect(await screen.findByText("Fixed calculation completed")).toBeInTheDocument();
    expect(runCalls).toBe(1);
    expect(screen.getByText("69,954.05")).toBeInTheDocument();
    expect(screen.getByText("61,719.64 – 78,188.46")).toBeInTheDocument();
    expect(screen.getByText(runResult.baseCase.path)).not.toBeVisible();
    await userEvent.click(screen.getByText("View run details"));
    expect(screen.getByText(runResult.baseCase.path)).toBeVisible();
    expect(screen.getByText(runResult.baseCase.sha256)).toBeVisible();
    expect(screen.getByText(runResult.runId)).toBeVisible();
  });

  it("uses a researcher-facing message when fixed inputs have changed", async () => {
    failRun = true;
    render(<HeorStarters onPick={() => {}} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Open the cost–utility teaching case/i }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Run and view results" }));
    await waitFor(() => expect(toastState.errors).toHaveLength(1));
    expect(toastState.errors[0]).toMatch(/The fixed inputs have been edited/i);
    expect(toastState.errors[0]).not.toMatch(/differs from the bundled teaching example/i);
  });

  it("does not prepare a request when the local example cannot be installed", async () => {
    failInstall = true;
    const onPick = vi.fn();
    render(<HeorStarters onPick={onPick} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Open the cost–utility teaching case/i }),
    );
    await waitFor(() => expect(installCalls).toHaveLength(1));
    expect(onPick).not.toHaveBeenCalled();
  });

  it("does not write the example when a standalone scope cannot be prepared", async () => {
    const onPick = vi.fn();
    render(
      <HeorStarters
        onPick={onPick}
        ensureWorkspace={vi.fn().mockResolvedValue(false)}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Open the cost–utility teaching case/i }),
    );
    await waitFor(() => expect(onPick).not.toHaveBeenCalled());
    expect(installCalls).toHaveLength(0);
  });
});

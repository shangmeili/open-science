import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HeorStarters } from "./HeorStarters";

const installCalls: string[] = [];
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
  installExample: async (name: string) => {
    installCalls.push(name);
    if (failInstall) throw new Error("resource missing");
    return name;
  },
  runHeorTeachingExample: async () => {
    runCalls += 1;
    if (failRun) throw new Error("fixed inputs changed");
    return runResult;
  },
}));

describe("HeorStarters", () => {
  beforeEach(() => {
    installCalls.length = 0;
    failInstall = false;
    runCalls = 0;
    failRun = false;
  });

  it("shows the model-independent HEOR teaching example on the default surface", () => {
    render(<HeorStarters onPick={() => {}} />);
    expect(screen.getAllByRole("button")).toHaveLength(6);
    expect(screen.getByText("Run the cost-effectiveness teaching example")).toBeInTheDocument();
    expect(screen.getByText(/reproduce costs, QALYs, and ICER with fixed code/i))
      .toBeInTheDocument();
    expect(screen.queryByText(/climate|materials|weather/i)).not.toBeInTheDocument();
  });

  it("installs the example and keeps the deterministic request as an editable draft", async () => {
    const onPick = vi.fn();
    render(<HeorStarters onPick={onPick} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Run the cost-effectiveness teaching example/i }),
    );
    await waitFor(() => expect(onPick).toHaveBeenCalledTimes(1));
    expect(installCalls).toEqual(["heor-cost-effectiveness"]);
    expect(onPick.mock.calls[0][0]).toContain(
      "python run_analysis.py --check expected/base-case-result.json",
    );
    expect(onPick.mock.calls[0][0]).toContain("low and high one-way sensitivity scenarios");
    expect(onPick.mock.calls[0][0]).toContain("ask me whether to continue");
    expect(screen.getByText("The local teaching case is ready")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run locally" })).toBeInTheDocument();
    expect(runCalls).toBe(0);
  });

  it("runs only after the auxiliary confirmation and shows the recorded result", async () => {
    render(<HeorStarters onPick={() => {}} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Run the cost-effectiveness teaching example/i }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Run locally" }));
    expect(screen.getByRole("alertdialog", { name: "Run the fixed teaching calculation?" }))
      .toBeInTheDocument();
    expect(runCalls).toBe(0);

    await userEvent.click(screen.getByRole("button", { name: "Run fixed calculation" }));

    expect(await screen.findByText("Fixed calculation completed")).toBeInTheDocument();
    expect(runCalls).toBe(1);
    expect(screen.getByText("69,954.05")).toBeInTheDocument();
    expect(screen.getByText("61,719.64 – 78,188.46")).toBeInTheDocument();
    expect(screen.getByText(runResult.baseCase.path)).toBeInTheDocument();
    expect(screen.getByText(runResult.baseCase.sha256)).toBeInTheDocument();
    expect(screen.getByText(runResult.runId)).toBeInTheDocument();
  });

  it("does not run when the researcher cancels the confirmation", async () => {
    render(<HeorStarters onPick={() => {}} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Run the cost-effectiveness teaching example/i }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Run locally" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(runCalls).toBe(0);
  });

  it("does not prepare a request when the local example cannot be installed", async () => {
    failInstall = true;
    const onPick = vi.fn();
    render(<HeorStarters onPick={onPick} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Run the cost-effectiveness teaching example/i }),
    );
    await waitFor(() => expect(installCalls).toHaveLength(1));
    expect(onPick).not.toHaveBeenCalled();
  });
});

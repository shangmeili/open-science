import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HeorStarters } from "./HeorStarters";

const installCalls: string[] = [];
let failInstall = false;
vi.mock("@/lib/tauri", () => ({
  isTauri: true,
  installExample: async (name: string) => {
    installCalls.push(name);
    if (failInstall) throw new Error("resource missing");
    return name;
  },
}));

describe("HeorStarters", () => {
  beforeEach(() => {
    installCalls.length = 0;
    failInstall = false;
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
    expect(onPick.mock.calls[0][0]).toContain("ask me whether to continue");
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

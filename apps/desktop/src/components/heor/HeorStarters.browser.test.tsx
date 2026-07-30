import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { HeorStarters } from "./HeorStarters";

vi.mock("@/lib/tauri", () => ({
  isTauri: false,
  currentResearchScope: vi.fn(),
  installExample: vi.fn(),
  runHeorTeachingExample: vi.fn(),
}));

describe("HeorStarters browser preview", () => {
  it("opens the case outline in place without installation or a model turn", async () => {
    const onPick = vi.fn();
    const ensureWorkspace = vi.fn();
    render(
      <HeorStarters
        onPick={onPick}
        ensureWorkspace={ensureWorkspace}
        desktopRuntime={false}
      />,
    );

    await userEvent.click(
      screen.getByRole("button", { name: /Open the complete cost–utility teaching case/i }),
    );

    expect(await screen.findByText("Preview of the complete teaching case"))
      .toBeInTheDocument();
    expect(screen.getByText("Available in the desktop app")).toBeInTheDocument();
    expect(ensureWorkspace).not.toHaveBeenCalled();
    expect(onPick).not.toHaveBeenCalled();
  });
});

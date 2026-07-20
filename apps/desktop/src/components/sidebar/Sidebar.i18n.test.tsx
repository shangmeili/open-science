import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useUiStore } from "@/lib/store";
import { renderAt } from "@/test/render";

// COPYCAT RULE: useUiStore is module-global; reset the locale after each test
// so this suite never bleeds a non-English locale into other test files.
afterEach(() => useUiStore.getState().setLocale("en"));

describe("Sidebar i18n", () => {
  it("uses researcher-facing navigation without a duplicate workspace item", async () => {
    renderAt("/files");

    const nav = await screen.findByRole("navigation");
    expect(within(nav).getByText("Research files")).toBeInTheDocument();
    expect(within(nav).queryByText("Analysis notes")).not.toBeInTheDocument();
    expect(within(nav).getByText("Analysis history")).toBeInTheDocument();
    expect(within(nav).getByText("New task")).toBeInTheDocument();
    expect(within(nav).getByText("Research capabilities")).toBeInTheDocument();
    expect(within(nav).queryByText("Research workspace")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Research workspace" })).toBeInTheDocument();
    expect(screen.getByText("Tasks")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Settings" })).toBeInTheDocument();
  });
});

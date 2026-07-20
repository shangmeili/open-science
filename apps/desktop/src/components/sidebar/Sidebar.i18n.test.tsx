import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useUiStore } from "@/lib/store";
import { renderAt } from "@/test/render";

// COPYCAT RULE: useUiStore is module-global; reset the locale after each test
// so this suite never bleeds a non-English locale into other test files.
afterEach(() => useUiStore.getState().setLocale("en"));

describe("Sidebar i18n", () => {
  it("uses task and skills-and-tools labels without a duplicate workspace nav item", async () => {
    renderAt("/files");

    const nav = await screen.findByRole("navigation");
    expect(within(nav).getByText("Files")).toBeInTheDocument();
    expect(within(nav).getByText("New task")).toBeInTheDocument();
    expect(within(nav).getByText("Skills & tools")).toBeInTheDocument();
    expect(within(nav).queryByText("Research workspace")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Research workspace" })).toBeInTheDocument();
    expect(screen.getByText("Tasks")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Settings" })).toBeInTheDocument();
  });
});

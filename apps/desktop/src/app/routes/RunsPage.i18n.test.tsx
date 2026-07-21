import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { useUiStore } from "@/lib/store";

// COPYCAT RULE: useUiStore is module-global; reset the locale after each test
// so this suite never bleeds a non-English locale into other test files.
afterEach(() => useUiStore.getState().setLocale("en"));

describe("RunsPage strings (i18n)", () => {
  it("renders the page heading and description in English", async () => {
    renderAt("/runs");
    expect(await screen.findByRole("heading", { level: 1, name: "Analysis history" })).toBeInTheDocument();
    expect(
      screen.getByText(
        /A local record of successful and failed analyses, plus outputs from successful runs\./,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Run again")).toBeInTheDocument();
  });

  it("renders the empty state (no runs recorded) in English", async () => {
    renderAt("/runs");
    expect(await screen.findByText("No analysis records yet")).toBeInTheDocument();
    expect(
      screen.getByText("Cost-effectiveness models, sensitivity analyses, and other local calculations will appear here after they run."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/python train\.py/)).not.toBeInTheDocument();
  });
});

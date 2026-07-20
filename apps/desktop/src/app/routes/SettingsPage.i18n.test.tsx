import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { useUiStore } from "@/lib/store";
import { useRuntimeStore } from "@/lib/runtime";
import { shippedLocales } from "@/i18n/config";

describe("Settings language selector", () => {
  it("shows a Language control with one button per shipped locale", async () => {
    renderAt("/settings");
    const group = await screen.findByRole("group", { name: "Language" });
    expect(within(group).getAllByRole("button")).toHaveLength(shippedLocales().length);
  });

  it("updates the store locale on change", async () => {
    renderAt("/settings");
    const group = await screen.findByRole("group", { name: "Language" });
    await userEvent.click(within(group).getByRole("button", { name: /日本語/ }));
    expect(useUiStore.getState().locale).toBe("ja");
    useUiStore.getState().setLocale("en");
  });
});

describe("Settings page strings (i18n)", () => {
  it("renders the page title, subtitle, and card titles in English", async () => {
    renderAt("/settings");
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Configure the AI assistant, models, evidence tools, workspace, and local analysis environment.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("AI assistant runtime")).toBeInTheDocument();
    expect(screen.getByText("Evidence and MCP tools")).toBeInTheDocument();
    expect(screen.getByText("Workspace")).toBeInTheDocument();
  });

  it("keeps the OpenCode engine and local endpoint inside closed advanced diagnostics", async () => {
    renderAt("/settings");
    const summary = await screen.findByText("Advanced diagnostics");
    const details = summary.closest("details");
    expect(details).not.toHaveAttribute("open");
    expect(within(details as HTMLElement).getByText("OpenCode")).toBeInTheDocument();
    expect(within(details as HTMLElement).getByLabelText("Local endpoint")).toBeInTheDocument();
    await userEvent.click(summary);
    expect(details).toHaveAttribute("open");
  });

  it("renders the disconnected-runtime prompts and the Workspace fallback text", async () => {
    renderAt("/settings");
    expect(await screen.findByText("Connect the runtime to configure models.")).toBeInTheDocument();
    expect(screen.getByText("Connect the runtime to configure MCP servers.")).toBeInTheDocument();
    expect(screen.getByText("available in the desktop app")).toBeInTheDocument();
  });

  it("renders separate model browsing and provider management surfaces when connected", async () => {
    const original = useRuntimeStore.getState();
    let view: ReturnType<typeof renderAt> | undefined;
    try {
      useRuntimeStore.setState({ status: "ready", defaultModel: null });
      view = renderAt("/settings");
      // No client behind this render: the Models card sits in its loading
      // state while the separate Providers card is already on screen.
      expect(await screen.findByText("Loading the model catalog…")).toBeInTheDocument();
      expect(screen.getByRole("heading", { level: 2, name: "Providers" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Manage" })).toHaveAttribute("aria-expanded", "false");
      expect(screen.getByText("HEOR evidence search")).toBeInTheDocument();
      expect(screen.getByText(/PubMed · ClinicalTrials\.gov · \$heor-evidence-search/)).toBeInTheDocument();
      expect(screen.queryByText("Materials Project")).not.toBeInTheDocument();
      expect(screen.queryByText("FRED economic data")).not.toBeInTheDocument();
    } finally {
      view?.unmount();
      useRuntimeStore.setState({ status: original.status, defaultModel: original.defaultModel });
    }
  });
});

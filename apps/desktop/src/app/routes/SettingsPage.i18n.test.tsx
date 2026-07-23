import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { useUiStore } from "@/lib/store";
import { useRuntimeStore } from "@/lib/runtime";
import { shippedLocales } from "@/i18n/config";

describe("Settings language selector", () => {
  it("uses the same selected-state treatment for theme and language controls", async () => {
    renderAt("/settings/appearance");
    const themeGroup = await screen.findByRole("group", { name: "Theme" });
    const languageGroup = screen.getByRole("group", { name: "Language" });
    const light = within(themeGroup).getByRole("button", { name: "Light" });
    const english = within(languageGroup).getByRole("button", { name: /English/ });

    expect(light).toHaveAttribute("aria-pressed", "true");
    expect(english).toHaveAttribute("aria-pressed", "true");
    expect(light).toHaveClass("bg-surface-2", "text-text");
    expect(english).toHaveClass("bg-surface-2", "text-text");
    expect(light).not.toHaveClass("shadow-card");
    expect(english).not.toHaveClass("shadow-sm");
  });

  it("shows a Language control with one button per shipped locale", async () => {
    renderAt("/settings/appearance");
    const group = await screen.findByRole("group", { name: "Language" });
    expect(within(group).getAllByRole("button")).toHaveLength(shippedLocales().length);
  });

  it("updates the store locale on change", async () => {
    renderAt("/settings/appearance");
    const group = await screen.findByRole("group", { name: "Language" });
    const japanese = within(group).getByRole("button", { name: /日本語/ });
    await userEvent.click(japanese);
    expect(useUiStore.getState().locale).toBe("ja");
    expect(japanese).toHaveClass("border-border", "bg-surface-2", "outline-none");
    expect(japanese).not.toHaveClass("border-accent", "shadow-sm");
    useUiStore.getState().setLocale("en");
  });
});

describe("Settings page strings (i18n)", () => {
  it("renders the general section without flattening controls from other settings sections", async () => {
    renderAt("/settings");
    expect(await screen.findByRole("heading", { level: 1, name: "General" })).toBeInTheDocument();
    expect(screen.getByText("Workspace")).toBeInTheDocument();
    expect(screen.queryByText("AI assistant runtime")).not.toBeInTheDocument();
    expect(screen.queryByText("Evidence and MCP tools")).not.toBeInTheDocument();
  });

  it("keeps the OpenCode engine and local endpoint inside closed advanced diagnostics", async () => {
    renderAt("/settings/runtime");
    const summary = await screen.findByText("Advanced diagnostics");
    const details = summary.closest("details");
    expect(details).not.toHaveAttribute("open");
    expect(within(details as HTMLElement).getByText("OpenCode")).toBeInTheDocument();
    expect(within(details as HTMLElement).getByLabelText("Local endpoint")).toBeInTheDocument();
    await userEvent.click(summary);
    expect(details).toHaveAttribute("open");
  });

  it("renders disconnected-runtime prompts in their matching sections", async () => {
    const models = renderAt("/settings/models");
    expect(await screen.findByText("Connect the runtime to configure models.")).toBeInTheDocument();
    expect(screen.queryByText("Connect the runtime to configure MCP servers.")).not.toBeInTheDocument();
    models.unmount();

    const connectors = renderAt("/settings/connectors");
    expect(await screen.findByText("Connect the runtime to configure MCP servers.")).toBeInTheDocument();
    connectors.unmount();

    renderAt("/settings/general");
    expect(await screen.findByText("available in the desktop app")).toBeInTheDocument();
  });

  it("renders separate model browsing and provider management surfaces when connected", async () => {
    const original = useRuntimeStore.getState();
    let view: ReturnType<typeof renderAt> | undefined;
    try {
      useRuntimeStore.setState({ status: "ready", defaultModel: null });
      view = renderAt("/settings/models");
      // No client behind this render: the Models card sits in its loading
      // state while the separate Providers card is already on screen.
      expect(await screen.findByText("Loading the model catalog…")).toBeInTheDocument();
      expect(screen.getByRole("heading", { level: 2, name: "Providers" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Manage" })).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByText("HEOR evidence search")).not.toBeInTheDocument();
      expect(screen.queryByText("Materials Project")).not.toBeInTheDocument();
      expect(screen.queryByText("FRED economic data")).not.toBeInTheDocument();
      view.unmount();

      view = renderAt("/settings/connectors");
      expect(await screen.findByText("HEOR evidence search")).toBeInTheDocument();
      expect(screen.getByText(/PubMed · ClinicalTrials\.gov · \$heor-evidence-search/)).toBeInTheDocument();
    } finally {
      view?.unmount();
      useRuntimeStore.setState({ status: original.status, defaultModel: original.defaultModel });
    }
  });
});

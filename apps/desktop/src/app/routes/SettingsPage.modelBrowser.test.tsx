import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProviderInfo } from "@ai4s/sdk";
import i18n from "@/i18n";
import * as runtime from "@/lib/runtime";
import { useRuntimeStore } from "@/lib/runtime";
import { useSetupStore } from "@/lib/setup";
import { useToastStore } from "@/lib/toast";
import { loadModelPreferences, saveModelPreferences } from "@/components/settings/modelPreferences";
import { Toaster } from "@/components/ui/Toaster";
import { SettingsPage } from "./SettingsPage";

const providers: ProviderInfo[] = [
  {
    id: "openai",
    name: "OpenAI",
    models: [
      { id: "gpt-5.2", name: "GPT-5.2" },
      { id: "o3", name: "o3" },
    ],
  },
];

let activeView: ReturnType<typeof render> | undefined;

function catalogClient(listProviders = vi.fn().mockResolvedValue(providers)) {
  return {
    listProviders,
    listAuthMethods: vi.fn().mockResolvedValue({}),
    listProviderCatalog: vi.fn().mockResolvedValue({ all: [] }),
    listCustomProviderIds: vi.fn().mockResolvedValue([]),
    listMcpServers: vi.fn().mockResolvedValue([]),
  } as unknown as NonNullable<ReturnType<typeof runtime.getClient>>;
}

async function renderSettings(section = "models") {
  let view!: ReturnType<typeof render>;
  await act(async () => {
    view = render(
      // Models and Providers live in the "models" settings section.
      <MemoryRouter initialEntries={[`/settings/${section}`]}>
        <Routes>
          <Route path="/settings/:section" element={<SettingsPage />} />
        </Routes>
        <Toaster />
      </MemoryRouter>,
    );
  });
  activeView = view;
  return view;
}

describe("Settings model browser integration", () => {
  const initialRuntime = useRuntimeStore.getState();
  const initialSetup = useSetupStore.getState();

  beforeEach(async () => {
    window.localStorage.clear();
    useToastStore.setState({ toasts: [] });
    useSetupStore.setState({ generation: 0 });
    useRuntimeStore.setState({ status: "ready", defaultModel: "openai/gpt-5.2", switching: false });
    await i18n.changeLanguage("en");
  });

  afterEach(() => {
    activeView?.unmount();
    activeView = undefined;
    vi.restoreAllMocks();
    useToastStore.setState({ toasts: [] });
    useSetupStore.setState(initialSetup, true);
    useRuntimeStore.setState(initialRuntime, true);
  });

  it("shows user-facing AI4HEOR positioning and contact details without internal release-channel copy", async () => {
    await i18n.changeLanguage("zh-Hans");
    await renderSettings("general");

    expect(screen.getByRole("heading", { name: "关于 AI4HEOR" })).toBeInTheDocument();
    expect(screen.getByText(/由 Codex 负责开发建设/)).toBeInTheDocument();
    expect(screen.getByText(/基于 Open Science 开源底座搭建/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看 Open Science 开源项目" }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "shangmei.li@altolix.com" }))
      .toBeInTheDocument();
    expect(screen.getByRole("img", { name: "野生炼丹师老M的小红书名片" }))
      .toBeInTheDocument();
    expect(screen.queryByText(/尚未配置正式发布渠道/)).not.toBeInTheDocument();
    expect(screen.queryByText("暂未开放在线更新")).not.toBeInTheDocument();
  });

  it("shows one settings section at a time and keeps both MCP rows on the same grid", async () => {
    await renderSettings("connectors");

    expect(screen.getByRole("heading", { level: 1, name: "Connectors" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Model" })).not.toBeInTheDocument();
    const nameRow = screen.getByTestId("mcp-server-name-row");
    const commandRow = screen.getByTestId("mcp-server-command-row");
    expect(nameRow.className).toContain("sm:grid-cols-[minmax(0,1fr)_7.5rem]");
    expect(commandRow.className).toContain("sm:grid-cols-[minmax(0,1fr)_7.5rem]");
  });

  it("shows the connect prompt when the runtime errors before any model switch happened", async () => {
    // First boot with a dead sidecar: status "error", defaultModel null,
    // modelSwitchError null. The browser must NOT appear (the old page-local
    // sentinel compared null === null here and showed an empty browser).
    useRuntimeStore.setState({ status: "error", defaultModel: null, modelSwitchError: null });

    await renderSettings();

    expect(screen.getByText("Connect the runtime to configure models.")).toBeInTheDocument();
    expect(screen.queryByText("No models available.")).not.toBeInTheDocument();
  });

  it("keeps the browser up through an immediately-rejected retry after a failed switch", async () => {
    vi.spyOn(runtime, "getClient").mockReturnValue(catalogClient());
    // A dead server per the store contract: every attempt rejects AND records
    // modelSwitchError (the store owns the failure fact now).
    const deadSwitch = vi.fn(async () => {
      useRuntimeStore.setState({ modelSwitchError: "Load failed" });
      throw new Error("Load failed");
    });
    useRuntimeStore.setState({ setDefaultModel: deadSwitch });
    await renderSettings();
    await screen.findByRole("button", { name: /^o3/ });

    await userEvent.click(screen.getByRole("button", { name: /^o3/ }));
    await waitFor(() => expect(deadSwitch).toHaveBeenCalledTimes(1));
    act(() => useRuntimeStore.setState({ status: "error", switching: false }));
    expect(screen.getByRole("searchbox", { name: "Search models" })).toBeInTheDocument();

    // Retrying while the server is still down must not collapse the surface.
    await userEvent.click(screen.getByRole("button", { name: /^o3/ }));
    await waitFor(() => expect(deadSwitch).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("searchbox", { name: "Search models" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^o3/ })).toBeInTheDocument();
  });

  it("shows a loading state, not a false unavailable-model warning, while the catalog loads", async () => {
    let resolveProviders!: (value: ProviderInfo[]) => void;
    const pending = new Promise<ProviderInfo[]>((resolve) => {
      resolveProviders = resolve;
    });
    vi.spyOn(runtime, "getClient").mockReturnValue(
      catalogClient(vi.fn().mockReturnValue(pending)),
    );

    await renderSettings();

    expect(screen.getByText("Loading the model catalog…")).toBeInTheDocument();
    expect(screen.queryByText(/Configured model unavailable/)).not.toBeInTheDocument();
    expect(screen.queryByText("No models available.")).not.toBeInTheDocument();
    await act(async () => resolveProviders(providers));
    expect(await screen.findByRole("button", { name: /^o3/ })).toBeInTheDocument();
  });

  it("shows models when the provider list succeeds even if auxiliary settings calls fail", async () => {
    const client = catalogClient();
    (client as { listAuthMethods: unknown }).listAuthMethods = vi
      .fn()
      .mockRejectedValue(new Error("aux down"));
    vi.spyOn(runtime, "getClient").mockReturnValue(client);

    await renderSettings();

    expect(await screen.findByRole("button", { name: /^o3/ })).toBeInTheDocument();
    expect(screen.queryByText("The model catalog is currently unavailable.")).not.toBeInTheDocument();
  });

  it("drops the cached catalog when the server URL changes (no stale models from the old runtime)", async () => {
    vi.spyOn(runtime, "getClient").mockReturnValue(catalogClient());
    await renderSettings();
    expect(await screen.findByRole("button", { name: /^o3/ })).toBeInTheDocument();

    act(() => useRuntimeStore.getState().setServerUrl("http://127.0.0.1:9999"));

    expect(screen.queryByRole("button", { name: /^o3/ })).not.toBeInTheDocument();
  });

  it("an expanded Providers card stays collapsible and shows a prompt after a disconnect", async () => {
    vi.spyOn(runtime, "getClient").mockReturnValue(catalogClient());
    await renderSettings();
    await screen.findByRole("button", { name: /^o3/ });
    await userEvent.click(screen.getByRole("button", { name: "Manage" }));

    act(() => useRuntimeStore.setState({ status: "offline", switching: false }));

    // The old wiring disabled the toggle and rendered an empty body — a
    // stuck-open blank panel the user could not close until reconnect.
    expect(screen.getByText("Connect the runtime to manage providers.")).toBeInTheDocument();
    const collapse = screen.getByRole("button", { name: "Collapse" });
    expect(collapse).toBeEnabled();
    await userEvent.click(collapse);
    expect(screen.queryByText("Connect the runtime to manage providers.")).not.toBeInTheDocument();
  });

  it("shows a localized unavailable state when the initial provider refresh fails", async () => {
    vi.spyOn(runtime, "getClient").mockReturnValue(
      catalogClient(vi.fn().mockRejectedValue(new Error("catalog offline"))),
    );

    await renderSettings();

    expect(await screen.findByText("The model catalog is currently unavailable.")).toBeInTheDocument();
    expect(screen.queryByText("No models available.")).not.toBeInTheDocument();
  });

  it("retains the last successful model list when a later provider refresh fails", async () => {
    const listProviders = vi.fn()
      .mockResolvedValueOnce(providers)
      .mockRejectedValueOnce(new Error("catalog offline"));
    vi.spyOn(runtime, "getClient").mockReturnValue(catalogClient(listProviders));
    await renderSettings();
    expect(await screen.findByRole("button", { name: /^o3/ })).toBeInTheDocument();

    await act(async () => useSetupStore.setState({ generation: 1 }));

    await waitFor(() => expect(listProviders).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("button", { name: /^o3/ })).toBeInTheDocument();
    expect(screen.queryByText("The model catalog is currently unavailable.")).not.toBeInTheDocument();
  });

  it("hides a cached model snapshot after an ordinary runtime disconnect", async () => {
    vi.spyOn(runtime, "getClient").mockReturnValue(catalogClient());
    await renderSettings();
    expect(await screen.findByRole("searchbox", { name: "Search models" })).toBeInTheDocument();

    act(() => useRuntimeStore.setState({ status: "offline", switching: false }));

    expect(await screen.findByText("Connect the runtime to configure models.")).toBeInTheDocument();
    expect(screen.queryByRole("searchbox", { name: "Search models" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^o3/ })).not.toBeInTheDocument();
  });

  it("prefills MiniMax China without placing its key in endpoint config", async () => {
    const client = catalogClient() as ReturnType<typeof catalogClient> & {
      addCustomProvider: ReturnType<typeof vi.fn>;
      setProviderApiKey: ReturnType<typeof vi.fn>;
    };
    client.addCustomProvider = vi.fn().mockResolvedValue(undefined);
    client.setProviderApiKey = vi.fn().mockResolvedValue(undefined);
    vi.spyOn(runtime, "getClient").mockReturnValue(client);
    await renderSettings();
    await screen.findByRole("button", { name: /^o3/ });

    await userEvent.click(screen.getByRole("button", { name: "Manage" }));
    await userEvent.click(screen.getByRole("button", { name: /Custom endpoint/ }));
    await userEvent.click(screen.getByRole("button", { name: "Fill MiniMax China Token Plan" }));

    expect(screen.getByPlaceholderText("Name — e.g. Ollama, My DeepSeek gateway")).toHaveValue(
      "MiniMax CN Token Plan",
    );
    expect(screen.getByDisplayValue("Anthropic-compatible")).toHaveValue("@ai-sdk/anthropic");
    expect(screen.getByPlaceholderText(/Base URL/)).toHaveValue(
      "https://api.minimaxi.com/anthropic/v1",
    );
    expect(screen.getByPlaceholderText("Model ids, comma-separated")).toHaveValue("MiniMax-M3");
    expect(screen.getByText(/endpoint configuration never contains the API key/i)).toBeVisible();

    await userEvent.type(
      screen.getByPlaceholderText("API key — optional, Ollama needs none"),
      "local-test-key",
    );
    await userEvent.click(screen.getByRole("button", { name: "Add endpoint" }));

    await waitFor(() =>
      expect(client.addCustomProvider).toHaveBeenCalledWith("minimax-cn-token-plan", {
        name: "MiniMax CN Token Plan",
        npm: "@ai-sdk/anthropic",
        baseURL: "https://api.minimaxi.com/anthropic/v1",
        models: ["MiniMax-M3"],
      }),
    );
    expect(client.setProviderApiKey).toHaveBeenCalledWith(
      "minimax-cn-token-plan",
      "local-test-key",
    );
    expect(client.addCustomProvider.mock.invocationCallOrder[0]).toBeLessThan(
      client.setProviderApiKey.mock.invocationCallOrder[0],
    );
  });

  it("keeps the runtime default and error semantics after a post-write reconnect failure", async () => {
    vi.spyOn(runtime, "getClient").mockReturnValue(catalogClient());
    saveModelPreferences({ favorites: [], recent: ["openai/gpt-5.2"] });
    let exhaustReconnect!: () => void;
    const reconnectFailure = vi.fn((model: string) => new Promise<void>((_resolve, reject) => {
      useRuntimeStore.setState({
        defaultModel: model,
        switching: true,
        status: "connecting",
        error: null,
      });
      exhaustReconnect = () => {
        // Per the store contract, a failed switch records modelSwitchError.
        useRuntimeStore.setState({
          switching: false,
          status: "error",
          error: "reconnect failed",
          modelSwitchError: "reconnect failed",
        });
        reject(new Error("reconnect failed"));
      };
    }));
    useRuntimeStore.setState({ setDefaultModel: reconnectFailure });
    await renderSettings();
    const targetRow = await screen.findByRole("button", { name: /^o3/ });

    await userEvent.click(targetRow);

    await waitFor(() => expect(reconnectFailure).toHaveBeenCalledWith("openai/o3"));
    expect(useRuntimeStore.getState()).toMatchObject({
      defaultModel: "openai/o3",
      switching: true,
      status: "connecting",
    });
    expect(screen.getByRole("searchbox", { name: "Search models" })).toBeInTheDocument();
    expect(screen.getByText("Switching…")).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: /^o3/ })).getByText("Current default")).toBeInTheDocument();

    await act(async () => exhaustReconnect());

    await waitFor(() => expect(screen.getByText("Could not set the model: reconnect failed")).toBeInTheDocument());
    expect(useRuntimeStore.getState().defaultModel).toBe("openai/o3");
    const currentRow = screen.getByRole("button", { name: /^o3/ });
    expect(within(currentRow).getByText("Current default")).toBeInTheDocument();
    expect(currentRow).toBeEnabled();
    expect(screen.getByRole("button", { name: /^GPT-5.2/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Add o3 to favorites" })).toBeEnabled();
    expect(loadModelPreferences().recent).toEqual(["openai/gpt-5.2"]);

    act(() => useRuntimeStore.setState({ status: "offline", switching: false }));
    expect(await screen.findByText("Connect the runtime to configure models.")).toBeInTheDocument();
    expect(screen.queryByRole("searchbox", { name: "Search models" })).not.toBeInTheDocument();
  });
});

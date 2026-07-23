import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";

const shellMocks = vi.hoisted(() => ({
  toggleSidebar: vi.fn(),
}));

vi.mock("@/components/sidebar/Sidebar", () => ({ Sidebar: () => <aside>Sidebar</aside> }));
vi.mock("@/components/command-palette/CommandPalette", () => ({ CommandPalette: () => null }));
vi.mock("@/components/ui/Toaster", () => ({ Toaster: () => null }));
vi.mock("@/lib/runtime", () => ({
  useRuntimeStore: { getState: () => ({ bootstrap: vi.fn() }) },
}));
vi.mock("@/lib/setup", () => ({
  ensureJupyter: vi.fn(),
  ensureSetupProgressListener: vi.fn(),
}));
vi.mock("@/lib/store", () => ({
  useOverlayTitlebar: () => false,
  useUiStore: Object.assign(
    () => ({ sidebarCollapsed: false, setSidebarCollapsed: vi.fn() }),
    { getState: () => ({ toggleSidebar: shellMocks.toggleSidebar }) },
  ),
}));
vi.mock("@/lib/tauri", () => ({
  ensureJupyter: vi.fn(),
  isTauri: true,
  openExternal: vi.fn(),
  watchFullscreen: vi.fn().mockResolvedValue(() => {}),
}));
vi.mock("@/lib/update", () => ({
  useUpdateStore: { getState: () => ({ maybeAutoCheck: vi.fn() }) },
}));

describe("AppShell accessibility", () => {
  it("provides a localized skip link to a programmatically focusable main region", () => {
    render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<h1>HEOR content</h1>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Skip to HEOR workspace" })).toHaveAttribute(
      "href",
      "#ai4heor-main",
    );
    expect(screen.getByRole("main")).toHaveAttribute("id", "ai4heor-main");
    expect(screen.getByRole("main")).toHaveAttribute("tabindex", "-1");
  });

  it("suppresses the packaged webview's native context menu", () => {
    render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<a href="https://example.com">External source</a>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    screen.getByRole("link", { name: "External source" }).dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);

    const blankEvent = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    screen.getByRole("main").dispatchEvent(blankEvent);
    expect(blankEvent.defaultPrevented).toBe(true);
  });
});

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { AgentMessage } from "./atoms";
import { clearResolvedArtifactPaths } from "@/lib/artifactFile";

const mocks = vi.hoisted(() => ({ invoke: vi.fn(), error: vi.fn() }));
vi.mock("@/lib/tauri", () => ({ isTauri: true }));
vi.mock("@/lib/toast", () => ({ toast: { error: mocks.error } }));

describe("conversation file previews", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    mocks.invoke.mockReset();
    mocks.error.mockReset();
    clearResolvedArtifactPaths();
    mocks.invoke.mockImplementation(async (_command, { path }) => path);
    // Exercise the real API wrapper with a stubbed native bridge. Concurrent
    // dynamic imports can bypass a module mock in the test runner.
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: { invoke: mocks.invoke } });
  });
  afterEach(() => { Reflect.deleteProperty(window, "__TAURI_INTERNALS__"); });

  it("opens inline paths and Markdown file links through the existing preview callback", async () => {
    const open = vi.fn();
    const { container } = render(<AgentMessage markdown={'`heor/report.md` and [results](heor/results/base-case.json)'} onOpenArtifact={open} />);
    fireEvent.click(screen.getByRole("button", { name: "Preview heor/report.md" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith(expect.objectContaining({ path: "heor/report.md", artifact: "report" })));
    fireEvent.click(screen.getByRole("button", { name: "Preview heor/results/base-case.json" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith(expect.objectContaining({ path: "heor/results/base-case.json" })));
    expect(container.querySelector("a[href='heor/results/base-case.json']")).toBeNull();
    // Existing attachment chips remain separate, usable controls.
    fireEvent.click(await screen.findByRole("button", { name: "report.md" }));
    await waitFor(() => expect(open).toHaveBeenCalledTimes(3));
  });

  it("refreshes a previously missing attachment after file-producing tools complete", async () => {
    mocks.invoke.mockResolvedValue(null);
    render(<AgentMessage markdown="`heor/report.md`" onOpenArtifact={vi.fn()} />);
    await waitFor(() => expect(mocks.invoke).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "report.md" })).toBeNull();
    mocks.invoke.mockResolvedValue("heor/report.md");
    act(() => clearResolvedArtifactPaths());
    expect(await screen.findByRole("button", { name: "report.md" })).toBeInTheDocument();
  });

  it("rechecks missing files when streaming ends even if paths did not change", async () => {
    mocks.invoke.mockResolvedValue(null);
    const open = vi.fn();
    const { rerender } = render(<AgentMessage markdown="`heor/report.md`" streaming onOpenArtifact={open} />);
    await waitFor(() => expect(mocks.invoke).toHaveBeenCalled());
    mocks.invoke.mockResolvedValue("heor/report.md");
    rerender(<AgentMessage markdown="`heor/report.md`" onOpenArtifact={open} />);
    expect(await screen.findByRole("button", { name: "report.md" })).toBeInTheDocument();
  });

  it("reports missing files and real resolver errors without opening stale previews", async () => {
    mocks.invoke.mockResolvedValue(null);
    const open = vi.fn();
    render(<AgentMessage markdown="`heor/missing.json`" onOpenArtifact={open} />);
    await waitFor(() => expect(mocks.invoke).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Preview heor/missing.json" }));
    await waitFor(() => expect(mocks.error).toHaveBeenCalledWith(expect.stringContaining("heor/missing.json")));
    mocks.invoke.mockRejectedValue(new Error("path escapes the workspace"));
    fireEvent.click(screen.getByRole("button", { name: "Preview heor/missing.json" }));
    await waitFor(() => expect(mocks.error).toHaveBeenCalledWith("path escapes the workspace"));
    expect(open).not.toHaveBeenCalled();
  });

  it("does not open a delayed click after the workspace changes", async () => {
    const open = vi.fn();
    const { unmount } = render(<AgentMessage markdown="`heor/report.md`" onOpenArtifact={open} />);
    await screen.findByRole("button", { name: "report.md" });
    let finish!: (path: string) => void;
    mocks.invoke.mockImplementation(() => new Promise<string>((resolve) => { finish = resolve; }));
    fireEvent.click(screen.getByRole("button", { name: "Preview heor/report.md" }));
    await waitFor(() => expect(finish).toBeDefined());
    act(() => clearResolvedArtifactPaths());
    unmount();
    await act(async () => finish("heor/report.md"));
    expect(open).not.toHaveBeenCalled();
  });

  it("keeps fenced code, external links, formulas and non-path code unchanged", () => {
    const { container } = render(<AgentMessage markdown={'```text\nheor/report.md\n```\n\n[Web `report.md`](https://example.org/report.md) and `ICER` and $x^2$'} onOpenArtifact={vi.fn()} streaming />);
    expect(container.querySelector("pre button")).toBeNull();
    expect(container.querySelector("a button")).toBeNull();
    expect(screen.getByRole("link").getAttribute("href")).toBe("https://example.org/report.md");
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Preview ICER" })).toBeNull();
  });

  it("supports Chinese, spaces, Windows paths and streaming sealed blocks", async () => {
    const open = vi.fn();
    render(<AgentMessage markdown={'`heor/中文 报告.md`\n\n`C:\\Research\\report.md`\n\n[encoded](heor/report%20draft.md)\n\nTail'} onOpenArtifact={open} streaming />);
    for (const path of ["heor/中文 报告.md", "C:/Research/report.md", "heor/report draft.md"]) {
      fireEvent.click(screen.getByRole("button", { name: `Preview ${path}` }));
      await waitFor(() => expect(mocks.invoke).toHaveBeenCalledWith("resolve_artifact", { path }, undefined));
      expect(mocks.error.mock.calls).toEqual([]);
      await waitFor(() => expect(open).toHaveBeenCalledWith(expect.objectContaining({ path })));
    }
  });

  it("does not navigate unsafe or traversal links away from the desktop", () => {
    const { container } = render(<AgentMessage markdown={'[escape](../report.md) [unsafe](javascript:report.md) `../report.md`'} onOpenArtifact={vi.fn()} />);
    expect(container.querySelector("a[href]")).toBeNull();
    expect(container.querySelector("button[data-workspace-path]")).toBeNull();
  });
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DirEntry } from "@/lib/artifactFile";
import { FilesPage } from "./FilesPage";

const listDir = vi.fn();
vi.mock("@/lib/artifactFile", () => ({
  listDir: (rel: string, root?: string) => listDir(rel, root),
}));
vi.mock("@/components/inspector/FilePreviewInspector", () => ({
  FilePreviewInspector: ({ data }: { data: { filename: string } }) => (
    <div data-testid="preview">preview:{data.filename}</div>
  ),
}));
vi.mock("@/components/notebook/NotebookEditor", () => ({
  NotebookEditor: ({ path }: { path: string }) => <div data-testid="nb">nb:{path}</div>,
}));

const root: DirEntry[] = [
  { path: "data", name: "data", isDir: true, size: 0, modified: 2 },
  { path: "figure.png", name: "figure.png", isDir: false, size: 2048, modified: 3 },
  { path: "run.ipynb", name: "run.ipynb", isDir: false, size: 500, modified: 1 },
];
const sub: DirEntry[] = [{ path: "data/genes.bed", name: "genes.bed", isDir: false, size: 120, modified: 4 }];

describe("FilesPage", () => {
  beforeEach(() => {
    listDir.mockReset();
    listDir.mockImplementation((rel: string) => Promise.resolve(rel === "data" ? sub : root));
  });

  it("lists workspace entries with sizes and opens a file in the previewer", async () => {
    render(<FilesPage />);
    expect(await screen.findByText("figure.png")).toBeInTheDocument();
    expect(listDir).toHaveBeenCalledWith("", "workspace");
    expect(screen.getByText("2 KB")).toBeInTheDocument();

    await userEvent.click(screen.getByText("figure.png"));
    expect(screen.getByTestId("preview")).toHaveTextContent("preview:figure.png");
  });

  it("opens notebooks in the runnable editor", async () => {
    render(<FilesPage />);
    await userEvent.click(await screen.findByText("run.ipynb"));
    expect(screen.getByTestId("nb")).toHaveTextContent("nb:run.ipynb");
  });

  it("navigates into a folder and back via the breadcrumb", async () => {
    render(<FilesPage />);
    await userEvent.click(await screen.findByText("data"));
    expect(await screen.findByText("genes.bed")).toBeInTheDocument();
    expect(listDir).toHaveBeenCalledWith("data", "workspace");

    await userEvent.click(screen.getByRole("button", { name: "Research files" }));
    await waitFor(() => expect(screen.getByText("figure.png")).toBeInTheDocument());
  });

  it("opens the active scope directly instead of showing its dated storage folder", async () => {
    render(<FilesPage />);

    expect(await screen.findByText("figure.png")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Research files" })).toBeInTheDocument();
    expect(screen.queryByText("7月20日 14:08 的任务")).not.toBeInTheDocument();
    expect(screen.queryByText("2026-07-20-1408")).not.toBeInTheDocument();
    expect(listDir).not.toHaveBeenCalledWith("", "base");
  });
});

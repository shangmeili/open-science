import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  exportReport: vi.fn(),
  success: vi.fn(),
}));

vi.mock("@/lib/tauri", async () => {
  const actual = await vi.importActual<typeof import("@/lib/tauri")>("@/lib/tauri");
  return {
    ...actual,
    isTauri: true,
    exportSupportReport: mocks.exportReport,
  };
});

vi.mock("@/lib/toast", () => ({
  toast: { success: mocks.success, error: vi.fn() },
}));

import { SupportReportCard } from "./SupportReportCard";

beforeEach(() => {
  mocks.exportReport.mockReset();
  mocks.success.mockReset();
  mocks.exportReport.mockResolvedValue({ kind: "saved", path: "/tmp/report.json" });
});

describe("SupportReportCard", () => {
  it("explains the privacy boundary and exports through the native command", async () => {
    render(<SupportReportCard />);

    expect(
      screen.getByText(
        "The report contains the app version, system architecture, local assistant status, and aggregate diagnostic event counts. It does not contain model credentials, project paths, research files, conversations, or raw logs.",
      ),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Export diagnostic report" }));

    expect(mocks.exportReport).toHaveBeenCalledTimes(1);
    expect(mocks.success).toHaveBeenCalledWith("Diagnostic report saved");
  });
});

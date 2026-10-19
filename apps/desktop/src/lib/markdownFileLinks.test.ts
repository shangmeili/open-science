import { describe, expect, it } from "vitest";
import { workspaceFilePath } from "./markdownFileLinks";

describe("workspace file references", () => {
  it.each([
    ["heor/report.md", "heor/report.md"],
    ["./heor/report.md", "./heor/report.md"],
    ["报告/成本 效用.md", "报告/成本 效用.md"],
    ["heor/report%20draft.md", "heor/report draft.md"],
    ["/Users/research/project/report.md", "/Users/research/project/report.md"],
    ["C:\\Research\\报告.md", "C:/Research/报告.md"],
  ])("recognizes %s", (value, expected) => {
    expect(workspaceFilePath(value)).toBe(expected);
  });

  it.each([
    "https://example.org/report.md", "javascript:report.md", "data:report.md",
    "mailto:report.md", "//example.org/report.md", "\\\\host\\share\\report.md",
    "../report.md", "heor/../../report.md", "%2e%2e/report.md", "bad%ZZ.md",
    "report.md\ncommand", "report.md?command=1", "ICER", "QALY = 1.5",
  ])("does not treat %s as a workspace file", (value) => {
    expect(workspaceFilePath(value)).toBeNull();
  });
});

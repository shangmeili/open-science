import { describe, expect, it } from "vitest";
import { sameLocalPath } from "./localPath";

describe("sameLocalPath", () => {
  it("matches Windows drive paths across slash style, casing and trailing separators", () => {
    expect(sameLocalPath(
      "C:\\Users\\Researcher\\Documents\\AI4HEOR\\Project-A",
      "c:/users/researcher/documents/AI4HEOR/Project-A/",
    )).toBe(true);
  });

  it("matches an extended-length Windows path to its ordinary form", () => {
    expect(sameLocalPath(
      "\\\\?\\C:\\Users\\Researcher\\Documents\\AI4HEOR",
      "c:/users/researcher/documents/AI4HEOR",
    )).toBe(true);
  });

  it("keeps different Windows directories distinct", () => {
    expect(sameLocalPath("C:\\AI4HEOR\\A", "C:\\AI4HEOR\\B")).toBe(false);
  });

  it("keeps POSIX paths case-sensitive", () => {
    expect(sameLocalPath("/Users/researcher/AI4HEOR", "/Users/Researcher/AI4HEOR"))
      .toBe(false);
  });

  it("does not treat an unavailable path as a match", () => {
    expect(sameLocalPath(null, "C:\\AI4HEOR")).toBe(false);
  });
});

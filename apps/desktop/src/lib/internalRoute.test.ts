import { describe, expect, it } from "vitest";
import { heorTaskPath, legacyTaskPath, runRecordPath } from "./internalRoute";

describe("internal route construction", () => {
  it("preserves ordinary application identifiers", () => {
    expect(heorTaskPath("ses_123-abc")).toBe("/heor/ses_123-abc");
    expect(legacyTaskPath("ses_123-abc")).toBe("/live/ses_123-abc");
    expect(runRecordPath("run_123-abc")).toBe("/runs?run=run_123-abc");
  });

  it("keeps attacker-shaped identifiers inside the application route", () => {
    const hostile = "\\\\outside.example/path?next=#fragment";

    expect(heorTaskPath(hostile)).toBe(
      "/heor/%5C%5Coutside.example%2Fpath%3Fnext%3D%23fragment",
    );
    expect(legacyTaskPath(hostile)).toBe(
      "/live/%5C%5Coutside.example%2Fpath%3Fnext%3D%23fragment",
    );
    expect(runRecordPath(hostile)).toBe(
      "/runs?run=%5C%5Coutside.example%2Fpath%3Fnext%3D%23fragment",
    );
  });
});

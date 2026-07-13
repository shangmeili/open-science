import { describe, expect, it } from "vitest";
import { buildHeorPrompt, HEOR_BROWSER_DEMO_PLAN, parseHeorPlan } from "./heor";

describe("AI4HEOR artifact contract", () => {
  it("parses the browser fixture and preserves review metadata", () => {
    const parsed = parseHeorPlan(JSON.stringify(HEOR_BROWSER_DEMO_PLAN));
    expect(parsed.analysis_id).toBe("first-line-nsclc-demo");
    expect(parsed.decision_problem.population).toContain("NSCLC");
    expect(parsed.assumptions).toHaveLength(1);
  });

  it("rejects a plan without a human-reviewable decision problem", () => {
    const invalid = { ...HEOR_BROWSER_DEMO_PLAN, decision_problem: undefined };
    expect(() => parseHeorPlan(JSON.stringify(invalid))).toThrow(/decision_problem/);
  });

  it("keeps natural-language intent primary while invoking the domain skill", () => {
    const prompt = buildHeorPrompt("Compare treatment A with standard care.");
    expect(prompt).toContain("Use $heor-workbench");
    expect(prompt).toContain("Compare treatment A with standard care.");
    expect(prompt).toContain("never create or claim human approvals");
  });
});

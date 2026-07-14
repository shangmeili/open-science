import { describe, expect, it } from "vitest";
import {
  auditHeorConceptualModel,
  auditHeorEvidence,
  buildHeorPrompt,
  HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL,
  HEOR_BROWSER_DEMO_BUDGET_IMPACT_AUDIT,
  HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT,
  HEOR_BROWSER_DEMO_PLAN,
  HEOR_BROWSER_DEMO_REFERENCE_CASE_AUDIT,
  HEOR_BROWSER_DEMO_UNCERTAINTY_AUDIT,
  HEOR_MODEL_VALIDATION_PATH,
  parseHeorConceptualModel,
  parseHeorPlan,
} from "./heor";

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

  it("fails closed when model inputs lack provenance", () => {
    const audit = auditHeorEvidence(HEOR_BROWSER_DEMO_PLAN);
    expect(audit.complete).toBe(false);
    expect(audit.coveredInputs).toBe(0);
    expect(audit.requiredInputs).toBe(14);
    expect(audit.unresolvedAssumptions).toEqual(["demo-only"]);
  });

  it("requires source-based inputs to bind the synthesis and exact extractions", () => {
    const plan = structuredClone(HEOR_BROWSER_DEMO_PLAN);
    plan.evidence_sources = [{
      id: "trial-1",
      title: "Input study",
      source_type: "randomized_trial",
      url: "https://example.test/trial-1",
      accessed_on: "2026-07-14",
    }];
    plan.input_provenance = [{
      path: "cycles",
      source_ids: ["trial-1"],
      assumption_ids: [],
      unit: "cycles",
      jurisdiction: "China",
      selection_rationale: "Directly reported follow-up",
      uncertainty_status: "fixed",
    }];
    let audit = auditHeorEvidence(plan);
    expect(audit.invalidMappings[0]).toContain("current evidence synthesis binding");
    expect(audit.invalidMappings[0]).toContain("no selected extraction");

    plan.evidence_synthesis = {
      path: "heor/evidence-synthesis.json",
      content_sha256: "a".repeat(64),
    };
    plan.input_provenance[0].extraction_ids = ["extract-cycles"];
    audit = auditHeorEvidence(plan);
    expect(audit.invalidMappings.join("; ")).not.toContain("current evidence synthesis binding");
    expect(audit.selectedExtractionCount).toBe(1);
  });

  it("audits the conceptual model independently from numerical inputs", () => {
    const parsed = parseHeorConceptualModel(JSON.stringify(HEOR_BROWSER_DEMO_CONCEPTUAL_MODEL));
    const audit = auditHeorConceptualModel(parsed);
    expect(audit.complete).toBe(true);
    expect(audit.stateCount).toBe(3);
    expect(audit.transitionCount).toBe(5);

    const unresolved = structuredClone(parsed);
    unresolved.structural_assumptions[0].status = "unresolved";
    expect(auditHeorConceptualModel(unresolved).complete).toBe(false);

    const missingExternalValidation = structuredClone(parsed);
    missingExternalValidation.validation_plan.external = [];
    const validationAudit = auditHeorConceptualModel(missingExternalValidation);
    expect(validationAudit.complete).toBe(false);
    expect(validationAudit.errors).toContain(
      "validation_plan.external must be a non-empty string array",
    );
    expect(auditHeorConceptualModel(parsed, "different-analysis").errors).toContain(
      "conceptual model analysis_id does not match the current analysis plan",
    );
  });

  it("keeps profile selection separate from reference-case compliance", () => {
    expect(HEOR_BROWSER_DEMO_PLAN.reference_case.status).toBe("current");
    expect(HEOR_BROWSER_DEMO_REFERENCE_CASE_AUDIT.complete).toBe(false);
    expect(HEOR_BROWSER_DEMO_REFERENCE_CASE_AUDIT.blockingGaps).toContain("cost-scope");
  });

  it("keeps a documented uncertainty path separate from an executable audit", () => {
    expect(HEOR_BROWSER_DEMO_PLAN.uncertainty_analysis?.path).toBe(
      "heor/uncertainty-plan.json",
    );
    expect(HEOR_BROWSER_DEMO_UNCERTAINTY_AUDIT.complete).toBe(false);
    expect(HEOR_BROWSER_DEMO_UNCERTAINTY_AUDIT.errors[0]).toContain(
      "uncertainty-plan.json",
    );
  });

  it("keeps the budget impact artifact separate and fail-closed", () => {
    expect(HEOR_BROWSER_DEMO_PLAN.budget_impact_analysis?.path).toBe(
      "heor/budget-impact-plan.json",
    );
    expect(HEOR_BROWSER_DEMO_BUDGET_IMPACT_AUDIT.complete).toBe(false);
    expect(HEOR_BROWSER_DEMO_BUDGET_IMPACT_AUDIT.errors[0]).toContain(
      "budget-impact-plan.json",
    );
  });

  it("keeps independent validation separate, local, and fail-closed", () => {
    expect(HEOR_MODEL_VALIDATION_PATH).toBe("heor/model-validation.json");
    expect(HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT.complete).toBe(false);
    expect(HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT.approvable).toBe(false);
    expect(HEOR_BROWSER_DEMO_MODEL_VALIDATION_AUDIT.requiredCoverageCount).toBe(18);
  });
});

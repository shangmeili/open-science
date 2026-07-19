import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import type { ConceptualModelDiagramAudit, HeorConceptualModel } from "@/lib/heor";
import { useUiStore } from "@/lib/store";
import { ConceptualModelDiagramAssessment } from "./ConceptualModelDiagramAssessment";

const model: HeorConceptualModel = {
  schema_version: "0.1.0",
  model_id: "model-1",
  analysis_id: "analysis-1",
  status: "ready_for_human_review",
  objective: "Compare treatment strategies",
  scope: {
    population: "Adults",
    intervention: "A",
    comparator: "B",
    perspective: "Healthcare system",
    time_horizon: "Lifetime",
    outcomes: ["cost", "QALY"],
    jurisdiction: "China",
    decision_context: "Research",
  },
  care_pathway: ["Treat", "Progress", "Death"],
  model_type: { proposed: "cohort_state_transition", rationale: "Adequate states" },
  states: [
    { id: "stable", label: "Stable", definition: "No progression", absorbing: false },
    { id: "progressed", label: "Progressed", definition: "Disease progression", absorbing: false },
    { id: "dead", label: "Dead", definition: "All-cause death", absorbing: true },
  ],
  transitions: [
    { id: "stable-stable", from: "stable", to: "stable", trigger: "Remain" },
    { id: "stable-progressed", from: "stable", to: "progressed", trigger: "Progress" },
    { id: "progressed-dead", from: "progressed", to: "dead", trigger: "Death" },
    { id: "dead-dead", from: "dead", to: "dead", trigger: "Absorbing" },
  ],
  structural_assumptions: [{
    id: "memoryless",
    statement: "Memoryless",
    rationale: "Model form",
    status: "proposed",
  }],
  structural_alternatives: [{
    id: "alt",
    description: "Alternative",
    rationale: "Plausible",
    expected_impact: "Occupancy",
  }],
  evidence_links: [{ claim: "Pathway", source_ids: ["source-1"] }],
  validation_plan: {
    face: ["Expert review"],
    internal: ["Boundary checks"],
    external: ["Outcome comparison"],
  },
  validation_questions: ["Are states exhaustive?"],
};

const readyAudit: ConceptualModelDiagramAudit = {
  complete: true,
  readyToGenerate: true,
  outputsCurrent: false,
  status: "ready_to_generate",
  modelId: "model-1",
  modelPath: "heor/conceptual-model.json",
  layoutPath: "deliverables/conceptual-model-layout.json",
  svgPath: "deliverables/conceptual-model.svg",
  graphmlPath: "deliverables/conceptual-model.graphml",
  auditPath: "deliverables/conceptual-model.audit.json",
  conceptualModelSha256: "a".repeat(64),
  layoutSha256: null,
  svgSha256: null,
  graphmlSha256: null,
  stateCount: 3,
  transitionCount: 4,
  positions: [],
  humanReviewStatus: "awaiting_human_review",
  errors: [],
  warnings: [],
};

afterEach(async () => {
  useUiStore.getState().setLocale("en");
  await act(async () => i18n.changeLanguage("en"));
});

describe("conceptual model diagram assessment", () => {
  it("edits only node positions and sends a complete layout to the native exporter", async () => {
    const onGenerate = vi.fn();
    render(
      <ConceptualModelDiagramAssessment
        model={model}
        modelComplete
        state={{ kind: "ready", audit: readyAudit }}
        generating={false}
        desktopAvailable
        onRequestModel={vi.fn()}
        onGenerate={onGenerate}
      />,
    );

    expect(screen.getByText(/Moving a node changes only the layout/)).toBeInTheDocument();
    const stable = screen.getByRole("button", { name: "Move state Stable" });
    stable.focus();
    await userEvent.keyboard("{ArrowRight}");
    await userEvent.click(screen.getByRole("button", { name: "Export SVG and editable GraphML" }));

    expect(onGenerate).toHaveBeenCalledOnce();
    const positions = onGenerate.mock.calls[0][0];
    expect(positions).toHaveLength(3);
    expect(new Set(positions.map((position: { stateId: string }) => position.stateId))).toEqual(
      new Set(["stable", "progressed", "dead"]),
    );
    expect(positions.find((position: { stateId: string }) => position.stateId === "stable").x)
      .toBeGreaterThan(120);
  });

  it("opens both current outputs while keeping the layout editable", () => {
    render(
      <ConceptualModelDiagramAssessment
        model={model}
        modelComplete
        state={{
          kind: "ready",
          audit: {
            ...readyAudit,
            outputsCurrent: true,
            status: "current",
            positions: [
              { stateId: "stable", x: 180, y: 300 },
              { stateId: "progressed", x: 500, y: 300 },
              { stateId: "dead", x: 820, y: 300 },
            ],
          },
        }}
        generating={false}
        desktopAvailable
        onRequestModel={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(screen.getByText("Current diagram is ready for review")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open SVG" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open editable GraphML" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Arrange automatically" })).toBeInTheDocument();
  });

  it("uses natural Chinese copy and sends structural changes back to the conversation", async () => {
    useUiStore.getState().setLocale("zh-Hans");
    await act(async () => i18n.changeLanguage("zh-Hans"));
    const onRequestModel = vi.fn();
    render(
      <ConceptualModelDiagramAssessment
        model={model}
        modelComplete={false}
        state={{ kind: "ready", audit: { ...readyAudit, complete: false, readyToGenerate: false } }}
        generating={false}
        desktopAvailable
        onRequestModel={onRequestModel}
        onGenerate={vi.fn()}
      />,
    );

    expect(screen.getByText(/移动节点只调整版式/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "与助手讨论模型结构" }));
    expect(onRequestModel).toHaveBeenCalledOnce();
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HEOR_BROWSER_DEMO_EVIDENCE_SYNTHESIS_AUDIT } from "@/lib/heor";
import { useUiStore } from "@/lib/store";
import { EvidenceVerificationDialog, HeorReviewPane } from "./HeorReviewPane";

afterEach(() => useUiStore.getState().setLocale("en"));

describe("AI4HEOR human review pane", () => {
  it("shows exact extraction details and records a selected rejection", async () => {
    const onSubmit = vi.fn();
    render(
      <EvidenceVerificationDialog
        audit={HEOR_BROWSER_DEMO_EVIDENCE_SYNTHESIS_AUDIT}
        running={false}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    expect(screen.getByText("CNY 12,500 per cycle")).toBeInTheDocument();
    expect(screen.getByText(/Table 3, intervention arm/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reject selected" }));
    await userEvent.click(screen.getByRole("checkbox", {
      name: "Select extraction extract-cost",
    }));
    await userEvent.type(screen.getByPlaceholderText("Name or local reviewer label"), "Reviewer A");
    await userEvent.type(
      screen.getByPlaceholderText(/How you checked the values/),
      "The table reports a different cycle cost.",
    );
    await userEvent.click(screen.getByRole("checkbox", {
      name: /I personally checked and reject all 1 selected extractions/,
    }));
    await userEvent.click(screen.getByRole("button", { name: "Record rejection" }));
    expect(onSubmit).toHaveBeenCalledWith(
      "Reviewer A",
      "The table reports a different cycle cost.",
      "rejected",
      ["extract-cost"],
    );
  });

  it("reads an agent-authored artifact and keeps approval human-only", async () => {
    render(
      <HeorReviewPane
        project={{ id: "ai4heor-demo", name: "Demo" }}
        onClose={vi.fn()}
        onRequestRevision={vi.fn()}
      />,
    );

    expect(
      await screen.findByText("Cost-effectiveness of a new first-line treatment for advanced NSCLC"),
    ).toBeInTheDocument();
    expect(screen.getByText("Human-authorized evidence search")).toBeInTheDocument();
    expect(screen.getByText("Exact request is ready for human authorization")).toBeInTheDocument();
    expect(screen.getByText("semaglutide AND type 2 diabetes AND cost effectiveness")).toBeInTheDocument();
    expect(screen.getByText("Evidence synthesis ledger")).toBeInTheDocument();
    expect(screen.getByText("Local evidence library")).toBeInTheDocument();
    expect(screen.getByText("Local sources are hash-bound and searchable")).toBeInTheDocument();
    expect(screen.getByText("Evidence synthesis needs human-guided work")).toBeInTheDocument();
    expect(screen.getByText("Not assessed")).toBeInTheDocument();
    expect(screen.getByText("Reviewer confirmations")).toBeInTheDocument();
    expect(screen.getByText("0/4")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review and authorize exact search" }))
      .not.toBeInTheDocument();
    expect(screen.getByText("Evidence audit incomplete")).toBeInTheDocument();
    expect(await screen.findByText("Structural audit complete")).toBeInTheDocument();
    expect(screen.getAllByText("0/14")).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Review Decision problem" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Record approval" });
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByPlaceholderText("Name or local reviewer label"), "Local reviewer");
    await userEvent.type(
      screen.getByPlaceholderText("What you checked and why this gate can proceed"),
      "Decision context checked against the project question.",
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "I performed this review myself" }));
    await userEvent.click(submit);

    expect(await screen.findByText("Approved for this artifact")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review Conceptual model" })).toBeInTheDocument();
  });

  it("keeps analysis-plan approval locked until evidence traceability is complete", async () => {
    const onRequestRevision = vi.fn();
    render(
      <HeorReviewPane
        project={{ id: "ai4heor-demo", name: "Demo" }}
        onClose={vi.fn()}
        onRequestRevision={onRequestRevision}
      />,
    );
    await screen.findByText("Evidence audit incomplete");
    expect(screen.getByText("Reference-case audit incomplete")).toBeInTheDocument();
    expect(screen.getByText("Uncertainty audit incomplete")).toBeInTheDocument();
    expect(screen.getByText("Budget impact audit incomplete")).toBeInTheDocument();
    expect(screen.getByText("Validation package is incomplete")).toBeInTheDocument();
    expect(screen.getByText("Report package is incomplete")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review Analysis plan" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask agent to resolve evidence gaps" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to continue screening and synthesis",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-evidence-synthesis"),
    );
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to search the local library",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-local-evidence"),
    );
    await userEvent.click(screen.getByRole("button", {
      name: "Ask agent to assess or repair reference-case gaps",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(expect.stringContaining("$heor-reference-case"));
    await userEvent.click(screen.getByRole("button", {
      name: "Ask agent to create or repair uncertainty analysis",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-uncertainty-analysis"),
    );
    await userEvent.click(screen.getByRole("button", {
      name: "Ask the Agent to build or repair budget impact",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-budget-impact"),
    );
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to prepare validation evidence",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-model-validation"),
    );
    await userEvent.click(screen.getByRole("button", {
      name: "Ask Agent to prepare or repair the report package",
    }));
    expect(onRequestRevision).toHaveBeenCalledWith(
      expect.stringContaining("$heor-reporting"),
    );
  });

  it("runs the browser fixture as an explicitly exploratory calculation", async () => {
    render(
      <HeorReviewPane
        project={{ id: "ai4heor-demo", name: "Demo" }}
        onClose={vi.fn()}
        onRequestRevision={vi.fn()}
      />,
    );
    await screen.findByText("Decision and model snapshot");
    await userEvent.click(screen.getByRole("button", { name: "Run deterministic analysis" }));
    expect(await screen.findByText("Exploratory")).toBeInTheDocument();
    expect(screen.getByText("Not decision-ready")).toBeInTheDocument();
  });
});

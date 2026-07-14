import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useUiStore } from "@/lib/store";
import { HeorReviewPane } from "./HeorReviewPane";

afterEach(() => useUiStore.getState().setLocale("en"));

describe("AI4HEOR human review pane", () => {
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
    expect(screen.queryByRole("button", { name: "Review and authorize exact search" }))
      .not.toBeInTheDocument();
    expect(screen.getByText("Evidence audit incomplete")).toBeInTheDocument();
    expect(screen.getByText("Structural audit complete")).toBeInTheDocument();
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

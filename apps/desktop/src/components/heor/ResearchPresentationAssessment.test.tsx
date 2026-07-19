import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useUiStore } from "@/lib/store";
import i18n from "@/i18n";
import { ResearchPresentationAssessment } from "./ResearchPresentationAssessment";

const readyAudit = {
  complete: true,
  readyToGenerate: true,
  outputCurrent: false,
  status: "ready_to_generate" as const,
  deckId: "project-readout",
  title: "Cost-effectiveness results",
  manifestPath: "deliverables/research-presentation.json",
  outputPath: "deliverables/research-presentation.pptx",
  auditPath: "deliverables/research-presentation.audit.json",
  manifestSha256: "a".repeat(64),
  outputSha256: null,
  authoredSlideCount: 8,
  renderedSlideCount: 9,
  sourceCount: 3,
  humanReviewStatus: "awaiting_human_review",
  errors: [],
};

afterEach(async () => {
  useUiStore.getState().setLocale("en");
  await act(async () => i18n.changeLanguage("en"));
});

describe("research presentation assessment", () => {
  it("offers deterministic generation only after the source-bound manifest is ready", async () => {
    const onGenerate = vi.fn();
    render(
      <ResearchPresentationAssessment
        state={{ kind: "ready", audit: readyAudit }}
        generating={false}
        onRequestPreparation={vi.fn()}
        onGenerate={onGenerate}
      />,
    );

    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByText(/not scientific approval/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Generate PPTX" }));
    expect(onGenerate).toHaveBeenCalledOnce();
  });

  it("keeps preparation conversational and uses natural Chinese research wording", async () => {
    useUiStore.getState().setLocale("zh-Hans");
    await act(async () => i18n.changeLanguage("zh-Hans"));
    const onPrepare = vi.fn();
    render(
      <ResearchPresentationAssessment
        state={{ kind: "ready", audit: { ...readyAudit, complete: false, readyToGenerate: false, status: "invalid", errors: ["缺少局限性页"] } }}
        generating={false}
        onRequestPreparation={onPrepare}
        onGenerate={vi.fn()}
      />,
    );

    expect(screen.getByText("尚未准备汇报内容")).toBeInTheDocument();
    expect(screen.getByText(/使用前仍需由研究者逐页核对/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "与助手一起准备汇报内容" }));
    expect(onPrepare).toHaveBeenCalledOnce();
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import i18n from "@/i18n";
import type { JournalSubmissionAudit } from "@/lib/heor";
import { JournalSubmissionAssessment } from "./JournalSubmissionAssessment";

const audit: JournalSubmissionAudit = {
  complete: true,
  readyToGenerate: true,
  outputsCurrent: false,
  status: "ready",
  checkId: "target-journal",
  title: "目标期刊投稿前核对",
  journalName: "Value in Health",
  articleType: "Economic Evaluation",
  guideAccessedOn: "2026-07-20",
  manifestPath: "deliverables/journal-submission-check.json",
  markdownPath: "deliverables/journal-submission-check.md",
  resultsPath: "deliverables/journal-submission-check.results.json",
  auditPath: "deliverables/journal-submission-check.audit.json",
  manifestSha256: "a".repeat(64),
  fileCount: 3,
  ruleCount: 8,
  passedCount: 5,
  failedRequiredCount: 1,
  reviewIssueCount: 1,
  unresolvedCount: 1,
  humanReviewStatus: "awaiting_human_review",
  errors: [],
  warnings: ["Mechanical checks do not establish journal compliance or permission to submit."],
};

function renderAssessment(props: Partial<React.ComponentProps<typeof JournalSubmissionAssessment>> = {}) {
  const onRequestPreparation = vi.fn();
  const onGenerate = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <JournalSubmissionAssessment
        state={{ kind: "ready", audit }}
        generating={false}
        onRequestPreparation={onRequestPreparation}
        onGenerate={onGenerate}
        {...props}
      />
    </I18nextProvider>,
  );
  return { onRequestPreparation, onGenerate };
}

describe("JournalSubmissionAssessment", () => {
  it("shows journal-specific counts without claiming submission readiness", () => {
    renderAssessment();
    expect(screen.getByText("Target-journal submission check")).toBeInTheDocument();
    expect(screen.getByText(/Value in Health/)).toBeInTheDocument();
    expect(screen.getByText("Required issues")).toBeInTheDocument();
    expect(screen.queryByText(/ready to submit|journal compliant/i)).not.toBeInTheDocument();
  });

  it("requests natural-language preparation when the manifest is missing", () => {
    const onRequestPreparation = vi.fn();
    renderAssessment({
      state: { kind: "invalid", message: "manifest missing" },
      onRequestPreparation,
    });
    fireEvent.click(screen.getByRole("button", { name: "Prepare checks with the assistant" }));
    expect(onRequestPreparation).toHaveBeenCalledTimes(1);
  });

  it("keeps deterministic generation as an explicit auxiliary action", () => {
    const { onGenerate } = renderAssessment();
    fireEvent.click(screen.getByRole("button", { name: "Generate check report" }));
    expect(onGenerate).toHaveBeenCalledTimes(1);
  });
});

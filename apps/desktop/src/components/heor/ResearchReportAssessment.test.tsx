import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { useUiStore } from "@/lib/store";
import { ResearchReportAssessment } from "./ResearchReportAssessment";

const readyAudit = {
  complete: true,
  readyToGenerate: true,
  outputsCurrent: false,
  status: "ready_to_generate" as const,
  documentId: "heor-report",
  title: "Cost-effectiveness report",
  manifestPath: "deliverables/heor-report-export.json",
  docxPath: "deliverables/heor-report.docx",
  pdfPath: "deliverables/heor-report.pdf",
  auditPath: "deliverables/heor-report.audit.json",
  manifestSha256: "a".repeat(64),
  reportPackageSha256: "b".repeat(64),
  reportDocumentSha256: "c".repeat(64),
  docxSha256: null,
  pdfSha256: null,
  blockCount: 42,
  tableCount: 3,
  pdfPageCount: 0,
  humanReviewStatus: "awaiting_human_review",
  fontName: "Source Han Sans CN",
  fontVersion: "2.005R",
  fontLicense: "OFL-1.1",
  fontSha256: "d".repeat(64),
  errors: [],
};

afterEach(async () => {
  useUiStore.getState().setLocale("en");
  await act(async () => i18n.changeLanguage("en"));
});

describe("research report assessment", () => {
  it("generates both document formats only from a ready source-bound manifest", async () => {
    const onGenerate = vi.fn();
    render(
      <ResearchReportAssessment
        state={{ kind: "ready", audit: readyAudit }}
        generating={false}
        onRequestPreparation={vi.fn()}
        onGenerate={onGenerate}
      />,
    );

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText(/does not approve the study/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Generate DOCX and PDF" }));
    expect(onGenerate).toHaveBeenCalledOnce();
  });

  it("uses direct Chinese research wording and keeps preparation conversational", async () => {
    useUiStore.getState().setLocale("zh-Hans");
    await act(async () => i18n.changeLanguage("zh-Hans"));
    const onPrepare = vi.fn();
    render(
      <ResearchReportAssessment
        state={{ kind: "ready", audit: { ...readyAudit, complete: false, readyToGenerate: false, status: "invalid", errors: ["报告正文已变化"] } }}
        generating={false}
        onRequestPreparation={onPrepare}
        onGenerate={vi.fn()}
      />,
    );

    expect(screen.getByText("尚未准备报告文件")).toBeInTheDocument();
    expect(screen.getByText(/仍需研究者核对正文、数字、表格/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "与助手一起整理报告" }));
    expect(onPrepare).toHaveBeenCalledOnce();
  });
});

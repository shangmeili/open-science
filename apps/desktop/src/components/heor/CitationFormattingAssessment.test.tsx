import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CitationFormattingAssessment } from "./CitationFormattingAssessment";
import type { CitationFormattingAudit } from "@/lib/heor";

const openArtifactExternally = vi.fn();

vi.mock("@/lib/artifactFile", () => ({ openArtifactExternally: (...args: unknown[]) => openArtifactExternally(...args) }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const audit: CitationFormattingAudit = {
  complete: true,
  readyToGenerate: true,
  outputCurrent: false,
  status: "ready_to_generate",
  documentId: "report",
  title: "Report references",
  styleId: "ai4heor-cn-medical-numeric-v1",
  planPath: "references/citation-plan.json",
  libraryPath: "references/library.json",
  outputPath: "deliverables/references.md",
  auditPath: "deliverables/references.audit.json",
  planSha256: "a".repeat(64),
  librarySha256: "b".repeat(64),
  outputSha256: null,
  citationCount: 3,
  bibliographyCount: 5,
  metadataWarningCount: 1,
  humanReviewStatus: "awaiting_human_review",
  errors: [],
  warnings: ["ref-5: missing page"],
};

describe("CitationFormattingAssessment", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows source-bound counts and generates only when the plan is ready", () => {
    const onGenerate = vi.fn();
    render(<CitationFormattingAssessment state={{ kind: "ready", audit }} generating={false} onRequestPreparation={vi.fn()} onGenerate={onGenerate} />);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText(/ref-5: missing page/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("citationFormatting.generate"));
    expect(onGenerate).toHaveBeenCalledTimes(1);
  });

  it("opens only the audited current output", () => {
    render(<CitationFormattingAssessment state={{ kind: "ready", audit: { ...audit, outputCurrent: true, outputSha256: "c".repeat(64) } }} generating={false} onRequestPreparation={vi.fn()} onGenerate={vi.fn()} />);
    fireEvent.click(screen.getByText("citationFormatting.open"));
    expect(openArtifactExternally).toHaveBeenCalledWith("deliverables/references.md");
  });

  it("routes a missing plan back to natural-language preparation", () => {
    const onRequestPreparation = vi.fn();
    render(<CitationFormattingAssessment state={{ kind: "ready", audit: { ...audit, complete: false, readyToGenerate: false, status: "missing", errors: ["citation plan is required"] } }} generating={false} onRequestPreparation={onRequestPreparation} onGenerate={vi.fn()} />);
    fireEvent.click(screen.getByText("citationFormatting.askPrepare"));
    expect(onRequestPreparation).toHaveBeenCalledTimes(1);
  });
});

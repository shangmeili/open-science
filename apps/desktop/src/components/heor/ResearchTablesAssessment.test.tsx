import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ResearchTablesAudit } from "@/lib/heor";
import { ResearchTablesAssessment } from "./ResearchTablesAssessment";

const openArtifactExternally = vi.fn();

vi.mock("@/lib/artifactFile", () => ({ openArtifactExternally: (...args: unknown[]) => openArtifactExternally(...args) }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const audit: ResearchTablesAudit = {
  complete: true,
  readyToGenerate: true,
  outputsCurrent: false,
  status: "ready",
  workbookId: "cea-summary",
  title: "CEA summary tables",
  manifestPath: "deliverables/research-tables.json",
  xlsxPath: "deliverables/research-tables.xlsx",
  csvDirectory: "deliverables/research-tables",
  auditPath: "deliverables/research-tables.audit.json",
  manifestSha256: "a".repeat(64),
  sourceCount: 3,
  tableCount: 2,
  rowCount: 12,
  csvFileCount: 0,
  xlsxSha256: null,
  humanReviewStatus: "awaiting_human_review",
  neutralizedTextCount: 1,
  errors: [],
  warnings: ["one formula-like text value will be neutralized in CSV"],
};

describe("ResearchTablesAssessment", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows source-bound counts and generates only from a ready manifest", () => {
    const onGenerate = vi.fn();
    render(<ResearchTablesAssessment state={{ kind: "ready", audit }} generating={false} onRequestPreparation={vi.fn()} onGenerate={onGenerate} />);
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText(/formula-like/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("researchTables.generate"));
    expect(onGenerate).toHaveBeenCalledTimes(1);
  });

  it("opens only current audited outputs", () => {
    render(<ResearchTablesAssessment state={{ kind: "ready", audit: { ...audit, outputsCurrent: true, status: "current", csvFileCount: 2, xlsxSha256: "b".repeat(64) } }} generating={false} onRequestPreparation={vi.fn()} onGenerate={vi.fn()} />);
    fireEvent.click(screen.getByText("researchTables.openXlsx"));
    fireEvent.click(screen.getByText("researchTables.openCsvFolder"));
    expect(openArtifactExternally).toHaveBeenNthCalledWith(1, "deliverables/research-tables.xlsx");
    expect(openArtifactExternally).toHaveBeenNthCalledWith(2, "deliverables/research-tables");
  });

  it("routes a missing manifest back to the conversation", () => {
    const onRequestPreparation = vi.fn();
    render(<ResearchTablesAssessment state={{ kind: "ready", audit: { ...audit, complete: false, readyToGenerate: false, status: "missing", errors: ["manifest required"] } }} generating={false} onRequestPreparation={onRequestPreparation} onGenerate={vi.fn()} />);
    fireEvent.click(screen.getByText("researchTables.askPrepare"));
    expect(onRequestPreparation).toHaveBeenCalledTimes(1);
  });
});

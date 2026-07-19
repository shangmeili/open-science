import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderAt } from "@/test/render";
import { useUiStore } from "@/lib/store";
import i18n from "@/i18n";

const mocks = vi.hoisted(() => ({
  auditSkillCandidates: vi.fn(),
  appendSkillCandidateReview: vi.fn(),
}));

vi.mock("@/lib/tauri", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/tauri")>();
  return {
    ...actual,
    auditSkillCandidates: mocks.auditSkillCandidates,
    appendSkillCandidateReview: mocks.appendSkillCandidateReview,
  };
});

afterEach(async () => {
  useUiStore.getState().setLocale("en");
  await act(async () => i18n.changeLanguage("en"));
  vi.clearAllMocks();
});

describe("SkillsPage project capability review", () => {
  it("requires an explicit Human assertion before activating exact candidate bytes", async () => {
    mocks.auditSkillCandidates.mockResolvedValue({
      projectAvailable: true,
      projectId: "0123456789abcdef",
      complete: true,
      candidates: [{
        candidateId: "heor-table-notes",
        createdAt: "2026-07-19T13:00:00Z",
        request: "Preserve our reviewed table-note format.",
        localized: {
          en: {
            displayName: "HEOR table notes",
            description: "Format reviewed HEOR table notes.",
            licenseNote: "Local project use only.",
            limitations: ["Presentation only"],
            acceptanceChecks: ["Values remain unchanged"],
          },
          "zh-Hans": {
            displayName: "药物经济学表注",
            description: "整理已经复核的药物经济学表注。",
            licenseNote: "仅限当前本地项目使用。",
            limitations: ["仅调整呈现方式"],
            acceptanceChecks: ["数值保持不变"],
          },
        },
        provider: "minimax-cn",
        model: "MiniMax-M2.7",
        licenseSpdx: "LicenseRef-Project-Private",
        licenseNote: "Local project use only.",
        acceptanceChecksSha256: "a".repeat(64),
        decisionSha256: "b".repeat(64),
        activeTreeSha256: "c".repeat(64),
        valid: true,
        validationErrors: [],
        status: "inactive",
        canActivate: true,
        canReject: true,
        canRevoke: false,
      }],
      integrity: "verified_unanchored_sha256_chain",
      identityAssurance: "app_owned_local_human_assertion",
      errors: [],
    });
    mocks.appendSkillCandidateReview.mockResolvedValue({ reviewId: "review" });

    renderAt("/skills");
    expect(await screen.findByText("HEOR table notes")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Review and activate" }));
    expect(screen.getByRole("dialog", { name: "Review and activate this capability" })).toBeInTheDocument();
    expect(screen.getByText("Values remain unchanged")).toBeInTheDocument();
    expect(screen.getByText("Presentation only")).toBeInTheDocument();

    const submit = screen.getByRole("button", { name: "Record and activate" });
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByPlaceholderText("For example: HEOR methods reviewer"), "Methods reviewer");
    await userEvent.type(
      screen.getByPlaceholderText("State what you checked and why this narrow capability is acceptable for this project."),
      "Exact instructions and limitations reviewed.",
    );
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(submit);

    await waitFor(() => expect(mocks.appendSkillCandidateReview).toHaveBeenCalledWith({
      projectId: "0123456789abcdef",
      candidateId: "heor-table-notes",
      decisionSha256: "b".repeat(64),
      acceptanceChecksSha256: "a".repeat(64),
      action: "activate",
      actorLabel: "Methods reviewer",
      rationale: "Exact instructions and limitations reviewed.",
    }));
  });

  it("shows localized acceptance checks and limitations in the review dialog", async () => {
    mocks.auditSkillCandidates.mockResolvedValue({
      projectAvailable: true,
      projectId: "0123456789abcdef",
      complete: true,
      candidates: [{
        candidateId: "heor-table-notes",
        createdAt: "2026-07-19T13:00:00Z",
        request: "Preserve our reviewed table-note format.",
        localized: {
          en: {
            displayName: "HEOR table notes",
            description: "Format reviewed HEOR table notes.",
            licenseNote: "Local project use only.",
            limitations: ["Presentation only"],
            acceptanceChecks: ["Values remain unchanged"],
          },
          "zh-Hans": {
            displayName: "药物经济学表注",
            description: "整理已经复核的药物经济学表注。",
            licenseNote: "仅限当前本地项目使用。",
            limitations: ["仅调整呈现方式"],
            acceptanceChecks: ["数值保持不变"],
          },
        },
        provider: "local-test",
        model: "fixture",
        licenseSpdx: "MIT",
        licenseNote: "仅限本地项目测试。",
        acceptanceChecksSha256: "a".repeat(64),
        decisionSha256: "b".repeat(64),
        activeTreeSha256: "c".repeat(64),
        valid: true,
        validationErrors: [],
        status: "inactive",
        canActivate: true,
        canReject: true,
        canRevoke: false,
      }],
      integrity: "verified_unanchored_sha256_chain",
      identityAssurance: "app_owned_local_human_assertion",
      errors: [],
    });

    renderAt("/skills");
    await act(async () => {
      useUiStore.getState().setLocale("zh-Hans");
      await i18n.changeLanguage("zh-Hans");
    });
    await userEvent.click(await screen.findByRole("button", { name: "复核并启用" }));
    expect(screen.getByText("数值保持不变")).toBeInTheDocument();
    expect(screen.getByText("仅调整呈现方式")).toBeInTheDocument();
    expect(screen.getByText("仅限当前本地项目使用。")).toBeInTheDocument();
    expect(screen.queryByText("Values remain unchanged")).not.toBeInTheDocument();
    expect(screen.queryByText("Local project use only.")).not.toBeInTheDocument();
  });
});

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderAt } from "@/test/render";
import { useUiStore } from "@/lib/store";

const mocks = vi.hoisted(() => ({
  auditLocalPreferences: vi.fn(),
  appendLocalPreferenceReview: vi.fn(),
}));

vi.mock("@/lib/tauri", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/tauri")>();
  return {
    ...actual,
    auditLocalPreferences: mocks.auditLocalPreferences,
    appendLocalPreferenceReview: mocks.appendLocalPreferenceReview,
  };
});

afterEach(() => {
  useUiStore.getState().setLocale("en");
  vi.clearAllMocks();
});

describe("SkillsPage local preference review", () => {
  it("requires a Human review and permits editing before accepting exact proposal and store bytes", async () => {
    mocks.auditLocalPreferences.mockResolvedValue({
      projectAvailable: true,
      projectId: "0123456789abcdef",
      complete: true,
      storeSha256: "a".repeat(64),
      proposals: [{
        proposalId: "concise-table-note",
        createdAt: "2026-07-19T13:00:00Z",
        scope: "presentation",
        proposedRule: "Always add a concise note below result tables.",
        evidence: [
          { interactionRef: "session-a", observedAt: "2026-07-19T12:00:00Z", summary: "Asked for a concise Chinese table note." },
          { interactionRef: "session-b", observedAt: "2026-07-19T12:30:00Z", summary: "Asked for the same table-note format again." },
        ],
        counterexamples: [],
        reviewCondition: "Review when the output language changes.",
        proposalSha256: "b".repeat(64),
        valid: true,
        validationErrors: [],
        accepted: false,
      }],
      preferences: [],
      integrity: "verified_unanchored_sha256_chain",
      identityAssurance: "app_owned_local_human_assertion",
      errors: [],
    });
    mocks.appendLocalPreferenceReview.mockResolvedValue({ reviewId: "review" });

    renderAt("/skills");
    expect(await screen.findByText("Always add a concise note below result tables.")).toBeInTheDocument();
    expect(screen.getByText("Supported by 2 independent interactions · Review when the output language changes.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Review and accept" }));

    const dialog = screen.getByRole("dialog", { name: "Review this suggested preference" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText("Asked for a concise Chinese table note.")).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Record and accept" });
    expect(submit).toBeDisabled();

    const rule = screen.getByDisplayValue("Always add a concise note below result tables.");
    await userEvent.clear(rule);
    await userEvent.type(rule, "Add a concise Chinese note below reviewed HEOR result tables.");
    await userEvent.type(screen.getByPlaceholderText("For example: project researcher"), "Project researcher");
    await userEvent.type(
      screen.getByPlaceholderText("Explain why this repeated pattern should become a local work preference."),
      "This presentation preference was requested independently twice.",
    );
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(submit);

    await waitFor(() => expect(mocks.appendLocalPreferenceReview).toHaveBeenCalledWith({
      projectId: "0123456789abcdef",
      preferenceId: "concise-table-note",
      proposalSha256: "b".repeat(64),
      storeSha256: "a".repeat(64),
      action: "accept",
      rule: "Add a concise Chinese note below reviewed HEOR result tables.",
      actorLabel: "Project researcher",
      rationale: "This presentation preference was requested independently twice.",
    }));
  });
});

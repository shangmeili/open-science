import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { useUiStore } from "@/lib/store";
import { Composer } from "./Composer";

// COPYCAT RULE: useUiStore is module-global; reset the locale after each test
// so this suite never bleeds a non-English locale into other test files.
afterEach(() => useUiStore.getState().setLocale("en"));

describe("Composer strings (i18n)", () => {
  it("renders the default placeholder and the approval-mode switch in English", () => {
    render(<Composer onSend={() => {}} approvalMode="approve" onApprovalModeChange={() => {}} />);
    expect(screen.getByPlaceholderText("Ask anything")).toBeInTheDocument();
    expect(screen.getByLabelText("Approval mode")).toHaveTextContent("Approve for me");
  });
});

describe("LiveSessionPage strings (i18n)", () => {
  it("keeps runtime implementation details out of the disconnected research surface", async () => {
    const view = renderAt("/live");
    expect(await screen.findByText("AI assistant unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Reconnect, or check the AI assistant runtime in Settings. Your local project files remain available.",
      ),
    ).toBeInTheDocument();
    expect(view.container).not.toHaveTextContent(/OpenCode|opencode serve/i);
  });
});

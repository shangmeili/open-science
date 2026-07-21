import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { UserMessage } from "./atoms";

vi.mock("@/lib/clipboard", () => ({ copyText: vi.fn(async () => {}) }));

describe("UserMessage history actions", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("does not offer rollback actions until the runtime supplies a message id", () => {
    render(<UserMessage block={{ kind: "user", text: "Question" }} />);
    expect(screen.queryByRole("button", { name: "Edit and continue from here" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
  });

  it("edits a message only after an explicit save", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    render(
      <UserMessage
        block={{ kind: "user", text: "Original question", messageID: "msg-1" }}
        onEdit={onEdit}
        onRevert={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Edit and continue from here" }));
    const editor = screen.getByRole("textbox", { name: "Edit message" });
    await user.clear(editor);
    await user.type(editor, "Revised question");
    await user.click(screen.getByRole("button", { name: "Save and continue" }));

    expect(onEdit).toHaveBeenCalledWith("msg-1", "Revised question");
  });

  it("requires confirmation before returning to an earlier point", async () => {
    const user = userEvent.setup();
    const onRevert = vi.fn();
    render(
      <UserMessage
        block={{ kind: "user", text: "Original question", messageID: "msg-1" }}
        onEdit={vi.fn()}
        onRevert={onRevert}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Return to this point" }));
    expect(onRevert).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog", { name: "Return to this point?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return here" }));
    expect(onRevert).toHaveBeenCalledWith("msg-1", "Original question");
  });
});

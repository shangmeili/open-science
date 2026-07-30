import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PromptQueue } from "./PromptQueue";

const items = [
  { id: "q1", text: "First follow-up" },
  { id: "q2", text: "Second follow-up", skill: { id: "audit", label: "Audit" } },
];

describe("PromptQueue", () => {
  it("shows queued messages and supports reorder and removal", () => {
    const onMove = vi.fn();
    const onRemove = vi.fn();
    render(<PromptQueue items={items} onMove={onMove} onRemove={onRemove} />);

    expect(screen.getByText("First follow-up")).toBeInTheDocument();
    expect(screen.getByText("Second follow-up")).toBeInTheDocument();
    expect(screen.getByText("Skill: Audit")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Move message 2 up" }));
    expect(onMove).toHaveBeenCalledWith("q2", "up");
    fireEvent.click(screen.getByRole("button", { name: "Remove queued message 1" }));
    expect(onRemove).toHaveBeenCalledWith("q1");
  });
});

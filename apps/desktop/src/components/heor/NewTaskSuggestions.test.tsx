import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NewTaskSuggestions } from "./NewTaskSuggestions";

describe("NewTaskSuggestions", () => {
  it("prefills a researcher-facing evidence request without development internals", async () => {
    const onPick = vi.fn();
    render(<NewTaskSuggestions onPick={onPick} />);

    await userEvent.click(screen.getByRole("button", { name: "Find and organize evidence" }));

    expect(onPick).toHaveBeenCalledTimes(1);
    const prompt = onPick.mock.calls[0][0] as string;
    expect(prompt).toContain("literature, trial registries, and methods sources");
    expect(prompt).toContain("RIS, BibTeX, or CSL-JSON");
    expect(prompt).toContain("lawfully available open versions");
    expect(prompt).not.toMatch(/Git|\.json|panel|permission mode|full-access|\$heor-/i);
  });
});

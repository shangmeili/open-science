import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReasoningRow } from "./ReasoningRow";

describe("ReasoningRow", () => {
  it("shows a localized activity signal without exposing raw model reasoning", () => {
    render(<ReasoningRow block={{ kind: "reasoning", text: "Checking evidence quality" }} streaming />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("Checking evidence quality")).not.toBeInTheDocument();
  });

  it("does not retain completed reasoning as conversation clutter", () => {
    const { container } = render(
      <ReasoningRow block={{ kind: "reasoning", text: "Compared model assumptions" }} />,
    );
    expect(screen.queryByText("Compared model assumptions")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });
});

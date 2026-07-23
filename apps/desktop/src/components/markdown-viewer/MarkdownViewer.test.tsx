import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownViewer } from "./MarkdownViewer";

describe("MarkdownViewer", () => {
  it("renders inline and block health-economic formulas with KaTeX", () => {
    const { container } = render(
      <MarkdownViewer>{"ICER: $\\Delta C / \\Delta E$.\n\n$$QALY = \\sum_t u_t \\Delta t$$"}</MarkdownViewer>,
    );
    expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(2);
    expect(container.textContent).not.toContain("$\\Delta C / \\Delta E$");
  });

  it("keeps currency text with a lone dollar sign literal", () => {
    const { container } = render(<MarkdownViewer>{"It costs $5 and **works**."}</MarkdownViewer>);
    expect(container.querySelector("strong")?.textContent).toBe("works");
    expect(container.querySelector(".katex")).toBeNull();
    expect(container.textContent).toContain("$5");
  });

  it("renders bracket-delimited LaTeX without exposing raw commands", () => {
    const { container } = render(
      <MarkdownViewer>{"Distance \\(d\\):\n\n\\[d=\\sqrt{x^2+y^2}\\]"}</MarkdownViewer>,
    );
    expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(2);
    container.querySelectorAll("annotation").forEach((annotation) => annotation.remove());
    expect(container.textContent).not.toContain("\\sqrt");
    expect(container.textContent).not.toContain("\\[");
  });

  it("does not normalize bracket delimiters inside code", () => {
    const { container } = render(
      <MarkdownViewer>{"Use `\\(x\\)` inline.\n\n```latex\n\\[E=mc^2\\]\n```"}</MarkdownViewer>,
    );
    expect(container.querySelector(".katex")).toBeNull();
    expect(container.textContent).toContain("\\(x\\)");
    expect(container.textContent).toContain("\\[");
  });
});

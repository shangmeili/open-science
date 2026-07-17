import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";

describe("legacy generic example routes", () => {
  it("does not expose inherited Open Science showcase sessions", () => {
    renderAt("/example/lit-review");
    expect(screen.getByText("404 — Not found")).toBeInTheDocument();
    expect(screen.queryByText("Cross-species scRNA-seq Integration")).not.toBeInTheDocument();
  });
});

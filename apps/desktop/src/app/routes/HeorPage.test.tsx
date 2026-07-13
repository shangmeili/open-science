import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { useRuntimeStore } from "@/lib/runtime";
import { useUiStore } from "@/lib/store";

const defaults = {
  status: useRuntimeStore.getState().status,
  currentId: useRuntimeStore.getState().currentId,
};

afterEach(() => {
  useRuntimeStore.setState(defaults);
  useUiStore.getState().setLocale("en");
});

describe("AI4HEOR conversation route", () => {
  it("makes natural-language research the primary empty state", async () => {
    useRuntimeStore.setState({ status: "ready", currentId: null });
    renderAt("/heor");

    expect(await screen.findByRole("heading", { name: "Start with the research question" })).toBeInTheDocument();
    expect(screen.getByText(/forms stay secondary/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Describe the decision problem/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review analysis" })).toBeInTheDocument();
  });
});

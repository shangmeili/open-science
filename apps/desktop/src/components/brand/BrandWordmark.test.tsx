import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useUiStore } from "@/lib/store";
import { BrandWordmark } from "./BrandWordmark";

describe("BrandWordmark", () => {
  afterEach(() => act(() => useUiStore.setState({ theme: "light" })));

  it("uses the supplied wordmark that remains legible in each app theme", () => {
    useUiStore.setState({ theme: "light" });
    render(<BrandWordmark alt="AI4HEOR" data-testid="wordmark" />);
    expect(screen.getByTestId("wordmark")).toHaveAttribute(
      "src",
      expect.stringContaining("ai4heor-wordmark-light.svg"),
    );

    act(() => useUiStore.getState().setTheme("warm"));
    expect(screen.getByTestId("wordmark")).toHaveAttribute(
      "src",
      expect.stringContaining("ai4heor-wordmark-light.svg"),
    );

    act(() => useUiStore.getState().setTheme("dark"));
    expect(screen.getByTestId("wordmark")).toHaveAttribute(
      "src",
      expect.stringContaining("ai4heor-wordmark-dark.svg"),
    );
  });
});

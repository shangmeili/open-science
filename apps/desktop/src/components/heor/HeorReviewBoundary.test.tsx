import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { expect, it, vi } from "vitest";
import { HeorReviewBoundary } from "./HeorReviewBoundary";

function BrokenReview(): ReactElement {
  throw new Error("mapping.path.endsWith is not a function");
}

it("keeps review failures inside a researcher-facing recovery card", async () => {
  const onRetry = vi.fn();
  render(
    <HeorReviewBoundary
      title="Research and analysis could not be displayed"
      body="Your files have not been changed."
      retryLabel="Read again"
      onRetry={onRetry}
    >
      <BrokenReview />
    </HeorReviewBoundary>,
  );

  expect(screen.getByRole("heading", { name: "Research and analysis could not be displayed" }))
    .toBeInTheDocument();
  expect(screen.getByText("Your files have not been changed.")).toBeInTheDocument();
  expect(screen.queryByText(/endsWith/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Read again" }));
  expect(onRetry).toHaveBeenCalledOnce();
});

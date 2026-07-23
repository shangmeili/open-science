import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useThrottledValue } from "./useThrottledValue";

describe("useThrottledValue", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("commits an initial change immediately and then the latest trailing value", () => {
    const { result, rerender } = renderHook(({ value }) => useThrottledValue(value, 100), {
      initialProps: { value: "a" },
    });
    act(() => rerender({ value: "b" }));
    expect(result.current).toBe("b");
    act(() => rerender({ value: "c" }));
    act(() => rerender({ value: "d" }));
    expect(result.current).toBe("b");
    act(() => vi.advanceTimersByTime(100));
    expect(result.current).toBe("d");
  });
});

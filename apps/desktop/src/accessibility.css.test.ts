import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve("src/index.css"), "utf8");

function token(name: string): string {
  const value = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))?.[1];
  if (!value) throw new Error(`missing color token --${name}`);
  return value;
}

function luminance(hex: string): number {
  const channels = hex
    .slice(1)
    .match(/.{2}/g)!
    .map((part) => Number.parseInt(part, 16) / 255)
    .map((part) => (part <= 0.04045 ? part / 12.92 : ((part + 0.055) / 1.055) ** 2.4));
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(foreground: string, background: string): number {
  const first = luminance(foreground);
  const second = luminance(background);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

describe("light-theme accessibility tokens", () => {
  it("keeps normal supporting and primary-button text at WCAG AA contrast", () => {
    expect(contrast(token("muted"), token("bg"))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("muted"), token("surface"))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("accent-fg"), token("accent"))).toBeGreaterThanOrEqual(4.5);
  });
});

import { describe, expect, it } from "vitest";
import { splitStreamingMarkdown } from "./markdownSegments";

describe("splitStreamingMarkdown", () => {
  it("seals completed paragraphs and leaves the growing tail open", () => {
    expect(splitStreamingMarkdown("First.\n\nSecond.\n\nThird")).toEqual({
      sealed: ["First.\n\n", "Second.\n\n"],
      tail: "Third",
    });
  });

  it("does not split open code fences or block math", () => {
    expect(splitStreamingMarkdown("Intro.\n\n```py\nx = 1\n\n").sealed).toEqual(["Intro.\n\n"]);
    expect(splitStreamingMarkdown("Intro.\n\n$$\nx + y\n\n").sealed).toEqual(["Intro.\n\n"]);
  });

  it("keeps loose lists and nested code together", () => {
    const text = "- Build:\n\n    ```bash\n    make\n    ```\n\n- Test\n\nAfter";
    expect(splitStreamingMarkdown(text)).toEqual({
      sealed: ["- Build:\n\n    ```bash\n    make\n    ```\n\n- Test\n\n"],
      tail: "After",
    });
  });

  it("is lossless and prefix-stable while text grows", () => {
    const final = "One.\n\nTwo.\n\n```\ncode\n\nmore\n```\n\nLast";
    let previous: string[] = [];
    for (let index = 1; index <= final.length; index += 1) {
      const current = final.slice(0, index);
      const result = splitStreamingMarkdown(current);
      expect(result.sealed.join("") + result.tail).toBe(current);
      previous.forEach((segment, segmentIndex) => expect(result.sealed[segmentIndex]).toBe(segment));
      previous = result.sealed;
    }
  });

  it("tolerates CRLF input", () => {
    expect(splitStreamingMarkdown("One.\r\n\r\nTwo.")).toEqual({
      sealed: ["One.\r\n\r\n"],
      tail: "Two.",
    });
  });
});

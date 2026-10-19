export interface StreamingSegments {
  sealed: string[];
  tail: string;
}

const FENCE = /^(\s*)(`{3,}|~{3,})/;
const MATH = /^\s*\$\$/;
const LIST_ITEM = /^([-*+]|\d{1,9}[.)])(\s|$)/;
const LIST_ITEM_PREFIX = /^([-*+]|\d{1,9}[.)]?)$/;

function startsNewBlock(line: string, complete: boolean): boolean | null {
  if (/^\s/.test(line) || LIST_ITEM.test(line)) return false;
  if (!complete && LIST_ITEM_PREFIX.test(line)) return null;
  return true;
}

/** Split a growing Markdown document into immutable blocks plus a live tail. */
export function splitStreamingMarkdown(text: string): StreamingSegments {
  const sealed: string[] = [];
  let fence: string | null = null;
  let inMath = false;
  let hasContent = false;
  let segmentStart = 0;
  let boundary: number | null = null;

  const length = text.length;
  let index = 0;
  while (index < length) {
    let endOfLine = text.indexOf("\n", index);
    const complete = endOfLine !== -1;
    if (!complete) endOfLine = length;
    const line = text.slice(index, endOfLine);
    const trimmed = line.trim();
    const blank = trimmed === "";

    if (!blank && boundary !== null) {
      const verdict = startsNewBlock(line, complete);
      if (verdict === null) break;
      if (verdict) {
        sealed.push(text.slice(segmentStart, boundary));
        segmentStart = boundary;
      }
      boundary = null;
    }

    const fenceHit = line.match(FENCE);
    if (fence !== null) {
      if (
        fenceHit &&
        fenceHit[2][0] === fence[0] &&
        fenceHit[2].length >= fence.length &&
        line.slice(fenceHit[0].length).trim() === ""
      ) fence = null;
    } else if (fenceHit) {
      fence = fenceHit[2];
    } else if (MATH.test(line)) {
      const selfContained = trimmed.length > 3 && trimmed.endsWith("$$");
      if (!selfContained) inMath = !inMath;
    }

    if (blank && fence === null && !inMath && hasContent && boundary === null) {
      boundary = complete ? endOfLine + 1 : length;
      hasContent = false;
    } else if (!blank) {
      hasContent = true;
    }
    index = endOfLine + 1;
  }

  return { sealed, tail: text.slice(segmentStart) };
}

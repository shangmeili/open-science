import { describe, expect, it } from "vitest";
import {
  conversationSourceFromLocationState,
  conversationSourceIndex,
  conversationSourceNavigationState,
} from "./conversationSource";

describe("conversation source navigation", () => {
  it("keeps exact source identifiers in internal router state", () => {
    const state = conversationSourceNavigationState("msg_assistant_1", "toolu_1");
    expect(conversationSourceFromLocationState(state)).toEqual({
      assistantMessageId: "msg_assistant_1",
      toolCallId: "toolu_1",
    });
  });

  it("does not fall back when an assistant/tool pair has no exact composite match", () => {
    const index = {
      "message:msg_assistant_1": 2,
      "tool:toolu_unrelated": 7,
    };
    expect(conversationSourceIndex(index, {
      assistantMessageId: "msg_assistant_1",
      toolCallId: "toolu_unrelated",
    })).toBeUndefined();
  });

  it("rejects malformed or control-character source state", () => {
    expect(conversationSourceFromLocationState(null)).toBeNull();
    expect(conversationSourceFromLocationState({
      conversationSource: { assistantMessageId: "msg\nunsafe" },
    })).toBeNull();
  });
});

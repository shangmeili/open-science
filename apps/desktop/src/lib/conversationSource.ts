export interface ConversationSource {
  assistantMessageId: string;
  toolCallId?: string;
}

interface ConversationSourceLocationState {
  conversationSource: ConversationSource;
}

const sourceId = (value: unknown): string | undefined => {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  const hasControlCharacter = [...trimmed].some((character) => {
    const code = character.charCodeAt(0);
    return code <= 31 || code === 127;
  });
  return trimmed && trimmed.length <= 256 && !hasControlCharacter
    ? trimmed
    : undefined;
};

/** Keep source identifiers in router state, not the visible URL. */
export function conversationSourceNavigationState(
  assistantMessageId: string,
  toolCallId?: string,
): ConversationSourceLocationState {
  return {
    conversationSource: {
      assistantMessageId,
      ...(toolCallId ? { toolCallId } : {}),
    },
  };
}

export function conversationSourceFromLocationState(value: unknown): ConversationSource | null {
  if (!value || typeof value !== "object") return null;
  const candidate = (value as { conversationSource?: unknown }).conversationSource;
  if (!candidate || typeof candidate !== "object") return null;
  const assistantMessageId = sourceId(
    (candidate as { assistantMessageId?: unknown }).assistantMessageId,
  );
  const toolCallId = sourceId((candidate as { toolCallId?: unknown }).toolCallId);
  if (!assistantMessageId) return null;
  return { assistantMessageId, ...(toolCallId ? { toolCallId } : {}) };
}

/** Most-specific first. A record carrying both ids must match the exact pair;
 * it never falls back to a nearby message or tool. */
export function conversationSourceKeys(
  assistantMessageId: string | undefined,
  toolCallId?: string,
): string[] {
  const message = sourceId(assistantMessageId);
  const tool = sourceId(toolCallId);
  return [
    ...(message && tool ? [`source:${message}:${tool}`] : []),
    ...(message ? [`message:${message}`] : []),
    ...(tool ? [`tool:${tool}`] : []),
  ];
}

export function conversationSourceIndex(
  index: Record<string, number>,
  source: ConversationSource,
): number | undefined {
  const key = source.toolCallId
    ? conversationSourceKeys(source.assistantMessageId, source.toolCallId)[0]
    : conversationSourceKeys(source.assistantMessageId)[0];
  return key ? index[key] : undefined;
}

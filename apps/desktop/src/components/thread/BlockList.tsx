import type { ArtifactBlock, FigureAnnotation, ThreadBlock } from "@ai4s/shared";
import { AgentMessage, DataTable, RunningJobsOverlay, StatusLine, UserMessage } from "./atoms";
import { ToolCallRow } from "./ToolCallRow";
import { ToolGroup, groupToolBlocks } from "./ToolGroup";
import { ReviewerCard } from "./ReviewerCard";
import { ReasoningRow } from "./ReasoningRow";
import { StepSummaryRow } from "./StepSummaryRow";
import { FigureBlock } from "./FigureBlock";
import { ArtifactCard } from "./ArtifactCard";

export interface BlockHandlers {
  /** Replace a past user message and continue from the restored workspace. */
  onMessageEdit?: (messageID: string, text: string) => void;
  /** Return to a past user message and put its text back in the composer. */
  onMessageRevert?: (messageID: string, text: string) => void;
  /** Open an artifact in the inspector (live session). */
  onArtifactOpen?: (a: ArtifactBlock) => void;
  /** Forward a figure annotation to the agent (live session). */
  onFigureComment?: (annotation: FigureAnnotation, figureTitle: string) => void;
  /** Live one-line activity of the subagent a task tool spawned (live session). */
  subagentActivity?: (childSessionId: string) => string | undefined;
}

export function renderBlock(
  block: ThreadBlock,
  i: number,
  handlers?: BlockHandlers,
  liveReasoningIndex?: number,
) {
  switch (block.kind) {
    case "user":
      return (
        <UserMessage
          key={i}
          block={block}
          onEdit={handlers?.onMessageEdit}
          onRevert={handlers?.onMessageRevert}
        />
      );
    case "agent":
      return <AgentMessage key={i} markdown={block.markdown} onOpenArtifact={handlers?.onArtifactOpen} />;
    case "reasoning":
      return <ReasoningRow key={i} block={block} streaming={i === liveReasoningIndex} />;
    case "step-summary":
      return <StepSummaryRow key={i} block={block} />;
    case "tool-call":
      return (
        <ToolCallRow
          key={i}
          block={block}
          activity={
            block.childSessionId ? handlers?.subagentActivity?.(block.childSessionId) : undefined
          }
        />
      );
    case "reviewer":
      return <ReviewerCard key={i} block={block} />;
    case "table":
      return <DataTable key={i} block={block} />;
    case "figure":
      return <FigureBlock key={i} block={block} onComment={handlers?.onFigureComment} />;
    case "artifact":
      return <ArtifactCard key={i} block={block} onOpen={handlers?.onArtifactOpen} />;
    case "running-jobs":
      return <RunningJobsOverlay key={i} block={block} />;
    case "status-line":
      return <StatusLine key={i} block={block} />;
  }
}

export function BlockList({
  blocks,
  handlers,
  liveReasoningIndex,
}: {
  blocks: ThreadBlock[];
  handlers?: BlockHandlers;
  liveReasoningIndex?: number;
}) {
  // Runs of quiet tool steps render as one collapsible group (Codex-style);
  // everything else — text, artifacts, prominent tool cards — on its own.
  return (
    <>
      {groupToolBlocks(blocks).map((item) =>
        item.kind === "group" ? (
          <ToolGroup
            key={`group:${item.start}`}
            blocks={item.blocks}
            start={item.start}
            liveReasoningIndex={liveReasoningIndex}
            activityFor={handlers?.subagentActivity}
          />
        ) : (
          renderBlock(item.block, item.index, handlers, liveReasoningIndex)
        ),
      )}
    </>
  );
}

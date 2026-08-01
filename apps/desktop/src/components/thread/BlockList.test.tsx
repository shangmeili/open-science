import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { BlockList } from "./BlockList";
import { useRuntimeStore } from "@/lib/runtime";

// A running task row surfaces its subagent's latest step. The activity is no
// longer threaded through props — the row self-subscribes to the child thread in
// the store (SubagentActivity), so these tests seed that thread directly (#34).
describe("BlockList", () => {
  afterEach(() => {
    act(() => useRuntimeStore.setState({ threads: {} }));
  });

  it("shows a running task row the live activity of its subagent", () => {
    useRuntimeStore.setState({
      threads: {
        ses_child: {
          blocks: [{ kind: "tool-call", title: "python3 analyze slide-03.jpg", status: "running" }],
          index: {},
          loaded: true,
        },
      },
    });
    render(
      <BlockList
        blocks={[
          { kind: "tool-call", title: "Visual QA for slides", status: "running", childSessionId: "ses_child" },
        ]}
      />,
    );
    expect(screen.getByText("python3 analyze slide-03.jpg")).toBeInTheDocument();
  });

  it("renders a row that spawned no subagent without any activity line", () => {
    render(<BlockList blocks={[{ kind: "tool-call", title: "ls -la", status: "running" }]} />);
    expect(screen.getByText("ls -la")).toBeInTheDocument();
    expect(document.querySelector("[data-subagent-activity]")).toBeNull();
  });

  it("opens a folded tool group and marks only the exact requested source row", () => {
    render(
      <BlockList
        blocks={[
          { kind: "tool-call", title: "python prepare.py", status: "success", verb: "Ran" },
          { kind: "tool-call", title: "python cea.py", status: "success", verb: "Ran" },
        ]}
        targetIndex={1}
      />,
    );

    const target = document.querySelector('[data-conversation-source-target="true"]');
    expect(target).not.toBeNull();
    expect(target).toHaveTextContent("python cea.py");
    expect(target).not.toHaveTextContent("python prepare.py");
  });
});

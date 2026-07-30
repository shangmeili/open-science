import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PermissionAskedEvent, QuestionAskedEvent } from "@ai4s/sdk";
import { InteractionPrompt } from "./InteractionPrompt";

const singleQ: QuestionAskedEvent = {
  type: "question.asked",
  sessionId: "ses_1",
  requestId: "que_1",
  questions: [
    {
      question: "Which data file should I analyze?",
      header: "Select file",
      options: [
        { label: "atlas.csv", description: "3 rows: species" },
        { label: "export.csv", description: "306 rows" },
      ],
    },
  ],
};

const multiQ: QuestionAskedEvent = {
  ...singleQ,
  requestId: "que_2",
  questions: [{ ...singleQ.questions[0], multiple: true }],
};

const noop = () => {};

describe("InteractionPrompt — question", () => {
  it("keeps a free-answer path and submits a single selection explicitly", async () => {
    const onAnswer = vi.fn();
    render(<InteractionPrompt question={singleQ} onAnswer={onAnswer} onReject={noop} onPermission={noop} />);
    await userEvent.click(screen.getByText("atlas.csv"));
    expect(onAnswer).not.toHaveBeenCalled();
    expect(screen.getByText("None of these fit? Type your answer directly.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Which data file should I analyze?" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(onAnswer).toHaveBeenCalledWith("que_1", [["atlas.csv"]]);
  });

  it("accepts a direct answer when none of the suggested options fits", async () => {
    const onAnswer = vi.fn();
    render(<InteractionPrompt question={singleQ} onAnswer={onAnswer} onReject={noop} onPermission={noop} />);
    const input = screen.getByRole("textbox", { name: "Which data file should I analyze?" });
    await userEvent.type(input, "Use the cohort file attached to this task.");
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(onAnswer).toHaveBeenCalledWith("que_1", [["Use the cohort file attached to this task."]]);
  });

  it("uses a direct answer instead of a previously selected suggestion", async () => {
    const onAnswer = vi.fn();
    render(<InteractionPrompt question={singleQ} onAnswer={onAnswer} onReject={noop} onPermission={noop} />);
    await userEvent.click(screen.getByText("atlas.csv"));
    await userEvent.type(
      screen.getByRole("textbox", { name: "Which data file should I analyze?" }),
      "Use the task attachment.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(onAnswer).toHaveBeenCalledWith("que_1", [["Use the task attachment."]]);
  });

  it("collects multiple selections behind a Submit for a multi-select question", async () => {
    const onAnswer = vi.fn();
    render(<InteractionPrompt question={multiQ} onAnswer={onAnswer} onReject={noop} onPermission={noop} />);
    // No immediate answer on click.
    await userEvent.click(screen.getByText("atlas.csv"));
    await userEvent.click(screen.getByText("export.csv"));
    expect(onAnswer).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(onAnswer).toHaveBeenCalledWith("que_2", [["atlas.csv", "export.csv"]]);
  });

  it("skips a question via reject", async () => {
    const onReject = vi.fn();
    render(<InteractionPrompt question={singleQ} onAnswer={noop} onReject={onReject} onPermission={noop} />);
    await userEvent.click(screen.getByText("Skip"));
    expect(onReject).toHaveBeenCalledWith("que_1");
  });

  it("hides a corrupted model-generated option description without changing its label", () => {
    const corrupted: QuestionAskedEvent = {
      ...singleQ,
      requestId: "que_corrupted",
      questions: [{
        ...singleQ.questions[0],
        options: [{
          label: "Natural-history comparator",
          description: "\\ ".repeat(40),
        }],
      }],
    };

    render(<InteractionPrompt question={corrupted} onAnswer={noop} onReject={noop} onPermission={noop} />);

    expect(screen.getByText("Natural-history comparator")).toBeInTheDocument();
    expect(screen.queryByText(corrupted.questions[0].options[0].description!)).not.toBeInTheDocument();
    expect(screen.getByText("The model returned an invalid option description, so it was hidden.")).toBeInTheDocument();
  });

  it("does not render an option description that refers to a missing table", () => {
    const missingContext: QuestionAskedEvent = {
      ...singleQ,
      requestId: "que_missing_context",
      questions: [{
        question: "9 个健康状态与低血糖事件层这个划分可不可以？",
        header: "健康状态",
        options: [{
          label: "状态划分接受",
          description: "按上面表格中的9个状态进行计算。",
        }],
      }],
    };

    render(<InteractionPrompt question={missingContext} onAnswer={noop} onReject={noop} onPermission={noop} />);

    expect(screen.queryByText("按上面表格中的9个状态进行计算。")).not.toBeInTheDocument();
    expect(screen.getByText(/refers to content that is not shown/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "9 个健康状态与低血糖事件层这个划分可不可以？" })).toBeInTheDocument();
  });

  it("does not present model-generated medicine indications as answer options", async () => {
    const onAnswer = vi.fn();
    const unsafe: QuestionAskedEvent = {
      ...singleQ,
      requestId: "que_medicine_fact",
      questions: [{
        question: "本次索欣赞药物经济学分析针对哪个适应症？",
        header: "目标适应症",
        options: [
          { label: "III期 NSCLC 巩固治疗", description: "模型生成的未核验药品事实" },
          { label: "复发难治性 NK/T 细胞淋巴瘤", description: "模型生成的未核验药品事实" },
        ],
      }],
    };

    render(<InteractionPrompt question={unsafe} onAnswer={onAnswer} onReject={noop} onPermission={noop} />);

    expect(screen.queryByText("III期 NSCLC 巩固治疗")).not.toBeInTheDocument();
    expect(screen.queryByText("复发难治性 NK/T 细胞淋巴瘤")).not.toBeInTheDocument();
    expect(screen.getByText(/public literature or data/i)).toBeInTheDocument();
    const input = screen.getByRole("textbox", {
      name: "本次索欣赞药物经济学分析针对哪个适应症？",
    });
    expect(input).toHaveAccessibleDescription(
      /public literature or data/i,
    );
    await userEvent.type(input, "Use the NMPA-approved label for the verified active ingredient.");
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(onAnswer).toHaveBeenCalledWith("que_medicine_fact", [[
      "Use the NMPA-approved label for the verified active ingredient.",
    ]]);
  });

  it("presents medicine candidates as a form only when every option carries a public source and retrieval date", async () => {
    const onAnswer = vi.fn();
    const sourced: QuestionAskedEvent = {
      ...singleQ,
      requestId: "que_sourced_medicine_fact",
      questions: [{
        question: "请选择本研究拟评价的目标适应证。",
        header: "目标适应证",
        options: [
          {
            label: "成人 2 型糖尿病",
            description: "来源：国家药监局药品说明书 https://example.gov.cn/label；检索日期：2026-07-28。",
          },
          {
            label: "成人肥胖症的长期体重管理",
            description: "来源：监管机构公开说明书 https://example.gov.cn/weight-label；检索日期：2026-07-28。",
          },
        ],
      }],
    };

    render(<InteractionPrompt question={sourced} onAnswer={onAnswer} onReject={noop} onPermission={noop} />);

    expect(screen.getByText("成人 2 型糖尿病")).toBeInTheDocument();
    expect(screen.getByText("成人肥胖症的长期体重管理")).toBeInTheDocument();
    expect(screen.queryByText(/模型生成的选项不是证据/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("成人 2 型糖尿病"));
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(onAnswer).toHaveBeenCalledWith("que_sourced_medicine_fact", [["成人 2 型糖尿病"]]);
  });

  it("keeps the form blocked when even one public-fact candidate lacks traceable retrieval evidence", () => {
    const partlySourced: QuestionAskedEvent = {
      ...singleQ,
      requestId: "que_partly_sourced_medicine_fact",
      questions: [{
        question: "请选择本研究拟评价的目标适应证。",
        header: "目标适应证",
        options: [
          {
            label: "成人 2 型糖尿病",
            description: "来源：国家药监局药品说明书 https://example.gov.cn/label；检索日期：2026-07-28。",
          },
          {
            label: "另一适应证",
            description: "尚未附公开来源。",
          },
        ],
      }],
    };

    render(<InteractionPrompt question={partlySourced} onAnswer={noop} onReject={noop} onPermission={noop} />);

    expect(screen.queryByText("成人 2 型糖尿病")).not.toBeInTheDocument();
    expect(screen.queryByText("另一适应证")).not.toBeInTheDocument();
    expect(screen.getByText(/public literature or data/i)).toBeInTheDocument();
  });

  it("does not present model-invented price sources or citation identifiers as choices", () => {
    const unsafe: QuestionAskedEvent = {
      ...singleQ,
      requestId: "que_public_price",
      questions: [{
        question: "价格补齐后，下一步怎么走？",
        header: "价格证据",
        options: [
          { label: "你提供价格表", description: "挂网价或采购价" },
          { label: "使用文献占位", description: "PMID 41705603" },
        ],
      }],
    };

    render(<InteractionPrompt question={unsafe} onAnswer={noop} onReject={noop} onPermission={noop} />);

    expect(screen.queryByText("你提供价格表")).not.toBeInTheDocument();
    expect(screen.queryByText("使用文献占位")).not.toBeInTheDocument();
    expect(screen.getByText(/public literature or data/i)).toBeInTheDocument();
  });
});

describe("InteractionPrompt — permission", () => {
  const perm: PermissionAskedEvent = {
    type: "permission.asked",
    sessionId: "ses_1",
    requestId: "per_1",
    action: "bash",
    resources: ["rm -rf build/"],
  };

  it("shows the action and resources and replies once / always / reject", async () => {
    const onPermission = vi.fn();
    render(<InteractionPrompt permission={perm} onAnswer={noop} onReject={noop} onPermission={onPermission} />);
    expect(screen.getByText("rm -rf build/")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Allow once" }));
    expect(onPermission).toHaveBeenCalledWith("per_1", "once");
    await userEvent.click(screen.getByRole("button", { name: "Always allow" }));
    expect(onPermission).toHaveBeenCalledWith("per_1", "always");
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(onPermission).toHaveBeenCalledWith("per_1", "reject");
  });
});

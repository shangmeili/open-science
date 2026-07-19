import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";

vi.mock("@/lib/tauri", () => ({ isTauri: true }));

import { EvidenceLibraryAssessment } from "./HeorReviewPane";

afterEach(async () => {
  await act(async () => i18n.changeLanguage("en"));
});

describe("AI4HEOR bundled learning library", () => {
  it("offers a direct Chinese installation action without replacing the conversation", async () => {
    await act(async () => i18n.changeLanguage("zh-Hans"));
    const onInstallBundled = vi.fn();
    render(
      <EvidenceLibraryAssessment
        state={{ kind: "invalid", message: "尚未建立索引" }}
        syncing={false}
        onInstallBundled={onInstallBundled}
        onAddFiles={vi.fn()}
        onAddFolder={vi.fn()}
        onSync={vi.fn()}
        onAsk={vi.fn()}
      />,
    );

    expect(screen.getByText("本地证据库为空、已过期或被阻断")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "安装内置药物经济学学习库" }));
    expect(onInstallBundled).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "添加知识库文件夹" })).toBeInTheDocument();
    expect(screen.getByText(/应用不调用模型、不联网/)).toBeInTheDocument();
  });
});

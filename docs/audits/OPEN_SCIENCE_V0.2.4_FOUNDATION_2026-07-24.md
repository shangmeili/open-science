# Open Science v0.2.4 科研底座与 AI4HEOR 运行时核对

**核对日期：** 2026-07-24
**上游基线：** `ai4s-research/open-science` `v0.2.4-12-gfa0b6ba` (`fa0b6ba7aaadb05de59c5c3efe43e4734bb48bda`)
**通用 Skill 来源：** `ai4s-research/ai4s-skills` 固定提交 `8fa2ab0523082c135598909b227ed8feb48263ad`
**产品原则：** Open Science 完整科研底座 + HEOR 工作流、专业 Skill、证据溯源、确定性计算和复核能力 = AI4HEOR。

## 结论

此前只打包第一方 HEOR Skill、未把 7 个 Open Science 通用科研 Skill 和 7 个科研连接器带入可交付运行时，是**严重失误**和 **release blocker**。当前源码已经恢复这些能力，并以 CI 合约阻止再次退化；HEOR 层只能增加专业约束，不能替换通用科研底座。

## 逐项验收

| 核对项 | 当前 AI4HEOR 状态 | 可验证证据 | 发布条件 |
| --- | --- | --- | --- |
| 53 个第一方 HEOR Skill | 已打包 | `runtime/skills/core/`；核心 Skill 测试 | 必须恰好 53 个 |
| 7 个 Open Science 通用 Skill | 已恢复并打包 | `runtime/skills/external/ai4s-skills/`、准入登记表、Tauri `skills-admitted-ai4s/` 资源映射 | 必须全部存在、固定提交、无符号链接、逐目录 MIT 许可证和精确树哈希一致 |
| 多语言 Skill 描述 | 已覆盖 | 7 个 `skills.json`；共 60 个 Skill 的本地化一致性测试 | 7 种已发布界面语言不得缺项 |
| Anthropic 文档 Skill | 不打包 | 实际 `LICENSE.txt` 不允许作为可再分发产品资产；第一方 DOCX/PDF/PPTX/XLSX 实现替代 | 不得被误写为 Apache-2.0 或进入发布资源 |
| 7 个科研连接器 | 已恢复为按需安装 | `scienceConnectors.ts`、设置页、应用独立 `science-mcp-env`、Rust 包名注入防护测试 | 目录不得缺项；不能取得 HEOR 证据纳入、方法选择或批准权 |
| 自管 MCP | 保留 | Settings 的本地/远程 MCP 表单及现有 OpenCode 配置 | 明示为研究者管理的外部能力 |
| `packages/shared` 共享领域类型 | 已存在且被实际引用 | Desktop 与 SDK 的 `@ai4s/shared` 依赖；`RuntimeStatus`、`Project`、`Session`、`ThreadBlock` 等导出 | 不能只保留目录而断开消费链 |
| 共享图表色板 | 已存在并一致 | `CHART_PALETTE_LIGHT/DARK`；CSS `--series-1..8`；出版图形 mplstyle | 三处色值漂移时阻断发布 |
| 通用运行链 | 保留 | OpenCode sidecar、项目/任务、文件、Notebook、运行记录、预览、溯源和 MCP | HEOR 导航和工作流不得删掉底层运行能力 |

## 上游 v0.2.4 改进处理

| 上游改进 | 处理 | 理由 |
| --- | --- | --- |
| 长回复流式 Markdown 节流 | 已移植 | 降低长对话中 React Markdown 与 KaTeX 的重复解析，直接改善真实研究任务响应性 |
| `\(...\)` / `\[...\]` LaTeX 分隔符 | 已移植 | 科学与药物经济学公式不再显示原始转义文本；保留代码块和行间距语义 |
| 拖放文件重复复制修复 | 已移植 | 解决流式更新期间重复注册原生监听器以及工作区文件再次复制的问题 |
| 自定义模型接口自动探测 | 待单独移植 | 有价值，但涉及 Rust 网络探测、7 语言设置表单和凭据/网络边界；不能在未经完整交互与安全测试时整块合并 |
| 新内联模型与推理强度选择器 | 待单独移植 | AI4HEOR 已有模型选择路径；上游改动超过 500 行并改变主要输入交互，需按现有设计系统单独验收 |
| 移动端远程访问细节 | 保留现有实现，待差异测试 | AI4HEOR 已有 gateway/web mode；不得用上游页面覆盖 HEOR 项目、任务和复核交互 |

## 脚本型 Skill 的运行边界

通用 Skill 的指令、模板和脚本已经进入安装资源。需要 Python 包或浏览器运行时的脚本仍采用按需、隔离安装，不修改系统 Python。本次核对在临时 `uv` 环境中完成：

- `integrity-auditor`：依照其 `requirements.txt` 安装依赖后，自带 smoke test 22/22 通过。
- `mindmap-render`：在临时 Playwright/Pillow 环境中，自带 15 项单元测试通过；真正导出 PNG/PDF 还需要浏览器运行时，不能仅凭单元测试宣称端到端渲染已验收。

因此“已打包”与“所有可选依赖已预装”严格区分。发布包保留通用 Skill，不把几十 MB 的可选依赖静默装进用户系统；用户实际选择相应能力时，应用应使用自己的隔离环境进行设置。

## 自动化门禁

`.github/workflows/build.yml` 在打包前必须依次获取固定 Skill 包并执行 `scripts/dev/test_open_science_foundation.py`。该测试同时核对 53 + 7 Skill 数量、许可证、精确哈希、Tauri 资源映射、7 个连接器、共享类型消费链和图表色板一致性。任何一项失败，安装包不得生成。

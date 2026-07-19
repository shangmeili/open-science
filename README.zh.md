<div align="center">

[![AI4HEOR — 本地优先的药物经济学与 HEOR 工作台](./docs/assets/banner.webp)](https://github.com/ai4s-research/open-science)

# AI4HEOR

**本地优先、模型无关的 macOS、Windows & Linux 药物经济学与 HEOR 工作台。**

AI4HEOR 基于开源项目 Open Science Desktop 开发，使用 Tauri、MCP、
Skills 和可复现工件。自然语言是主交互，表单只辅助检查与人工复核。
人类研究者主导科学工作；配置的模型/运行时协助整理证据、执行、检查与解释。

<p>
  <a href="./README.md">English</a> ·
  <b>简体中文</b> ·
  <a href="./README.ja.md">日本語</a> ·
  <a href="./README.es.md">Español</a> ·
  <a href="./README.de.md">Deutsch</a> ·
  <a href="./README.fr.md">Français</a> ·
  <a href="./README.ko.md">한국어</a>
</p>

<p>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://internscience.github.io/ResearchClawBench-Home/"><img src="https://img.shields.io/badge/%F0%9F%8F%86%20%231-ResearchClawBench-FFB300" alt="#1 on ResearchClawBench"></a>
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-blue" alt="Platforms">
  <img src="https://img.shields.io/badge/i18n-7%20languages-5B8DEF" alt="7 interface languages">
  <img src="https://img.shields.io/badge/built%20with-Tauri%202%20%2B%20React-24C8DB" alt="Built with Tauri + React">
  <img src="https://img.shields.io/badge/runtime-OpenCode-success" alt="OpenCode runtime">
  <a href="https://discord.gg/fWNMDKcd5P"><img src="https://img.shields.io/badge/Join-Discord-5865F2" alt="Join Discord"></a>
  <a href="http://makeapullrequest.com"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome"></a>
  <a href="https://linux.do"><img src="https://img.shields.io/badge/Join-linux.do-orange" alt="linux.do"></a>
</p>

</div>

---

🎉 **平台源流：** 上游 Open Science Desktop 在 [ResearchClawBench](https://internscience.github.io/ResearchClawBench-Home/)
的已评分任务平均分排名第 1（Pass@1，2026 年 7 月 9 日）。这一上游
Agent 基准不能证明 AI4HEOR 内的科学工作应由 Agent 主导，也不能证明产出有效。

---

## 目录

- [✨ 它能做什么](#它能做什么)
- [🎬 效果演示](#效果演示)
- [🧪 当前能力](#当前能力)
- [🔌 技能与连接器](#技能与连接器)
- [📦 安装](#安装)
- [🚀 从源码构建](#从源码构建)
- [🔒 安全与隐私](#安全与隐私)
- [🗂️ 仓库结构](#仓库结构)
- [📌 状态](#状态)
- [🤝 参与贡献](#参与贡献)
- [📖 引用](#引用)
- [⚖️ 许可证](#许可证)

## 它能做什么

**支持人类主导的 HEOR 工作流**——从研究者界定的问题出发，形成可复核的
证据、确定性分析、验证与报告工件，全程保持可审计。

- **自然语言优先的辅助**：研究者发起并控制工作；模型/运行时在有界限的步骤中
  提出建议或执行，留下真实可检查的工件，但不取得科学判断权。
- **本地 HEOR 知识库**：研究者可以明确安装注明日期的内置中文药物经济学学习库，
  也可以添加自己的文件夹。资料保留原有层级，在本地绑定哈希并建立索引；用于学习时不会自动联网。
- **一切都可回溯**：图、表、报告、笔记本和运行输出都连回生成它们的确切代码、输入、环境、模型输出和对话。
- **本地优先，数据归你**：会话、数据、溯源、笔记本和运行记录都在本机的本地文件夹里，默认不外流。
- **模型无关运行时**：UI 通过 `packages/sdk` 调用内置固定版本的 OpenCode sidecar；模型提供方、技能和 MCP 服务器保持可插拔。
- **天然可复现**：本地、SSH/Slurm、Modal 和 notebook-batch 运行都记录为可复现的运行记录，而不是散落的终端输出。
- **可扩展**：智能体技能、MCP 服务器与一键科学连接器、`/` 命令、`!` shell 模式，以及模型无关的 SDK。

## 效果演示

**由人主导的 HEOR 请求 -> 可复核、可追溯的本地工作。**
新会话只提供药物经济学研究设计、HEOR 证据/数据分析、模型/报告
审计和合成成本效果分析示例。`examples/heor-cost-effectiveness/`
中的双策略、三状态队列案例只有在研究者点击后才安装，请求会先留在输入框中。
不依赖第三方包的 `run_analysis.py` 会绑定脚本、分析设定和 CSV 的准确哈希，
复算 `expected/base-case-result.json`，并运行预先声明的低值、高值成本敏感性分析。
研究者另行确认后，桌面应用可以在没有设置模型的情况下运行这套固定计算，写出三个
本地结果文件并保留运行和溯源记录；案例内容不会发送给模型服务。
其中的数值只是教学假设，不是临床或经济学证据，也不能生成批准、
具有成本效果、报销或政策结论。

![AI4HEOR 首次使用界面明确本地、模型、授权与 Human 科学权责边界](./docs/audits/2026-07-17-first-use/06-skip-link-stable.png)

![AI4HEOR 的 HEOR 专属自然语言任务入口](./docs/audits/2026-07-17-first-use/07-heor-workspace-final.png)

![模型执行前可编辑的成本效果分析自然语言请求](./docs/audits/2026-07-17-first-use/08-natural-language-draft-final.png)

## 当前能力

**把科研辅助收敛为有边界的 HEOR Skills。** AI4HEOR 的 50 个第一方 Skill
只路由研究者界定的任务，不取得批准权或方法选择权。代表性已准入工作流包括：

| 技能 | 职责 | 主要产出 |
| --- | --- | --- |
| `$heor-workbench` | 协调由研究者主导的 HEOR 工作，不取得科学决策权 | 可复核的本地计划、工件和停止点 |
| `$heor-local-evidence` | 盘点研究者明确选择的本地知识库，不自动联网 | 哈希绑定的本地证据目录 |
| `$heor-evidence-search` | 起草需 Human 联网授权的 PubMed/ClinicalTrials.gov 检索 | 精确请求哈希和导入的元数据候选 |
| `$literature-review` | 导入、去重、校验和导出项目内的参考文献数据 | 带来源记录的文献库以及 RIS、BibTeX 或 CSL-JSON 交换文件 |
| `$heor-model-design` | 结构化人类界定的决策问题与概念模型 | 决策问题和概念模型工件 |
| `$heor-cohort-state-transition` / `$heor-partitioned-survival` | 执行有边界的确定性经济学模型 | 可复现的成本、QALY、增量结果和检查 |
| `$heor-uncertainty-analysis` / `$heor-advanced-value-of-information` | 执行已声明的不确定性与有界 VOI 工作流 | DSA/PSA/CEAC/CEAF/EVPI 与单独复核的高级 VOI |
| `$heor-budget-impact` / `$heor-dynamic-budget-impact` | 执行静态或动态预算影响分析 | 分项预算结果和审计工件 |
| `$heor-model-validation` / `$heor-reporting` / `$heor-reproducibility-package` | 验证、报告并封装当前精确工件 | 独立复核包、有来源绑定的 DOCX/PDF/XLSX 报告和重放包 |
| `$research-presentation` | 准备有来源绑定的研究汇报内容并在本地生成 | 可逐页核对的无宏 PPTX 和生成审计记录 |

全部第一方 Skill 的名称与说明均随七种界面语言发布，同时保留精确
`$skill-id`；尚未完成的改写和已排除的外部来源只作为内部工程记录，不再
作为用户选项。

### 平台

| 范围 | 当前状态 |
| --- | --- |
| 桌面外壳 | Tauri 2 + React + TypeScript + Vite，主打 macOS 和 Windows 桌面构建，同时提供 Linux 包。 |
| 运行时 | 内置 OpenCode sidecar，由应用自动启动，并与用户自己的 OpenCode 配置/数据隔离。 |
| 会话 | 多会话聊天与历史、按时间创建的工作区文件夹、跨工作区全局历史、`/` 命令和 `!` shell 模式。 |
| 文件 | 全局和会话内文件浏览、右键菜单、系统打开/定位、复制路径、本地预览服务。 |
| 笔记本 | 真实 `.ipynb` 文件、Python/R 笔记本创建、本地内核运行、内置 `uv` 管理 Jupyter 环境，以及打开 JupyterLab。 |
| 运行记录 | 追加式 run log、全局 SQLite 索引、搜索/筛选/分页、本地与远程 surface、输出链接、日志和复现提示。 |
| 溯源 | `.openscience/provenance.jsonl` 记录文件版本，并把产物连回创建它的运行或编辑。 |
| 审查 | 内置 traceability、stats-integrity、domain-check、large-file、publication-figure、remote-compute、Modal run 等第一方技能。 |
| 查看器 | PDF、图片、视频、HTML、Markdown、代码、CSV/TSV 表格与图表、DOCX、XLSX、PPTX、分子、3D mesh、基因组轨道、FITS、DOS/DOSCAR、EIGENVAL bands、qcode、异常图和 phase 文件。 |
| 模型 | OpenCode 提供方目录、OAuth/API key 连接、自定义 OpenAI-compatible endpoint，以及 OpenCode 支持的本地/云模型选项。 |
| 界面语言 | English、简体中文、日本語、Español、Deutsch、Français、한국어。第一方 Skill 名称与说明在 7 种语言中发布，同时保留精确 `$skill-id`。Portuguese (Brazil) 和 Arabic 已注册，但还不可选。 |

## 技能与连接器

默认只打包 `runtime/skills/core/` 中的第一方技能，包括 AI4HEOR 的证据、
模型设计、参考案例、不确定性、预算影响、验证和报告工作流。第三方 Skill
与 MCP 由仅面向发布的包内登记表控制：登记表只包含授权兼容、完成审查、
通过跨平台检查、锁定精确哈希并实际随包发布的 `validated-adapter`，不保留
未完成或已排除的来源。当前登记表为空，因此没有第三方工具随 AI4HEOR 打包。

此前外部审查中有价值的能力意图改写为有边界的 AI4HEOR 第一方能力。许可证
不兼容的文档来源已从运行时和候选界面永久移除。PPTX 已由
`research-presentation` 替代，DOCX/PDF/XLSX 报告导出已由第一方
`heor-reporting` 原生渲染器替代；XLSX 复制已审计结果，不在工作簿中重算模型。
概念模型图也已由第一方实现：状态和转移来自当前
`heor/conceptual-model.json`，应用内只调整节点位置，并导出来源绑定的 SVG 和
可编辑 GraphML；导出不会改变模型语义，也不会形成研究者批准。
只读处置记录见
[`docs/THIRD_PARTY_ADMISSION_REVIEW.zh-CN.md`](./docs/THIRD_PARTY_ADMISSION_REVIEW.zh-CN.md)。
科研基础能力的已交付、部分交付与待建设边界见
[`docs/RESEARCH_FOUNDATION_CAPABILITIES.zh-CN.md`](./docs/RESEARCH_FOUNDATION_CAPABILITIES.zh-CN.md)。

默认界面不启动未经审查的第三方一键 MCP。第一方 `$heor-evidence-search`
只在 Human 明确授权后访问固定的 PubMed 与 ClinicalTrials.gov 元数据端点；
Jupyter 是唯一的一键托管本地计算工具。研究者仍可在 Settings 添加本地或远程
MCP，但它们会明确标为不受托管的外部能力，不获得科学判断或批准权。参见
[`docs/CONNECT_YOUR_TOOLS.md`](./docs/CONNECT_YOUR_TOOLS.md)。

中立定位对比见
[`Open Science Desktop vs OpenScience`](./docs/open-science-desktop-vs-openscience.md)。

## 安装

从 [Releases 页面](https://github.com/ai4s-research/open-science/releases/latest) 下载最新安装包。

- **macOS**：`.dmg` / `.app`，Apple Silicon 和 Intel，要求 macOS 13 Ventura 或更高。
- **Windows**：NSIS `.exe` 和 `.msi`，Windows 10/11 x64。
- **Linux**：x86_64 Linux 的 `.deb` 和 `.rpm`。

从 0.1.27 起，全新安装默认使用 `~/Documents/AI4HEOR`。如果新目录尚不存在，
AI4HEOR 会将旧默认目录 `~/Documents/OpenScience` 原子重命名并保留全部内容；
如果两个目录都已存在，则不自动合并或删除其中任何一个。在 Settings 中明确选择的
基础目录始终优先。

当前验证的 0.1.41 本地 x64 macOS 构建尚未代码签名或 notarize。

**macOS**：如果 Gatekeeper 提示应用已损坏或来自未知开发者，把应用安装到 Applications 后运行：

```bash
xattr -cr "/Applications/AI4HEOR.app"
```

**Windows**：如果出现 SmartScreen，选择 **更多信息 -> 仍要运行**。

**Linux**：

```bash
sudo apt install ./AI4HEOR_*.deb
# 或
sudo rpm -i AI4HEOR-*.rpm
```

## 从源码构建

前置依赖：

- Node.js >= 20
- pnpm 9
- Rust 工具链
- Tauri 在当前系统需要的 macOS、Windows 或 Linux 依赖

```bash
git clone https://github.com/ai4s-research/open-science
cd open-science
pnpm install

bash scripts/dev/fetch-opencode.sh
bash scripts/dev/fetch-uv.sh

pnpm --filter @ai4s/desktop tauri dev
pnpm --filter @ai4s/desktop tauri build
```

常用检查：

```bash
pnpm test
pnpm typecheck
pnpm lint
```

## 安全与隐私

- 工作区文件、原始数据、会话历史、溯源、笔记本和运行记录默认保留在本机。
- 命令执行、删除文件、安装依赖和远程连接在桌面应用中走人工批准流程。
- 提供方凭据写入应用私有运行时配置，不进入工作区、溯源、git、导出或用户全局 OpenCode 配置。
- Settings 中有大白话数据流说明，说明哪些内容可能发给所选模型提供方。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `apps/desktop/` | Tauri + React 桌面应用。 |
| `packages/sdk/` | `OpenCodeClient`，避免 UI 直接调用 OpenCode。 |
| `packages/shared/` | 共享领域类型和图表色板。 |
| `packages/ui/` | 共享 UI 包。 |
| `runtime/skills/core/` | 第一方科学技能。 |
| `runtime/skills/external/` | 外部候选的可选审查缓存；默认不打包。 |
| `runtime/harness/` | 新项目会加载的产品级“研究者主导、模型辅助”运行契约。 |
| `runtime/mcp/` | MCP 运行时说明和配置。 |
| `examples/` | 内置示例工作区。 |
| `scripts/dev/` | sidecar、`uv`、技能拉取器和聚焦回归探针。 |
| `docs/` | 产品、技术、operator、连接器和研究笔记。 |

## 状态

项目是正在积极开发的桌面 MVP。最可靠的当前实现日志是 [`PROGRESS.md`](./PROGRESS.md)。
产品和架构说明位于 [`docs/PRD.md`](./docs/PRD.md) 和
[`docs/TECHNICAL_DESIGN.md`](./docs/TECHNICAL_DESIGN.md)，但这些文档同时包含目标设计和历史状态说明。

当前开发刻意收敛为先在 Intel macOS 上跑通产品；Windows、Linux、Apple Silicon
与跨平台发布暂停，直到 macOS 路径通过验收。当前源码为 `0.1.47`；已完成隔离首次启动核验的 x64 macOS 交接包仍为
`0.1.41`。当前候选包 `AI4HEOR_0.1.46_x64.dmg` 从 `e44339f` 构建，大小为
89,903,352 字节，SHA-256 是
`1e17461b0482004fc6f929f8a519e744cb34ac96d5e4e987e7006bb11577184a`。
独立只读核验已确认 x86-64 架构、0.1.46 身份、OpenCode 1.17.13、uv 0.11.26、
347 个受控资源和包内 177 项 HEOR 测试，并取代 0.1.45 成为当前候选包。由于已安装应用仍在运行，该精确候选包的
隔离首次启动尚未核验，因此暂不取代已完成验收交接的 0.1.41 包。0.1.46 新增第一方概念模型版式编辑和 SVG/GraphML 导出，状态与转移仍以当前 JSON 为准。0.1.45 在同一条第一方、有来源绑定的报告链中新增确定性、无宏无公式的 XLSX 工作簿。五张中英双语工作表从已审计报告包复制带类型的数值、报告表格、报告规范覆盖情况、披露、局限性、来源路径和 SHA-256 绑定；工作簿不会重新计算经济学模型，仍需研究者复核。0.1.44 在第一方 `heor-reporting` 中新增有来源绑定的 DOCX/PDF 生成：原生应用重新核验当前报告包与报告，两个格式都嵌入已准入的中文字体，记录输出哈希，并保持待研究者复核。发布清单不保留隔离或拒绝选项；完成改写的能力直接作为第一方实现交付，未完成和授权不兼容的第三方来源不进入产品列表。0.1.43 新增第一方、仅本地运行的 `literature-review` Skill：它可导入、去重、校验和确定性导出带来源记录的 RIS、受控 BibTeX 和 CSL-JSON 文献数据，并保留字段冲突供研究者复核；不声称已实现 CSL 样式渲染或文献信息正确性。0.1.42 增加了本机使用准备检查，核对项目文件夹、内置 Skill、药物经济学计算资源、
项目 harness 和本地助手。本地助手异常时，现在可以直接在“设置”中重新启动并连接，无需重启应用；
模型、Python 和 Jupyter 均为按需配置，这项检查不代表方法适用或科学有效。0.1.41 新增有来源绑定、确定性、无宏的
研究汇报幻灯生成，生成后的每一页仍等待研究者核对。0.1.40 会在每个能力复核弹窗中先说明这项 Skill 做什么、来自
哪项项目要求，并明确它不是药物经济学分析，也不能替研究者作出科研判断。0.1.39 增加了项目能力候选的
应用内复核链路：原生程序重新核验准确文件，以哈希链记录启用、
拒绝或撤销，只把纯指令副本启用到当前项目，并拒绝覆盖或删除已经发生变化的内容。
该版本也增加了本地使用习惯的应用内复核：研究者可以查看形成建议的重复交流、修改建议表述、采用、暂停、
恢复或删除；准确的建议文件和设置文件哈希以及本机决定链可阻止过期或未经复核的改动被当作已采用习惯。
0.1.38 让两个能力成长 Skill 从运行时报告的实际安装目录调用校验器，不再假定用户从源码仓库
启动应用。0.1.37 新增了失败关闭的能力成长 harness：
研究者可以用自然语言提出新能力，系统只会生成带中英文描述、精确哈希和授权记录的指令型 Skill 候选项；
至少两次独立交互中重复出现的非敏感工作习惯，只能成为本地偏好建议。两者都不会自行启用，
也不能修改治理规则、核心 Skill、计算引擎或审批记录。该版本同时替换了应用标志，记录了当前授权边界，
并保留 0.1.36 包含 25 份资料的版本化中文药物经济学学习库和本机安装入口。
应用会核对安装包中的清单和每份资料的 SHA-256，不调用模型、不联网，
直接建立与当前项目绑定的本地索引；稳定理论与方法资料、注明日期的最新进展保持分开，研究者修改过的
已安装资料不会被覆盖。它保留 0.1.35 为教学案例增加的单独确认本机复算入口：
程序先核对脚本、分析设定、输入数据和预期结果是否仍与内置版本一致，再写出基线结果与低值、高值
敏感性分析，并保留运行和溯源记录；案例内容不会发送给模型服务。它保留 0.1.34 的第六个药物经济学入口，
以及 0.1.33 对简体中文研究界面和内置 Skill 的重写；当前 50 个内置 Skill 统一使用常见的
中国药物经济学表述；原先写死在代码中的下载、文件管理、Jupyter、笔记本和助手提示也已进入
七种语言的资源文件。0.1.32 建立的失败关闭项目约束和研究者科学决策权保持不变。模型无关的教学案例会记录
1 条成功运行和 3 条溯源记录；固定输入发生变化时，应用使用自然中文说明拒绝复算，并保留原有结果。
81,600,567 字节的
`AI4HEOR_0.1.41_x64.dmg` 的 SHA-256 为
`9fc18e035748a2aa67e06443409dce9ffbd2aed83496ab9f1003138391c18ee6`，由受控源码提交
`38e061708e56ee82d53ea3d68a79b95dd25ea5dc` 构建。验证确认 340 个受控资源与源码逐字节一致，
177 项包内 HEOR 测试全部通过，并完成全新启动和旧工作区迁移。前端交互测试确认，能力复核弹窗会在
启用前显示所选语言的能力名称、用途、原始要求、限制和检查项。该包仍未经
Developer ID 签名或 notarize；
这些工程证据不代表科学有效性。

### Intel macOS 产品负责人验收

`AI4HEOR_0.1.41_x64.dmg` 仅用于 Intel Mac 内部测试。打开前先核对上面的 SHA-256。由于该包尚未
签名，macOS 可能要求按住 Control 点击应用后选择“打开”；这只是内部测试方式，不代表已经具备公开分发条件。

1. 确认应用名称和图标均为 AI4HEOR，首页从药物经济学研究问题开始，只显示六个 HEOR 相关入口。
2. 新建一个一次性项目，确认存在 `AGENTS.md`、`policy.json`、`capabilities/candidates/`、
   `capabilities/reviews/`、`learning/proposals/` 和 `learning/preferences.json`。
3. 安装内置药物经济学学习库，检索“机会成本”，然后重复安装。检索应完全在本机完成；相同内容重复安装后，
   已安装资料、清单和索引字节不得变化。
4. 通过单独的本机运行确认执行成本-效果教学案例。自然语言请求必须保持可编辑且未发送；确定性结果不得给出
   成本有效、医保准入或政策结论。
5. 如需测试模型，只在“设置”中连接由你选择的模型服务。安装包不含任何密钥；连接失败必须明确显示，不能
   静默切换到其他模型服务。
6. 请助手根据当前项目准备有来源绑定的研究汇报。先在对话中确认听众、目的、语言和篇幅，再从研究汇报卡片生成
   PPTX；打开后逐页检查标题、图表、局限和自动生成的资料页。修改一个已绑定来源后，原 PPTX 不应继续显示为当前版本；
   生成过程不得创建任何批准记录。
7. 在“方法与工具”中要求 AI4HEOR 创建一个仅处理展示格式的窄范围 Skill 候选。名称、说明、授权说明、限制和
   检查项必须同时具备完整的中英文版本。复核并只在这个一次性项目中启用准确候选，然后撤销；核心 Skill 和
   其他项目不得发生变化。
8. 形成一项重复出现、非敏感的展示习惯建议，查看依据后采用，再依次暂停、恢复、修改和删除。研究方法、证据、
   参数、结论、审批、模型选择和数据去向不得成为学习偏好。
9. 检查“运行”和溯源记录能否区分模型生成草稿与本机确定性计算，并确认项目、记录、日志和导出内容中没有密钥。

当前验收边界：没有已准入的外部 Skill 或第三方 MCP；没有 Developer ID 签名和
公证；Apple Silicon、Windows 和当前 Linux 验收仍暂停；不主张科学有效性或方法学适用性。当前未签名版本中，
从设置输入的模型密钥保存在仅当前账户可读的应用私有 OpenCode 配置中，而不是 macOS 钥匙串；系统钥匙串存储
将在签名版本中重新评估。

同一干净提交还交叉构建了 76,095,510 字节的 `AI4HEOR_0.1.31_aarch64.dmg`
（SHA-256 `86b0583e36480affb90ec08b84d8c4276ec702b92e69ef90894f58c2888da42e`）。
Intel 主机上的只读检查确认主程序、OpenCode 和 uv 均为纯 arm64，固定 sidecar
字节一致、282 个资源与源码一致，且包内 HEOR 核心通过全部 177 项测试。严格验证器
在执行 arm64 OpenCode 时按预期以 `Bad CPU type` 失败关闭，未生成正式发布证据；
因此这不是 Apple Silicon 原生启动证明。该包只有 ad-hoc linker 签名，无 Team ID、
sealed resources 或 stapled ticket，严格 codesign 与 Gatekeeper 均拒绝。

## 参与贡献

欢迎 Issue 和 PR。请保持改动最小且可验证，遵循 [`AGENTS.md`](./AGENTS.md)，并在提交 PR 前运行检查。讨论和交流可以加入
[Open Science Discord](https://discord.gg/fWNMDKcd5P)，也可以在 [linux.do](https://linux.do) 社区参与。

## 引用

如果 AI4HEOR 对你的研究有帮助，请如下引用：

```bibtex
@software{ai4heor,
  author  = {{The AI4HEOR Contributors}},
  title   = {AI4HEOR: a local-first, model-agnostic AI workbench for pharmacoeconomics and HEOR},
  year    = {2026},
  version = {0.1.41},
  url     = {https://github.com/ai4s-research/open-science},
  license = {MIT}
}
```

仓库页顶部的 **"Cite this repository"** 按钮(由 [`CITATION.cff`](./CITATION.cff) 生成)提供 APA 与 BibTeX 两种格式。

## 许可证

[MIT](./LICENSE)。随附的第三方技能和连接器保留各自许可证。

> AI4HEOR 仍是 beta 阶段科研工具。人类研究者主导科研并承担方法与决策责任；发表或决策前必须核对数字、引用、代码和结论。

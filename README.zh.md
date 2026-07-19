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
- **本地 HEOR 知识库**：明确选定的文件夹保留层级，在本地绑定哈希并建立索引，
  用于研究者发起的学习，不会自动联网。
- **一切都可回溯**：图、表、报告、笔记本和运行输出都连回生成它们的确切代码、输入、环境、模型输出和对话。
- **本地优先，数据归你**：会话、数据、溯源、笔记本和运行记录都在本机的本地文件夹里,默认不外流。
- **模型无关运行时**：UI 通过 `packages/sdk` 调用内置固定版本的 OpenCode sidecar——自带模型即可;模型提供方、技能和 MCP 服务器保持可插拔。
- **天然可复现**：本地、SSH/Slurm、Modal 和 notebook-batch 运行都被记录为可复现的 run record,而不是散落的终端输出。
- **可扩展**：智能体技能、MCP 服务器与一键科学连接器、`/` 命令、`!` shell 模式,以及一个模型无关的 SDK。

## 效果演示

**由人主导的 HEOR 请求 -> 可复核、可追溯的本地工作。**
新会话只提供药物经济学研究设计、HEOR 证据/数据分析、模型/报告
审计和合成成本效果分析示例。`examples/heor-cost-effectiveness/`
中的双策略、三状态队列输入只是教学假设，不是临床或经济学证据，
也不能生成批准、报销或政策结论。

![AI4HEOR 首次使用界面明确本地、模型、授权与 Human 科学权责边界](./docs/audits/2026-07-17-first-use/06-skip-link-stable.png)

![AI4HEOR 的 HEOR 专属自然语言任务入口](./docs/audits/2026-07-17-first-use/07-heor-workspace-final.png)

![模型执行前可编辑的成本效果分析自然语言请求](./docs/audits/2026-07-17-first-use/08-natural-language-draft-final.png)

## 当前能力

**把科研辅助收敛为有边界的 HEOR Skills。** AI4HEOR 的 45 个第一方 Skill
只路由研究者界定的任务，不取得批准权或方法选择权。代表性已准入工作流包括：

| 技能 | 职责 | 主要产出 |
| --- | --- | --- |
| `$heor-workbench` | 协调由研究者主导的 HEOR 工作，不取得科学决策权 | 可复核的本地计划、工件和停止点 |
| `$heor-local-evidence` | 盘点研究者明确选择的本地知识库，不自动联网 | 哈希绑定的本地证据目录 |
| `$heor-evidence-search` | 起草需 Human 联网授权的 PubMed/ClinicalTrials.gov 检索 | 精确请求哈希和导入的元数据候选 |
| `$heor-model-design` | 结构化人类界定的决策问题与概念模型 | 决策问题和概念模型工件 |
| `$heor-cohort-state-transition` / `$heor-partitioned-survival` | 执行有边界的确定性经济学模型 | 可复现的成本、QALY、增量结果和检查 |
| `$heor-uncertainty-analysis` / `$heor-advanced-value-of-information` | 执行已声明的不确定性与有界 VOI 工作流 | DSA/PSA/CEAC/CEAF/EVPI 与单独复核的高级 VOI |
| `$heor-budget-impact` / `$heor-dynamic-budget-impact` | 执行静态或动态预算影响分析 | 分项预算结果和审计工件 |
| `$heor-model-validation` / `$heor-reporting` / `$heor-reproducibility-package` | 验证、报告并封装当前精确工件 | 独立复核包、报告和重放包 |

全部第一方 Skill 的名称与说明均随七种界面语言发布，同时保留精确
`$skill-id`；外部资产保留原始元数据，未经单独准入不会启用。

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
| 界面语言 | English、简体中文、日本語、Español、Deutsch、Français、한국어。第一方 Skill 名称与说明在 7 种语言中发布，同时保留精确 `$skill-id`；外部 Skill 保留其原始元数据。Portuguese (Brazil) 和 Arabic 已注册，但还不可选。 |

## 技能与连接器

默认只打包 `runtime/skills/core/` 中的第一方技能，包括 AI4HEOR 的证据、
模型设计、参考案例、不确定性、预算影响、验证和报告工作流。第三方 Skill
与 MCP 由安装包内的准入注册表控制：发现候选保持停用，只有许可证兼容、
经过审查、完成跨平台验证并锁定精确哈希的 `validated-adapter` 才能进入
应用托管的运行时。

`ai4s-research/ai4s-skills` 的 7 个条目当前处于隔离改造状态。Anthropic
的 `docx`、`pdf`、`pptx`、`xlsx` 是 source-available，而非可再分发的
开源资产；其目录许可证禁止复制、衍生和分发，因此 AI4HEOR 不再获取或打包。

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

当前验证的 0.1.32 本地 x64 macOS 构建尚未代码签名或 notarize。

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
与跨平台发布暂停，直到 macOS 路径通过验收。当前源码和已验证的 x64 macOS 安装包均为
`0.1.32`。该版本将新项目 harness 初始化改为失败关闭，
并新增精确的机器可读契约：人类掌握科学权威、不允许模型提供商静默降级、确定性计算是计算权威、
审批由应用持有，外部内容是不可信数据而非操作指令。80,106,479 字节的
`AI4HEOR_0.1.32_x64.dmg` 的 SHA-256 为
`2bbac3379a826be022a0467255707187ac1182dbc0e0bfed177e70b2203d83c2`，已从干净提交
`2bd1bea0de2fb151c8f11a57b28600223eee34ce` 构建，验证了 283 个
受控资源、177 项包内 HEOR 测试，以及两次隔离 LaunchServices 运行：全新创建
`Documents/AI4HEOR`，以及保留内容地将 `Documents/OpenScience` 迁移为 AI4HEOR；
两次均证明应用复制、单一应用进程、单一内置 OpenCode 子进程与完整清理。它仍未经 Developer ID 签名或 notarize；
这些工程证据不代表科学有效性。

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
  version = {0.1.32},
  url     = {https://github.com/ai4s-research/open-science},
  license = {MIT}
}
```

仓库页顶部的 **"Cite this repository"** 按钮(由 [`CITATION.cff`](./CITATION.cff) 生成)提供 APA 与 BibTeX 两种格式。

## 许可证

[MIT](./LICENSE)。随附的第三方技能和连接器保留各自许可证。

> AI4HEOR 仍是 beta 阶段科研工具。人类研究者主导科研并承担方法与决策责任；发表或决策前必须核对数字、引用、代码和结论。

<div align="center">

[![Open Science Desktop — 本地优先 AI 科研桌面工作台](./docs/assets/banner.webp)](https://github.com/ai4s-research/open-science)

# Open Science Desktop

**本地优先、模型无关的 macOS、Windows & Linux AI 科研桌面工作台。**

原名 Open Science。它是 Claude Science 及同类 AI-for-science 工作台的开源桌面替代：
基于 Tauri、MCP、agent skills 和可复现工件构建。它把智能体、笔记本、文件、图表、
报告、运行记录和审查连接成一条可审计的桌面工作流。

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

🎉 **认可：** Open Science Desktop 在面向自主科研智能体的端到端基准 [ResearchClawBench](https://internscience.github.io/ResearchClawBench-Home/) 上，按已评分任务平均分排名第 1（Pass@1 榜单，2026 年 7 月 9 日）。

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

**跑完整个科研闭环**——从一个宽泛的方向到一篇成稿论文：探索、文献综述、假设、实验代码、分析、绘图、写作，全部在一次连续、可审计的会话里完成。

- **自主科研智能体**：内置的 `ai4s-agent` 端到端串起各专项技能(探索 → 综述 → 实验 → 写作)，每一步都把一个真实、可检查的工件落到你的工作区里,而不只是一条聊天回复。
- **一切都可回溯**：图、表、报告、笔记本和运行输出都连回生成它们的确切代码、输入、环境、模型输出和对话。
- **本地优先，数据归你**：会话、数据、溯源、笔记本和运行记录都在本机的本地文件夹里,默认不外流。
- **模型无关运行时**：UI 通过 `packages/sdk` 调用内置固定版本的 OpenCode sidecar——自带模型即可;模型提供方、技能和 MCP 服务器保持可插拔。
- **天然可复现**：本地、SSH/Slurm、Modal 和 notebook-batch 运行都被记录为可复现的 run record,而不是散落的终端输出。
- **可扩展**：智能体技能、MCP 服务器与一键科学连接器、`/` 命令、`!` shell 模式,以及一个模型无关的 SDK。

## 效果演示

**一句提示 -> 一份完整、可追溯的分析。**

![端到端剂量-响应分析：智能体运行代码，产出拟合图与报告](./docs/assets/showcase-workflow.webp)

**每个工件都能回到它的代码、输入和对话。**

![工件检查器展示某张图的生成代码、输入与溯源信息](./docs/assets/showcase-provenance.webp)

**文献 -> 可验证报告。**

![文献综述产出渲染后的 PDF 稿件，并附带可追溯性评审](./docs/assets/showcase-literature.webp)

<details>
<summary><b>更多截图</b></summary>

<br>

![智能体驱动 Jupyter 笔记本并实时绘制 matplotlib 图](./docs/assets/showcase-notebook.webp)

![实验扫描表格与实时分析笔记本并列](./docs/assets/showcase-experiment.webp)

![技能库列出内置的科学技能](./docs/assets/showcase-skills.webp)

</details>

## 当前能力

**把科研闭环做成技能。** 一个元技能跑完整条流水线;每个阶段都是一个自足的技能,产出真实、可评审的工件——在 OpenCode 支持的任意模型上都能跑:

| 技能 | 职责 | 主要产出 |
| --- | --- | --- |
| `ai4s-agent` | 按顺序运行下面四个技能 | 完整的研究包 |
| `research-explorer` | 把宽泛方向收敛成具体课题 | `research_exploration.md`、`topic_matrix.md`、`literature_pre_survey.md` |
| `literature-survey` | 撰写文献综述 | 6–20 页 PDF、60+ 条真实引用、LaTeX 源码、分类学图 |
| `experiment-suite` | 构建实验包 | 设计文档、可运行代码、带溯源的 `results.json`、图、报告 |
| `paper-writer` | 撰写研究论文 | 8–14 页 PDF、200+ 引用、4–8 张图、表格 |
| `mindmap-render` | 渲染思维导图 | 由 `topic_matrix.md` 生成的图片 |
| `integrity-auditor` | 审计论文完整性 | 图像/数值/逻辑问题、四级证据分级、`audit_report.md` |

这些上游 `ai4s-skills` 模式目前只作为停用的改造候选登记，不会作为运行时
能力发布；AI4HEOR 由第一方技能实现已准入的科研工作流。

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
| 界面语言 | English、简体中文、日本語、Español、Deutsch、Français、한국어。Portuguese (Brazil) 和 Arabic 已注册，但还不可选。 |

## 技能与连接器

默认只打包 `runtime/skills/core/` 中的第一方技能，包括 AI4HEOR 的证据、
模型设计、参考案例、不确定性、预算影响、验证和报告工作流。第三方 Skill
与 MCP 由安装包内的准入注册表控制：发现候选保持停用，只有许可证兼容、
经过审查、完成跨平台验证并锁定精确哈希的 `validated-adapter` 才能进入
应用托管的运行时。

`ai4s-research/ai4s-skills` 的 7 个条目当前处于隔离改造状态。Anthropic
的 `docx`、`pdf`、`pptx`、`xlsx` 是 source-available，而非可再分发的
开源资产；其目录许可证禁止复制、衍生和分发，因此 AI4HEOR 不再获取或打包。

当前一键科学 MCP 连接器包括：

- 文献检索：arXiv、PubMed、Crossref、Semantic Scholar、bioRxiv/medRxiv。
- 生物医学数据库：PubMed、ClinicalTrials.gov、MyVariant/ClinVar。
- Materials Project。
- FRED 经济数据。
- Space weather。
- Open-Meteo 天气与气候。
- USGS water data。

你也可以在 Settings 中添加任意本地或远程 MCP 服务器。参见
[`docs/CONNECT_YOUR_TOOLS.md`](./docs/CONNECT_YOUR_TOOLS.md)。

中立定位对比见
[`Open Science Desktop vs OpenScience`](./docs/open-science-desktop-vs-openscience.md)。

## 安装

从 [Releases 页面](https://github.com/ai4s-research/open-science/releases/latest) 下载最新安装包。

- **macOS**：`.dmg` / `.app`，Apple Silicon 和 Intel，要求 macOS 13 Ventura 或更高。
- **Windows**：NSIS `.exe` 和 `.msi`，Windows 10/11 x64。
- **Linux**：x86_64 Linux 的 `.deb` 和 `.rpm`。

当前构建尚未代码签名或 notarize。

**macOS**：如果 Gatekeeper 提示应用已损坏或来自未知开发者，把应用安装到 Applications 后运行：

```bash
xattr -cr "/Applications/Open Science.app"
```

**Windows**：如果出现 SmartScreen，选择 **更多信息 -> 仍要运行**。

**Linux**：

```bash
sudo apt install ./OpenScience_*.deb
# 或
sudo rpm -i OpenScience_*.rpm
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
bash scripts/dev/fetch-skills.sh

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
| `runtime/skills/external/` | 构建时拉取的外部技能。 |
| `runtime/harness/` | 运行时 harness 知识与 operator 上下文。 |
| `runtime/mcp/` | MCP 运行时说明和配置。 |
| `examples/` | 内置示例工作区。 |
| `scripts/dev/` | sidecar、`uv`、技能拉取器和聚焦回归探针。 |
| `docs/` | 产品、技术、operator、连接器和研究笔记。 |

## 状态

项目是正在积极开发的桌面 MVP。最可靠的当前实现日志是 [`PROGRESS.md`](./PROGRESS.md)。
产品和架构说明位于 [`docs/PRD.md`](./docs/PRD.md) 和
[`docs/TECHNICAL_DESIGN.md`](./docs/TECHNICAL_DESIGN.md)，但这些文档同时包含目标设计和历史状态说明。

近期工作集中在签名/notarize 发布、更广的 Windows/Linux 验证、自动更新、连接器加固，以及继续强化可复现性审查。

## 参与贡献

欢迎 Issue 和 PR。请保持改动最小且可验证，遵循 [`AGENTS.md`](./AGENTS.md)，并在提交 PR 前运行检查。讨论和交流可以加入
[Open Science Discord](https://discord.gg/fWNMDKcd5P)，也可以在 [linux.do](https://linux.do) 社区参与。

## 引用

如果 Open Science Desktop 对你的研究有帮助,请如下引用:

```bibtex
@software{open_science_desktop,
  author  = {{The Open Science Desktop Contributors}},
  title   = {Open Science Desktop: a local-first, model-agnostic AI research workbench},
  year    = {2026},
  version = {0.1.9},
  url     = {https://github.com/ai4s-research/open-science},
  license = {MIT}
}
```

仓库页顶部的 **"Cite this repository"** 按钮(由 [`CITATION.cff`](./CITATION.cff) 生成)提供 APA 与 BibTeX 两种格式。

## 许可证

[MIT](./LICENSE)。随附的第三方技能和连接器保留各自许可证。

> Open Science Desktop 仍是 beta 阶段科研工具。产出应视为草稿：发表或决策前请核对数字、引用、代码和结论。

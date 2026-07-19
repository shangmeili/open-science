# AI4HEOR 外部来源处置记录

**记录日期：** 2026-07-20

**性质：** 只读授权与替代审计，不是候选库，也不提供启用入口。

**当前运行时：** `runtime/assets/asset-admission-registry.json` 只登记已经通过全部检查并实际随包发布的外部适配器；当前为空。

AI4HEOR 不再把未完成改写或许可证不兼容的来源长期展示为“隔离”或“拒绝”选项。需要的能力转为第一方建设，完成合约测试后直接进入第一方 Skill 清单；不需要或不允许改作的来源从产品清单移除，只在本记录中保留授权和决策依据。

## 10 项原待改写来源的处置

| 原来源 | AI4HEOR 保留的能力意图 | 第一方替代结果 | 后续处理 |
| --- | --- | --- | --- |
| AI4S Agent | 自然语言研究协调、任务分解、交接 | `heor-workbench` 与项目 harness 已承担协调，科学判断仍由研究者作出 | 上游不进入运行时；继续完善第一方 harness 测试 |
| AI4S Experiment Suite | 可复现运行、结果比较、运行记录 | 确定性 HEOR 引擎、运行记录和溯源链已覆盖 | 上游不进入运行时；新分析方法逐项增加合约与重放测试 |
| AI4S Integrity Auditor | 数字、引用、代码、图表和来源一致性检查 | `stats-integrity`、`traceability-review`、`citation-reviewer`、`figure-provenance`、`heor-model-validation` 已分工覆盖 | 按 HEOR 工件补充检查，不引入通用审计链 |
| AI4S Literature Survey | 检索、筛选、提取、综述和引用追踪 | `literature-review`、`heor-evidence-search`、`heor-evidence-synthesis` 已提供有协议、有请求哈希和人工网络授权的路径 | 继续建设参考文献库与 RIS/BibTeX/CSL 导入导出 |
| AI4S Mindmap Renderer | 概念模型、研究路径和证据关系可视化 | `heor-model-design` 已交付可审计的概念模型工件 | 可编辑图形和稳定导出列入第一方建设，不保留上游渲染器 |
| AI4S Paper Writer | 依据研究工件形成报告和汇报材料 | `heor-reporting` 已覆盖结构化 HEOR 报告；`research-presentation` 已生成有来源绑定的 PPTX | DOCX/PDF 正式导出独立建设，不使用其他项目的受限文档 Skill |
| AI4S Research Explorer | 研究方向梳理、方法更新和研究优先级 | `heor-methods-watchlist` 与有边界的 `heor-advanced-value-of-information` 已覆盖 | 不采用自由主题自动评分；优先级由研究者结合方法和 VOI 结果判断 |
| HEORAgent MCP | HEOR 检索、模型、HTA、BIA 和材料组织 | 相关能力已拆入多个第一方 HEOR Skill；PubMed/ClinicalTrials.gov 由 `heor-evidence-search` 固定端点实现 | 不运行其 48-tool 进程；只按明确 HEOR 需求独立建设单项能力 |
| Paper Search MCP | 多源文献检索和元数据获取 | `heor-evidence-search` 已覆盖受控的 PubMed/ClinicalTrials.gov 元数据路径 | 新数据源按权利、固定出站、请求哈希和人工授权逐源独立实现 |
| BioMCP | 生物医学实体、试验、文献、变异和药物数据 | 与当前 HEOR 核心工作直接相关的试验和文献入口由第一方证据能力覆盖 | 其余生物信息学能力不作为 HEOR 默认功能；出现明确研究需求时再按单一数据源独立建设 |

上述“替代”指重新定义能力边界并由 AI4HEOR 第一方代码、Skill、工件和测试实现，不是复制上游目录后改名或重新编译。

## 4 项许可证不兼容来源的替代

Anthropic `docx`、`pdf`、`pptx`、`xlsx` 目录的来源许可证不允许 AI4HEOR 复制、改作或分发。四项已从运行时登记、产品界面和可选清单永久移除，不参与后续编译。

| 能力 | 选定方案 | 当前结果 |
| --- | --- | --- |
| DOCX 生成 | 根据 AI4HEOR 报告工件独立实现第一方 OOXML 导出 | 建设任务；不得使用 Anthropic 源码或素材 |
| PDF 生成 | 由第一方报告导出链生成；现有本地预览与提取继续使用已审核依赖 | 建设任务；不得使用 Anthropic 源码或素材 |
| PPTX 生成 | 第一方 `research-presentation`，确定性、无宏、来源绑定 | 已交付并有合约测试 |
| XLSX 生成 | 根据 AI4HEOR 表格和结果工件独立实现第一方 OOXML 导出 | 建设任务；不得使用 Anthropic 源码或素材 |

## 今后的登记规则

1. 用户界面只显示真正随包发布的外部适配器，不显示未完成、已排除或仅供调研的来源。
2. 第一方改写能力进入 `runtime/skills/core/`，按七种界面语言提供名称和说明，并通过对应合约、对抗和打包测试。
3. 外部适配器只有在许可证兼容、提交和内容哈希锁定、依赖与出站受控、方法与安全复核通过、停止开关可用且包内字节核对通过后，才可写入发布登记表。
4. 历史来源仅用于说明授权和设计决策，不得被应用自动下载、安装、启用或作为研究方法权威。

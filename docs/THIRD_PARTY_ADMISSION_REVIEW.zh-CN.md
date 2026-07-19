# AI4HEOR 第三方能力准入复核表

**复核基线：** `runtime/assets/asset-admission-registry.json`  
**清单日期：** 2026-07-20  
**当前结果：** 48 个 AI4HEOR 第一方 Skill 已内置；第三方资产 0 个准入、10 个隔离候选、4 个拒绝。

“隔离”不等于永久不用；它表示尚未通过依赖锁定、网络与数据权利、执行权限、方法复核、对抗测试、跨平台和停止开关等全部门槛。“拒绝”表示当前上游资产不能被 AI4HEOR 复制、改作或分发。

## 隔离候选（10）

| 资产 | 许可证 | 主要阻断原因 | 建议处理 |
| --- | --- | --- | --- |
| AI4S Agent | MIT | 通用自主研究链超出 AI4HEOR 的 Human-in-the-loop 边界；没有 AI4HEOR 工件合约和权责分离测试 | 不整体纳入。已由第一方 `heor-workbench` 和项目 harness 承担协调责任；只吸收经验，不复制上游运行链。 |
| AI4S Experiment Suite | MIT | 自由实验执行没有收敛到确定性 HEOR 引擎，也缺少方法与停止边界 | 不整体纳入。将有用的运行记录和对比模式独立改写为第一方确定性分析流程。 |
| AI4S Integrity Auditor | MIT | 取证依赖和证据分级没有针对 HEOR 独立验证 | 不整体纳入。已由 `traceability-review`、`stats-integrity` 和 `heor-model-validation` 分担可追溯、统计和模型验证。 |
| AI4S Literature Survey | MIT | 引用数量目标不能替代有协议的 HEOR 证据综述 | 不整体纳入。已由 `heor-evidence-search` 与 `heor-evidence-synthesis` 提供有请求哈希和人工网络授权的第一方路径。 |
| AI4S Mindmap Renderer | MIT | 渲染依赖未由 AI4HEOR 锁定或供给，输出与 HEOR 概念模型没有绑定 | 可优化后纳入需求，但应独立实现“概念模型/研究路径图”渲染器，先绑定当前项目工件并增加快照测试。 |
| AI4S Paper Writer | MIT | 通用论文目标与 CHEERS 及预算影响分析的独立报告要求不一致 | 不整体纳入。已由第一方 `heor-reporting` 承担 HEOR 结构化报告；通用 DOCX 生成另行清室实现。 |
| AI4S Research Explorer | MIT | 自由主题评分不是经验证的 HEOR 研究排序方法 | 不整体纳入。研究排序使用第一方方法有效性监测和有边界的 VOI 流程。 |
| HEORAgent MCP | MIT | 已审计版本安装时仍有 12 个依赖漏洞（含 4 个高危）；多源网络、全局项目根、遥测、计算和自证有效性集中在一个 48-tool 边界 | 不整体编译纳入。只选择价值明确的单个工具，由应用层控制出站、项目根、授权、输出结构和停止开关，逐项准入。 |
| Paper Search MCP | MIT | 直连多主机检索/下载未绑定请求哈希；可选 Sci-Hub 路径存在独立权利与合规问题；依赖和停止开关未完成 | 不整体纳入。只按数据源逐项实现官方元数据连接器；现有 PubMed/ClinicalTrials.gov 第一方路径保留。 |
| BioMCP | MIT | 旧一键配置的包名和启动命令已过时；广泛的生物医学来源、凭据、数据权利与网络边界未逐工具审核 | 不整体纳入。只对直接服务 HEOR 证据工作的具体工具建立隔离适配器；其余保留为用户自行安装候选。 |

## 已拒绝（4）

| 资产 | 许可证 | 拒绝原因 | 建议处理 |
| --- | --- | --- | --- |
| Anthropic DOCX Skill | LicenseRef-Anthropic-Source-Available | 目录许可证不允许 AI4HEOR 复制、改作或分发 | 不得修改后编译纳入。通用 DOCX 作者能力应根据需求清室实现，不使用上游源码与素材。 |
| Anthropic PDF Skill | LicenseRef-Anthropic-Source-Available | 同上 | 不得修改后编译纳入。现有 PDF 预览/提取保留第一方实现；新的 PDF 导出需求独立实现。 |
| Anthropic PPTX Skill | LicenseRef-Anthropic-Source-Available | 同上 | 不纳入上游。已由 AI4HEOR 第一方、无宏、有来源绑定的 `research-presentation` 替代。 |
| Anthropic XLSX Skill | LicenseRef-Anthropic-Source-Available | 同上 | 不得修改后编译纳入。通用 XLSX 作者能力作为第一方清室实现待办。 |

## 请产品所有者核对的决策

1. 是否同意“不整体纳入任何第三方 Agent/MCP”，只做第一方独立实现或逐工具适配？
2. 三项尚未完整交付的通用科研基础能力，建议优先级为：**DOCX 报告导出 → XLSX 表格导出 → 概念模型/研究路径图**。是否调整？
3. HEORAgent MCP、Paper Search MCP 和 BioMCP 中，是否有你希望先拆解的具体工具或数据源？未指定时，默认不启动第三方编译和纳入。


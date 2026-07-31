# AI4HEOR 工程基线与闭环记录（2026-07-31）

## 基线

- 分支：`codex/heor-workbench`
- 本 loop 修改前的已提交基线：`12193198a17bb731188daf3c25c168d148cf2188`
- 基线原则：在现有 Open Science/Tauri 技术栈上增量推进；AI 负责辅助推理，正式研究计算由可验证的确定性模块完成；科学、隐私、兼容性和公开接口决策保留 Human-in-the-loop。
- 已完成 loop 范围：不可信 HTML 预览边界、同主版本 JavaScript CPU 拒绝服务补丁、安装后 OpenCode 的鉴权 HTTP 就绪证据、经研究者确认的两策略 PSA 零 INMB 并列口径，以及 PPTX 预览中 ECharts `lines` 系列通告的不可达性门禁。其他科学计算、模型适配、研究数据和研究流程未修改。

## 当前架构与完成度

| 层 | 当前实现 | 本轮状态 |
| --- | --- | --- |
| 桌面与前端 | Tauri 2 + React/TypeScript/Vite | 保持原架构；HTML 预览安全边界已修复 |
| AI 调用与任务执行 | OpenCode 本地 sidecar，HTTP/SSE，模型提供商可配置 | 业务运行逻辑未修改；安装包首启门禁新增鉴权 HTTP 就绪证明 |
| HEOR 确定性计算 | Python 版本化计算模块 + Rust 授权、审计和哈希绑定 | 仅修正两策略 PSA 零 INMB 的边界分类；其他公式、参数和随机数列不变 |
| 数据与溯源 | 本地 JSON/JSONL/SQLite、证据与参数来源、运行记录和报告导出 | 未修改 |
| Human-in-the-loop | 关键科学定义、证据采用、结构与发布决策由研究者确认 | PSA 并列口径在研究者同意后才实施 |
| 文件预览 | React inspector + Tauri loopback preview server | HTML 改为被动展示；源码查看和外部打开保留 |

当前仓库已有主要单元/组件、确定性 HEOR、Rust 原生与资源门禁测试。macOS 与 Windows 发布脚本已有真实主机级安装、进程、工作区和清理检查，并已补上 OpenCode 鉴权 HTTP 就绪合同；但完整的安装后可视交互、任务执行、导入到导出 E2E 仍未建立，不能由 Vitest/jsdom 或仅有进程的结果替代。

## 问题与风险清单

| 编号 | 优先级 | 状态 | 证据与影响 |
| --- | --- | --- | --- |
| P0-SEC-001 | P0 | 本轮已修复 | `FilePreviewInspector` 原先向不可信 HTML 授予 `allow-scripts`，本地预览响应无 CSP，可能导致脚本执行和研究数据外发 |
| P1-SEC-002a | P1 | 已修复 | `brace-expansion 1.1.15 / 2.1.1` 受 CPU 拒绝服务通告影响；已同主版本升级并加入发布门禁 |
| P1-SEC-002b | P1 | 待单独处理 | `brace-expansion` OOM 通告当前只标记 5.0.8 为修复版；旧主版本跨版替换需独立兼容性决策，漏洞代码未进入当前 Tauri 前端产物 |
| P1-TEST-001a | P1 | 实现与合同已修复；新包执行待打包轮 | 安装包首启过去只证明 OpenCode 进程存在；现要求未授权健康请求返回 401，且证据不保存端口或密码 |
| P1-TEST-001b | P1 | 待单独处理 | 缺少安装后真实 Tauri 可视交互、任务、HTML 预览、权限和导入到导出的自动化 E2E |
| P1-SCI-001 | P1 | 已完成缺口核对；科学边界待研究者确认 | 知识库和模型设计 Skill 会说明决策树，但 Python 核心、CLI、产物合同、报告与复现链均无可执行决策树路径 |
| P1-SCI-002 | P1 | 待单独处理 | 亚组分析尚缺完整的预设、来源绑定、逐亚组结果与复核合同 |
| P1-SCI-003 | P1 | 已修复 | 两策略 PSA 旧汇总使用 `INMB >= 0`，将零值并列同时计入干预成本效果概率，与同一输出中单独报告并列的决策不确定性表冲突 |
| P1-AI-001 | P1 | 待单独处理 | 模型调用的提示词版本、token/费用和产物关联追踪仍不完整 |
| P2-SEC-003 | P2 | 待评估 | Tauri 主应用全局 CSP 仍为空；本轮已在不可信 HTML 的两个实际渲染入口建立独立限制。全局 CSP 会影响 loopback、SSE 和资源加载，需另行做兼容性测试 |
| P2-SEC-004 | P2 | 已评估；当前不可达 | ECharts 5.6.0 命中 `GHSA-fgmj-fm8m-jvvx`，但通告需要 `lines` 系列；当前 `pptx-preview` 只从导入文件构造 `line` / `bar` / `pie`，已用发布门禁防止未复审的可达性变化 |

## 优化任务列表

1. P0-SEC-001：完成 HTML 被动预览边界并建立回归合同（已完成）。
2. P1-TEST-001a：首启 OpenCode 鉴权 HTTP 就绪合同已完成；下一次新包必须在原生 macOS/Windows 验证器中产生该证据。
3. P1-TEST-001b：建立最小真实桌面可视 E2E，覆盖任务、HTML 预览、权限与导入。
4. P1-SEC-002：CPU 型通告已完成同主版本修复；OOM、UUID 和 React Router 通告继续按实际可达路径逐个处置，不强制整树升级。ECharts `lines` 系列通告已证明当前 PPTX 路径不可达。
5. P1-SCI-003：统一两策略 PSA 的零 INMB 并列口径（已完成）。
6. P1-SCI-001 / P1-SCI-002：分别建立人工可核算基准后再实现，禁止与界面修复混做。
7. P1-AI-001：在不记录密钥和敏感输入的前提下补齐模型调用审计合同。
8. P2-SEC-003：评估主应用全局 CSP；仅在不破坏本地服务和模型流式连接时实施。

## 验证矩阵

| 验证项 | 命令或方式 | 结果 |
| --- | --- | --- |
| 修复前前端复现 | 定向运行 `FilePreviewInspector.test.tsx` | 失败：实际为 `sandbox="allow-scripts"` |
| 修复前服务复现 | 定向运行新增 Rust CSP 测试 | 失败：HTML 响应没有 CSP |
| 前端定向回归 | `pnpm --filter @ai4s/desktop exec vitest run src/components/inspector/FilePreviewInspector.test.tsx` | 10/10 通过 |
| Rust 预览服务回归 | `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml preview_server::tests` | 7/7 通过 |
| 完整前端测试 | `pnpm test` | 112 个文件、762 项通过 |
| 完整 Rust 测试 | `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml` | 368 项通过、1 项既有忽略 |
| 类型检查 | `pnpm typecheck` | 通过 |
| ESLint | `pnpm lint` | 通过 |
| Rust 格式 | `cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check` | 通过 |
| 生产构建 | `pnpm build` | 通过；保留既有 3Dmol `eval` 与大包告警 |
| 发布资源预检 | `pnpm preflight:resources` | 39 个来源、440 个文件通过 |
| 浏览器界面回归 | `/heor` 加载并展开“打开一个教学案例” | 标题与主要内容正确；无错误遮罩、无控制台错误 |
| JS 依赖安全门禁 | `python3 scripts/dev/test_js_security_policy.py -v` | 2/2 通过 |
| CPU DoS 通告复审 | `pnpm audit --prod --json` | `GHSA-3jxr-9vmj-r5cp` 由 2 条降为 0 条；其他通告未隐藏 |
| XLSX 定向兼容性 | `pnpm --filter @ai4s/desktop exec vitest run src/lib/xlsx.test.ts` | 3/3 通过 |
| 生产产物可达性 | 在 `apps/desktop/dist/**/*.js` 查找 `brace-expansion` 及其 Node 归档依赖 | 0 命中 |
| 首启门禁修复前复现 | `python3 scripts/release/test_macos_distribution.py -v` 与 `test_release_evidence.py -v` | 4 处失败：缺少端口/HTTP 探测、证据检查和 Windows 合同 |
| 发布层完整回归 | `python3 -m unittest discover -s scripts/release -p 'test_*.py' -v` | 43/43 通过 |
| 当前运行时只读探测 | 未授权请求已安装 OpenCode 的 `/global/health` | 返回 401；未读取密码，未记录临时端口 |
| 旧 DMG 当前性检查 | 当前验证器检查既有 1.0.0 x64 DMG | 在启动前因包内 `heor-workbench/SKILL.md` 与当前源码字节不同而失败；未冒充新包证据 |
| PSA 并列修复前复现 | 定向运行新增的四次完全相同策略固定案例 | 失败：明细并列概率为 1.0，旧汇总成本效果概率也错报为 1.0 |
| PSA 定向回归 | `python -m unittest python/heor_core/tests/test_model.py -v` | 70/70 通过；黄金案例数值不变 |
| HEOR 完整回归 | `pnpm test:heor` | 178/178 通过 |
| HEOR 跨产物合同 | `python3 scripts/dev/test_heor_artifact_contracts.py -v` | 113/113 通过 |
| PPTX / ECharts 可达性门禁 | `python3 scripts/dev/test_js_security_policy.py -v` | 3/3 通过；锁定的 PPTX 适配器仅构造 `line` / `bar` / `pie` |

## Loop P0-SEC-001

### 发现与复现

- 当前行为：HTML iframe 使用 `sandbox="allow-scripts"`；loopback server 对 `text/html` 不发送 CSP。
- 风险：导入或受污染 HTML 可以在工作台上下文中运行脚本，并尝试 `fetch`、WebSocket、表单、frame 或插件访问。
- 失败测试：前端断言 iframe 无脚本权限且内联文档包含 `script-src 'none'` / `connect-src 'none'`；Rust 断言 HTML 响应包含相同限制。两项均在修复前失败。

### 根因

HTML 预览沿用了 Open Science 的交互式 HTML 兼容策略，但 AI4HEOR 没有为研究资料建立“外部 HTML 是不可信数据”的独立执行边界；iframe 权限与响应头同时缺少限制。

### 最小修复

- `apps/desktop/src/components/inspector/FilePreviewInspector.tsx`
  - 两种 HTML iframe 都使用空 sandbox 权限集。
  - browser/gateway 的 `srcdoc` 在任何导入标记之前注入限制性 CSP。
  - gateway 不再把远端 HTML URL 直接加载成应用内活动页面。
  - 桌面静态 HTML、源码查看和显式外部打开保持可用。
- `apps/desktop/src-tauri/src/preview_server.rs`
  - 仅 `text/html` 响应增加 CSP 与 `Referrer-Policy: no-referrer`。
  - 本地相对样式、图片、字体和媒体仍可展示；脚本、连接、frame、表单和对象被阻断。
  - PDF 等非 HTML 响应保持原样，并由测试固定。
- 对应前端和 Rust 回归测试覆盖上述边界。

### 验收、回滚与剩余风险

- 验收标准：应用内 HTML 不执行 JavaScript、不建立外部连接；静态内容、源码查看和外部打开保留；其他预览格式无回归；所有相关门禁通过。
- 验收结果：达到。
- 回滚方式：仅回滚本轮提交；不需要数据迁移，也不改变研究产物格式。
- 剩余风险：尚未用正式安装后的 WKWebView/WebView2 自动化 E2E 验证 CSP 控制台事件；这是 P1-TEST-001 的一部分。该缺口不改变 sandbox 与响应头的机器可验证限制。

## Loop P1-SEC-002a

### 发现与复现

- 当前行为：`pnpm audit --prod --json` 报告 `brace-expansion 1.1.15 / 2.1.1` 命中 [GHSA-3jxr-9vmj-r5cp](https://github.com/advisories/GHSA-3jxr-9vmj-r5cp) / CVE-2026-13149。
- 依赖路径：`exceljs 4.4.0 -> archiver/unzipper -> glob/readdir-glob -> minimatch -> brace-expansion`。
- 可达性：AI4HEOR 前端只使用 `ExcelJS.Workbook().xlsx.load()` 读取工作簿；Tauri 只打包 Vite `dist` 与明示资源，产物中无 `brace-expansion`、`glob`、`archiver` 或 `unzipper` 代码。因此当前安装包不可达，但开发/构建依赖树仍应清除已有同主版本补丁的高危项。
- 失败测试：新建 `scripts/dev/test_js_security_policy.py`，修复前同时证明缺少安全锁定且锁文件仍含两个受影响版本。

### 根因与最小修复

- 根因：`exceljs` 的间接依赖范围允许安全补丁，但旧锁文件没有重新解析到维护者已发布的补丁版。
- 修复：使用 pnpm 精确 override，仅把 `1.1.15 -> 1.1.16` 与 `2.1.1 -> 2.1.2`；不跨主版本，不改 `exceljs`、`minimatch` 或业务代码。
- 门禁：锁定规则已接入发布工作流，后续回退到受影响版本会直接阻断构建。

### 验收、回滚与剩余风险

- 验收结果：新门禁 2/2、XLSX 3/3、前端 762/762、Rust 368 通过/1 既有忽略，类型检查、lint、Rust 格式、生产构建和资源预检全部通过。
- 审计结果：`GHSA-3jxr-9vmj-r5cp` 为 0 条；保留并显式记录其他 6 个通告，未用 ignore 或降低审计阈值隐藏。
- 回滚方式：回滚本 loop 的独立提交；无数据迁移、无研究产物格式变化。
- 剩余风险：[GHSA-mh99-v99m-4gvg](https://github.com/advisories/GHSA-mh99-v99m-4gvg) 于 2026-07-24 标记所有 `<=5.0.7` 版本受 OOM 影响，官方只标记 `5.0.8` 为修复版。跨主版本强制替换可能破坏旧 `minimatch` 调用，必须在 P1-SEC-002b 中独立处置；当前产物检查确认漏洞代码未进入 Tauri 前端资源。

## Loop P1-TEST-001a

### 发现与复现

- 当前行为：macOS 与 Windows 安装包验证器只要求桌面进程和内置 OpenCode 进程存在并创建工作区。若 OpenCode 进程已经卡死、尚未监听或丢失密码边界，旧门禁仍可能通过。
- 目标行为：从唯一的包内 OpenCode 进程命令读取临时端口，对 `127.0.0.1` 的 `/global/health` 发起不带凭据的请求，并且只在返回 401 时判定本地服务已经监听且鉴权生效。
- 失败测试：端口解析/401 合同、macOS CI 检查、Windows 检查和发布证据配对检查在修改前分别失败；不是异步波动或测试环境错误。

### 根因与最小修复

- 根因：既有首启门禁把“进程存在”等同于“HTTP 服务可用且安全边界生效”。
- macOS 验证器新增有界端口解析与 1 秒 loopback HTTP 探测；200 或连接失败均不接受。
- Windows 验证器使用相同的路径、401 标准和 60 秒总就绪边界；真实脚本执行留在 Windows CI。
- 发布证据将 `opencode-authenticated-http` 与进程、工作区检查绑定，并只保存 `authentication_enforced=true`、固定路径和 401 状态，不保存端口、密码、响应正文或研究数据。
- CI 的 macOS 证据命令必须声明新检查；Windows 验证脚本必须声明并生成相同检查。

### 验收、回滚与剩余风险

- 验收结果：发布测试 43/43、前端 762/762、Rust 368 通过/1 既有忽略，类型检查、lint、Rust 格式、生产构建、资源预检和 diff 检查全部通过。
- 原生旁证：当前已安装 OpenCode 的无凭据健康请求返回 401。
- 旧包处理：已有 1.0.0 DMG 因包内 Skill 与当前源码不同被资源字节门禁阻断，不能用于当前源码的正式首启证明；未放宽门禁，也未生成替代证据。
- 回滚方式：回滚本 loop 的独立提交；无数据迁移、无业务运行变更、无研究产物格式变化。
- 剩余风险：新构建 macOS DMG 尚未用本轮验证器产生完整证据；Windows PowerShell 逻辑尚未在 Windows runner 执行。两项必须在后续打包轮通过。可视交互和导入到导出仍属于 P1-TEST-001b。

## Loop P1-SCI-003

### 发现、决策与失败测试

- 当前行为：两策略 PSA 的旧汇总字段用 `INMB >= 0` 统计干预成本效果概率，而同一结果的决策不确定性表用正、负和零分类，将零值单独报告为并列。
- 目标行为：正值归干预、负值归对照、零值只归并列；保留旧字段结构，不改变阈值、公式、抽样或随机数列。
- Human-in-the-loop：该口径可影响极少数精确零 INMB 样本的旧结果，已在 2026-07-31 获得研究者同意后实施。
- 失败测试：两个策略的转移、成本和效用完全一致，固定四次模拟均产生 `INMB = 0`。修复前旧汇总错报 1.0，而并列明细正确为 1.0。

### 根因、最小修复与验收

- 根因：`_run_psa` 的累计边界使用了非严格比较，与 `_decision_uncertainty` 的三分类口径不一致。
- 修改文件：`python/heor_core/src/heor_core/uncertainty.py` 只将 `>= 0` 改为 `> 0`；`python/heor_core/tests/test_model.py` 新增人工可核算的精确并列固定案例。
- 验收标准：固定案例的干预概率为 0、对照概率为 0、并列概率为 1；收敛检查点与最终汇总一致；现有黄金案例和所有 HEOR 合同不回归。
- 验收结果：达到。`test_model` 70/70、HEOR 完整回归 178/178、跨产物合同 113/113、类型检查、lint 和生产构建均通过。
- 回滚方式：回退本 loop 的独立提交；无数据迁移，不改变研究产物格式。
- 剩余风险：旧项目如果恰好含有精确零 INMB 样本，重算后该旧汇总字段可能降低；明细样本、并列概率和其他数值不变。

## Loop P2-SEC-004

### 发现与实际可达性

- 当前依赖：`pptx-preview 1.0.7 -> echarts 5.6.0`，生产构建包含 PPTX 预览和 ECharts 代码。
- 官方条件：[GHSA-fgmj-fm8m-jvvx](https://github.com/advisories/GHSA-fgmj-fm8m-jvvx) 只在 ECharts 6.1.0 之前同时使用 `lines` 系列、默认 tooltip，且 `series.data[i].name` 可控时可把未转义 HTML 送入 tooltip。
- 本地路径：`FilePreviewInspector -> PptxView -> pptx-preview -> ECharts.setOption`。已安装的 PPTX 适配器只识别 OOXML 折线、面积、柱状和饼图入口，并只构造 ECharts `line`、`bar` 和 `pie` 类型；不存在 `lines` 类型或由 PPTX 文本动态指定系列类型的路径。
- 结论：版本命中成立，但当前不可信 PPTX 无法满足该通告的必要触发条件，未复现可达 XSS。

### 最小处置、验收与剩余风险

- 处置：不强制将 `pptx-preview` 的 `echarts ^5.5.1` 跨主版本替换为 6.1.0，不改动 PPTX 预览功能。在 `scripts/dev/test_js_security_policy.py` 新增失效关闭门禁：锁定的 PPTX 适配器必须明确只构造 `line` / `bar` / `pie`，不得出现 `lines`。
- 验收标准：安全门禁在当前锁文件通过；任何后续 `pptx-preview` 变化或新增 `lines` 类型必须阻断构建并重新复核；生产构建和现有预览测试不回归。
- 验收结果：安全门禁 3/3、PPTX 正常化与文件预览 17/17、发布合同 43/43 通过；类型检查、lint 和生产构建通过。
- 回滚方式：回退本 loop 的测试与记录提交；本轮无业务代码、依赖或数据变更。
- 剩余风险：ECharts 中仍包含受影响实现；若平台未来新增直接 ECharts 配置、可控 tooltip formatter 或 `lines` 系列，必须升级至已修复版本或建立等效隔离，不得仅删除门禁。

## Loop P1-SCI-001 调查与待确认边界

### 现状与根因

- 用户可从本地知识库学到“决策树适用于短期、一次性事件、路径清楚”，`heor-model-design` 也可以在概念层提出决策树。
- 可执行层不存在 `decision_tree` 模块、版本化输入、结果、黄金案例或 Skill。`heor_core.cli` 在没有附加计算参数时会直接进入 `MarkovSpecification`，因此不能把决策树 JSON 当作另一种方法执行。
- 产物验证、本地 Human-in-the-loop 复核、报告和复现包只识别已有状态转移、分区生存和相关不确定性结果。所以缺口是端到端科学能力，不是 UI 遗漏。

### 建议的首版最小科学合同

1. 使用独立、版本化、哈希绑定的 `heor/decision-tree-plan.json`，不伪装成 Markov，不修改既有 Markov/PSM 格式。
2. 支持 2–16 个显式排序策略；每个策略以一个根节点开始，只允许有限无环的概率节点与终末节点。
3. 每个概率节点的分支概率必须为有限的 `[0, 1]` 数并在 `1e-9` 绝对误差内和为 1；拒绝循环、不可达节点、多父节点和非有限数值。
4. 首版终末节点只保存该路径的每人总成本与总 QALY；总成本必须为有限非负数，在一年边界内总 QALY 必须为有限的 `[-1, 1]` 数。不在边、中间节点和终末节点重复累加，避免静默双计。
5. 首版限定为 `0 < time_horizon_years <= 1` 的短期、一次性路径，要求成本和结果折现率均为 0，拒绝半周期校正、复发、时间依赖和长期外推；这些问题路由至状态转移或其他合适方法。
6. 输出每个策略的逐节点计算轨迹、期望成本、期望 QALY 和 NMB，并复用既有经验证的两两增量结果、完全增量前沿和阈值下最优策略逻辑。
7. 每个分支概率、终末成本和 QALY 必须声明非空来源或 `proposed` 假设 ID；便携验证先拒绝无来源数值，后续再以单独 loop 连接现有证据综合、双人复核与输入溯源账本。
8. 首版只做确定性计算。DSA/PSA 必须在确定性合同通过后用独立版本化产物扩展，不把未确认的分布默认加入首版。

### 人工可核算黄金案例与验收

- 对照：成功概率 0.60，成功路径成本 1000、QALY 0.80，失败路径成本 3000、QALY 0.50；期望成本 `1800`，期望 QALY `0.68`。
- 干预：成功概率 0.75，成功路径成本 2200、QALY 0.85，失败路径成本 5000、QALY 0.40；期望成本 `2900`，期望 QALY `0.7375`。
- 增量：成本 `1100`，QALY `0.0575`，ICER `19130.434782608696`；在 50000/每 QALY 阈值下 INMB `1775`。
- 误差：逐节点概率和质量守恒用绝对误差 `1e-9`；成本、QALY、ICER 和 NMB 使用 `rel_tol=1e-12, abs_tol=1e-9`。
- 完整验收还必须覆盖：输入不可变、策略顺序、重复/缺失节点、概率越界与不归一、循环、溢出、NaN/Infinity、负成本、QALY 越界、零增量效果的 ICER 表达、哈希绑定、CLI 重放和既有 Markov/PSM 回归。

### 预计修改与回滚

- 第一个实现 loop 预计只新增 `python/heor_core/src/heor_core/decision_tree.py`、`python/heor_core/tests/test_decision_tree.py`、`python/heor_core/golden_cases/two_strategy_decision_tree.json`，并最小扩展 `cli.py` 和 `__init__.py`。
- Skill、便携验证器、输入溯源、本地 Human-in-the-loop、报告、复现包和 UI 集成将在确定性内核有独立黄金证据后逐个闭环，不用一个巨大提交混合审查。
- 回滚时只回退对应 loop 的新文件和 CLI 分支；不迁移、重写或改释既有 Markov/PSM 项目。

# AI4HEOR 工程基线与闭环记录（2026-07-31）

## 基线

- 分支：`codex/heor-workbench`
- P1-AI-001b2 开始前的已提交基线：`38babd9`；P1-AI-001b3 实施前的已提交基线：`bc71b1b`；P1-TEST-001b1 实施前的已提交基线：`38a5687`；P1-TEST-001b2 实施前的已提交基线：`076180f`；P1-TEST-001b3 实施前的已提交基线：`14254f8`；P1-TEST-001b4 实施前的已提交基线：`1cf99a8`；P1-TEST-001b5 实施前的已提交基线：`6f48f57`；P1-TEST-001b6 实施前的已提交基线：`93912be`；P1-TEST-001b7 实施前的已提交基线：`7e26b0d`；P1-TEST-001b8 调查前的已提交基线：`27802d4`；P1-TEST-001b9 安装包验证基线：`b480c26`；P1-TEST-001b10 供应商失败恢复实施前基线：`d275c0a`；P1-TEST-001b11 导入—执行—导出验收实施前基线：`ab3b2d5`；P1-AI-001c 研究者可见审计实施前基线：`85fa920`；P1-AI-001d 精确对话定位实施前基线：`5040b1f`；P1-QUEUE-001 队列竞态实施前基线：`5c0a6ac`；P1-SCI-001a 决策树 Skill 与任务执行实施前基线：`68a9076`；P1-SCI-001b 专用桌面复核实施前基线：`499f968`；P1-SEC-002b OOM 通告修复实施前基线：`04b2142`。更早已完成业务修复均保留为独立提交，本轮不重复修改。
- 基线原则：在现有 Open Science/Tauri 技术栈上增量推进；AI 负责辅助推理，正式研究计算由可验证的确定性模块完成；科学、隐私、兼容性和公开接口决策保留 Human-in-the-loop。
- 已完成 loop 范围：不可信 HTML 预览边界、同主版本 JavaScript CPU 拒绝服务补丁、安装后 OpenCode 的鉴权 HTTP 就绪证据、安装后前端 bootstrap 证据合同、经研究者确认的两策略 PSA 零 INMB 并列口径、PPTX 预览中 ECharts `lines` 系列通告的不可达性门禁、经研究者确认后实现的首版短期确定性决策树内核、决策树第一方 Skill、自然语言任务执行路径和按精确输入字节绑定的专用桌面复核、不含对话正文的模型调用用量/费用元数据账本、应用固定 HEOR 前导提示的精确指纹和回复语言记录、模型调用与工具产物/运行的准确关联、研究者可见调用详情、从审计记录返回精确助手/工具动作的对话定位，以及 OpenCode 双重空闲事件导致的排队竞态。决策树 DSA/PSA、报告和复现包仍未连接。

## 当前架构与完成度

| 层 | 当前实现 | 本轮状态 |
| --- | --- | --- |
| 桌面与前端 | Tauri 2 + React/TypeScript/Vite | 保持原架构；HTML 预览安全边界已修复 |
| AI 调用与任务执行 | OpenCode 本地 sidecar，HTTP/SSE，模型提供商可配置 | 使用固定上游源码、补丁与 Bun 构建 `1.17.13-ai4heor.2`；主模型请求在插件完成 system 转换后、供应商调用前，将精确有序系统块的内容无关 SHA-256 与块数绑定到对应助手消息；完成调用的提供商、模型、时间、token、缓存 token、结束原因和运行时报告费用已归一化；新的 HEOR 调用记录固定前导提示的精确 SHA-256 与回复语言；sidecar 每次启动都校验并额外加载应用自有产品 Harness，项目原有指令文件不被覆盖；“始终允许”以当前项目、动作和精确资源落盘，可在隐私设置中撤销 |
| HEOR 确定性计算 | Python 版本化计算模块 + Rust 授权、审计和哈希绑定 | 独立决策树 schema 0.1.0、CLI 重放、第一方 `$heor-decision-tree`、原子结果写入和启动资源门禁已连接；既有 Markov/PSM 公式、参数和随机数列不变 |
| 数据与溯源 | 本地 JSON/JSONL/SQLite、证据与参数来源、运行记录和报告导出 | 工作区内 `.openscience/model-calls.jsonl` 保存内容无关、追加式、哈希链调用账本；新的模型工具产物和本地运行记录以可选 `assistantMessageId` 精确连接对应调用，并以 `toolCallId` 区分具体工具动作；产物溯源与运行记录可展开本地校验后的调用详情并返回对应对话工具行，不显示原始 ID、哈希或提示/回答正文；旧记录和非模型运行不伪造关联 |
| Human-in-the-loop | 关键科学定义、证据采用、结构与发布决策由研究者确认 | PSA 并列口径在研究者同意后才实施 |
| 文件预览 | React inspector + Tauri loopback preview server | HTML 改为被动展示；源码查看和外部打开保留 |

当前仓库已有主要单元/组件、确定性 HEOR、Rust 原生与资源门禁测试。macOS 与 Windows 发布脚本已有真实主机级安装、进程、工作区和清理检查，并已补上 OpenCode 鉴权 HTTP 与前端 bootstrap 合同。测试专用 macOS WebDriver 变体已在真实 Tauri/WKWebView 中完成基础导航、被动 HTML 预览、项目/独立任务作用域、队列、Human 问题、权限、provider 失败恢复，以及真实项目导入—项目内任务执行—确定性 DOCX/PDF/XLSX 报告导出验证；安装包完整任务 UI 仍未建立自动化 E2E，且调试构建证据不能替代安装包字节的原生验收。

## 问题与风险清单

| 编号 | 优先级 | 状态 | 证据与影响 |
| --- | --- | --- | --- |
| P0-SEC-001 | P0 | 本轮已修复 | `FilePreviewInspector` 原先向不可信 HTML 授予 `allow-scripts`，本地预览响应无 CSP，可能导致脚本执行和研究数据外发 |
| P0-AI-002 | P0 | 已修复 | 导入项目原有 `AGENTS.md` 会被 OpenCode 作为项目级系统指令加载，而旧实现只在缺文件时复制产品 Harness，导致产品科研与数据边界可能整体缺席；现保留用户文件并在每次 sidecar 启动时 fail-closed 校验、额外加载应用自有 Harness |
| P1-SEC-002a | P1 | 已修复 | `brace-expansion 1.1.15 / 2.1.1` 受 CPU 拒绝服务通告影响；已同主版本升级并加入发布门禁 |
| P1-SEC-002b | P1 | 已修复 | `brace-expansion` OOM 通告更新后已为三条受影响维护线提供补丁；锁文件固定为 1.1.18、2.1.4、5.0.9，并以语义版本门禁阻止重新引入受影响范围；生产审计高危项已归零 |
| P1-TEST-001a | P1 | macOS x64 原生执行通过；Windows 待执行 | 安装包首启过去只证明 OpenCode 进程存在；现要求未授权健康请求返回 401，且证据不保存端口或密码 |
| P1-TEST-001b | P1 | 调试构建主要交互分支及导入—执行—导出已完成；安装包内 A1 权限已验证；安装后完整 UI 待后续 loop | 测试专用 macOS Tauri WebDriver 已验证 IPC 桥接、真实侧边栏/文件操作、HTML 安全边界、任务作用域隔离、队列排序/删除/逐条发送、OpenCode `question` 回答恢复、provider 400 失败恢复、危险 bash 命令的一次授权/拒绝，以及项目原生导入、受管副本内项目任务执行、确定性 DOCX/PDF/XLSX 报告导出与当前性审计；外部源目录保持不变。当前 DMG 另已验证精确权限的保存、重启复用、撤销和重新询问。安装包完整任务 UI 仍缺自动化 E2E |
| P1-PERM-001 | P1 | 已按研究者确认的方案 A 修复 | “始终允许”现将当前项目、动作和精确资源写入本地 SQLite；同项目同资源在应用重启后复用，不同项目或资源仍询问；研究者可在隐私设置查看并撤销，撤销后重新询问；项目 ID 迁移同步迁移权限记录 |
| P1-TEST-001c | P1 | macOS x64 原生执行通过；Windows 待执行 | 安装包首启过去没有证明 WebView 已挂载 AppShell、执行 JavaScript 并通过 Tauri IPC 取得本地服务地址；现从隔离首启的应用私有日志生成无正文、无端口的布尔证据 |
| P1-TEST-002 | P1 | 已修复 | Tauri 的资源复制只覆盖源文件，不删除复用 profile 目录中的额外文件；构建入口现先触发一次受限的 Cargo 重建，由 build script 只删除可再生成的 `skills-admitted-ai4s` 暂存树再交给 Tauri 复制，原生 E2E 同时对准入资产部署错误日志 fail-closed |
| P1-SCI-001 | P1 | 内核、Skill、自然语言任务执行与专用桌面复核已完成；报告和复现包待后续 loop | 已有独立 schema、黄金案例、来源/假设声明、逐节点计算轨迹、增量前沿、CLI 哈希重放、第一方 `$heor-decision-tree`、独立计划/结果路径、多语言目录、完整 53-Skill 启动准入和真实 Tauri 资源部署；桌面仅在 `input_sha256` 与当前计划原始字节一致时展示数值。DSA/PSA、报告与复现包未由本轮冒充完成 |
| P1-SCI-002 | P1 | 待单独处理 | 亚组分析尚缺完整的预设、来源绑定、逐亚组结果与复核合同 |
| P1-SCI-003 | P1 | 已修复 | 两策略 PSA 旧汇总使用 `INMB >= 0`，将零值并列同时计入干预成本效果概率，与同一输出中单独报告并列的决策不确定性表冲突 |
| P1-AI-001a | P1 | 本轮已修复 | OpenCode 已返回提供商、模型、时间、token、缓存 token、结束原因和运行时报告费用，但 AI4HEOR 原先丢弃；现已建立内容无关、幂等、哈希链本地账本 |
| P1-AI-001b1 | P1 | 本轮已修复 | 新的 HEOR 调用现在记录应用固定前导提示的精确 SHA-256、模板 ID 和回复语言；研究者文本及其哈希都不进入账本 |
| P1-AI-001b2 | P1 | 已修复并通过 macOS x64 安装包验证 | 研究者已同意方案 A 和本地派生数据边界；固定 OpenCode 1.17.13 源码的最小补丁在供应商请求前把插件处理后的最终系统块指纹写入准确助手消息；当前 DMG 已完成实际 provider 请求、持久化助手消息和重算指纹的三方一致性校验 |
| P1-AI-001b3 | P1 | 已修复 | OpenCode 工具事件现在保留准确助手消息与工具调用 ID；直接产物、本地运行及其输出原样持久化可选关联键，不按时间猜测或回填历史 |
| P1-AI-001c | P1 | 已修复 | 产物溯源与运行记录现可按准确关联键读取并展示本地校验后的模型调用详情；缺失关联不猜测、损坏账本明确报错，且不展示原始 ID、哈希或提示/回答正文 |
| P1-AI-001d | P1 | 已修复 | 运行记录与产物溯源使用已有准确 `assistantMessageId + toolCallId` 进入对应任务、展开折叠工具组并定位到精确工具行；实时与恢复历史使用同一索引，缺失锚点明确失败，不按时间或最近回复猜测 |
| P1-QUEUE-001 | P1 | 已修复 | 固定 OpenCode 对同一次 runner 结束依次发布 `session.status(idle)` 与 `session.idle`；SDK 原先把两者都转换成终止信号，旧重复信号可错误解除下一轮排队任务的运行锁。现只转发专用 `session.idle`，保留 busy/retry 状态；失败测试、真实原生队列和全量回归通过 |
| P1-LEGAL-001 | P1 | 已修复 | `brace-expansion` 锁文件升级后，打包的 npm 许可证清单仍绑定旧锁文件哈希和旧版本；现已从当前锁文件重生成并通过资源合同 |
| P2-SEC-003 | P2 | 待评估 | Tauri 主应用全局 CSP 仍为空；本轮已在不可信 HTML 的两个实际渲染入口建立独立限制。全局 CSP 会影响 loopback、SSE 和资源加载，需另行做兼容性测试 |
| P2-SEC-004 | P2 | 已评估；当前不可达 | ECharts 5.6.0 命中 `GHSA-fgmj-fm8m-jvvx`，但通告需要 `lines` 系列；当前 `pptx-preview` 只从导入文件构造 `line` / `bar` / `pie`，已用发布门禁防止未复审的可达性变化 |

## 优化任务列表

1. P0-SEC-001：完成 HTML 被动预览边界并建立回归合同（已完成）。
2. P1-TEST-001a：首启 OpenCode 鉴权 HTTP 就绪合同已在新 macOS x64 DMG 原生执行通过；Windows 仍需在原生 runner 产生证据。
3. P1-TEST-001b：调试构建的基础导航、被动 HTML、项目/独立任务作用域、消息队列、Human 问题恢复、provider 失败恢复、危险命令一次授权/拒绝，以及项目导入—项目内任务—确定性报告导出 E2E 已完成；当前安装包也已验证“始终允许”的精确作用域、重启复用、撤销和重新询问。后续只补安装包完整任务 UI，不用一个过大 E2E 隐藏失败点。
4. P1-PERM-001：方案 A 已完成并独立验证；项目级精确规则持久化、重启复用、跨项目/跨资源隔离、研究者可见撤销、撤销后重新询问和项目 ID 迁移均纳入回归。
5. P1-TEST-001c：安装后前端 bootstrap 合同已在新 macOS x64 DMG 原生执行通过；Windows 待执行，且不得据此宣称完整可视 E2E 已完成。
6. P1-TEST-002：调试构建资源目录确定性重建及原生 E2E 部署错误门禁已完成；构建仅清理可再生成的准入 Skill 暂存树，不触及源码、用户数据或安装应用。
7. P1-SEC-002：CPU 与 OOM 型 `brace-expansion` 通告均已在兼容维护线上修复，并用发布门禁阻止回退；UUID 与 React Router 通告继续按实际可达路径分别处置，不强制整树升级。ECharts `lines` 系列通告已证明当前 PPTX 路径不可达。
8. P1-SCI-003：统一两策略 PSA 的零 INMB 并列口径（已完成）。
9. P1-SCI-001：首版确定性内核、第一方 Skill、自然语言任务执行和专用桌面复核已完成；后续分别为报告与复现包建立独立合同。P1-SCI-002 仍需先建立人工可核算基准，禁止与界面修复混做。
10. P0-AI-002：产品 Harness 已改为每次运行必定校验和叠加加载，用户/项目指令保留但不得替代产品治理边界（已完成）。
11. P1-AI-001a、P1-AI-001b1、P1-AI-001b2、P1-AI-001b3、P1-AI-001c 和 P1-AI-001d：内容无关模型调用账本、固定 HEOR 前导提示指纹、当次实际最终系统块指纹、模型调用到具体工具产物/运行的准确关联、研究者可见详情及精确对话动作定位均已完成；不按时间猜测，也不把内部标识放入 URL。
12. P1-QUEUE-001：独立失败测试已复现并关闭双重空闲事件竞态；没有延长超时、自动重试或修改队列内容（已完成）。
13. P2-SEC-003：评估主应用全局 CSP；仅在不破坏本地服务和模型流式连接时实施。
14. P1-LEGAL-001：依赖锁文件变更后必须重生成许可证清单，其锁文件 SHA-256 不一致时由现有打包资源合同 fail-closed（已完成）。

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
| OOM DoS 修复前复现 | `python3 -B -m unittest scripts.dev.test_js_security_policy -v` | 失败：锁文件仍含 1.1.16、2.1.2、5.0.7，且缺少三条受影响范围的维护线 override |
| JS 依赖安全门禁 | `python3 -B -m unittest scripts.dev.test_js_security_policy -v` | 3/3 通过；语义版本门禁覆盖当前 OOM 受影响范围 |
| CPU DoS 通告复审 | `pnpm audit --prod --json` | `GHSA-3jxr-9vmj-r5cp` 由 2 条降为 0 条；其他通告未隐藏 |
| OOM DoS 通告复审 | `pnpm audit --prod --json` | `GHSA-mh99-v99m-4gvg` 为 0 条，高危项为 0；其余 6 个中危通告继续显式保留 |
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
| 决策树修复前复现 | 定向运行新增黄金案例测试 | 失败：`heor_core.decision_tree` 不存在，CLI 只能按 Markov 解析 |
| 决策树定向回归 | `python -B -m unittest python/heor_core/tests/test_decision_tree.py -v` | 10/10 通过；包括人工核算、拓扑、来源、fail-closed 字段、零增量效果和 CLI 哈希重放 |
| HEOR 完整回归（决策树后） | `pnpm test:heor` | 188/188 通过 |
| 决策树打包资源合同 | `test_every_python_module_is_bundled_once_at_the_expected_path` + `preflight_resources.mjs` | 通过；40 个来源、441 个文件 |
| 许可证清单漂移复现 | `test_legal_boundary_and_inventories_are_packaged` | 失败：npm 清单哈希 `f3fe...` 与当前锁文件 `c44a...` 不一致 |
| 许可证与资源回归 | `test_tauri_heor_resources.py -v` + `test_js_security_policy.py -v` + `preflight_resources.mjs` | 10/10、3/3 与 40 来源/441 文件通过 |
| 前端 bootstrap 修复前复现 | 4 项定向发布契约测试 | 3 项失败、1 项错误：缺少日志解析器、发布证据字段、macOS CI 检查和 Windows 检查 |
| 前端 bootstrap 定向回归 | 同一组 4 项定向发布契约测试 | 4/4 通过 |
| 发布层完整回归（bootstrap 后） | `python3 -m unittest discover -s scripts/release -p 'test_*.py' -v` | 44/44 通过 |
| 前端完整回归（bootstrap 后） | `pnpm test` | 112 个文件、762 项通过；既有 React `act(...)` 与 Router 告警未新增、未屏蔽 |
| 静态与构建回归（bootstrap 后） | `pnpm typecheck`、`pnpm lint`、`pnpm build`、`pnpm preflight:resources` | 全部通过；40 个来源、441 个文件 |
| 模型调用账本修复前复现 | SDK 定向集成测试 + `cargo test ... model_calls::tests` | SDK 缺少 `message.usage` 事件；新增 3 项 Rust 账本测试全部失败 |
| 模型调用 SDK/桥接定向回归 | `vitest run src/lib/modelCalls.test.ts src/test/opencode-client.node.test.ts` | 20/20 通过；进行中消息不产生完成事件，历史与实时元数据一致，桥接只传白名单字段 |
| 模型调用账本定向回归 | `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml model_calls::tests` | 3/3 通过；覆盖幂等、冲突、非法时间/费用、损坏链和符号链接 |
| 模型调用账本后完整前端回归 | `pnpm test` | 113 个文件、764 项通过；既有 React `act(...)` 与 Router 告警未新增、未屏蔽 |
| 模型调用账本后完整 Rust 回归 | `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml` | 371 项通过、1 项既有公网测试忽略 |
| 模型调用账本后发布与构建回归 | 发布测试、类型检查、ESLint、Rust 格式、生产构建、资源预检 | 发布 44/44；其余全部通过；40 个来源、441 个文件 |
| 提示模板指纹修复前复现 | `heor.test.ts` + `modelCalls.test.ts` + `model_calls::tests` | 失败：无固定模板上下文解析器，TypeScript 桥接忽略上下文，Rust 严格 schema 拒绝新字段 |
| 提示模板指纹定向回归 | `vitest run src/lib/heor.test.ts src/lib/modelCalls.test.ts` + `runtime.store.test.ts` + `cargo test ... model_calls::tests` | 33/33、87/87 与 4/4 通过；覆盖实时调用、历史回放、七种界面语言、旧记录兼容、新会话发送失败清理、非 HEOR 文本不误标及研究者文本不进入上下文 |
| 提示模板指纹后全量回归 | `pnpm test` + `cargo test` + `pnpm test:heor` + 发布测试、类型检查、ESLint、Rust 格式、生产构建、资源预检 | 前端 768/768；Rust 372 通过/1 项既有公网测试忽略；HEOR 188/188；发布 44/44；其余全部通过；40 来源/441 文件 |
| 产品 Harness 修复前复现 | `cargo test ... opencode_config::tests` + `python3 scripts/dev/test_heor_harness.py -v` | Rust 缺少临时配置合并函数而编译失败；Harness 合同 5 处失败，精确指向缺少项目指令边界、机器策略字段和运行时注入 |
| 产品 Harness 定向回归 | `cargo test ... opencode_config::tests` + `cargo test ... harness::tests` + `test_heor_harness.py -v` | 9/9、7/7、16/16 通过；覆盖原有项目文件保留、临时配置保留/去重/顺序、非法继承配置拒绝、整树内容指纹漂移与链接拒绝 |
| 产品 Harness 后全量回归 | 前端、Rust、开发合同、HEOR、发布合同、类型、ESLint、格式、构建、资源预检 | 前端 768/768；Rust 376 通过/1 项既有公网测试忽略；开发合同 376/376；HEOR 188/188；发布 44/44；其余全部通过；40 来源/441 文件 |
| 最终系统上下文修复前复现 | SDK/Rust 定向测试与补丁发布合同 | 新字段加入实现前，Vitest 3 项失败、Rust 5 处编译失败，发布合同因仍下载官方二进制且缺少补丁清单而失败；补充块数上限合同后又准确出现 1 项失败 |
| 固定 OpenCode 补丁与实际 sidecar | `python3 scripts/dev/test_patched_opencode.py -v` + 固定 Bun 1.3.14 执行 `build-opencode.sh` | 补丁合同 4/4；固定源码与补丁哈希校验通过；上游 19/19、上游类型检查、x64 构建和 `1.17.13-ai4heor.1` 版本冒烟通过；只接受 1–1024 个系统块 |
| 系统上下文 SDK/账本定向回归 | `vitest run src/lib/modelCalls.test.ts src/test/opencode-client.node.test.ts` + `cargo test ... model_calls::tests` | 21/21 与 4/4 通过；只转发合同、SHA-256 和块数，旧消息/旧账本仍可读，非法或不完整上下文拒绝 |
| 系统上下文全量回归 | 前端、Rust、HEOR、开发合同、发布合同、类型、ESLint、Rust 格式、生产构建、资源预检 | 前端 113 个文件、768/768；Rust 376 通过/1 项既有忽略；HEOR 188/188；本轮相关开发合同 234 项、发布合同 33 项通过；其余全部通过；41 个来源/445 个文件 |
| 被动 HTML 原生 E2E 修复前复现 | `python3 scripts/dev/test_desktop_e2e_contract.py -v` | 先后因缺少 `untrusted-e2e.html`、稳定文件元素等待和本地请求观察器而按预期失败 |
| 被动 HTML 原生 E2E 定向稳定性 | `python3 scripts/e2e/verify_desktop_webdriver.py` 连续执行 | 3/3 通过；真实 WKWebView 完成任务文件选择、HTML iframe 加载、响应头检查且未请求测试脚本 |
| 被动 HTML 原生 E2E 完整命令 | `pnpm test:e2e:desktop` | 通过；包含前端构建、41 来源/445 文件资源预检、Rust 测试变体构建、Tauri 桥接、导航、任务文件和被动 HTML 预览 |
| 被动 HTML loop 全量回归 | 前端、Rust、HEOR、开发合同、发布合同、类型、ESLint、Rust 格式、资源预检及定向预览测试 | 前端 113 文件/770 项、Rust 377 通过/1 项既有忽略、HEOR 188/188、开发合同 386/386、发布合同 46/46；类型、lint、格式、资源预检、前端 10/10 和 Rust 7/7 预览测试通过 |
| 独立任务原生 E2E 修复前复现 | `python3 -B scripts/dev/test_desktop_e2e_contract.py -v` + 直接原生驱动 | 先后准确失败于缺少本地模型夹具、主请求与标题辅助请求无法区分、默认模型首次初始化不稳定，以及输入框节点/受控状态尚未同步即点击发送 |
| 独立任务原生 E2E 定向稳定性 | `python3 -B scripts/e2e/verify_desktop_webdriver.py` 连续执行 | 最终 3/3 通过；真实创建项目和独立任务，显示本地夹具回复，验证任务目录为 `session`、项目目录为 `heor`，且任务不在任何项目 DOM 下 |
| 独立任务原生 E2E 完整命令 | `pnpm test:e2e:desktop` | 通过；从项目入口重建测试特性二进制，完成 41 来源/445 文件预检、真实模型回合、作用域隔离、任务文件和被动 HTML 预览 |
| 独立任务 loop 全量回归 | 前端、Rust、HEOR、开发合同、发布合同、类型、ESLint、Rust 格式和资源预检 | 前端 113 文件/770 项、Rust 377 通过/1 项既有忽略及资源暂存 2/2、HEOR 188/188、开发合同 390/390、发布合同 47/47；其余全部通过 |
| 调试资源污染修复前复现 | 向 `target/debug/skills-admitted-ai4s/integrity-auditor` 加入忽略的 Python 字节码后运行既有原生 E2E | 运行时记录 `failed to deploy admitted asset ... content hash mismatch`，但旧 E2E 仍报告通过且污染文件保留 |
| 调试资源确定性重建 | 修改后的 `pnpm test:e2e:desktop`，并比较源码与重建暂存树 | 原生 E2E 通过；污染文件被清除，两个 `integrity-auditor` 树哈希均为 `db4d137dd69ec7295aa6517238ae1f6817abc051395d0708d5283c687a1d5bb4`，暂存树 Python 缓存数为 0 |
| 暂存重建定向回归 | `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --test resource_staging` + E2E/资源触发器合同 | Rust 2/2、桌面 E2E 合同 8/8、资源触发器合同 6/6 通过；连续普通 Cargo 构建第二次为 `Fresh`，无自触发重建循环 |
| “始终允许”修复前复现 | 真实 macOS Tauri/WKWebView + SQLite 检查 | 同一 sidecar 进程会记住完全相同命令，但 `opencode.db.permission` 为空；应用重启后再次询问，证明旧实现只有进程内记忆 |
| “始终允许”定向回归 | 固定 OpenCode 权限/项目测试 + SDK/UI 测试 + 原生桌面 E2E | OpenCode 112/112 及类型检查通过；覆盖重启式实例重载、精确资源、项目隔离、拒绝优先、撤销和项目 ID 迁移；真实桌面完成一次允许、拒绝、始终允许、应用重启自动复用、设置中撤销及撤销后重新询问 |
| “始终允许”全量回归 | 前端、Rust、HEOR、开发/发布合同、类型、ESLint、Rust 格式、生产构建和资源预检 | 前端 114 文件/775 项；Rust 377 通过/1 项既有忽略及资源暂存 2/2；HEOR 188/188；补丁 4/4、桌面 E2E 合同 11/11、包内夹具 6/6、macOS 发布合同 16/16；41 来源/445 文件预检通过 |
| 安装包内“始终允许”持久化 | `verify_packaged_opencode_fixture.py` + 发布证据 `opencode-permission-persistence` 检查 | 旧 OpenCode `.1` DMG 在保存权限接口处失败；新 `.2` DMG 完成精确记录校验、同一隔离配置重启后免询问复用、撤销、规则消失、重新询问与拒绝后哨兵不变；夹具 8/8、macOS 发布合同 16/16 |
| 系统上下文安装包执行门禁 | `verify_packaged_opencode_fixture.py` + macOS 构建工作流 | 单元合同 2/2 与 CI 接线合同通过；当前 1.0.0 x64 DMG 实际执行通过：2 次本地 provider 请求、主请求流式响应、回复标记命中，实际 system 块与对应助手消息的 `ai4heor.system-context/v1` 指纹一致 |
| 当前 macOS x64 DMG | `tauri build --target x86_64-apple-darwin --bundles dmg` + `verify_macos_package.py --verify-first-launch` + `verify_packaged_opencode_fixture.py` | 由干净提交 `b480c26` 构建；96,470,656 字节，SHA-256 `746332065bf3cbdee0b3f507affb6a67dea39c095f9c074b2189679ab9661673`；445 个资源逐字节一致，包内 HEOR 188/188，OpenCode `1.17.13-ai4heor.2`，隔离首启、HTTP 401、AppShell/JavaScript/Tauri IPC、工作区隔离、系统上下文审计，以及精确权限的重启复用、撤销和重新询问通过；发布证据已在同一干净提交上生成并校验；无可用 Developer ID 签名，仅供内部测试 |
| 产物关联修复前复现 | SDK、provenance、run 定向测试及 Rust 定向编译 | 前端 7 项失败；Rust 10 处编译失败，准确证明工具事件、桥接和持久记录均缺少关联字段 |
| 产物关联定向回归 | `vitest run opencode-client.node.test.ts provenance.test.ts runs.test.ts` + `cargo test ... provenance::tests` + `cargo test ... runs::tests` | 前端 43/43、Rust 6/6 与 9/9 通过；覆盖直接写入、`apply_patch`、本地运行、运行输出、Tauri 参数、旧/远程记录兼容及异常标识拒绝 |
| 产物关联全量回归 | 前端、Rust、HEOR、开发合同、发布合同、类型、ESLint、Rust 格式、生产构建、资源预检 | 前端 113 个文件、770/770；Rust 377 通过/1 项既有忽略；HEOR 188/188；开发合同 380/380；发布合同 46/46；其余全部通过；41 个来源/445 个文件 |
| Provider 失败恢复修复前复现 | 本地确定性 provider 返回一次 HTTP 400 + 真实 Tauri/WKWebView 队列 | 错误可见且队列项被取出，但该用户消息只写入会话历史，provider 请求数不增加；绕过 UI 的隔离 sidecar 实验同样复现会话永久 `busy` |
| Provider 失败恢复根因验证 | 同一隔离 OpenCode 会话在错误后分别直接再次提交、执行 `abort` 后再次提交 | 直接提交不调用 provider；执行会话 `abort` 清理执行器后立即提交可正常调用 provider 并返回，证明不是提示词、队列内容或模型配置问题 |
| Provider 失败恢复原生验收 | `pnpm test:e2e:desktop` | 通过；错误保持可见，排队消息在错误前零发送，清理后恰好发出一次并完成，队列清空、停止按钮消失、输入框恢复；既有队列、Human、权限、任务文件和被动 HTML 流程同步通过 |
| Provider 失败恢复全量回归 | 前端、Rust、HEOR、开发/发布合同、类型、ESLint、Rust 格式、生产构建、diff 与资源预检 | 前端 114 文件/776 项；Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2；HEOR 188/188；开发合同 392/392；发布合同 54/54；41 来源/445 文件预检通过 |
| 导入—执行—导出修改前合同 | `python3 -m unittest scripts.dev.test_desktop_e2e_contract` | 失败：原生驱动缺少导入项目、源目录快照、项目内任务、报告导出与当前性审计的合同路径 |
| 导入—执行—导出定向回归 | `python3 -m unittest scripts.dev.test_desktop_e2e_contract scripts.dev.test_heor_acceptance_fixture` + `python3 -m py_compile scripts/e2e/verify_desktop_webdriver.py` | 16/16 通过；原生驱动语法检查通过 |
| 导入—执行—导出原生验收 | `python3 scripts/e2e/verify_desktop_webdriver.py` 连续执行 | 最终 2/2 通过；真实原生导入受管副本，项目内任务调用本地 provider，生成非空 DOCX/PDF/XLSX，导出审计为当前且外部源目录字节不变；一次较早运行出现既有队列第二条超时，随后复跑及最终两次通过，仍保留为间歇性风险 |
| 导入—执行—导出完整根命令 | `pnpm test:e2e:desktop` | 通过；重建前端与测试特性 Tauri 二进制，41 来源/445 文件资源预检通过，新增流程与既有队列、Human、权限、provider 恢复、任务文件和被动 HTML 预览同时通过 |
| 可见模型调用审计修复前复现 | `vitest run modelCalls.test.ts ModelCallAudit.test.tsx ProvenancePanel.test.tsx RunsPage.test.tsx` + 桌面 E2E 合同 | 失败：缺少原生账本读取桥接、可见详情组件，以及真实运行到调用记录的原生验收分支 |
| 可见模型调用审计定向回归 | 同一组 4 个前端测试 + `python3 -m unittest scripts.dev.test_desktop_e2e_contract` | 26/26 与 14/14 通过；精确关联、缺失不猜测、损坏显式报错，且不渲染原始消息/调用 ID 或哈希 |
| 可见模型调用审计原生验收 | `python3 scripts/e2e/verify_desktop_webdriver.py` | 通过；隔离任务执行无副作用 Python 运行，打开运行记录和模型调用记录，匹配精确 loopback provider/model，随后完整通过既有队列、Human、权限、恢复及导入导出流程 |
| 可见模型调用审计全量回归 | 前端、Rust、HEOR、开发/发布合同、类型、ESLint、生产构建与资源预检 | 前端 115 文件/781 项；Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2；HEOR 188/188；开发合同 394/394；发布合同 54/54；41 来源/445 文件预检通过 |
| 队列竞态修复前复现 | 固定 OpenCode 协议夹具依次发布 `session.status(idle)` 与 `session.idle`，运行 SDK 集成测试 | 失败：同一轮产生 2 个应用级 `session.idle`，可由旧重复信号解除下一轮运行锁 |
| 队列竞态定向回归 | SDK 与运行状态测试 + 原生桌面合同 | 108/108 与 15/15 通过；同一轮只产生一个终止信号，busy/retry 状态保持不变 |
| 队列竞态原生验收 | `pnpm test:e2e:desktop` | 真实 Tauri/WKWebView 通过队列排序、删除和逐条发送，并完成 provider 失败恢复、Human 输入、权限、任务文件、项目导入及确定性 DOCX/PDF/XLSX 导出 |
| 队列竞态全量回归 | 前端、HEOR、Rust、开发/发布合同、类型、ESLint、Rust 格式、生产构建、diff 与资源预检 | 前端 116 文件/791 项；HEOR 188/188；Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2；开发合同 395/395；发布合同 54/54；41 来源/445 文件预检通过 |
| 决策树 Skill 修复前复现 | 运行新增第一方 Skill 黄金案例合同 | 失败：`runtime/skills/core/heor-decision-tree/SKILL.md` 不存在 |
| 决策树任务执行修复前复现 | 第一方运行器执行 `heor/decision-tree-plan.json` | 失败：旧运行器把决策树交给 Markov 输入溯源合同，拒绝后不产生结果 |
| 决策树 Skill 与执行定向回归 | Skill Creator 校验、核心 Skill 合同、第一方运行器、HEOR 核心、Rust 启动审计 | Skill 合法；11/11、4/4、188/188 与 5/5 通过；黄金案例精确得到比较策略成本 1800、干预策略成本 2900，篡改结果被重放校验拒绝；仅剩 52 个第一方 Skill 时启动失败 |
| 决策树 Skill 全量回归 | 前端、HEOR、Rust、开发/发布合同、类型、ESLint、Rust 格式、生产构建、diff、资源预检与原生 E2E | 前端 791/791；HEOR 188/188；Rust 378 通过/1 项既有公网测试忽略及资源暂存 2/2；开发合同 397/397；发布合同 54/54；41 来源/450 文件；真实 Tauri/WKWebView 既有任务、队列、Human、权限、恢复、文件、导入与报告导出全部通过 |

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

## Loop P1-SEC-002b

### 发现、复现与根因

- 当前行为：上游于 2026-07-31 更新 [GHSA-mh99-v99m-4gvg](https://github.com/advisories/GHSA-mh99-v99m-4gvg) / CVE-2026-14257，明确受影响范围为 `<1.1.17`、`>=2.0.0 <2.1.3` 和 `>=4.0.0 <5.0.8`。当前锁文件中的 1.1.16、2.1.2、5.0.7 均命中，`pnpm audit --prod --json` 因生产依赖路径报告两个高危项。
- 依赖与可达性：生产路径仍为 `exceljs -> archiver/unzipper -> glob/readdir-glob -> minimatch -> brace-expansion`，5.x 来自开发工具链。Vite 桌面产物中没有 `brace-expansion`、`archiver-utils` 或 `readdir-glob` 标记，因此当前发布前端不可达；但构建依赖树和生产审计仍不应保留已有兼容补丁的高危版本。
- 失败测试：先把门禁改为按通告语义范围检查，修复前稳定报告三个受影响版本以及三条缺失的范围 override。根因是通告在 P1-SEC-002a 后补充了旧维护线修复范围，先前固定的 1.1.16、2.1.2 和 5.0.7 不再满足新边界，而非业务代码或 XLSX 处理逻辑变化。

### 最小修复与验收

- 最小修复：只将三条兼容维护线固定到 1.1.18、2.1.4、5.0.9，并重生成 pnpm 锁文件与其 SHA-256 绑定的 npm 许可证清单；安全门禁从拒绝几个旧精确版本改为拒绝通告定义的完整受影响范围。没有替换 `exceljs`、`minimatch` 或技术栈，也没有修改界面、研究数据、模型调用、HEOR 公式、默认参数或研究 schema。
- 验收结果：安全门禁 3/3、XLSX 3/3、前端 117 文件/794 项、HEOR 188/188、Rust 378 通过/1 项既有公网测试忽略及资源暂存 2/2、开发合同 397/397、发布合同 54/54；类型检查、ESLint、Rust 格式、生产构建、diff 和 41 来源/450 文件资源预检均通过。真实测试特性 Tauri/WKWebView E2E 继续通过任务、排队、Human 输入、权限、provider 失败恢复、文件、项目导入和确定性 DOCX/PDF/XLSX 导出。
- 审计结果：`GHSA-mh99-v99m-4gvg` 为 0 条，生产审计高危项为 0。`pnpm audit --prod` 仍因 6 个中危通告返回非零，本轮没有降低阈值、忽略或把它们伪装成已修复；UUID、React Router 等必须按各自可达路径继续独立评估。
- 回滚与边界：回退本 loop 的独立提交即可，无数据迁移或历史研究结果改写。新的许可证清单只反映当前锁文件，不改变各组件许可证。调试 E2E 不替代安装后 DMG 完整任务 UI 验收；本轮不生成安装包。Node 的 `DEP0169` 既有运行时告警也未在本安全 loop 中顺便处理。

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

### 实现 loop 结果

- Human-in-the-loop：研究者于 2026-07-31 确认上述首版科学边界后才开始业务实现。
- 修改前行为：定向黄金案例首次运行因 `ModuleNotFoundError: heor_core.decision_tree` 失败；未声明附加计算模式的 CLI 主输入只会进入 Markov 解析。
- 根因：概念层的决策树建议没有对应独立计算合同，也没有可重放内核和打包资源映射。
- 修改范围：新增 `decision_tree.py`、10 项定向测试和两策略黄金案例；最小扩展 `cli.py`、`__init__.py` 和 Tauri 资源清单。Markov、PSM、不确定性模块和桌面研究流程没有改动。
- 科学合同：仅接受 2–16 策略、不超过 1 年、零折现、无半周期校正的有限无环概率树；概率在 `1e-9` 内归一，每个数值必须指向来源或已声明的 `proposed` 假设。未知字段、复发、时间依赖、中间节点奖励、循环、多父节点与不可达节点均 fail-closed。
- 计算证据：黄金案例得到对照成本 `1800`、QALY `0.68`，干预成本 `2900`、QALY `0.7375`，增量成本 `1100`、增量 QALY `0.0575`、ICER `19130.434782608696`，阈值 50000 下 INMB `1775`；与人工核算一致。
- 输出与溯源：每个策略输出逐节点到达概率、终末贡献及其具体来源/假设 ID；CLI 输出绑定原始输入 SHA-256，并复用已验证的增量结果、完全增量前沿和阈值最优策略逻辑。
- 验证结果：定向 10/10、HEOR 188/188、前端 762/762、Rust 368 通过/1 项既有忽略，类型检查、ESLint、Rust 格式、生产构建、打包资源合同和 40 来源/441 文件资源预检通过。
- 回滚方式：回退本 loop 提交即可；无数据迁移，无现有 schema 或公式修改。
- 剩余风险：首版内核尚未进入桌面审查、证据账本、报告和复现包；不得在这些端到端合同完成前宣称用户已可从 UI 完成正式决策树研究。DSA/PSA 仍为明确未实现范围。

## Loop P1-LEGAL-001

- 当前行为与复现：运行完整 Tauri HEOR 资源合同时，许可证清单检查失败；`pnpm-lock.yaml` 当前 SHA-256 为 `c44ada400a37260ea0940a0df523f3bfe31e8c63ea70c0084369ca5f100a82af`，而已打包清单仍记录 `f3fe115adad991838f9e2d0c01000a2e4f41638c45d348695e1bc87968913e28`。
- 目标行为：对外分发的许可证清单必须与当前锁文件字节绑定，并准确记录已锁定的 `brace-expansion` 1.1.16 和 2.1.2。
- 根因：上一个依赖安全修复更新了锁文件，但遗漏运行仓库自带的许可证清单生成器。
- 最小修改：使用 `scripts/dev/generate_license_inventory.py` 从当前本地锁定依赖重生成 npm 清单；Cargo 组件和哈希未变，仅同步生成日期。
- 验收标准与结果：清单哈希等于当前锁文件，安全补丁版本准确，未解决许可证边界不变；资源合同 10/10、JavaScript 安全门禁 3/3 和资源预检通过。
- 回滚方式：回退本 loop 的两个生成清单；无业务代码、依赖锁文件或研究数据变更。
- 剩余风险：这是清单与锁文件的一致性证据，不替代对每个依赖条款的独立法务意见。

## Loop P1-TEST-001c

- 当前行为：现有安装包验证已证明应用进程、OpenCode 鉴权 HTTP 和工作区，但应用主进程即使没有成功挂载 AppShell、执行前端 JavaScript 或完成 `start_runtime` Tauri IPC，旧门禁仍可能通过。
- 目标行为：在隔离的首次启动环境中，必须同时出现 AppShell 调用 bootstrap 的起始记录和 Tauri IPC 返回 loopback 本地服务地址的就绪记录，才能生成发布证据。
- 根因：发布门禁只观察进程、HTTP 与文件系统，没有把现有前端启动链路的两条应用私有诊断记录纳入证据合同。
- 失败测试：修改前 4 项定向测试稳定出现 3 项失败和 1 项错误，分别对应缺少日志解析器、macOS 工作流声明、Windows 验证器实现与发布证据字段。
- 最小修改：macOS 和 Windows 验证器只读取新鲜隔离首启产生的 `debug.log` 尾部，要求固定格式的启动与就绪记录以及有效 loopback 端口；发布证据仅保存 `app_shell_mounted`、`javascript_executed`、`tauri_runtime_command_returned` 三个真值，不保存日志、端口或路径。应用业务代码、模型调用、科研计算与研究数据均未修改。
- 验收结果：定向 4/4、发布层 44/44、前端 762/762、类型检查、ESLint、生产构建和 40 来源/441 文件资源预检通过；`git diff --check` 在提交前执行。
- 回滚方式：回退本 loop 的发布脚本、工作流、契约测试和记录；无数据迁移、业务接口或研究产物变化。
- 剩余风险：本机没有 PowerShell，Windows 脚本只能由文本合同覆盖，仍需 Windows runner 原生执行；新 macOS DMG 尚未构建，因此也没有当前提交对应的安装后证据。该门禁只证明前端启动与 Tauri IPC，不证明窗口可见、任务操作、权限交互、HTML 预览或导入到导出；完整可视 E2E 仍是 P1-TEST-001b。

## Loop P1-AI-001a

- 当前行为：OpenCode 1.17.13 的完成助手消息已经提供消息/父消息、会话、提供商、模型、Agent、开始/完成时间、输入/输出/推理/缓存 token、结束原因和运行时报告费用；AI4HEOR 的 SDK 与桌面层原先只保留角色和消息 ID，这些调用审计信息被丢弃。
- 目标行为：只对字段完整且数值有效的完成调用生成标准事件；桌面工作区以追加式 JSONL 保存白名单元数据，实时 SSE 与任务历史均可补记，同一消息重复事件幂等，冲突和损坏历史 fail-closed。不得保存提示词、回答、API key、请求 URL 或错误正文。
- 根因：SDK 的 `message.updated` 归一化只处理用户消息，`getMessages` 只映射完成时间和错误；桌面只有确定性命令运行记录，没有模型调用账本。
- 失败测试：SDK 集成测试最初缺少预期的 `message.usage`；3 项 Rust 测试分别因账本未实现、损坏历史未拒绝和符号链接未拒绝而失败。
- 最小修改：扩展 SDK 事件与历史消息的内容无关用量类型；新增 `modelCalls.ts` 白名单桥接；实时完成事件写入，打开任务后从历史幂等补记；新增由 Tauri 串行化的 `.openscience/model-calls.jsonl`，采用 20 MiB 上限、严格输入校验、消息级幂等和 SHA-256 前向哈希链。未修改提示词、模型请求、重试/降级策略、HEOR 公式、研究 schema、研究数据或界面。
- 验收结果：定向前端 20/20、定向 Rust 3/3、完整前端 764/764、完整 Rust 371 通过/1 项既有公网测试忽略、发布 44/44；类型检查、ESLint、Rust 格式、生产构建和 40 来源/441 文件资源预检通过。
- 回滚方式：回退本 loop 提交即可；没有迁移或改写既有研究文件。已由测试版本产生的 `.openscience/model-calls.jsonl` 是用户审计数据，回滚代码不自动删除。
- 剩余风险：`runtimeReportedCost` 只保留运行时给出的数值，不自行推定币种、账单或结算金额；应用固定 HEOR 前导提示指纹和实际最终系统块指纹已分别由 P1-AI-001b1/b2 补齐，产物级调用关联和面向研究者的审计查看界面仍属 P1-AI-001b3/c。账本是完整性检测而非外部可信时间戳或数字签名，不应被描述为不可否认审计。

## Loop P1-AI-001b1

- 当前行为：HEOR 自然语言任务在发送前会加入应用固定前导提示和界面语言合同，但调用账本无法说明当次使用哪一版。
- 目标行为：新的 HEOR 调用记录固定模板 ID、该版前导提示的精确 SHA-256 和回复语言；不记录研究者文本、完整提示词或它们的哈希，不对命令和普通非 HEOR 文本伪造上下文。
- 根因：`buildHeorPrompt` 只返回拼接后字符串，发送链和账本桥接没有模板来源数据；历史回放虽保留父用户消息 ID，但未解析其固定前缀。
- 失败测试：修复前先加入三层合同；前端分别因缺少 `heorPromptContext`、桥接忽略第二参数而失败，Rust 因未知严格字段拒绝解析。
- 最小修改：从已构建的 HEOR 文本中仅识别应用拥有的精确前缀与受支持语言；实时轮次在内存中按会话关联，结束/错误/重连时清理；历史回放按 `parentMessageId` 恢复；Rust 只接受三字段全有或全无的有界合同。旧账本记录仍可读取，同一已记录调用不因后来可恢复的可选上下文而改写追加式历史。
- 验收结果：定向前端 33/33、运行时 87/87、定向 Rust 4/4；完整前端 768/768、完整 Rust 372 通过/1 项既有公网测试忽略、HEOR 188/188、发布 44/44；类型检查、ESLint、Rust 格式、生产构建和 40 来源/441 文件资源预检全部通过。
- 回滚方式：回退本 loop 独立提交；无 schema 迁移、研究产物或旧账本改写。新记录的可选字段由旧版读取时忽略，不影响核心调用元数据。
- 剩余风险：该固定模板指纹本身不代表当次实际工作区 Harness；最终系统块指纹现已由 P1-AI-001b2 补齐，但仍没有建立调用到产物的因果或来源关联，也没有研究者可见审计界面。已存在且未记录上下文的历史账本不会被追溯改写；后两项分别保留为 P1-AI-001b3 和 P1-AI-001c。

## Loop P0-AI-002

- 当前行为：导入项目时，AI4HEOR 会完整保留已有 `AGENTS.md`；OpenCode 1.17.13 会把该文件作为项目级系统指令加载，而应用仅在工作区缺失 `AGENTS.md` 时复制产品 Harness。因此保留用户文件的正确兼容行为，意外变成了可让产品安全与科研治理指令整体缺席的路径。
- 目标行为：导入/用户的项目指令保持字节不变并继续作为项目上下文；应用自有产品 Harness 在每次 sidecar 启动前独立校验，然后通过进程级 OpenCode 临时配置叠加加载。
- 根因：工作区播种层同时承担“不覆盖用户文件”与“产品治理不可缺席”两个不同责任，但它只实现了前者。上游行为由 [OpenCode 1.17.13 指令加载器](https://github.com/anomalyco/opencode/blob/v1.17.13/packages/opencode/src/session/instruction.ts) 和 [配置合并器](https://github.com/anomalyco/opencode/blob/v1.17.13/packages/opencode/src/config/config.ts) 确认。
- 失败测试：修改实现前先加入 Rust 临时配置合同与 Python 跨资源合同；Rust 因函数不存在而 5 处编译失败，Python 准确产生 5 处失败。
- 最小修改：提取共用的应用资源校验入口，并将精确路径与内容绑定的整树 SHA-256 编译进应用；sidecar 启动前将经校验的绝对 `harness/AGENTS.md` 路径追加到 `OPENCODE_CONFIG_CONTENT.instructions`。已继承的合法 JSON 对象、其他字段与自定义指令按原顺序保留，产品路径去重后置于末尾；非法 JSON、非对象或非字符串指令数组直接拒绝。不写入持久 OpenCode 配置，不覆盖项目文件。
- 验收结果：导向 9/9 Rust 配置、7/7 Rust Harness、16/16 Python Harness 通过；导入项目 `AGENTS.md` 保留测试继续通过，任一未单独列断言的 Harness 内容变化也会由整树指纹拒绝。全量前端 768/768，Rust 376 通过/1 项既有公网测试忽略，开发合同 376/376，HEOR 188/188，发布 44/44；类型、ESLint、Rust 格式、生产构建和 40 来源/441 文件资源预检均通过。
- 回滚方式：回退本 loop 独立提交即可；无数据迁移、持久配置写入、项目文件改写或研究产物变更。
- 剩余风险：上游组织/受管配置的更后置合并层级未在本地企业环境实证，不扩大宣称为所有上游扩展下的绝对最终优先级；原生工具权限仍是强制执行边界。P1-AI-001b2 现已在插件完成转换后记录当次实际最终系统块指纹，但该指纹不替代权限强制执行或科学正确性复核。

## Loop P1-AI-001b2 调查、研究者确认与实现

- 当前行为：模型调用账本能证明应用固定 HEOR 前导提示的版本，但不能证明当次供应商请求实际使用的完整系统指令集合。产品 Harness 已在 sidecar 启动前独立校验和叠加加载，这只证明加载合同，不是逐调用审计记录。
- 目标行为：每个由 OpenCode 持久化的助手模型调用都绑定插件处理完成后的最终系统指令集合指纹；只保存本地 SHA-256、系统块数、指纹合同版本、OpenCode 版本和准确的助手消息 ID，不保存系统指令、研究者文本、回答、URL 或凭据，也不把指纹发送给模型供应商。
- 上游证据：OpenCode 1.17.13 在 `LLMRequestPrep.prepare` 中组装 agent/provider、环境、项目/用户指令、MCP、Skill 与用户级 system，依次运行 `experimental.chat.system.transform` 后才构造供应商消息；插件钩子顺序执行，但钩子输入只有可选 `sessionID` 和模型，没有助手消息 ID 或调用 ID。
- 根因：最终系统指令集合与助手消息 ID 分属两个内部层级。插件能看到前者，`SessionProcessor` 能看到后者，当前公开钩子没有准确的共同关联键。同一会话还会并发启动标题、摘要和主任务调用，因此按时间、顺序、最近未完成消息或完成后重新读取文件推断都可能错配；远程指令和调用期间被修改的文件也无法事后恢复原始字节。
- 已拒绝的降级方案：不采用插件队列、时间窗口、最近消息、完成后文件哈希或仅记录清单并称其为“实际最终上下文”。这些方法可生成看似完整的字段，却不能满足可复现和可审计合同。
- 建议方案 A：基于固定 OpenCode 1.17.13 维护最小、可审查补丁，在主模型请求真正发出前由内部调用链把最终 system 指纹写入当前助手消息的可选持久字段。标题等没有对应助手消息上下文的辅助调用不写；完成事件和历史回放读取同一字段，避免并发、漏收 SSE 与重启错配。
- 兼容性与隐私影响：方案 A 会使 AI4HEOR 使用经过补丁和重新校验的 OpenCode sidecar，而不是官方发布的原始字节；需要重建源码来源、构建、跨架构校验和、许可证与升级验证。完整系统指纹是本地派生数据，虽然不保存正文也不外发，仍可能暴露相同上下文是否重复出现。按项目规则，未获得研究者明确确认前不得实施。
- 备选方案 B：继续使用官方 sidecar，只记录产品 Harness 指纹、固定前导提示指纹和发送时观察到的项目指令清单，并明确标为不完整清单。它不能关闭 P1-AI-001b2，也不得宣称逐调用上下文可复现。
- 预计修改范围（仅在方案 A 获批后）：固定上游补丁及可复现 sidecar 构建/校验合同；SDK 助手消息上下文字段；桌面模型调用白名单桥接和账本可选字段；并发关联、历史兼容、内容缺席、指纹稳定性与发布资源测试。不得同时修改模型提示正文、HEOR 公式、研究产物或界面。
- 验收标准：标题/摘要与主任务并发时不串记录；每个工具循环助手消息绑定自己的最终指纹；同一最终 system 产生同一指纹，任一块变化产生不同指纹；新字段不包含正文、URL、密钥或研究文本且不进入外部请求；旧消息和旧账本继续可读；完整前端、Rust、HEOR、开发合同、构建和发布资源门禁通过。
- 回滚方式：回退该独立 loop 的上游补丁、sidecar 校验、可选消息/账本字段与测试；不改写或删除已经生成的本地审计历史，也不迁移研究产物。
- 研究者决策：已明确同意方案 A，并同意只在本地保存最终有序系统块的 SHA-256、块数、合同版本、OpenCode 版本和准确助手消息 ID；不得保存或外发系统正文、研究者文本、回答、URL 或凭据。
- 失败测试：先加入补丁来源、触及文件、构建链、CI 顺序、SDK 白名单、Rust 严格字段和实际消息持久化合同；修复前分别出现发布合同失败、Vitest 3 项失败和 Rust 5 处编译失败。全量审查又发现源层未限制块数，随后先加入 1–1024 上限合同并观察到 1 项预期失败，再修改实现。
- 最小修复：固定上游 commit `10c894bdeef3618f5666fb506ef7f9491bb964d8`、源码归档 SHA-256、补丁 SHA-256 与 Bun 1.3.14；`LLMRequestPrep.prepare` 完成所有 system transform 后、供应商调用前生成 `ai4heor.system-context/v1` 指纹，由 `SessionProcessor` 只写入当前助手消息。块数在源层、SDK 与 Rust 统一为 1–1024；标题等没有助手消息绑定的辅助调用不写。桌面账本沿用可选字段和旧记录兼容，不迁移或回写历史。
- 隐私与许可：本地消息与账本只包含合同、64 字符小写十六进制 SHA-256 和块数；发布夹具从实际供应商请求重新计算并比较，不把指纹加入请求。补丁、清单、上游 MIT 许可与 notice 作为应用资源打包，第三方通告和许可审计同步更新。
- 验收结果：固定补丁合同 4/4、上游 19/19、SDK/桥接 21/21、Rust 账本 4/4、前端 768/768、Rust 376 通过/1 项既有忽略、HEOR 188/188、本轮相关开发合同 234 项与发布合同 33 项通过；类型、ESLint、Rust 格式、生产构建和 41 来源/445 文件资源预检通过。固定 Bun 1.3.14 已从最终补丁重新构建 x64 Mach-O sidecar，版本冒烟为 `1.17.13-ai4heor.1`；新 1.0.0 x64 DMG 完成 445 个资源和包内 HEOR 188/188 校验、隔离首启，并通过实际 provider 请求、持久化助手消息与重算指纹三方一致性夹具。
- 回滚方式：回退本 loop 独立提交；不改写或删除已形成的本地账本和研究产物。回滚后新字段会被旧客户端忽略，旧消息与旧账本仍可读取。
- 剩余风险：macOS x64 安装包证据已完成，但 Windows、Apple Silicon 和 Linux 二进制仍需各自原生 CI 重建与执行；当前 DMG 未经 Developer ID 签名和公证，只能作内部测试包。指纹证明当次系统块字节一致，不证明指令本身科学正确，也不建立模型调用到研究产物的因果来源；后两项分别保留在 P1-AI-001b3 与 P1-AI-001c。

## Loop P1-AI-001b3 调查、研究者确认与实现

### 当前行为、复现证据与根因

- `.openscience/model-calls.jsonl` 已以助手消息 `messageId` 为幂等键记录一次具体模型调用；`.openscience/provenance.jsonl` 和 `.openscience/runs.jsonl` 目前只记录 `sessionId`。同一任务可包含多次助手模型调用和多次工具循环，因此会话级字段不能证明某个文件或运行结果来自哪一次调用。
- 固定的 OpenCode 1.17.13 上游源码在 [`partBase`](https://github.com/anomalyco/opencode/blob/10c894bdeef3618f5666fb506ef7f9491bb964d8/packages/schema/src/v1/session.ts#L81-L85) 中要求每个 part 都有 `messageID`，并在 [`ToolPart`](https://github.com/anomalyco/opencode/blob/10c894bdeef3618f5666fb506ef7f9491bb964d8/packages/schema/src/v1/session.ts#L315-L322) 中同时要求 `callID`。当前 `OpenCodeClient.normalize` 已读取前者来排除用户消息，却在生成 `ToolUpdatedEvent` 时只保留 `callID`，丢弃了助手消息 ID。后续 `runtime.ts -> recordProvenance/recordRun -> Tauri` 因而没有可传递的准确关联键。
- 直接写入、编辑和 `apply_patch` 形成的产物通过工具事件写入 provenance；本地 Python/R 等执行先写入 run，再由 `link_run_outputs` 给每个输出写入 provenance。两条路径都能在事件发生时取得准确工具调用 ID；本地模型发起的工具事件还可取得对应助手消息 ID，不需要按时间或顺序猜测。
- 当前 `ProvenancePanel` 和 `RunsPage` 只能打开 `/heor/{sessionId}`，线程块也没有助手消息锚点。它们不能精确跳到生成产物的模型调用。这属于 P1-AI-001c 的研究者可见审计界面，不作为本轮持久化关联合同的替代品。

### 目标合同与建议方案

- 建议方案 A：给规范化 `ToolUpdatedEvent` 增加可选 `messageId`；给 `ProvenanceRecord` 和 `RunRecord` 增加可选 `assistantMessageId` 与 `toolCallId`。模型发起的直接文件工具、运行记录及运行输出都原样传播这两个 ID；`assistantMessageId` 与模型调用账本的 `messageId` 精确连接，`toolCallId` 证明具体执行动作。同一助手消息的多个工具调用可区分，同一运行的多个输出共享同一组来源键。
- 用户直接执行的 shell、应用自有确定性计算或旧版记录可能没有助手消息；这些记录保持字段缺席，不伪造模型来源。历史 JSONL 不迁移、不按时间回填，也不把缺失关联误报为已建立。
- 新字段仅是本地有界标识符，不保存提示词、回答、文件正文、URL、API key 或供应商请求，也不发送给模型供应商。模型调用账本仍以自身哈希链保持完整性；本轮不把 provenance/runs 改称不可否认审计。
- 备选方案 B：在模型调用完成后另建 `artifact-model-links.jsonl`。它需要暂存尚未完成调用的工具关系、维护第三个并发追加账本并处理两个账本之间的部分失败，复杂度更高且仍需改动现有记录读取端，因此不建议。

### 兼容性、失败测试、预计修改与验收

- 兼容性影响：`ProvenanceRecord`、`RunRecord` 和 `ToolUpdatedEvent` 是共享/可移植数据合同；方案 A 只增加 `serde(default, skip_serializing_if = "Option::is_none")` 的可选字段。旧 JSONL、远程 Skill 生成的 run 记录和没有模型参与的确定性运行继续可读；旧应用会忽略新 JSON 字段。由于这是持久化和公开类型合同变更，按项目规则先等待研究者确认。
- 失败测试计划：先让 SDK 模拟服务在助手工具部分携带 `messageID`，断言规范化事件必须保留；断言直接 provenance、`apply_patch`、本地 run 和 run 输出均保存相同的助手消息/工具调用 ID；断言旧记录缺字段仍可读、字段不会被猜测、用户 shell/应用自有计算不伪造模型来源；断言异常空值、控制字符或超长 ID 被拒绝。
- 预计最小修改文件：`packages/sdk/src/types.ts`、`packages/sdk/src/OpenCodeClient.ts`、`packages/sdk/src/mockServer.ts`、`apps/desktop/src/test/opencode-client.node.test.ts`、`apps/desktop/src/lib/runtime.ts`、`apps/desktop/src/lib/provenance.ts`、`apps/desktop/src/lib/runs.ts`、`packages/shared/src/index.ts`、`apps/desktop/src-tauri/src/provenance.rs`、`apps/desktop/src-tauri/src/runs.rs` 及各自定向测试。不得同时修改模型提示、HEOR 公式、研究 schema、现有研究结果或界面。
- 验收标准：一条模型工具调用形成的直接产物和本地运行输出都能通过 `assistantMessageId` 唯一连接到对应 `ModelCallRecord.messageId`，并由 `toolCallId` 连接到具体工具动作；并发工具循环不串联；旧记录、非模型运行和远程 Skill 记录兼容；新增字段内容受限且不进入供应商请求；定向失败测试转绿后，完整前端、Rust、HEOR、类型、lint、构建与资源门禁全部通过。
- 回滚方式：回退本 loop 的可选字段、传播路径与测试；既有 JSONL 和研究文件不迁移、不删除。回滚后的旧客户端会忽略已写入的新可选字段。

### 研究者确认、最小修复与验证结果

- 研究者决策：已明确同意方案 A，即在既有事件与记录合同中加入可选关联字段；不另建第三个关联账本，不按时间、顺序或最近消息推断来源。
- 失败测试：实现前先扩充 SDK 模拟服务、事件归一化、直接 provenance、`apply_patch`、run、run 输出及 Tauri 桥接断言；前端 7 项失败，Rust 因字段和函数参数尚不存在出现 10 处预期编译失败。最小实现后，完整 Rust 编译又发现教学案例两个应用自有运行调用仍使用旧签名；它们被明确补为无模型关联，而非伪造助手消息。
- 最小修改：OpenCode SDK 原样转发工具 part 的 `messageID`；前端将它与既有 `callID` 传播到 provenance/run 输入；共享 TypeScript 类型和 Rust JSONL 记录增加 `assistantMessageId`、`toolCallId` 可选字段；直接文件工具、`apply_patch`、本地运行及成功运行的输出记录保留同一组键。Rust 拒绝空白、控制字符或超过 256 字节的来源标识。应用自有确定性教学运行、用户/远程运行和历史记录保持字段缺席。
- 隐私与兼容性：新增内容只有本地有界标识符，不包含提示词、回答、研究正文、URL、API key 或供应商请求，也不发送给模型供应商。JSON 字段可选且缺省不序列化；旧 JSONL、远程 Skill 记录和旧应用保持兼容，不迁移、不猜测、不回填历史。
- 验收结果：定向前端 43/43、Rust provenance 6/6、Rust runs 9/9；完整前端 770/770、Rust 377 通过/1 项既有公网测试忽略、HEOR 188/188、开发合同 380/380、发布合同 46/46；类型检查、ESLint、Rust 格式、生产构建和 41 来源/445 文件资源预检全部通过。既有 React `act(...)`、Router、Vite 大包和 Node `url.parse` 告警未隐藏，也非本轮引入。
- 回滚方式：回退本 loop 独立提交；不删除或改写用户已有 JSONL 和研究文件。旧代码会忽略已写入的新可选字段。
- 剩余风险：内部记录已经具备准确连接键，但当前 `ProvenancePanel`、`RunsPage` 和对话线程仍没有面向研究者的消息锚点、来源详情与可解释导航；该产品层工作继续保留为 P1-AI-001c。provenance/run 与 model-call 账本是不同的本地追加存储，关联键解决准确连接，不提供跨文件事务或外部可信签名，因此不得宣传为不可否认审计。

## Loop P1-TEST-001b1：测试专用 macOS 原生导航 E2E

- 当前行为与复现：既有 macOS 验证能确认进程、OpenCode 鉴权 HTTP、AppShell bootstrap 和 Tauri IPC，但没有对真实 WKWebView DOM 定位或点击任何用户控件。修复前 4 项契约分别缺少根命令、Cargo 测试特性/依赖、原生驱动脚本和 CI 门禁，结果为 3 项失败、1 项错误。
- 目标行为：仅在显式 `desktop-e2e` 测试变体中启动 W3C WebDriver，用隔离 HOME/XDG 的真实 Tauri 窗口验证 IPC 桥接，并点击进入“新建任务”和“插件与技能”。普通与发布构建不得包含 WebDriver 服务器。
- 根因：macOS 过去无法直接使用 [`tauri-driver`](https://v2.tauri.app/develop/tests/webdriver/)；仓库因而只建立进程/日志证据，没有随后补入 WebdriverIO 官方记录的 [macOS 嵌入式 WebDriver 路径](https://webdriver.io/docs/desktop-testing/tauri/plugin-setup/)。
- 最小修复：精确锁定可选的 MIT `tauri-plugin-wdio-webdriver 1.2.0`，只由 Cargo `desktop-e2e` 特性注册；新增纯 Python 标准库驱动脚本，临时隔离已运行安装版的单实例 socket，限时等待 WebDriver 和 Tauri 桥接，通过 W3C 元素端点点击中/英文导航项，最后删除 session 并终止测试进程。CI 在 Intel macOS 打包前执行该冒烟。
- 稳定性修正：首次真实执行发现隔离环境按系统语言启动为英文，因而定位器改为匹配已发布的中/英文标签；又发现 WebDriver `/status` 可早于 React/Tauri 桥接挂载，因而改为有界等待，超时仍 fail-closed。修复后原生驱动连续 3 次通过。
- 生产隔离证据：普通 `cargo tree -e normal` 不含 WebDriver；只有 `--features desktop-e2e` 的依赖树包含 1.2.0。既有单实例插件仍第一个注册，不改生产 capability、界面、业务逻辑、模型调用或科学计算。
- 许可完整性：复核发现既有 Cargo 清单生成器会漏掉可选特性依赖。先加失败合同，再将清单改为 `--all-features`；当前清单登记 641 个第三方 Cargo 包加 1 个工作区包，明确包含该 MIT 测试依赖，同时许可审计声明其不随产品分发。
- 验收结果：原生 E2E 完整命令通过，且直接驱动连续 3/3 通过；定向契约 5/5，完整前端 770/770、Rust 377 通过/1 项既有忽略、HEOR 188/188、开发合同 385/385、发布合同 46/46，类型检查、ESLint、Rust 格式、普通/测试特性 `cargo check`、生产构建和 41 来源/445 文件资源预检全部通过。
- 回滚方式：回退本 loop 的独立提交；无数据迁移、研究文件修改或用户配置变更。
- 剩余风险：该测试驱动开发构建，不是当前 DMG 中的安装后产品字节；当前 CI 只在 Intel macOS 运行该冒烟。HTML 被动预览已由 P1-TEST-001b2 补齐，但模型任务、消息队列、Human-in-the-loop、权限交互、导入/导出或科学计算流程仍未完成端到端验证。这些必须作为 P1-TEST-001b 的后续独立 loop。

## Loop P1-TEST-001b2：真实 WKWebView 被动 HTML 预览 E2E

- 当前行为：前端与 Rust 单元测试已经固定被动 HTML 预览合同，但测试专用原生 E2E 只点击“新建任务”和“插件与技能”，没有在真实 WKWebView 中打开任务文件，也没有观察实际 iframe、loopback 响应头或不可信脚本请求。
- 目标行为：在隔离 HOME/XDG 的真实 Tauri 测试窗口中打开一个本地 HTML 文件，确认实际 iframe 使用空 sandbox、实际 loopback 响应包含 `script-src 'none'`、`connect-src 'none'` 与 `Referrer-Policy: no-referrer`，且页面加载期间不会请求外部脚本。
- 根因：P0-SEC-001 的验证停留在 jsdom 与 Rust HTTP 单元层；P1-TEST-001b1 为控制范围只完成基础导航，没有把两层安全合同串到真实 WebView。
- 修改前失败测试：先扩展 `test_desktop_e2e_contract.py`，分别观察到缺少 HTML 夹具、稳定元素定位和本地请求观察器的预期失败；这些测试没有通过放宽断言或跳过检查转绿。
- 最小修改范围：只修改测试契约与标准库原生驱动。驱动在临时工作区写入可见静态内容、内联脚本标记及指向随机 loopback 端口的外部脚本，使用真实侧边栏进入“任务文件”，等待同一 DOM 文件按钮稳定后只点击一次；随后检查 iframe 属性、真实 HEAD 响应头、顶层可观察的 iframe `load` 事件和本地观察器零请求。未修改产品业务、UI、科研计算、模型调用、研究数据或发布包。
- 稳定性边界：启动阶段工作区状态可能合法替换文件列表 DOM；直接保存一次 WebDriver 元素 ID 会产生竞态。修复采用页面内 DOM 节点身份连续稳定 1 秒后再获取元素并点击，有界超时仍 fail-closed。沙箱 iframe 禁止 WebDriver 通过 JavaScript 进入其内部是正确安全行为，因此测试不以绕过沙箱读取内部 DOM 作为验收条件。
- 验收结果：测试契约 6/6；直接原生驱动最终连续 3/3；`pnpm test:e2e:desktop` 完整通过。全量回归为前端 113 文件/770 项、Rust 377 通过/1 项既有忽略、HEOR 188/188、开发合同 386/386、发布合同 46/46；类型检查、ESLint、Rust 格式、41 来源/445 文件资源预检、前端 10/10 与 Rust 7/7 定向预览测试均通过。
- 隔离与隐私：测试只使用 `/private/tmp` 下临时 HOME 和随机本地端口；不访问公网，不读取用户 API key，不保存研究内容，结束后删除 WebDriver session、终止测试进程并清理临时目录。本轮确认无遗留测试进程。
- 回滚方式：回退本 loop 的两个测试文件和本节记录；无数据迁移、用户文件或产品接口变化。
- 剩余风险：这是测试特性构建的真实 WKWebView 证据，不是已安装 DMG 字节证据；它证明 iframe 加载、安全属性、实际响应头与测试脚本零请求，不宣称覆盖所有 HTML 子资源、视觉排版或任意恶意内容。任务执行、队列、Human-in-the-loop、权限与导入/导出仍待独立 E2E。另行发现的调试资源缓存污染记录为 P1-TEST-002，不在本轮顺便修复。

## Loop P1-TEST-002：Tauri 准入 Skill 暂存树确定性重建

- 当前行为与复现：Tauri 构建依赖的资源复制只覆盖已有源文件，不会删除复用 profile 资源目录中的额外文件。向调试暂存的 `integrity-auditor` 加入一个忽略的 `__pycache__/*.pyc` 后，运行时因内容哈希失配正确拒绝部署，但旧原生 E2E 没有检查启动日志，仍报告通过且污染文件保留。
- 目标行为：每次 Tauri 构建都从源码重新形成准入 Skill 暂存树；清理范围必须精确限制在 Cargo `OUT_DIR` 对应 profile 下可再生成的 `skills-admitted-ai4s`，不得触及源码、用户数据、安装应用或同级其他资源；原生 E2E 遇到任何准入资产部署失败日志必须失败。
- 根因：`tauri-build 2.6.3` 的资源复制没有镜像删除语义，而现有构建和 E2E 合同分别缺少生成目录清洁步骤与部署失败日志门禁。运行时的树哈希 fail-closed 行为本身正确。
- 修改前失败测试：新增 Rust 路径/清理边界测试时因实现模块不存在而失败；桌面 E2E 合同因缺少暂存触发、受限清理和部署日志检查而失败；资源预检合同因触发器不存在而失败。没有删除测试、放宽断言或屏蔽运行时错误。
- 最小修复：`beforeBuildCommand` 先运行标准库 Node 触发器，只更新同目录固定触发文件的时间戳；Cargo build script 观察该文件，在严格校验 `OUT_DIR` 形状后仅删除 profile 的准入 Skill 暂存目录，再由原有 Tauri 资源复制恢复。原生 E2E 在成功输出前读取应用日志并拒绝 `failed to deploy admitted asset`。第一次尝试直接观察并清理输出目录会造成 Cargo 每次都判定 Dirty，已在提交前撤销；当前连续普通 Cargo 构建的第二次为 `Fresh`。
- 验收结果：污染夹具经真实 `pnpm test:e2e:desktop` 自动清除，源码与重建暂存树哈希均为 `db4d137dd69ec7295aa6517238ae1f6817abc051395d0708d5283c687a1d5bb4`，缓存数为 0；Rust 清理边界 2/2、桌面 E2E 合同 8/8、资源触发器合同 6/6、前端 770/770、HEOR 188/188、Rust 377 通过并有 1 项既有忽略、开发合同 388/388、发布合同 47/47、类型检查、ESLint、Rust 格式和 41 来源/445 文件资源预检均通过。
- 回滚方式：回退本 loop 的独立提交即可；无数据迁移、研究文件、产品界面、模型请求、科学公式或发布包变化。
- 剩余风险：普通 `cargo test` 不需要消费打包资源，确定性清理绑定到实际 Tauri build 入口。macOS 与 Windows 发布配置共用该入口和 build script，但本轮只取得 macOS 调试 E2E 证据，没有生成或验证新的 DMG，也没有 Windows 原生证据。

## Loop P1-TEST-001b3：真实独立任务与项目隔离 E2E

- 当前行为与复现：既有原生驱动只验证导航、任务文件和被动 HTML，不会创建项目、提交模型任务或证明全局“新建任务”不会沿用当前项目作用域。修复前新增合同因本地模型夹具不存在而失败，真实执行也无法在无真实密钥环境中可重复完成一轮任务。
- 目标行为：在隔离 HOME/XDG 的真实 Tauri/WKWebView 中创建一个项目，再从全局入口创建独立任务；使用仅监听 `127.0.0.1` 的确定性 Anthropic 兼容夹具完成回复，并同时证明独立任务位于基准工作区直属目录、元数据 `kind=session`、项目元数据 `kind=heor`、二者目录不同，且侧边栏任务 DOM 不隶属于任何项目。
- 根因：原生 E2E 没有可重复的本地模型提供商，也没有把任务路径、工作区指针、项目元数据和侧边栏归属串成一个可验证合同。测试初版还暴露四个驱动问题：Enter 必须走 W3C actions；同一用户文本会出现在主回答与标题等辅助请求中，不能以文本命中总数判断重复提交；隔离配置中的模型并不保证首次目录实例立即成为界面默认模型；WebView 输入框可能在启动状态刷新时重建，不能向一次取得的旧元素输入后立即点击。
- 修改前失败测试：新增本地夹具合同首先因 `prepare_local_fixture_runtime` 不存在而失败；真实运行随后分别失败于模型未设置、辅助请求误计为重复提交，以及输入值或发送状态未落到当前输入框节点。一次 3/3 后的根命令重建仍准确复现“模型未设置”，因此没有把偶然通过当成完成。每次均保留失败证据并修正测试边界，没有删除测试、放宽产品断言或屏蔽错误。
- 最小修改：只扩展 `scripts/e2e/verify_desktop_webdriver.py` 和对应 Python 契约测试。复用发布测试已有的本地夹具协议，在临时应用私有 XDG 中写入无秘密测试凭据并注入测试子进程；若界面仍无默认模型，驱动通过公开的“选择模型”入口进入设置的模型页，显式选择夹具模型并返回应用。主回答只按“带非空工具上下文且含任务文本”分类；输入阶段有界地重新定位当前输入框、核对实际值，只在缺失或漂移时清空重输，并等待当前发送按钮启用。随后验证任务路由、夹具回复、实际工作区与元数据。未修改产品业务、UI、科学计算、模型适配、研究数据格式或安装应用。
- 清理边界：终止测试应用前枚举其精确子进程，只结束该测试进程树；不按进程名全局清理，不影响已安装 AI4HEOR。历史失败测试留下的 6 个 `/private/tmp/ai4heor-desktop-e2e-*` 目录经确认不含运行进程后删除；修复后的连续运行不再新增残留目录。
- 验收结果：定向契约 10/10；直接原生驱动最终连续 3/3；从根命令重建后的 `pnpm test:e2e:desktop` 完整通过。全量回归为前端 113 文件/770 项、HEOR 188/188、Rust 377 通过/1 项既有忽略及资源暂存 2/2、开发合同 390/390、发布合同 47/47；类型检查、ESLint、Rust 格式、`git diff --check` 与 41 来源/445 文件资源预检均通过。
- 隔离、隐私与回滚：测试不访问公网、不读取或写入用户 API key、不使用真实模型、不保存研究内容；夹具只监听随机 loopback 端口并使用明确非秘密凭据。回退本 loop 的两个测试文件和本节记录即可，无数据迁移、用户设置或产品接口变化。
- 剩余风险：这是测试特性调试构建的真实 WKWebView 证据，不是当前 DMG 的安装后字节证据；只覆盖一轮普通主回答与项目/任务隔离，不覆盖消息队列、Human-in-the-loop 问题/权限、失败恢复、导入/导出或科学计算端到端。没有生成新安装包。

## Loop P1-TEST-001b4：真实消息队列交互 E2E

- 当前行为与复现：消息队列的 store 和 React 组件有单元测试，但未证明真实 macOS WebView 中模型回答期间仍能连续输入，也未证明调整顺序、删除和当前回答结束后的逐条发送。旧本地模型夹具立即回复，无法稳定建立该交互窗口。
- 目标行为：在隔离 HOME/XDG 的真实 Tauri/WKWebView 内暂停首轮本地模型回复，加入三条待发送消息；将第三条上移、删除原第一条后，只允许剩余两条按新顺序进入模型主请求，队列最后清空。
- 根因与修改前失败测试：原生 E2E 夹具缺少“仅暂停下一个带工具主请求”的有界控制点。先增加失败合同，确切失败于 `FixtureState.pause_next_main_reply` 不存在，然后才增加实现。
- 最小修复：只扩展本地发布测试夹具、原生 WebDriver 和对应合同。夹具使用一次性 `Event` 门，仅对 stream 且带非空 tools 的下一个请求生效，30 秒超时后 fail-closed；默认行为不变。原生驱动通过可见控件加入、上移和删除消息，再以每个请求最后一条 user 文本核对主请求顺序。未修改业务代码、UI、科学计算、用户设置、研究数据或模型适配。
- 验收结果：定向桌面合同 11/11，夹具发布合同 2/2；直接原生驱动连续 3/3；从根命令重建后的 `pnpm test:e2e:desktop` 完整通过。全量回归为前端 113 文件/770 项、HEOR 188/188、Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2、开发合同 391/391、发布合同 47/47；类型检查、ESLint、Rust 格式、`git diff --check` 和 41 来源/445 文件资源预检全部通过。
- 隔离、回滚与剩余风险：全程仅访问随机 loopback 端口，不读取真实密钥、不访问公网、不保存研究内容；测试异常时 `finally` 必定释放回复门。回退本 loop 独立提交即可。这仍是测试特性调试构建证据，不是 DMG 安装后证据；本轮未生成新安装包，且未覆盖队列中携带 Skill/附件、Human-in-the-loop 阻断后恢复或模型错误重试。

## Loop P1-TEST-001b5：真实 Human 问题与队列恢复 E2E

- 当前行为与复现：`InteractionPrompt`、SDK 问题端点、runtime store 和队列阻断都有单元合同，但没有证明真实 OpenCode 执行模型 `question` 工具时，Tauri/WKWebView 能显示、回答并恢复同一回合，也没有证明待发送消息不会越过待回答问题。
- 目标行为：本地确定性模型发起一个普通、非医药事实问题；真实界面显示问题和选项。研究者未回答前，新消息只进队列且不进入 provider；选择后答案进入原回合的续跑请求，原回合完成后才发送队列消息。
- 依据与根因：按项目固定的 OpenCode `1.17.13` 上游提交 `10c894bdeef3618f5666fb506ef7f9491bb964d8` 核对 `question` 工具参数和 `question.asked/replied` 生命周期。现有本地 provider 夹具只能返回文本，无法在无真实密钥、无公网的情况下可重复地触发该生命周期。
- 修改前失败测试：先向发布夹具合同加入“下一个主回复仅生成一次 question”，确切失败于 `FixtureState.question_next_main_reply` 不存在。首次直接原生复现因前一轮普通 `cargo test` 覆盖了同路径的测试特性二进制而未启动 WebDriver；使用根级 `test:e2e:desktop` 重建明确特性后才进入产品复现，不将该构建顺序错误误判为产品缺陷。
- 最小修改：本地 provider 夹具新增一次性、仅对 stream 且带 tools 的主请求生效的 question 回复类型，使用标准 Anthropic `tool_use` 流交给 OpenCode；默认仍是原文本回复。原生驱动在既有队列验证后再触发问题，核对卡片文本、队列未提前发送、答案进入续跑请求、队列随后清空。未修改任何业务代码、UI、权限规则、科学计算或数据格式。
- 验收结果：夹具定向合同 3/3、桌面定向合同 11/11；根级 `pnpm test:e2e:desktop` 通过，随后直接原生复跑 2/2，合计连续 3/3。全量回归为前端 113 文件/770 项、HEOR 188/188、Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2、开发合同 391/391、发布合同 48/48；类型检查、ESLint、Rust 格式、`git diff --check` 和 41 来源/445 文件资源预检全部通过。
- 隔离、回滚与剩余风险：夹具仅监听随机 loopback 端口，不用真实模型或密钥，问题与回答都是明确测试字符串。回退本 loop 独立提交即可。这仍是测试特性调试构建证据，不是 DMG 安装后证据；不覆盖“跳过”/问题拒绝、多选/自定义回答、命令权限卡、子代理问题或 provider 失败后恢复；本轮未生成新安装包。

## Loop P1-TEST-001b6：真实危险命令权限与队列恢复 E2E

- 当前行为与目标：默认“由我确认”模式的 bash `ask` 规则、SDK 权限回复、权限卡和 store 恢复只有分层单元测试。本轮目标是在真实 OpenCode、Tauri 与 WKWebView 中证明危险命令会展示具体资源并暂停，待回答队列不得越过，研究者选择“仅允许一次”后命令执行并先恢复原回合，然后才排空队列。
- 上游依据与根因：固定 OpenCode `1.17.13` 当前实际注册的是 V1 [ShellTool](https://github.com/anomalyco/opencode/blob/10c894bdeef3618f5666fb506ef7f9491bb964d8/packages/opencode/src/tool/shell.ts)，它把命令扫描结果交给 V1 [Permission](https://github.com/anomalyco/opencode/blob/10c894bdeef3618f5666fb506ef7f9491bb964d8/packages/opencode/src/permission/index.ts)；`once` 只解锁当前请求。缺口的根因不是产品逻辑缺失，而是本地 provider 夹具无法可重复地生成 `bash` `tool_use`。
- 修改前失败测试：新增“下一个主回复只生成一次 bash”合同，精确失败于 `FixtureState.bash_next_main_reply` 不存在。首次原生测试已真实显示命令权限卡，但测试观察器未把新权限提示纳入候选集而报序列不匹配；只补该候选集，没有放宽顺序、权限或工具结果断言。
- 最小修复：夹具增加一次性 bash 回复类型和标准 Anthropic `tool_use` 流，命令固定为对隔离临时工作区中不存在占位文件的 `rm -f`。原生驱动核对卡片中的完整命令、确认前队列零发送、一次授权后的 `tool_result`、原回合续跑与最终队列清空。未修改业务代码、UI、权限规则、科学计算、用户配置或数据合同。
- 验收结果：修正观察器后原生流程连续 3/3 通过，其中最后一次由根级 `pnpm test:e2e:desktop` 重建测试特性并执行。全量回归为前端 113 文件/770 项、HEOR 188/188、Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2、开发合同 391/391、发布合同 49/49；类型检查、ESLint、Rust 格式和 41 来源/445 文件资源预检全部通过。
- 隔离、回滚与剩余风险：命令只运行于自动清理的临时任务目录；provider 仅监听随机 loopback 端口，无真实密钥或公网访问。回退本 loop 独立提交即可。当前证据仍来自测试特性调试构建，不是 DMG 安装后完整任务证据；不覆盖权限拒绝、永久允许的持久化/作用域、多个权限请求、子代理请求或 provider 失败恢复；本轮未生成安装包。

## Loop P1-TEST-001b7：真实危险命令拒绝与队列恢复 E2E

- 当前行为与目标：权限拒绝在组件与 SDK 层已有调用合同，但没有真实桌面证据证明命令不会执行、拒绝结果保留在会话历史、待发送消息不会越过权限卡且会在当前回合终止后继续。本轮只补这一拒绝分支，不修改权限语义。
- 上游依据与根因：固定 OpenCode `1.17.13` 当前实际使用的 V1 [Permission](https://github.com/anomalyco/opencode/blob/10c894bdeef3618f5666fb506ef7f9491bb964d8/packages/opencode/src/permission/index.ts) 在 `reject` 时拒绝当前 deferred 权限并结束工具回合。缺口根因是本地 provider 夹具只有一个一次授权 bash 请求，无法用不同工具 ID 和实际存在的文件区分“拒绝”与“命令已执行”。
- 修改前失败测试：先增加独立拒绝探针合同，精确失败于 `FixtureState.bash_rejection_next_main_reply` 不存在；再扩展桌面静态合同，精确失败于原生驱动没有拒绝路径。首次真实原生运行在命令未执行、拒绝工具结果和队列消息均已出现后，因测试错误要求拒绝后还应产生一次模型恢复请求而失败。请求结构证明 OpenCode 拒绝会终止工具回合，随后唯一的新模型请求就是队列消息；其历史包含被拒绝的 `tool_result` 是正常上下文，不是消息合并或产品竞态，因此没有修改业务代码。
- 最小修改：夹具增加第二个一次性 bash `tool_use`，使用独立消息/工具 ID，并固定请求删除隔离任务目录中预先创建的哨兵文件。原生驱动核对完整命令、确认前队列零发送、点击“拒绝”后哨兵内容不变、下一次主请求的最新用户消息正是排队内容、历史保留匹配的拒绝工具结果、队列清空且回合最终空闲。测试观察器按真实拒绝语义由“额外两次请求”修正为“一次独立队列请求”，没有删除或放宽安全、顺序、文件和状态断言。
- 验收结果：夹具定向合同 5/5、桌面定向合同通过；修正测试观察模型后，原生流程连续 3/3 通过，其中一次由根级 `pnpm test:e2e:desktop` 完整重建测试特性。全量回归为前端 113 文件/770 项、HEOR 188/188、Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2、开发合同 391/391、发布合同 50/50；类型检查、ESLint、Rust 格式、生产构建和 41 来源/445 文件资源预检全部通过。
- 隔离、回滚与剩余风险：哨兵和删除命令只存在于自动清理的临时独立任务目录；provider 只监听随机 loopback 端口，不使用真实模型、密钥或公网。本 loop 未修改产品 UI、权限规则、模型逻辑、科学计算、用户配置或数据格式，回退本独立提交即可。当前仍是测试特性调试构建证据，不是 DMG 安装后证据；永久允许的持久化/作用域、多个并行或子代理权限请求、provider 失败恢复及安装后完整任务仍待独立 loop。本轮未生成安装包。

## Loop P1-TEST-001b8 / P1-PERM-001：真实“始终允许”持久化、作用域与撤销

- 当前行为与目标：旧界面提供“始终允许”，但固定 OpenCode V1 权限服务只把规则保存在 `InstanceState.approved` 内存数组。目标按研究者确认的方案 A 收敛为：规则本地落盘，只绑定当前项目、动作和精确资源；同项目同资源在应用重启后复用；不同项目或资源仍询问；研究者可见并可撤销。
- 修改前失败测试与复现：夹具和桌面合同先准确暴露缺少重复命令、重启、撤销与数据库观察路径；真实 WKWebView 点击“始终允许”后，同一进程第二次相同命令自动执行，但 30 秒内 `opencode.db.permission` 始终为空，应用重启后重新询问。实现过程中，原生 E2E 又发现任务目录虽已创建但初始 Git 提交异步执行，OpenCode 可能先按父级仓库创建会话和权限；恢复任务路由也可能在运行时尚未切换到正确工作区时暂时开放输入。
- 根因：V1 `Permission` 没有接入已有 SQLite `PermissionSaved`；设置页调用隐式依赖客户端启动目录，可能读取错误作用域；任务 Git 初始化与工作区切换存在竞态；上游项目 ID 迁移只迁移 session/workspace，没有迁移 permission 表。可见问题因此不是单一 UI 缺陷，而是权限存储、项目身份和桌面工作区时序共同造成。
- 最小修复：固定 OpenCode 补丁让 V1 权限服务在配置规则之后读取当前项目的精确持久规则，“always”只写入当前请求的精确 `action + patterns`；新增当前项目的列出/删除接口，并在项目 ID 迁移时先去重再迁移权限。SDK 只增加对应类型与方法；隐私设置按当前运行时工作区列出和撤销规则；权限卡明确作用域。桌面在任务 Git 仓库完成首个同步提交后才切换工作区，恢复路由在会话与运行时工作区一致前禁用输入。未改 HEOR 公式、模型提示、研究 schema、模型供应商协议或研究文件。
- 验收结果：固定 OpenCode 目标测试及类型检查 112/112；补丁合同 4/4；桌面 E2E 合同 11/11；前端 114 文件/775 项；Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2；HEOR 188/188；包内夹具 6/6；macOS 发布合同 16/16；类型检查、ESLint、Rust 格式、生产构建和 41 来源/445 文件资源预检均通过。最终真实原生 E2E 完成一次允许、拒绝、始终允许、完整应用重启、同项目同命令自动复用、隐私设置可见撤销、撤销后再次询问，并验证哨兵文件未被拒绝路径删除。
- 隔离、回滚与剩余风险：权限记录只在应用本地 SQLite 中保存，不含模型正文或研究数据；精确资源不会扩展成通配符，配置中的显式 deny/allow 优先于保存规则。回退本独立提交可恢复旧 sidecar 与 UI；新表沿用上游 schema，不需破坏性迁移。当前证据来自测试特性调试构建，不代表已签名/公证 DMG 的安装后证明；多个并行或子代理权限请求、provider 失败恢复和安装后完整任务仍是后续独立 loop。本轮未生成安装包。

## Loop P1-TEST-001b9：安装包内“始终允许”持久化验证

- 当前行为与目标：P1-TEST-001b8 已证明测试特性调试构建中的完整 WebView 交互，但已有 1.0.0 DMG 仍携带 OpenCode `1.17.13-ai4heor.1`，不能代表 A1 修复后的发布字节。目标只是在隔离环境内证明新 DMG 的 `.2` sidecar 确实保存当前项目、动作和精确资源，重启后复用，撤销后删除并重新询问。
- 修改前失败测试与根因：先扩展包内夹具合同，因缺少持久权限验证函数而失败；实现验证器后，旧 `.1` DMG 在 `GET /permission/saved` 返回非 JSON，准确证明其没有 A1 接口。根因不是新业务回归，而是 A1 完成后尚未从当前干净源码重建并绑定安装包证据。
- 最小修改：只扩展发布验证器、其单元合同和 macOS 发布证据门禁；验证器在临时 Git 项目、临时 XDG 配置、随机 loopback provider 和固定安全命令中运行，不访问真实模型、密钥、研究资料或用户配置。它核对精确权限记录，停止并重启同一包内 OpenCode，证明免询问复用，删除记录后证明规则消失和重新询问，再拒绝请求并核对哨兵不变。未修改业务代码、UI、HEOR 公式、模型提示、研究 schema 或 provider 协议。
- 验收结果：包内夹具合同 8/8、macOS 发布合同 16/16；最终包内夹具报告 `permission_restart=True`、`permission_revoke=True`。由干净提交 `b480c26edda41e476c7c1bd56820ddd3e126d3e3` 构建的 `AI4HEOR_1.0.0_x64.dmg` 为 96,470,656 字节，SHA-256 `746332065bf3cbdee0b3f507affb6a67dea39c095f9c074b2189679ab9661673`；包内 OpenCode 为 `1.17.13-ai4heor.2`，445 个资源逐字节一致，HEOR 188/188，隔离首启、前端 bootstrap、鉴权 HTTP、工作区隔离、系统上下文与权限持久化门禁通过。全量回归为前端 114 文件/775 项、Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2、发布测试 53/53、HEOR 188/188，以及类型、ESLint、Rust 格式、生产构建和 41 来源/445 文件资源预检通过。
- 回滚与剩余风险：回退本 loop 的发布验证提交并删除可再生成的 DMG 即可，不影响用户数据或研究结果。证据验证的是安装包内 sidecar 协议与持久化边界，不替代已单独完成的调试 WebView 交互证据，也不证明安装后完整任务 UI、provider 失败恢复或导入到导出。该 DMG 没有 Developer ID 签名或公证，仅供 Intel macOS 内部测试；不宣称 Gatekeeper 或公开分发可信。

## Loop P1-TEST-001b10：真实 Provider 失败与队列恢复

- 当前行为与目标：SDK 和 runtime store 已有错误展示测试，但真实 Tauri/WKWebView 从未让 provider 确定性失败。目标是在当前任务中制造一次真实 HTTP 400，证明错误对研究者可见、待发送消息不会提前进入模型；失败处理完成后，同一任务的下一条队列消息必须恰好调用 provider 一次、完成回复、清空队列并恢复输入。
- 修改前失败证据：新增的一次性 provider 错误夹具和原生合同先因缺少 `provider_error_next_main_reply` 等能力而失败。接入夹具后，原生运行稳定复现：错误可见、队列项消失、用户消息出现在历史，但 provider 主请求数保持不变。第一次状态时序修复还暴露普通两条队列只发送第一条；改为可响应防重入状态后普通队列恢复，但 provider 错误分支仍失败，因此没有把局部绿灯冒充完成。
- 根因：第一处竞态是异步 `prompt_async` 在 POST 返回后才设置运行锁；错误与 `session.idle` 可先到达并清锁，POST 返回又把已结束回合复活为假运行。更深层根因由隔离 sidecar 实验确认：OpenCode `1.17.13-ai4heor.2` 在 provider 400 后虽发出错误和 idle，却残留同一会话执行器；直接再次提交只保存 user/assistant 空消息并永久 `busy`，provider 不收到请求。调用其既有 `/session/:id/abort` 清理后立即再次提交则正常调用 provider，且任务历史保留。
- 最小修复：普通异步回合在 POST 前建立运行锁，HTTP 本身失败时显式清理；session 错误立即写入可见错误行，但运行边界同时等待 `session.idle` 和受支持的会话 abort 清理完成。队列防重入由不可响应 ref 改为 state，避免第一条发送 Promise 收尾时错过下一条；不加入诊断阶段尝试过但无必要的固定延时。夹具只增加一次性、非重试的 Anthropic 兼容 `invalid_request_error`，原生驱动继续要求零提前发送和恰好一次恢复请求。
- 验收结果：`pnpm test:e2e:desktop` 在最终最小实现上通过，覆盖普通队列、provider 错误后的同任务恢复、错误可见、精确一次发送、队列清空、输入恢复，以及既有 Human 问题、权限、任务文件和被动 HTML。全量回归通过：前端 114 文件/776 项；Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2；HEOR 188/188；开发合同 392/392；发布合同 54/54；类型检查、ESLint、Rust 格式、生产构建、`git diff --check` 和 41 来源/445 文件资源预检均通过。
- 范围、回滚与剩余风险：未改变 provider 重试/降级策略、提示词、模型请求正文、HEOR 公式、研究 schema、权限或研究文件；测试只使用随机 loopback 端口、隔离 HOME/XDG 和非秘密固定凭据，不访问公网或真实研究数据。回退本 loop 独立提交即可，无数据迁移。当前只覆盖确定性 400 `invalid_request_error`；限流、超时、网络断连和鉴权错误需分别建立可验证 loop。此证据来自测试特性调试构建，不是安装后 DMG 完整任务证据；本轮未生成安装包，安装包任务 UI 与导入到导出仍待后续 P1。

## Loop P1-TEST-001b11：真实项目导入、项目内任务与确定性报告导出

- 当前行为与目标：导入命令、任务执行和确定性报告导出分别有实现与分层测试，但没有一条真实 Tauri/WKWebView 证据把“外部项目导入受管副本—在该项目中新建并执行任务—生成可审计 DOCX/PDF/XLSX”连接起来。目标是验证现有业务路径，同时证明导入后的运行与导出不会改写外部源目录。
- 修改前失败测试与根因：先增加原生驱动合同，精确失败于缺少导入项目、源目录快照、项目内任务、报告导出和当前性审计的实路径。真实运行又暴露三个测试问题：注入的 Tauri invoke JavaScript 括号错误；测试误把 OpenCode 运行时派生的 project ID 当成 AI4HEOR 项目 ID；临时最小分析计划不符合完整 schema，产品因此正确隐藏下游报告动作。这些都是 E2E 驱动/夹具假设，未发现需要修改的业务缺陷。
- 最小修改：只扩展原生 E2E 驱动与静态合同。驱动复用现有 HEOR 验收夹具生成器建立明确标记为“合成验收数据”的完整项目，补入有界基准结果、不确定性结果、BIA 结果和报告包；通过原生 `import_project` 导入，用可见“项目内新建任务”动作执行本地 provider，再通过“研究与分析”的可见按钮生成三种报告。没有修改业务代码、用户界面、提示词、HEOR 公式、研究 schema、提供商协议或用户文件。
- 验收结果：定向合同与夹具测试 16/16，原生驱动语法检查通过；最终完整原生流程直接连续 2/2 通过，根级 `pnpm test:e2e:desktop` 重建后再完整通过。导入后记录的 `importedFrom` 指向外部源，实际任务作用于应用受管副本，OpenCode 会话目录与该项目一致；DOCX/PDF/XLSX 均存在且非空，报告审计返回 `outputsCurrent`；运行后外部源目录的相对路径与 SHA-256 快照不变。第一次最终根命令又准确拦截了验收夹具测试在打包 Skill 源码中生成的 4 个 `__pycache__`；先增加失败合同，再让 E2E 子进程设置 `PYTHONDONTWRITEBYTECODE=1`，同时在夹具验证模块动态加载 Skill 脚本前设置 `sys.dont_write_bytecode = True`。将本轮已生成缓存移入可逆临时隔离目录后，重跑 16/16 仍不产生缓存，41 来源/445 文件门禁和完整根命令通过，未放宽门禁。
- 范围、回滚与剩余风险：测试只使用临时目录、随机 loopback 端口和非秘密固定凭据，不访问公网、不使用真实研究数据。回退本 loop 独立提交即可，无数据迁移。一次较早未改变的原生运行在 60 秒内只发送了两条队列中的第一条，立即复跑与最终两次均通过；该间歇性队列时序风险仍保留，未通过放宽断言或屏蔽错误关闭。此证据是测试特性调试构建，不是安装后 DMG 完整任务 UI 证据；本轮不生成安装包。

## Loop P1-AI-001c：研究者可见的模型调用审计详情

- 当前行为与目标：`.openscience/model-calls.jsonl` 已保存内容无关、哈希链校验的调用记录，产物和运行也已有准确 `assistantMessageId` 关联键，但研究者只能看到内部 JSONL。目标是在产物溯源和运行记录中按该准确键展开对应调用，显示足够复核的调用事实；缺失与损坏必须明确，不得展示提示词、回答正文、原始 ID、哈希、凭据或 URL。
- 修改前失败测试与根因：先增加账本读取、详情组件、产物/运行接入及原生交互合同，定向测试准确失败于 `listModelCalls` 和 `ModelCallAudit` 不存在；原生验收最初又暴露两个测试设计问题：维护性 `rm` 命令按产品规则不属于研究运行，且用完整命令文本定位运行行不稳定。根因是现有读取端没有安全的本地校验桥接和产品详情组件，不是账本或准确关联键缺失。
- 最小修复：TypeScript 桥接只调用已有 `list_model_calls`，由原生命令先验证完整哈希链；新增可折叠详情展示 provider/model、完成时间、耗时、token/cache token、运行时报告费用及其供应商定义单位、固定提示版本、回复语言和研究约束是否被记录。产物溯源和运行记录只在存在准确 `assistantMessageId` 时显示入口；找不到对应记录时不猜测，账本读取失败时显示错误。原生夹具新增独立、无副作用、可记录的 `python3 -c 'print(1)'` 运行，隔离于一次授权/拒绝夹具；不修改模型请求、提示正文、权限规则、HEOR 公式、研究 schema 或用户数据。
- 验收结果：定向前端 26/26、桌面合同 14/14、类型检查和 ESLint 通过；真实 Tauri/WKWebView 在隔离任务中执行该运行，打开“运行记录”，展开唯一运行项及“模型调用记录”，并匹配准确的 loopback provider/model，随后继续完成既有队列、Human 问题、一次/拒绝/持久权限、重启恢复、provider 失败恢复、任务文件、被动 HTML、项目导入和确定性 DOCX/PDF/XLSX 导出。全量回归为前端 115 文件/781 项、HEOR 188/188、Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2、开发合同 394/394、发布合同 54/54；生产构建和 41 来源/445 文件预检通过。
- 边界、回滚与剩余风险：调用详情只读取本地审计账本，不发起网络请求，也不保存新的研究数据；旧记录没有关联键时不伪造入口。回退本 loop 独立提交即可，没有数据库或研究文件迁移，已存在账本继续保留。P1-AI-001c 的可见详情已完成，但当前“打开对话”只进入对应任务，尚不能精确滚动到原助手消息；该缺口单列 P1-AI-001d，必须使用准确消息键实现，不能按时间或最近回复猜测。本轮没有生成安装包，调试构建证据不替代安装后完整 UI 验收。

## Loop P1-AI-001d：从审计记录返回精确对话动作

- 当前行为与目标：产物溯源与运行记录已有准确 `assistantMessageId` 和可选 `toolCallId`，但“打开对话”只导航到任务路由。目标是使用该已有准确键返回产生记录的助手/工具动作；实时会话与重载后的历史必须一致，折叠工具组必须展开，缺失目标必须显式失败，不得按时间或最近回复猜测。
- 修改前失败测试与根因：先为实时折叠、历史恢复、折叠工具组、运行记录/产物路由状态和原生窗口路径增加失败测试，精确失败于历史 `Thread.index` 为空、工具组没有目标行、入口只传任务 ID。首轮原生运行又稳定发现运行记录面板打开时可能一直为空：运行完成通过 fire-and-forget 异步落盘，而页面只在挂载时查询一次，首次查询可能早于持久化完成。
- 最小修复：新增只处理有界内部标识的对话来源工具，最精确键为 `assistantMessageId + toolCallId`；实时事件和历史恢复建立同一索引，工具组只展开并标记精确行。入口通过 React Router 内部 state 传递标识，不写入 URL；会话加载完成后关闭遮挡面板并有界等待目标行挂载。运行账本在 `recordRun` 成功后递增内存 revision，已打开页面据此重新查询一次，不轮询、不改数据库/JSONL。没有修改模型请求、提示词、HEOR 公式、研究 schema、权限或研究数据。
- 失败关闭与兼容性：同时存在消息与工具标识时必须命中复合键，不能退回同一消息中的另一工具；标识为空、过长或含控制字符时拒绝；历史旧记录没有准确键时不伪造目标。页面找不到目标时显示本地化错误，而不是滚动到邻近内容。公开 SDK 类型、持久化格式和路由 URL 均未改变。
- 验收结果：失败测试转绿后，6 个定向前端文件 158/158、桌面静态合同 15/15、类型检查与 ESLint 通过。根级 `pnpm test:e2e:desktop` 重新构建测试特性二进制和 41 来源/445 文件资源，真实 Tauri/WKWebView 创建无副作用 Python 运行、在已打开账本中看到落盘记录、展开准确模型调用，再返回包含该完整命令的精确工具行且目标位于可见滚动区；随后原有队列、Human 输入、一次/拒绝/持久权限、provider 失败恢复、任务文件、HTML 被动预览、项目导入与确定性 DOCX/PDF/XLSX 导出全部通过。全量回归为前端 116 文件/791 项、HEOR 188/188、Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2、开发合同 395/395、发布合同 54/54。
- 回滚与剩余风险：回退本 loop 独立提交即可，无数据迁移或历史记录重写。一次较早的直接原生复跑再次出现“队列只发送第一条”的既有间歇性现象；最终完整根命令通过，但该风险保留为 P1-QUEUE-001，不能由本轮完成状态覆盖。当前证据来自测试特性调试构建，不是已安装 DMG 完整任务 UI；本轮不生成安装包。

## Loop P1-QUEUE-001：排队消息偶发只执行一条

- 当前行为与目标：原生完整流程偶发只把队列中的第一条消息送到模型，立即复跑可能通过。目标是稳定复现真实时序根因，并保证一轮回复只释放一条排队消息；不能靠延长等待时间、自动重试或放宽断言隐藏。
- 修改前失败测试与根因：固定 OpenCode 1.17.13 在 runner 结束时先发布 `session.status` 且状态为 `idle`，随后再发布兼容事件 `session.idle`。`OpenCodeClient` 原先把两者都归一化成应用级 `session.idle`。新增协议夹具和断言后，测试稳定得到 2 个终止事件而不是 1 个。第一个事件启动下一条排队消息后，来自上一轮的第二个事件会清除新一轮运行锁；界面可继续取出后续消息，而 OpenCode 的原 runner 仍在收尾，形成“消息已写入历史但没有独立 provider 执行”的丢失竞态。
- 最小修复：SDK 继续转发 `session.status(busy/retry)`，但不再把冗余的 `session.status(idle)`转换为终止事件；专用 `session.idle` 是唯一终止信号，并承担流式缓存和步骤状态清理。没有修改队列 store、UI、提示词、provider 重试/降级策略、HEOR 公式、研究 schema、数据库或用户文件。
- 验收结果：修复前新增测试稳定红灯，修复后 SDK/运行状态 108/108、桌面合同 15/15、类型检查和 ESLint 通过。根级 `pnpm test:e2e:desktop` 重新构建资源与测试特性二进制，真实 Tauri/WKWebView 完成队列排序、删除、逐条发送及现有 provider 失败恢复、Human 输入、权限、任务文件、项目导入和确定性 DOCX/PDF/XLSX 导出。全量回归为前端 116 文件/791 项、HEOR 188/188、Rust 377 通过/1 项既有公网测试忽略及资源暂存 2/2、开发合同 395/395、发布合同 54/54；类型检查、ESLint、Rust 格式、生产构建、diff 和 41 来源/445 文件资源预检通过。
- 回滚与边界：回退本 loop 独立提交即可，无迁移和历史数据改写。修复依据产品固定打包的 OpenCode 协议；不宣称兼容未验证、只发布 `session.status(idle)` 而不发布专用 `session.idle` 的其他运行时。当前是调试特性构建的真实原生证据，不替代安装后 DMG 完整任务 UI 验收；本轮不生成安装包。

## Loop P1-SCI-001a：短期确定性决策树 Skill 与自然语言任务执行

- 当前行为与目标：首版决策树内核已有独立 schema、人工核算黄金案例、逐节点轨迹和 CLI 哈希重放，但没有第一方 Skill，`heor-workbench` 也不会把研究者已经选定的一年内有限非重复事件树路由到该能力。目标是在不改变既有 Markov/PSM 公式或 schema 的前提下，建立可发现、可多语言说明、可验证、可执行和可精确复算的任务路径。
- 修改前失败测试与根因：新增核心 Skill 合同首先因 `runtime/skills/core/heor-decision-tree/SKILL.md` 不存在而失败；第一方运行器合同随后稳定失败，因为旧运行器无条件把任何计划交给 Markov `input_provenance` 审计，决策树被报告为缺少周期、转移矩阵和 Markov 字段。根因是计算内核先于产品 Harness 和任务运行路径交付，并非公式或黄金结果错误。
- 最小修改：新增 `$heor-decision-tree` 的 Skill、七语种目录说明、严格无数值模板、方法边界、验证/精确重放脚本和 Skill Creator 元数据；`heor-workbench` 只在研究者已选择一年内有限非重复事件树时路由到它。复用既有 `run_first_party_analysis.py`：先识别 `analysis_type=decision_tree`，由决策树内核自身执行来源/拟议假设、拓扑和数值合同，原子写入独立 `heor/results/decision-tree.json`；Markov 继续沿用原 `heor/results/base-case.json` 与完整输入溯源审计。启动审计要求完整当前 53 个第一方 Skill、新 Skill 和 `decision_tree.py`；缺失任一当前能力即本地可恢复失败。没有增加 DSA/PSA、科学批准、自动方法选择、报告口径或研究 schema 迁移。
- 科学验收：黄金案例由两条可人工核算路径组成，比较策略期望成本为 `0.6×1000 + 0.4×3000 = 1800`，干预策略为 `0.75×2200 + 0.25×5000 = 2900`；正式运行结果绑定原计划字节的 SHA-256。验证器重算全部输出，任意把比较策略成本改动 1 都会 fail-closed。每个概率、成本和 QALY 必须声明至少一个来源标识或顶层 `proposed` 假设；来源标识在正式使用前仍须由现有证据/输入溯源记录解析，结构通过不代表证据适用或研究者接受。
- 验证结果：Skill Creator 官方校验通过；核心 Skill 11/11、第一方运行器 4/4、HEOR 188/188、Rust 启动审计 5/5、完整前端 791/791、Rust 378 通过/1 项既有公网测试忽略及资源暂存 2/2、开发合同 397/397、发布合同 54/54、类型检查、ESLint、Rust 格式、生产构建、diff 和 41 来源/450 文件预检均通过。根级 `pnpm test:e2e:desktop` 重建后通过，证明新增资源随真实 Tauri/WKWebView 启动且既有任务、队列、Human 输入、权限、provider 恢复、文件、项目导入和确定性 DOCX/PDF/XLSX 报告导出无回归。
- 回滚与剩余风险：回退本 loop 独立提交即可，无数据迁移；既有 Markov/PSM 计划和结果路径未改。决策树结果尚未进入专用桌面复核卡、报告包或复现包，也不支持 DSA/PSA、复发、状态占用、周期、折现或一年以上时域；这些继续作为 P1-SCI-001b 及后续独立 loop，不能用通用 JSON 预览或模型解释冒充完成。本轮没有生成安装包。

## Loop P1-SCI-001b：短期确定性决策树专用桌面复核

- 当前行为与目标：P1-SCI-001a 已能从自然语言任务生成、校验和运行 `heor/decision-tree-plan.json`，但“研究与分析”只认识 Markov `heor/analysis-plan.json`。有效决策树会落入错误的 Markov 解析路径，研究者无法在专用界面分辨当前输入、确定性结果和结果是否过期。目标是只读复核既有第一方计算，不复制公式、不让模型解释替代计算，也不新建形式化审批。
- 修改前失败测试与根因：先新增组件合同，稳定失败于 `DecisionTreeReview` 不存在。根因是决策树计算内核、Skill 和任务运行路径已交付，但桌面工件路由仍只有单一 Markov 分支。通用 JSON 预览无法判断结果是否对应当前输入，也无法防止旧结果被误读为当前结果。
- 最小修复：新增独立只读复核组件；面板在进入 Markov 解析器前检测专用决策树计划。界面从计划汇总策略、参考案例、短期时域、实际被引用的来源标识和 `proposed` 假设；从第一方结果读取策略成本、QALY及相对基线的增量成本、增量 QALY和 ICER。数值只在结果 `input_sha256` 与计划原始字节 SHA-256 完全一致时展示；结果缺失、结构损坏或哈希过期时不展示其中的数字，只提供打开当前计划及通过 `$heor-decision-tree` 重新校验运行的自然语言入口。没有修改 Python 公式、schema、计划或结果文件、Human 记录、权限、数据库或模型请求协议。
- 科学与产品边界：TypeScript 只解析并展示确定性引擎已写入的结果，不重算概率树，也不把结构检查、来源标识存在或哈希一致描述为证据适用、参考案例合规、方法学有效或研究结论。决策树专用面板与 Markov 面板互斥，既有 Markov 研究流程和结果路径不变。当前结果和计划都可从面板直接打开核对；缺失/损坏/过期状态失败关闭。
- 验收结果：失败测试转绿，决策树 3/3 和既有复核面板 28/28 定向测试通过；全量为前端 794/794、HEOR 188/188、Rust 378 通过/1 项既有公网测试忽略及资源暂存 2/2、开发合同 397/397、发布合同 54/54，类型检查、ESLint、生产构建、diff 及 41 来源/450 文件资源预检通过。根级 `pnpm test:e2e:desktop` 重建真实测试特性 Tauri/WKWebView，并通过既有任务、排队、Human 输入、权限、provider 失败恢复、任务文件、被动 HTML、项目导入和确定性 DOCX/PDF/XLSX 导出分支。
- 回滚与剩余风险：回退本 loop 独立提交即可，无数据迁移或历史结果改写。当前原生 E2E 证明新增前端进入真实桌面构建且既有主要流程无回归，但尚未为决策树卡本身建立安装后 DMG 可视自动化；报告包、复现包、DSA/PSA、复发、周期、状态占用、折现和一年以上时域仍未支持，继续作为独立工作。本轮不生成安装包。

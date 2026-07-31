# AI4HEOR 工程基线与闭环记录（2026-07-31）

## 基线

- 分支：`codex/heor-workbench`
- P1-AI-001b2 开始前的已提交基线：`38babd9`；P1-AI-001b3 实施前的已提交基线：`bc71b1b`；P1-TEST-001b1 实施前的已提交基线：`38a5687`。更早已完成业务修复均保留为独立提交，本轮不重复修改。
- 基线原则：在现有 Open Science/Tauri 技术栈上增量推进；AI 负责辅助推理，正式研究计算由可验证的确定性模块完成；科学、隐私、兼容性和公开接口决策保留 Human-in-the-loop。
- 已完成 loop 范围：不可信 HTML 预览边界、同主版本 JavaScript CPU 拒绝服务补丁、安装后 OpenCode 的鉴权 HTTP 就绪证据、安装后前端 bootstrap 证据合同、经研究者确认的两策略 PSA 零 INMB 并列口径、PPTX 预览中 ECharts `lines` 系列通告的不可达性门禁、经研究者确认后实现的首版短期确定性决策树内核、不含对话正文的模型调用用量/费用元数据账本，以及应用固定 HEOR 前导提示的精确指纹和回复语言记录。实际工作区 Harness 指纹、模型调用与研究产物关联、决策树 DSA/PSA、桌面审查、报告和 UI 集成未在本轮扩展。

## 当前架构与完成度

| 层 | 当前实现 | 本轮状态 |
| --- | --- | --- |
| 桌面与前端 | Tauri 2 + React/TypeScript/Vite | 保持原架构；HTML 预览安全边界已修复 |
| AI 调用与任务执行 | OpenCode 本地 sidecar，HTTP/SSE，模型提供商可配置 | 使用固定上游源码、补丁与 Bun 构建 `1.17.13-ai4heor.1`；主模型请求在插件完成 system 转换后、供应商调用前，将精确有序系统块的内容无关 SHA-256 与块数绑定到对应助手消息；完成调用的提供商、模型、时间、token、缓存 token、结束原因和运行时报告费用已归一化；新的 HEOR 调用记录固定前导提示的精确 SHA-256 与回复语言；sidecar 每次启动都校验并额外加载应用自有产品 Harness，项目原有指令文件不被覆盖 |
| HEOR 确定性计算 | Python 版本化计算模块 + Rust 授权、审计和哈希绑定 | 新增独立决策树 schema 0.1.0 与 CLI 重放；既有 Markov/PSM 公式、参数和随机数列不变 |
| 数据与溯源 | 本地 JSON/JSONL/SQLite、证据与参数来源、运行记录和报告导出 | 工作区内 `.openscience/model-calls.jsonl` 保存内容无关、追加式、哈希链调用账本；新的模型工具产物和本地运行记录以可选 `assistantMessageId` 精确连接对应调用，并以 `toolCallId` 区分具体工具动作；旧记录和非模型运行不伪造关联 |
| Human-in-the-loop | 关键科学定义、证据采用、结构与发布决策由研究者确认 | PSA 并列口径在研究者同意后才实施 |
| 文件预览 | React inspector + Tauri loopback preview server | HTML 改为被动展示；源码查看和外部打开保留 |

当前仓库已有主要单元/组件、确定性 HEOR、Rust 原生与资源门禁测试。macOS 与 Windows 发布脚本已有真实主机级安装、进程、工作区和清理检查，并已补上 OpenCode 鉴权 HTTP 与前端 bootstrap 合同。新的测试专用 macOS WebDriver 变体已在真实 Tauri/WKWebView 中点击“新建任务”和“插件与技能”，但完整的安装后任务执行、HTML 预览、权限交互和导入到导出 E2E 仍未建立，不能由基础导航冒烟、Vitest/jsdom、进程或 bootstrap 结果替代。

## 问题与风险清单

| 编号 | 优先级 | 状态 | 证据与影响 |
| --- | --- | --- | --- |
| P0-SEC-001 | P0 | 本轮已修复 | `FilePreviewInspector` 原先向不可信 HTML 授予 `allow-scripts`，本地预览响应无 CSP，可能导致脚本执行和研究数据外发 |
| P0-AI-002 | P0 | 已修复 | 导入项目原有 `AGENTS.md` 会被 OpenCode 作为项目级系统指令加载，而旧实现只在缺文件时复制产品 Harness，导致产品科研与数据边界可能整体缺席；现保留用户文件并在每次 sidecar 启动时 fail-closed 校验、额外加载应用自有 Harness |
| P1-SEC-002a | P1 | 已修复 | `brace-expansion 1.1.15 / 2.1.1` 受 CPU 拒绝服务通告影响；已同主版本升级并加入发布门禁 |
| P1-SEC-002b | P1 | 待单独处理 | `brace-expansion` OOM 通告当前只标记 5.0.8 为修复版；旧主版本跨版替换需独立兼容性决策，漏洞代码未进入当前 Tauri 前端产物 |
| P1-TEST-001a | P1 | macOS x64 原生执行通过；Windows 待执行 | 安装包首启过去只证明 OpenCode 进程存在；现要求未授权健康请求返回 401，且证据不保存端口或密码 |
| P1-TEST-001b | P1 | 基础原生导航已完成；完整流程待后续 loop | 测试专用 macOS Tauri WebDriver 已验证 IPC 桥接与两个真实侧边栏点击；任务执行、HTML 预览、权限和导入到导出仍缺安装后自动化 E2E |
| P1-TEST-001c | P1 | macOS x64 原生执行通过；Windows 待执行 | 安装包首启过去没有证明 WebView 已挂载 AppShell、执行 JavaScript 并通过 Tauri IPC 取得本地服务地址；现从隔离首启的应用私有日志生成无正文、无端口的布尔证据 |
| P1-SCI-001 | P1 | 首版确定性内核已完成；端到端流程待后续 loop | 已有独立 schema、黄金案例、输入溯源、逐节点计算轨迹、增量前沿、CLI 哈希重放与安装包资源映射；Skill、桌面复核、报告和复现包尚未连接 |
| P1-SCI-002 | P1 | 待单独处理 | 亚组分析尚缺完整的预设、来源绑定、逐亚组结果与复核合同 |
| P1-SCI-003 | P1 | 已修复 | 两策略 PSA 旧汇总使用 `INMB >= 0`，将零值并列同时计入干预成本效果概率，与同一输出中单独报告并列的决策不确定性表冲突 |
| P1-AI-001a | P1 | 本轮已修复 | OpenCode 已返回提供商、模型、时间、token、缓存 token、结束原因和运行时报告费用，但 AI4HEOR 原先丢弃；现已建立内容无关、幂等、哈希链本地账本 |
| P1-AI-001b1 | P1 | 本轮已修复 | 新的 HEOR 调用现在记录应用固定前导提示的精确 SHA-256、模板 ID 和回复语言；研究者文本及其哈希都不进入账本 |
| P1-AI-001b2 | P1 | 已修复并通过 macOS x64 安装包验证 | 研究者已同意方案 A 和本地派生数据边界；固定 OpenCode 1.17.13 源码的最小补丁在供应商请求前把插件处理后的最终系统块指纹写入准确助手消息；当前 DMG 已完成实际 provider 请求、持久化助手消息和重算指纹的三方一致性校验 |
| P1-AI-001b3 | P1 | 已修复 | OpenCode 工具事件现在保留准确助手消息与工具调用 ID；直接产物、本地运行及其输出原样持久化可选关联键，不按时间猜测或回填历史 |
| P1-AI-001c | P1 | 待单独处理 | 账本尚无面向研究者的可见审计界面；不得以内部 JSONL 代替产品层可解释性 |
| P1-LEGAL-001 | P1 | 已修复 | `brace-expansion` 锁文件升级后，打包的 npm 许可证清单仍绑定旧锁文件哈希和旧版本；现已从当前锁文件重生成并通过资源合同 |
| P2-SEC-003 | P2 | 待评估 | Tauri 主应用全局 CSP 仍为空；本轮已在不可信 HTML 的两个实际渲染入口建立独立限制。全局 CSP 会影响 loopback、SSE 和资源加载，需另行做兼容性测试 |
| P2-SEC-004 | P2 | 已评估；当前不可达 | ECharts 5.6.0 命中 `GHSA-fgmj-fm8m-jvvx`，但通告需要 `lines` 系列；当前 `pptx-preview` 只从导入文件构造 `line` / `bar` / `pie`，已用发布门禁防止未复审的可达性变化 |

## 优化任务列表

1. P0-SEC-001：完成 HTML 被动预览边界并建立回归合同（已完成）。
2. P1-TEST-001a：首启 OpenCode 鉴权 HTTP 就绪合同已在新 macOS x64 DMG 原生执行通过；Windows 仍需在原生 runner 产生证据。
3. P1-TEST-001b：基础原生导航冒烟已完成；后续分别补任务执行、HTML 预览、权限与导入到导出，不用一个过大 E2E 隐藏失败点。
4. P1-TEST-001c：安装后前端 bootstrap 合同已在新 macOS x64 DMG 原生执行通过；Windows 待执行，且不得据此宣称完整可视 E2E 已完成。
5. P1-SEC-002：CPU 型通告已完成同主版本修复；OOM、UUID 和 React Router 通告继续按实际可达路径逐个处置，不强制整树升级。ECharts `lines` 系列通告已证明当前 PPTX 路径不可达。
6. P1-SCI-003：统一两策略 PSA 的零 INMB 并列口径（已完成）。
7. P1-SCI-001：首版确定性内核已完成；后续分别为 Skill、桌面审查、报告与复现包建立独立合同。P1-SCI-002 仍需先建立人工可核算基准，禁止与界面修复混做。
8. P0-AI-002：产品 Harness 已改为每次运行必定校验和叠加加载，用户/项目指令保留但不得替代产品治理边界（已完成）。
9. P1-AI-001a、P1-AI-001b1、P1-AI-001b2 和 P1-AI-001b3：内容无关模型调用账本、固定 HEOR 前导提示指纹、当次实际最终系统块指纹及模型调用到具体工具产物/运行的准确关联已完成；P1-AI-001c 单独建立研究者可见审计界面，不以内部标识符替代可解释产品界面。
10. P2-SEC-003：评估主应用全局 CSP；仅在不破坏本地服务和模型流式连接时实施。
11. P1-LEGAL-001：依赖锁文件变更后必须重生成许可证清单，其锁文件 SHA-256 不一致时由现有打包资源合同 fail-closed（已完成）。

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
| 系统上下文安装包执行门禁 | `verify_packaged_opencode_fixture.py` + macOS 构建工作流 | 单元合同 2/2 与 CI 接线合同通过；当前 1.0.0 x64 DMG 实际执行通过：2 次本地 provider 请求、主请求流式响应、回复标记命中，实际 system 块与对应助手消息的 `ai4heor.system-context/v1` 指纹一致 |
| 当前 macOS x64 DMG | `tauri build --target x86_64-apple-darwin --bundles dmg` + `verify_macos_package.py --verify-first-launch` | 由干净提交 `feffae7` 构建；96,464,683 字节，SHA-256 `eb8f43c403335457c153c4ebb7e07d847669bc2810886df848e9ce34da22bfba`；445 个资源逐字节一致，包内 HEOR 188/188，OpenCode `1.17.13-ai4heor.1`，隔离首启、HTTP 401、AppShell/JavaScript/Tauri IPC 和工作区隔离通过；发布证据已在同一干净提交上生成并校验；无可用 Developer ID 签名，仅供内部测试 |
| 产物关联修复前复现 | SDK、provenance、run 定向测试及 Rust 定向编译 | 前端 7 项失败；Rust 10 处编译失败，准确证明工具事件、桥接和持久记录均缺少关联字段 |
| 产物关联定向回归 | `vitest run opencode-client.node.test.ts provenance.test.ts runs.test.ts` + `cargo test ... provenance::tests` + `cargo test ... runs::tests` | 前端 43/43、Rust 6/6 与 9/9 通过；覆盖直接写入、`apply_patch`、本地运行、运行输出、Tauri 参数、旧/远程记录兼容及异常标识拒绝 |
| 产物关联全量回归 | 前端、Rust、HEOR、开发合同、发布合同、类型、ESLint、Rust 格式、生产构建、资源预检 | 前端 113 个文件、770/770；Rust 377 通过/1 项既有忽略；HEOR 188/188；开发合同 380/380；发布合同 46/46；其余全部通过；41 个来源/445 个文件 |

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
- 剩余风险：该测试驱动开发构建，不是当前 DMG 中的安装后产品字节；当前 CI 只在 Intel macOS 运行该冒烟。它只证明 Tauri 桥接和两个基础导航操作，不证明模型任务、消息队列、Human-in-the-loop、HTML 预览、权限交互、导入/导出或科学计算流程已完成端到端验证。这些必须作为 P1-TEST-001b 的后续独立 loop。

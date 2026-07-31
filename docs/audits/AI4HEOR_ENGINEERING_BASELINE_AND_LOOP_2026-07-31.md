# AI4HEOR 工程基线与闭环记录（2026-07-31）

## 基线

- 分支：`codex/heor-workbench`
- 已提交业务基线：`73858d60690d199f6e70f88300d35a288d956447`
- 基线原则：在现有 Open Science/Tauri 技术栈上增量推进；AI 负责辅助推理，正式研究计算由可验证的确定性模块完成；科学、隐私、兼容性和公开接口决策保留 Human-in-the-loop。
- 本轮范围：仅修复不可信 HTML 在应用内预览时可能执行脚本并发起外部请求的问题，不修改科学计算、模型适配、研究数据或其他文件预览。

## 当前架构与完成度

| 层 | 当前实现 | 本轮状态 |
| --- | --- | --- |
| 桌面与前端 | Tauri 2 + React/TypeScript/Vite | 保持原架构；HTML 预览安全边界已修复 |
| AI 调用与任务执行 | OpenCode 本地 sidecar，HTTP/SSE，模型提供商可配置 | 未修改 |
| HEOR 确定性计算 | Python 版本化计算模块 + Rust 授权、审计和哈希绑定 | 未修改；既有回归保持通过 |
| 数据与溯源 | 本地 JSON/JSONL/SQLite、证据与参数来源、运行记录和报告导出 | 未修改 |
| Human-in-the-loop | 关键科学定义、证据采用、结构与发布决策由研究者确认 | 未修改 |
| 文件预览 | React inspector + Tauri loopback preview server | HTML 改为被动展示；源码查看和外部打开保留 |

当前仓库已有完整的主要单元/组件、确定性 HEOR、Rust 原生与资源门禁测试；真实安装包桌面端 E2E 仍不是自动化基线的一部分，不能由 Vitest/jsdom 结果替代。

## 问题与风险清单

| 编号 | 优先级 | 状态 | 证据与影响 |
| --- | --- | --- | --- |
| P0-SEC-001 | P0 | 本轮已修复 | `FilePreviewInspector` 原先向不可信 HTML 授予 `allow-scripts`，本地预览响应无 CSP，可能导致脚本执行和研究数据外发 |
| P1-SEC-002 | P1 | 待单独处理 | 生产依赖存在已知安全通告，需要先做可达性和兼容性分析，不能强制整树升级 |
| P1-TEST-001 | P1 | 待单独处理 | 缺少安装后真实 Tauri/OpenCode/权限/导入到导出的自动化 E2E |
| P1-SCI-001 | P1 | 待单独处理 | 尚缺独立的确定性决策树模块及人工可核算固定案例合同 |
| P1-SCI-002 | P1 | 待单独处理 | 亚组分析尚缺完整的预设、来源绑定、逐亚组结果与复核合同 |
| P1-AI-001 | P1 | 待单独处理 | 模型调用的提示词版本、token/费用和产物关联追踪仍不完整 |
| P2-SEC-003 | P2 | 待评估 | Tauri 主应用全局 CSP 仍为空；本轮已在不可信 HTML 的两个实际渲染入口建立独立限制。全局 CSP 会影响 loopback、SSE 和资源加载，需另行做兼容性测试 |

## 优化任务列表

1. P0-SEC-001：完成 HTML 被动预览边界并建立回归合同（已完成）。
2. P1-TEST-001：建立最小真实桌面 E2E，覆盖启动、任务、HTML 预览、OpenCode 连接与导出。
3. P1-SEC-002：按实际可达路径处置依赖通告，每个升级独立验证。
4. P1-SCI-001 / P1-SCI-002：分别建立人工可核算基准后再实现，禁止与界面修复混做。
5. P1-AI-001：在不记录密钥和敏感输入的前提下补齐模型调用审计合同。
6. P2-SEC-003：评估主应用全局 CSP；仅在不破坏本地服务和模型流式连接时实施。

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


# AI4HEOR 工程基线与闭环记录（2026-07-31）

## 基线

- 分支：`codex/heor-workbench`
- 已提交业务基线：`73858d60690d199f6e70f88300d35a288d956447`
- 基线原则：在现有 Open Science/Tauri 技术栈上增量推进；AI 负责辅助推理，正式研究计算由可验证的确定性模块完成；科学、隐私、兼容性和公开接口决策保留 Human-in-the-loop。
- 已完成 loop 范围：不可信 HTML 预览边界、同主版本 JavaScript CPU 拒绝服务补丁，以及安装后 OpenCode 的鉴权 HTTP 就绪证据。均不修改科学计算、模型适配、研究数据或研究流程。

## 当前架构与完成度

| 层 | 当前实现 | 本轮状态 |
| --- | --- | --- |
| 桌面与前端 | Tauri 2 + React/TypeScript/Vite | 保持原架构；HTML 预览安全边界已修复 |
| AI 调用与任务执行 | OpenCode 本地 sidecar，HTTP/SSE，模型提供商可配置 | 业务运行逻辑未修改；安装包首启门禁新增鉴权 HTTP 就绪证明 |
| HEOR 确定性计算 | Python 版本化计算模块 + Rust 授权、审计和哈希绑定 | 未修改；既有回归保持通过 |
| 数据与溯源 | 本地 JSON/JSONL/SQLite、证据与参数来源、运行记录和报告导出 | 未修改 |
| Human-in-the-loop | 关键科学定义、证据采用、结构与发布决策由研究者确认 | 未修改 |
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
| P1-SCI-001 | P1 | 待单独处理 | 尚缺独立的确定性决策树模块及人工可核算固定案例合同 |
| P1-SCI-002 | P1 | 待单独处理 | 亚组分析尚缺完整的预设、来源绑定、逐亚组结果与复核合同 |
| P1-AI-001 | P1 | 待单独处理 | 模型调用的提示词版本、token/费用和产物关联追踪仍不完整 |
| P2-SEC-003 | P2 | 待评估 | Tauri 主应用全局 CSP 仍为空；本轮已在不可信 HTML 的两个实际渲染入口建立独立限制。全局 CSP 会影响 loopback、SSE 和资源加载，需另行做兼容性测试 |

## 优化任务列表

1. P0-SEC-001：完成 HTML 被动预览边界并建立回归合同（已完成）。
2. P1-TEST-001a：首启 OpenCode 鉴权 HTTP 就绪合同已完成；下一次新包必须在原生 macOS/Windows 验证器中产生该证据。
3. P1-TEST-001b：建立最小真实桌面可视 E2E，覆盖任务、HTML 预览、权限与导入。
4. P1-SEC-002：CPU 型通告已完成同主版本修复；OOM、ECharts、UUID 和 React Router 通告继续按实际可达路径逐个处置，不强制整树升级。
5. P1-SCI-001 / P1-SCI-002：分别建立人工可核算基准后再实现，禁止与界面修复混做。
6. P1-AI-001：在不记录密钥和敏感输入的前提下补齐模型调用审计合同。
7. P2-SEC-003：评估主应用全局 CSP；仅在不破坏本地服务和模型流式连接时实施。

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

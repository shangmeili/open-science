# AI4HEOR source, Skill, plugin, MCP, data, and asset authorization audit

Audit date: 2026-07-21
Distribution target: AI4HEOR 1.0.0 Intel macOS and Windows x64 internal test builds
Decision: **internal testing allowed; public redistribution blocked**

## Scope and decision rule

The audit covers tracked source, packaged first-party Skills, reviewed external
source decisions, npm and Cargo dependencies, bundled
OpenCode and uv executables, fonts, the HEOR knowledge base, examples, screenshots,
and the supplied AI4HEOR logo and product-owner contact card. A public URL or open repository is treated as a
locator only. Distribution requires an applicable license or rights record for
the exact bytes and preservation of all required notices.

## Findings

| Content class | Current evidence | Packaged | Decision |
| --- | --- | ---: | --- |
| Inherited Open Science source and AI4HEOR changes | Root MIT license; upstream `master` license is MIT | Yes | Allowed under MIT with notice |
| First-party core Skills | 52 active Skill directories; project-authored under root MIT | Yes | Allowed; embedded third-party notices preserved |
| Citation-formatting renderer | Project-authored Rust/Markdown renderer under root MIT; consumes the bounded CSL-JSON-compatible local library but includes no file from the CC BY-SA 3.0 CSL styles repository | Yes | Allowed; three AI4HEOR-owned profiles, source hashes, metadata warnings, and Human review boundary |
| Target-journal submission check | Project-authored Rust/Markdown renderer and portable validator under root MIT; official author-guide pages are recorded as links and local researcher-supplied snapshots only | Yes | Allowed; no journal instructions, reporting checklist, CSL style, or submission template is bundled or redistributed |
| Research-presentation renderer | Project-authored Rust OOXML/ZIP renderer and portable Python validator under root MIT; no Anthropic presentation code or asset is included | Yes | Allowed; macro-free first-party output path |
| Research-report renderer | Project-authored source-bound DOCX/PDF renderer; `printpdf` 0.11.3 (MIT), its reviewed `lopdf` 0.44.0 chain, and Source Han Sans CN 2.005R (OFL-1.1) are pinned and audited | Yes | Allowed for internal testing; generated documents remain awaiting human review |
| HEORAgent-informed evidence Skill | First-party rewrite; pinned upstream revision and MIT notice retained | Yes | Allowed; upstream package itself is not shipped |
| External Skill cache | Removed after the source review; no `runtime/skills/external/` tree remains | No | External source is not retained |
| External-adapter release registry | Schema 1.1.0, release-only, empty | Registry only | No external code loaded; unfinished and excluded sources are not user options |
| MCP servers | No third-party MCP config, binary, source tree, or dependency is mapped as a resource | No | Native bounded connectors only |
| Anthropic `docx` / `pdf` / `pptx` / `xlsx` Skills | Revision `9d2f1ae187231d8199c64b5b762e1bdf2244733d` was checked directory by directory. Each `LICENSE.txt` is an Anthropic service-linked source-available license, not Apache-2.0, and expressly prohibits retaining copies outside the Services, reproduction, derivative works, and redistribution. The local source cache is removed | No | The four upstream Skill trees cannot be copied into AI4HEOR. Preserve the corresponding capability through independently authored, first-party document workflows and deterministic renderers |
| npm production dependency universe | 266 packages: 227 MIT, 15 ISC, 6 BSD-3-Clause, 6 Apache-2.0, 3 OFL-1.1, 8 other compatible/multi-license expressions, 1 unresolved | Compiled/bundled as applicable | Internal test only until full notices and unresolved item are closed |
| `buffers@0.1.1` | Package metadata contains no license field or license file; pulled through `exceljs > unzipper > binary` | Potentially | Public-release blocker |
| Cargo locked dependency universe | 564 third-party packages plus the workspace crate; declared expressions recorded in inventory | Compiled as target requires | Internal test only until exact shipped-target notice corpus is bundled |
| OpenCode 1.17.13 | Pinned sidecar; upstream tag declares MIT | Yes | Allowed with exact license notice still to bundle |
| uv 0.11.26 | Pinned sidecar; upstream tag offers Apache-2.0 OR MIT | Yes | Allowed after selected license and notice are bundled |
| Bundled Chinese HEOR knowledge base | 25 first-party Markdown learning documents plus manifest; sources are cited/linked, not copied wholesale | Yes | Allowed as project-authored synthesis; current-source verification remains a scientific requirement |
| App and report fonts | Fontsource packages for Inter, JetBrains Mono, Source Serif 4 declare OFL-1.1; Source Han Sans CN 2.005R is pinned and its exact OFL-1.1 text is bundled | Yes | Source Han report-font notice is complete; remaining UI font notice corpus is a public-release task |
| Documentation screenshots/showcase images | Tracked in the MIT source history; no separate third-party attribution found | Repository only | Keep under source license; re-audit before public marketing reuse |
| AI4HEOR logo | Product owner supplied and explicitly requested project use | Yes | Internal test authorized; public rights record missing |
| Product-owner contact card | Product owner supplied and explicitly requested inclusion in the About page | Yes | Internal test authorized; public redistribution and third-party mark rights require confirmation |

## Skills, plugins, and MCP controls

First-party Skills are the only Skill pack mapped into Tauri resources. The app
validates the core pack, and the admission registry fails closed. The new
capability-authoring harness creates candidates only under
`capabilities/candidates/`; instruction-only candidates deny network, secrets,
commands, and outside-workspace access and remain inactive. No assistant or
candidate can create an app-owned activation decision.

Plugin support is architectural, not a distribution grant. No Codex connector
plugin listed by the development environment is copied into the application.
Any future plugin or MCP must have pinned provenance, compatible license,
permissions, egress, data-classification, security, method, test, platform, and
kill-switch evidence before admission.

## Remaining work before public release

1. Generate and bundle exact license and copyright texts for the final Intel
   macOS dependency closure, including sidecars and fonts.
2. Remove/replace `buffers@0.1.1` or obtain authoritative license evidence.
3. Record logo rights and trademark clearance.
4. Rebuild, sign, notarize, and inspect the mounted final DMG; compare every
   executable/resource hash with the release evidence.
5. Compare the final Intel macOS and Windows x64 package inventories with this
   source audit. Repeat the audit before adding Linux or Apple Silicon packages.

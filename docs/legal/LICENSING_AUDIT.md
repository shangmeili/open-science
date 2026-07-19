# AI4HEOR source, Skill, plugin, MCP, data, and asset authorization audit

Audit date: 2026-07-19  
Distribution target: Intel macOS internal test build  
Decision: **internal testing allowed; public redistribution blocked**

## Scope and decision rule

The audit covers tracked source, packaged first-party Skills, reviewed external
source decisions, npm and Cargo dependencies, bundled
OpenCode and uv executables, fonts, the HEOR knowledge base, examples, screenshots,
and the supplied AI4HEOR logo. A public URL or open repository is treated as a
locator only. Distribution requires an applicable license or rights record for
the exact bytes and preservation of all required notices.

## Findings

| Content class | Current evidence | Packaged | Decision |
| --- | --- | ---: | --- |
| Inherited Open Science source and AI4HEOR changes | Root MIT license; upstream `master` license is MIT | Yes | Allowed under MIT with notice |
| First-party core Skills | 48 active Skill directories after this change; project-authored under root MIT | Yes | Allowed; embedded third-party notices preserved |
| Research-presentation renderer | Project-authored Rust OOXML/ZIP renderer and portable Python validator under root MIT; no Anthropic presentation code or asset is included | Yes | Allowed; macro-free first-party output path |
| HEORAgent-informed evidence Skill | First-party rewrite; pinned upstream revision and MIT notice retained | Yes | Allowed; upstream package itself is not shipped |
| External Skill cache | Removed after the source review; no `runtime/skills/external/` tree remains | No | External source is not retained |
| External-adapter release registry | Schema 1.1.0, release-only, empty | Registry only | No external code loaded; unfinished and excluded sources are not user options |
| MCP servers | No third-party MCP config, binary, source tree, or dependency is mapped as a resource | No | Native bounded connectors only |
| Anthropic document Skills | Incompatible source-available terms recorded in the read-only decision trail; local source cache removed | No | Permanently excluded; first-party replacements only |
| npm production dependency universe | 266 packages: 227 MIT, 15 ISC, 6 BSD-3-Clause, 6 Apache-2.0, 3 OFL-1.1, 8 other compatible/multi-license expressions, 1 unresolved | Compiled/bundled as applicable | Internal test only until full notices and unresolved item are closed |
| `buffers@0.1.1` | Package metadata contains no license field or license file; pulled through `exceljs > unzipper > binary` | Potentially | Public-release blocker |
| Cargo locked dependency universe | 564 third-party packages plus the workspace crate; declared expressions recorded in inventory | Compiled as target requires | Internal test only until exact shipped-target notice corpus is bundled |
| OpenCode 1.17.13 | Pinned sidecar; upstream tag declares MIT | Yes | Allowed with exact license notice still to bundle |
| uv 0.11.26 | Pinned sidecar; upstream tag offers Apache-2.0 OR MIT | Yes | Allowed after selected license and notice are bundled |
| Bundled Chinese HEOR knowledge base | 25 first-party Markdown learning documents plus manifest; sources are cited/linked, not copied wholesale | Yes | Allowed as project-authored synthesis; current-source verification remains a scientific requirement |
| App fonts | Fontsource packages for Inter, JetBrains Mono, Source Serif 4 declare OFL-1.1 | Yes | Allowed with OFL texts and reserved-name checks still to bundle |
| Documentation screenshots/showcase images | Tracked in the MIT source history; no separate third-party attribution found | Repository only | Keep under source license; re-audit before public marketing reuse |
| AI4HEOR logo | Product owner supplied and explicitly requested project use | Yes | Internal test authorized; public rights record missing |

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
5. Repeat the audit for any later Windows or Linux package; those releases are
   paused and are not covered by this decision.

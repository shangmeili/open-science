# runtime/mcp

MCP (Model Context Protocol) server configurations.

## Current distribution boundary

| MCP | Purpose | Phase |
| --- | --- | --- |
| Native workspace commands | Project file operations exposed by the signed desktop application | shipped; not an MCP package |
| Native HEOR evidence search | Bounded PubMed and ClinicalTrials.gov connector with app-owned authorization | shipped; not an MCP package |
| `Zotero MCP` | Reference library | later |
| `GitHub MCP` | Repos / issues / releases | later |
| `local runtime MCP` | Local execution status | later |

The current application packages no third-party MCP server configuration,
binary, source tree, or transitive runtime. A public repository or compatible
license is discovery evidence, not permission to load code. Any future MCP must
pass the pinned-source, license, egress, permissions, data-classification,
security, method-boundary, platform, test, kill-switch, and Human-review checks
before it can enter the release-only `runtime/assets/asset-admission-registry.json`.
Unfinished or excluded sources are not retained in that registry or offered in
the product UI.

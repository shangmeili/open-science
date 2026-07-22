# AI4HEOR third-party notices and distribution boundary

This file records the third-party components intentionally shipped by the
AI4HEOR desktop application. It does not replace the exact upstream license
texts and copyright notices.

## Bundled executables

- OpenCode 1.17.13, `anomalyco/opencode`, MIT. The executable is pinned by
  checksum and runs in an app-private profile.
- uv 0.11.26, `astral-sh/uv`, Apache-2.0 OR MIT. The executable is pinned by
  checksum and provisions local Python tools only after a user action.
- agent-browser 0.32.1, `vercel-labs/agent-browser`, Apache-2.0. The
  platform-specific executable is fetched from the versioned upstream release;
  its license is bundled under `legal/agent-browser/LICENSE.txt`.

## Adapted components retained inside first-party Skills

- `heor-evidence-search` is a first-party rewrite informed by HEORAgent MCP at
  revision `19f5f0eea5764d7a2695c372f3ec8f3aa0f53dd8` (MIT). The upstream Node
  package is not bundled or executed. Its exact MIT notice is retained at
  `runtime/skills/core/heor-evidence-search/references/heoragent-mit-license.txt`.
- `heor-local-evidence` invokes the Rust `pdf-extract` dependency. Its MIT
  notice is retained at
  `runtime/skills/core/heor-local-evidence/references/pdf-extract-MIT.txt`.

## UI, Rust, fonts, and transitive packages

The current resolved package inventories are generated into:

- `docs/legal/npm-production-components.json`;
- `docs/legal/cargo-lock-components.json`.

The UI includes Inter, JetBrains Mono, and Source Serif 4 through Fontsource;
these font packages declare OFL-1.1. Other resolved packages declare the
license expressions recorded in the inventories.

The first-party DOCX/PDF report renderer uses:

- Source Han Sans CN 2.005R (`SourceHanSansCN-Regular.otf`), Adobe, SIL Open
  Font License 1.1. Its exact license text is bundled at
  `legal/fonts/SourceHanSansCN-OFL-1.1.txt`; the font is embedded in generated
  DOCX and PDF files so Chinese output does not depend on a system font.
- `printpdf` 0.11.3, MIT, compiled without its default features. It is used by
  the native PDF path; its resolved Cargo metadata is recorded in
  `docs/legal/cargo-lock-components.json`.

Pinned hashes and upstream locations are recorded in
`docs/legal/REPORT_RENDERER_ASSETS.md`.

## Not distributed or loaded

- `runtime/skills/external/` is an ignored local discovery cache and is not a
  packaged resource.
- The release-only external-adapter registry is empty. No third-party Skill,
  plugin, MCP, or package is release-eligible or loaded through that registry.
- The Anthropic `docx`, `pdf`, `pptx`, and `xlsx` Skills at revision
  `9d2f1ae187231d8199c64b5b762e1bdf2244733d` were checked using each Skill
  directory's own `LICENSE.txt`. Those files are not Apache-2.0: they prohibit
  retaining copies outside Anthropic's Services, reproduction, derivative
  works, and redistribution. The four upstream Skill trees are therefore
  absent from AI4HEOR source, package, runtime, and candidate UI. Equivalent
  document capabilities are implemented independently as first-party
  workflows and deterministic renderers.

## Open release blockers

This repository is currently suitable for internal product testing, not public
redistribution. Public release remains blocked until:

1. a complete package-specific license and copyright notice corpus is bundled
   for every distributed npm, Cargo, font, OpenCode, and uv component;
2. the unresolved `buffers@0.1.1` production dependency is replaced or its
   authoritative license grant and notice are recovered and reviewed;
3. the AI4HEOR logo rights holder and public redistribution authorization are
   recorded; and
4. the final signed/notarized package is re-audited against its exact bytes.

See `docs/legal/LICENSING_AUDIT.md` for evidence, scope, and decisions.

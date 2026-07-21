# Open Science upstream capability review — 2026-07-21

AI4HEOR is derived from the Open Science desktop codebase. This review compares
the current AI4HEOR source candidate with `ai4s-research/open-science` through
`d48cd278fa7b6089c8a841a9752ffbb900b6f042` (after tag `v0.2.2`). The historical
merge base is `42c8101ab969011c2205fa1eacb96572ef309c18`.

The comparison is capability-based. AI4HEOR keeps the Open Science research
foundation, but it does not copy generic branding, demo content, optional remote
exposure, or an upstream implementation when an equal or stricter local path is
already present.

## Integrated or independently strengthened

| Open Science capability | AI4HEOR implementation | Current evidence |
| --- | --- | --- |
| Local natural-language sessions, streaming output, tools, questions and permissions | Preserved; task and project scopes remain separate and existing sessions recover after reload | Desktop runtime tests and native smoke task |
| Model/provider selection and recovery | Preserved and strengthened: every turn is explicitly bound to the currently selected provider/model so an old session cannot silently use its creation-time model | SDK request-body and existing-session regression tests |
| Runtime-independent UI boundary | `AgentRuntime` now owns lifecycle, sessions, discovery, model selection, execution and Human-interaction APIs; OpenCode remains the bundled implementation and owns only its provider/MCP configuration surface | TypeScript compile-time contract |
| Visible long-task activity | Localized model-activity status, model-step count, tool activity, retry phase, elapsed time and stopped-turn recovery remain separate from the final answer. Raw provider reasoning is never rendered as progress because it can expose internal planning, hidden prompt fragments or provider-specific English | Runtime/store and thread component tests; native completed task |
| Hard-reload history recovery | Preserved and extended to reconcile missed idle/error tails instead of leaving a task locked | Runtime/store tests |
| File paste/drop and local materialisation | Preserved; attachments enter the selected local task/project only and do not themselves upload or call a model | Composer and native artifact tests |
| LaTeX and scientific file viewers | Preserved for chat, Markdown, tables, notebooks, PDFs, images, FITS, spectra, molecules and genomes | Viewer and Markdown test suites |
| Python/R/Jupyter and run records | Preserved; exact interpreter, environment, command, outputs and transparent wrappers are recorded | Rust kernel, run and provenance tests |
| Workspace provenance snapshots | Size and bulk-directory guards plus background debounce are integrated; AI4HEOR never operates on the Open Science workspace and never commits a user-brought repository | Rust snapshot and workspace-isolation tests |
| Multi-file `apply_patch` provenance | Every changed file receives its own deduplicated provenance version | Provenance unit tests |
| Research Skills and MCP extensibility | Preserved through the app-private OpenCode profile, project-local reviewed Skills and model/provider-neutral task surface | Startup audit, Skill discovery and capability-review tests |
| Human permission modes | Preserved; changing mode cannot restart the runtime while a task is active, and test/full-access mode does not manufacture scientific approval | Runtime/store and native permission-mode tests |
| Safe project import | Adapted as copy-import: AI4HEOR recursively copies an existing folder into its managed project base, does not follow symlinks, never edits the selected source, replaces copied Open Science metadata with AI4HEOR metadata, seeds the HEOR harness and records the source path | Rust copy/import tests, desktop store/UI tests and native macOS copy-import smoke with source/copy hashes checked |
| Edit or return to a past message | Adapted with explicit destructive confirmation, runtime-backed workspace rollback, HEOR prompt reconstruction after edits, stale interaction/pane clearing and renewed HEOR review after rollback | SDK endpoint/event tests, runtime/store rollback tests, history-id and component tests, plus native macOS cancel and confirmed-return smoke on a disposable task |

## Upstream changes not copied as AI4HEOR 1.0.0 research requirements

| Upstream change | Decision for this candidate | Reason |
| --- | --- | --- |
| Generic Open Science examples and promotional sessions | Excluded | They are product demo content, not research foundation capability, and would reintroduce non-HEOR tasks into the shipped first-run surface. |
| Multiple themes and unrelated visual restyling | Excluded | The verified AI4HEOR visual system and Chinese research terminology take precedence; zoom, accessibility and current light/dark behavior remain available. |
| Goal plugin | Excluded from 1.0.0 | It adds an external executable and an agent-owned goal abstraction. AI4HEOR keeps research questions, methods and approvals Human-owned and does not need the plugin to run a task. |
| Remote Access gateway | Not enabled or packaged | LAN/phone control expands the local attack surface and is not required to preserve desktop research capability. It requires a separate threat, authentication, packaging and data-egress review before admission. |
| Bundled agent-browser sidecar | Not enabled or packaged | Public evidence retrieval already uses bounded first-party PubMed and ClinicalTrials.gov connectors. General browser automation needs separate binary, network, licence and provenance admission. |

The capability comparison is now closed at source, automated-test and native
development-app level for project import and message rollback. The native smoke
used only disposable fixtures, verified that the selected source tree remained
byte-identical, and removed the managed copy afterwards. This is still not
installed-package acceptance evidence: the signed/notarized macOS package and
the Windows package must repeat the same gates before the 1.0.0 installers are
released.

## Licence boundary

Open Science is MIT-licensed. Bundled third-party components keep their own
licences. In particular, the Open Science fetch script's Apache-2.0 comment for
Anthropic `docx`, `pdf`, `pptx`, and `xlsx` is contradicted by those four
directories' own `LICENSE.txt`; AI4HEOR does not fetch, copy or redistribute
them. See `THIRD_PARTY_NOTICES.md` and `docs/legal/LICENSING_AUDIT.md`.

This review records source provenance and product decisions. It is not package
acceptance evidence; final macOS and Windows installers require byte-specific
resource, licence, signature, installation and live-task verification.

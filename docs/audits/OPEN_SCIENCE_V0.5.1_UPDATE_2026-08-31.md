# Open Science v0.5.1 update review — 2026-08-31

## Scope and exact revisions

- Upstream repository: <https://github.com/ai4s-research/open-science>
- Latest release reviewed: `v0.5.1`, commit `ff7cb05f6a96b8fbcd169f2607cf1bba9bb8aa26`
- Upstream `master` reviewed: `17a86604efd0a7f9c337a80fde1dd7587f441c30`
- AI4HEOR pre-review baseline: `3f6e06d0205ae1310129c8f8c9b91d24e99af397`
- Shared historical ancestor: `1ddf3f14a18d567e9b6dad2dfc9ab21246da9a4f`

This is a capability and risk review, not a branch merge. AI4HEOR retains the
Open Science research foundation while preserving its HEOR Harness, local data
boundaries, deterministic calculations, passive artifact preview, and
researcher-owned scientific decisions.

## Adapted in this loop

| Upstream improvement | AI4HEOR decision | Verification boundary |
| --- | --- | --- |
| File-preview tickets and gateway-token removal (`eaa09ba1`) | Adapted. Browser preview URLs now carry a short-lived capability for one resolved workspace file; the gateway bearer token travels only in the authenticated ticket request. An empty gateway token is rejected. | Frontend regression proves the bearer token never enters the preview URL. Native tests prove unknown and expired tickets fail. |
| Bounded file streaming (`eaa09ba1`) | Adapted for both gateway and local preview paths. Full and ranged file bodies are copied in at most 1 MiB slices instead of being allocated whole. | A bounded-writer regression test plus existing full/range/MIME/traversal tests pass. |
| Asynchronous and cached artifact resolution (`d2636cb0`) | Adapted. Basename search runs off the Tauri UI thread; hits and misses are cached within one workspace, transient failures retry, and a project/task workspace change clears the cache. | Frontend cache/retry tests, Rust artifact tests, and native project/task E2E pass. |
| Non-Latin custom-provider identifiers (`faa0fcee`, `908226c3`) | Adapted. Existing ASCII ids remain unchanged; non-ASCII display names receive a stable digest so Chinese endpoint names are accepted and cannot silently collide. | Dedicated unit tests and the existing Settings provider integration suite pass. |

AI4HEOR deliberately keeps a stricter passive HTML policy than upstream: scripts,
external requests, frames, forms, and plugins remain blocked in artifact previews.
The ticket update does not reopen active HTML execution.

## Reviewed but not directly integrated

| Upstream area | Decision and reason |
| --- | --- |
| `osd` headless server and ACP expansion | Not integrated in this desktop update. They introduce a second product/runtime surface and do not fix an existing HEOR desktop defect. The existing model-neutral SDK and gateway remain the compatibility boundary. |
| Open Science split panes, reviewer agent, generic examples, and generic UI hierarchy | Not integrated. They are product-specific interaction choices, not missing research-foundation capabilities, and would conflict with AI4HEOR task/project and scientific-review semantics. |
| Interactive scripted HTML previews | Not integrated. AI4HEOR treats generated and imported HTML as untrusted research data and retains passive rendering. |
| Direct multimodal image parts | Kept as a separately testable candidate. Workspace attachments remain available to the agent through local file tools across providers. Making every image a model request part requires provider-capability and request-size acceptance evidence before it can become model-agnostic default behavior. |
| Upstream OpenCode binary bump | Not integrated automatically. AI4HEOR ships a pinned, reviewed derivative with product permission and Harness patches; changing it requires rebasing those patches and rerunning the packaged-provider, permission, Windows, and release gates. |
| `osd-core` configuration recovery changes | Not copied across architectures. AI4HEOR's app-managed configuration path must be evaluated and tested independently rather than importing a recovery path for a different process boundary. |

## Existing AI4HEOR equivalents retained

- Windows workspace identity normalization and stopped-task reconciliation.
- Public read-only web retrieval without spurious Human approval while dangerous
  or side-effecting operations remain gated.
- Natural-language task queueing, standalone tasks, project-scoped tasks, and
  researcher-editable Human questions.
- App-managed Python/Jupyter installation, HEOR deterministic computation,
  evidence provenance, citation formatting, local literature storage, report
  generation, and release review gates.
- Hash-locked Open Science general Skills and the admitted research connector
  catalog remain package resources; this update does not replace or remove them.

## Verification

- Frontend: 120 files, 818 tests passed.
- Rust: 397 passed, 1 established fixed-public-network test ignored; resource
  staging 2/2 passed.
- TypeScript typecheck, ESLint, Rust formatting, diff checks, and production
  frontend build passed.
- HEOR Harness 16/16, desktop interaction contracts 15/15, Tauri resource
  contracts 10/10 passed.
- Release resource preflight passed with 44 sources and 461 files.
- Native Tauri/WKWebView E2E passed task navigation, queued messages, Human
  input, permission reuse/revocation, provider-failure recovery, task files,
  passive HTML preview, project import, deterministic DOCX/PDF/XLSX export, and
  process cleanup.

No installer was generated in this loop. The source update must be committed
before any new macOS or Windows package is produced.

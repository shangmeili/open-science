# AI4HEOR Desktop — Technical Design

> **Implementation status (v0.1.32 source, 2026-07-19).** Built and locally verified: Tauri 2 +
> React desktop shell; isolated bundled OpenCode and uv sidecars; model-provider-agnostic
> natural-language sessions; a HEOR-default root route, typed HEOR project creation,
> localized unsent project-intake drafts, a seven-language non-blocking first-use
> control boundary, HEOR-preserving project session routes;
> first-party scientific and HEOR Skills; Human-in-the-loop,
> hash-bound evidence, reference-case, analysis, validation, reporting, and release gates,
> including the 13/15-artifact PSM validation/report contract and deterministic release replay;
> deterministic cohort, uncertainty, bounded advanced-VOI, budget-impact, NMA, anchored-MAIC,
> bounded natural-history point calibration, bounded semi-Markov individual-level
> microsimulation, and bounded target-trial RWE-IPTW×IPOW engines, including portable full replay,
> native point/diagnostic challenge, and
> separate app-owned Human method reviews consolidated in a current-result review queue; and
> native macOS and x86_64 Linux packaging.
> The desktop shell also provides a seven-language main-content skip link, a product-wide
> visible keyboard-focus indicator, and light-theme normal-text contrast at or above 4.5:1
> on its supported paper and card surfaces. These are source/browser checks, not an
> assistive-technology or full WCAG conformance claim.
> The 0.1.32 x64 macOS DMG is content-verified from clean commit
> `2bd1bea0de2fb151c8f11a57b28600223eee34ce`; all 283 resources match source bytes,
> all 177 mounted-core HEOR tests pass, and isolated fresh plus legacy-migration starts
> were verified. Its ordinary research and closed-Settings surfaces identify only the AI
> assistant; the OpenCode engine name and local endpoint are confined to an explicitly
> opened Advanced diagnostics section. The current 0.1.31 Apple Silicon DMG was separately
> cross-built from the same clean commit `2834785e057ac54477a9633f07390bc173251644` on an Intel
> Mac; read-only inspection verified pure-arm64 payloads, all 282 resources byte-for-byte,
> and all 177 mounted-core HEOR tests. Native sidecar execution and first start remain
> unverified because the strict verifier correctly rejects arm64 execution on that host.
> The 0.1.30 Linux `.deb` and `.rpm` are built and content-verified from clean
> commit `0beb7b2bcb04a796f256bd8f8528bb787aa77319` in an isolated Ubuntu 22.04 builder.
> Both extracted packages independently pass all 177 HEOR tests and contain the same 282
> controlled resources as source. The `.deb` also passes a brand-new Ubuntu 22.04 non-root
> headless first start; the `.rpm` passes a Fedora 42 start with content-preserving legacy
> `OpenScience` to `AI4HEOR` workspace migration. Fail-closed native package evidence is wired
> for macOS arm64/x64, Windows x64, and Linux x64, with a four-target manifest gate;
> that current-commit CI manifest and native Windows/Apple-Silicon first-start evidence
> have not yet been produced. The inspected arm64 app has only an ad-hoc linker signature,
> no sealed resources, and fails Gatekeeper. A tag-only Developer ID/notarization gate is
> now implemented and locally fail-closed, but no credentialed tag run or signed artifact
> has yet proved it; Windows signing also remains open.
> Active delivery work is deliberately limited to Intel macOS product acceptance;
> Windows, Linux, Apple-Silicon, and cross-platform release work are paused until then.
> Sections below distinguish implemented contracts from target design.

> **Role boundary.** Codex leads construction and verification of the AI4HEOR
> software. Within AI4HEOR, the human researcher leads the scientific work and
> the configured model/runtime provides bounded assistance. Human-in-the-loop is
> therefore research ownership and method judgment, not merely a final approval
> appended to agent-directed research.

## Bounded model-calibration execution

`runtime/skills/core/heor-model-calibration` owns request/result schema `0.1.0`.
The request fixes a 2–6-state homogeneous continuous-time generator, initial
distribution, cycle grid, fixed directed rates, 1–4 calibrated rates with linear
or log bounds, aggregate state-occupancy targets, target roles, loss definition,
search settings, local-identifiability settings, exact evidence bytes, execution
authorization, limitations, and output directory. Unknown fields, unbound evidence
IDs, duplicate transitions, unsafe paths, excessive uniformization intensity,
missing held-out targets, or automatic threshold/covariance claims fail closed.

The Python standard-library runner creates a transition matrix through
uniformization at tail tolerance `1e-14`, evaluates a seven-level parameter grid,
refines the best eight points by normalized coordinate pattern search, and writes
an atomic immutable manifest plus canonical `search.csv`. The portable auditor
rebinds the current request, evidence, evaluator source, Python identity and trace,
then reruns the complete search, target predictions, validation summaries and
finite-difference Jacobian diagnostics. Rust embeds the exact evaluator bytes and
independently recomputes bounded-scale parameter values, the selected transition
matrix, occupancy predictions, scaled training objective, held-out RMSE, and
Jacobian cross-product eigenvalues. It explicitly labels its scope as selected-
point and local-identifiability replay rather than a second optimizer.

The React review pane provides a natural-language preparation action and a
secondary eight-checkbox form. The Rust command accepts or rejects only a current
native-reviewable result, binds the five-artifact graph, writes a new immutable
workspace snapshot, and appends an app-private hash-linked event. All eight checks
are mandatory for acceptance; rejection does not require false confirmations.
The record is a local Human assertion and only makes the candidate eligible for
later input selection. It cannot update an analysis plan or model input.

## Bounded semi-Markov microsimulation execution

`runtime/skills/core/heor-semi-markov-microsimulation` owns request/result schema
`0.1.0`. The request fixes the closed-cohort decision problem, 2–8 ordered states,
one absorbing death state, initial distribution, cycle timing, horizon, 2–4
strategies, 1–3 capped event-entry trackers, non-overlapping time-in-state and
tracker-count conditions, one final fallback rule per state, complete transition
rows, state rewards, transition-event costs, economics, evidence bytes, deterministic
simulation settings, trace sample, execution authorization, and limitations.
Unknown authority fields, unbound evidence, overlapping rules, incomplete rows,
unsafe paths, or more than five million patient-strategy-cycles fail closed.

The standard-library Python runner uses SplitMix64 in counter mode and converts the
top 53 bits to IEEE-754 uniforms. Its counter key is `(seed, replicate, patient,
cycle, stream)`, shared across strategies to provide common random numbers without
consuming a mutable stream. It writes an atomic immutable manifest, evaluator copy,
and canonical `traces.jsonl`. The portable auditor rebinds all current bytes and
reruns every patient cycle, aggregate, paired comparison, and sampled trace.

`heor_microsimulation.rs` is a separate implementation of the complete replay. It
revalidates the bounded request, independently regenerates initialization and
transition draws, applies the state-memory rules, trapezoidal state rewards,
end-cycle event costs and separate discount rates, and challenges the complete
manifest and trace with bounded numeric tolerance. Cross-language golden vectors
bind the PRNG and a Python-created 4,800-step fixture with 160 trace rows.

The React review pane keeps preparation and repair in natural-language conversation.
Its auxiliary form records eight Human judgments covering individual-model need,
structure and timing, provenance, state memory and rewards, history/event costs,
random numbers and traces, Monte Carlo error and performance, and omitted structural
and parameter uncertainty. Rust accepts only a current full-replay-clean result,
binds the five-artifact graph, writes an immutable workspace snapshot, and appends
an app-private unanchored SHA-256 event. Acceptance cannot select a strategy,
authorize a policy conclusion, or update another model.

## 1. Technical goals

A high-performance, open-source research workbench with macOS, Windows, and Linux installers.
Design priorities: fast startup; smooth UI; simple install; replaceable agent runtime;
local and sandboxed execution; MCP / skills / workflow support; artifact provenance;
extensibility to Jupyter, HPC, Modal, Docker, and remote servers.

## 2. Overall architecture

```text
AI4HEOR Desktop
├── Desktop Shell: Tauri 2
├── Frontend: React + TypeScript + Vite
├── UI System: Tailwind CSS + Radix UI / shadcn-style components
├── Local Service: Rust commands + bundled OpenCode sidecar
├── Agent Runtime: OpenCode (bundled single-binary sidecar)
├── Agent Protocol: OpenCode HTTP + SSE API (opencode serve)
├── Skills Layer: OpenCode skills/agents + optional third-party scientific skills
├── Capability Layer: governed HEOR evidence / managed Jupyter / user-managed MCP
├── Execution Layer: OpenCode agents/tools + optional Jupyter Kernel Gateway
├── Storage: Local workspace + SQLite + JSONL provenance
└── Packaging: Tauri DMG / APP / NSIS / MSI / DEB / RPM
```

## 3. Tauri over Electron

### 3.1 Recommendation

v1 uses **Tauri 2 + React + TypeScript + Vite**. Not Electron.

Reasons: Tauri is lighter with smaller installers; it uses the OS-native WebView,
suited to tool-type desktop apps; it is cross-platform (macOS / Windows / Linux); it
allows any frontend framework; and a Rust backend is well-suited to local files,
security, process management, and sidecar orchestration. Tauri positions itself around
small, fast, secure cross-platform apps built from a single codebase.

### 3.2 When Electron might fit

If later needs arise — complex browser capabilities, a more mature desktop ecosystem,
identical embedded Chromium behavior, or many native Node.js modules — Electron could be
reconsidered. But AI4HEOR's core is the workbench, files, agent, runtime, and
artifacts, which do not need Chromium-level capabilities, so Tauri fits better.

## 4. Frontend

### 4.1 Stack

React · TypeScript · Vite · Tailwind CSS · Radix UI · TanStack Query · Zustand ·
React Router · Monaco Editor · Markdown renderer · ECharts / Plotly / Observable Plot.

### 4.2 Module layout

```text
src/
  app/{routes,layout,providers}
  components/{sidebar,topbar,command-palette,cards,artifact-viewer,
             approval-dialog,tool-call-card,code-viewer,markdown-viewer}
  features/{onboarding,projects,chat,agent-runtime,literature,artifacts,
            provenance,review,skills,settings}
  lib/{api,events,store,theme}
```

### 4.3 UI performance strategy

Streaming chat render; virtualized log lists; lazy file tree; paginated CSV; chunked
large-Markdown render; on-demand figures; cached artifact previews; a unified agent
event bus; all heavy work off to sidecar / worker; the Tauri main process does system
capabilities only, not heavy computation.

## 5. Agent runtime

### 5.1 Choice: OpenCode (bundled)

The agent runtime is **OpenCode** (`anomalyco/opencode`, MIT), pinned to a stable
release (`OPENCODE_VERSION`, currently 1.17.13). It is distributed as a **single
binary**, which makes it ideal to bundle as a desktop sidecar — no Python/Node runtime
to package. It supports MCP, skills, and agents, is model-agnostic (BYOK), and serves as
an open-source coding/agent runtime in the spirit of Claude Code.

OpenCode exposes an HTTP + SSE server (`opencode serve`) that a GUI can drive directly —
sessions, prompts, streaming assistant/tool output, skills, and agents.

### 5.2 Researcher-led runtime harness

`runtime/harness/` is an app-owned operating contract bundled as a Tauri resource
and copied into every new project. Its `AGENTS.md` makes the Human researcher the
scientific lead and limits the runtime to delegated assistance. The runtime may
inspect local state, run deterministic checks, draft labelled alternatives, and
complete a researcher-selected plan. It must stop for unresolved choices about
the question, population, strategies, comparators, perspective, jurisdiction,
methods, evidence, model structure, assumptions, interpretation, or permitted use.

The same boundary applies to every cloud or local model. Only the Human-selected
provider or endpoint may be used; failure is visible and never triggers a silent
provider fallback. Model output remains a draft. Imported files, papers, web pages,
connector/MCP results, tool output, and model artifacts are untrusted content, not
instructions, and cannot change governance, authorize egress, or create approval.

`policy.json` is the exact machine-readable companion to `AGENTS.md`. It versions
the scientific-lead, interaction, provider, external-content, deterministic-calculation,
approval-store, and default data-classification contract. Before a new project can
become active, the native shell requires the exact harness resource tree, rejects
empty or extra files and source/target symlinks (including linked parent directories),
validates the policy values and required Human-authority text, copies only missing
files, and compares every newly copied byte. Any failure removes only the newly
created incomplete directory and returns a visible error; no active-workspace pointer
or initial Git snapshot is written. Existing projects are never reseeded or silently
rewritten. Rust and Python contract tests bind these fail-closed semantics and the
packaged-resource mapping.

### 5.3 Desktop ↔ OpenCode communication

The app talks to OpenCode over its HTTP + SSE API, wrapped by `packages/sdk`
(`OpenCodeClient`). Key endpoints:

| Endpoint | Use |
| --- | --- |
| `POST /session` · `GET /session` | Create / list sessions (conversation history) |
| `GET /session/:id/message` | Load a session's history |
| `POST /session/:id/prompt_async` | Send a prompt |
| `GET /event` (SSE) | Stream `message.part.updated` (text/tool), `session.idle`, `session.error` |
| `GET /api/skill` · `GET /agent` | Real loaded skills / agents |

Flow:

```text
App launch → Rust starts the bundled `opencode serve` (dedicated free port)
↓
OpenCodeClient opens GET /event (SSE) and creates/loads sessions
↓
Prompt → POST /session/:id/prompt_async
↓
SSE streams message.part.updated / session.idle → folded into thread blocks by part/call id
↓
Frontend renders streaming messages, tool cards, and per-session history
```

### 5.4 Bundling & isolation (no interference)

OpenCode is bundled as a Tauri **sidecar** (`externalBin`, one binary per target triple,
git-ignored and fetched by `scripts/dev/fetch-opencode.sh`). The Rust side
(`src-tauri/src/runtime.rs`) starts it so it never collides with a user's own OpenCode:

- runs the **bundled** binary (not the user's `PATH`);
- on a **dedicated free port** (not the default 4096);
- with an **app-private** config/data dir via `XDG_CONFIG_HOME`/`XDG_DATA_HOME` under
  `~/Library/Application Support/com.ai4s.workbench/runtime/` (macOS) — so the user's
  sessions/config are never touched;
- but it **shares the user's login**: the user's `auth.json` (OpenCode credentials / free
  access) is copied read-only into the sandbox at startup, so the bundled runtime can
  reply out of the box without a separate login. We only read the user's auth file; we
  never modify it or their sessions.
- killed on app exit.

OpenCode and uv release archives are admitted through
`scripts/dev/sidecar-checksums.sha256`. The fetchers require exactly one SHA-256 for
the pinned product/version/asset key and verify the downloaded bytes before extraction;
missing, duplicate, or changed digests fail closed. OpenCode values are recorded from
the [v1.17.13 GitHub release](https://github.com/anomalyco/opencode/releases/tag/v1.17.13)
asset metadata and uv values from the publisher's
[0.11.26 release checksums](https://github.com/astral-sh/uv/releases/tag/0.11.26).
The contract covers every supported macOS, Windows, and Linux archive and runs in both
build and cross-platform contract CI.

The user's model provider key (entered in Settings) is written into that app-private
`opencode.json` by the `configure_opencode` Rust command, and the sidecar is restarted
to pick it up. Keys never enter the user's global OpenCode config, logs, or git.

## 6. Skills & MCP

### 6.1 Skill layering

```text
skills/
  core/      # reproducible-research, literature-review, figure-provenance,
             # citation-reviewer, paper-to-report
  external/  # inactive third-party review cache; never loaded directly
  user/      # custom skills
```

### 6.2 v1 built-in skills

| Skill | Purpose |
| --- | --- |
| `reproducible-research` | Standardize project structure, artifacts, logs, reproducibility |
| `literature-review` | Search, filter, summarize literature |
| `bibliometric-analysis` | Year trends, keywords, journal distribution, clustering |
| `figure-provenance` | Figures must trace to code and data |
| `citation-reviewer` | Check citation format and sources |
| `paper-to-report` | Generate a Markdown report |

### 6.3 Third-party skills

Third-party Skills are discovery candidates, not runtime capabilities. The packaged
asset-admission registry requires a compatible license, pinned revision, declared
capability boundary, adaptation delta, tests, cross-platform evidence, reviews, kill
switch, and exact content hash before a `validated-adapter` can be copied into the
app-managed OpenCode profile. The Skills page shows both the native registry audit and
the real skills OpenCode loaded. Workspace `.opencode/skills/` content is visibly
unmanaged and never becomes a bundled product asset automatically.

The first-party `heor-evidence-search` connector is deliberately not an MCP
passthrough. The Agent writes only a validated request artifact. A native Tauri
command re-reads and hashes those bytes, checks a fixed PubMed/ClinicalTrials.gov
allowlist and non-sensitive egress declaration, then accepts an app-owned human
authorization bound to that hash. The HTTP client disables redirects and uses
fixed endpoints, bounded time/response sizes, JSON content checks, immutable
run files, response hashes, and a separate hash-linked authorization log. No
URL, header, credential, output path, or arbitrary upstream tool is supplied by
the Agent.

The first-party `heor-methods-watchlist` is deliberately a local control
artifact rather than an unlicensed HTA scraper. A dependency-free validator and
an independent Rust command audit strict schema `0.2.0`, source/change ordering,
ISO dates, HTTPS canonical links, overdue checks, unresolved method changes,
safe `heor/method-sources/` paths, non-symlink files, reuse status, media types,
and exact SHA-256 values. The workspace schema rejects `human_disposition` and
every equivalent approval field. Only a native command can append an app-private
Human review event for `accept_revalidation` or `dismiss_change`; the event chain
and immutable exported snapshot bind project, change, action, rationale, local
actor label, and exact watchlist bytes. Reads fail closed on malformed chains,
unsafe files, or record/hash drift, and any watchlist edit makes prior events
ineffective. Completion is relative to the artifact's reproducible `as_of_date`;
it does not imply that the file is current today. The form is an auxiliary Human
decision recorder while preparation and repair remain natural-language work.
This local unanchored assertion does not authenticate identity, confer approval,
or replace independent validation.

Candidate import is a second native trust boundary. It accepts only the latest
explicit run path/hash supplied by the UI, verifies that pair against the
app-owned authorization event and the immutable run's internal contract, and
requires the exact current SHA-256 of `heor/evidence-synthesis.json`. The writer
rejects symlinks and path escapes, stages and syncs a replacement, keeps a
rollback copy during rename, and produces app-owned provenance fields. Import
is idempotent by authorization/source ID and record ID; it adds source links to
existing records without modifying screening, critical appraisal, extraction,
or conflict judgments. The portable Python validator and native Rust audit both
fail closed on unknown fields, malformed dates, incomplete bindings, invalid
links, and collection caps.

Evidence review is a separate native trust boundary. The Agent may write
research fields in `heor/evidence-synthesis.json`, but only the desktop command
can append a local review event under the app-data directory. Schema-v2 event
hashes cover project ID, exact synthesis SHA-256, sorted extraction IDs, local
reviewer label, rationale, confirmed/rejected decision, timestamp, sequence,
and previous hash. Schema-v1 confirmation events remain readable. Log reads are
capped, reject symlinks, and verify every event before use.

The review surface renders exact extraction value, target, record, source
location, and applicability in bounded batches. The same case-insensitive local
label cannot decide the same extraction twice for one synthesis. The derived
verified set requires two distinct confirmations and zero rejections; any
rejection remains blocking until the synthesis bytes change. This is a local
integrity rule, not an authenticated reviewer-identity or independent-entry
system.

Analysis-plan schema `0.3.0` makes the evidence-to-input value transformation
executable. The plan-only audit checks the declared derivation method and exact
`model_value` snapshot. The portable validator additionally parses the bound
synthesis extraction as strict JSON. The native selection audit repeats that
check against current workspace bytes and, for monetary inputs, verifies each
`source_value` against its named extraction scalar or array index before the
existing normalization arithmetic. Only `direct_evidence`, `explicit_assumption`,
`monetary_adjustment`, and the schema `0.5.0` through `0.11.0` bounded
`deterministic_transformation` operations described below are supported. Free-form
expressions remain blocked.

Analysis-plan schema `0.4.0` adds a first-party piecewise transition schedule
without changing the evidence-derivation authority boundary. Each strategy has
exactly one static matrix or a list of `{start_cycle, matrix}` phases; schedules
start at cycle 1, are strictly ordered within the horizon, and are selected by
one-based model cycle. Python validates every phase and mass-conserving trace;
Rust, the portable provenance validator, and the TypeScript preview dynamically
require the schedule path instead of an absent static-matrix path. Uncertainty
allowlists accept complete scheduled matrix rows and structural change-point
scenarios. The result declares `static` or `piecewise_by_model_cycle` plus the
change points. No layer interprets this as time-in-state, semi-Markov memory,
hazard conversion, patient history, time-varying rewards, or microsimulation.

Analysis-plan schema `0.5.0` admits `constant_competing_rates` only on a strategy
transition matrix or schedule. Each complete phase declares ordered state rows;
each nonzero event declares a target, positive annual rate, and exactly one
extraction or proposed-assumption basis. The Python engine, Rust approval path,
portable provenance validator, and TypeScript preview independently compute
`1 - exp(-sum(rate)*cycle_length)`, allocate event mass by rate share, and compare
the complete result with both the derivation snapshot and model input. Static
outputs require one phase; schedules start at cycle 1 and remain strictly ordered.
Uncertainty schemas `0.3.0` through `0.7.0` admit only exact positive event-rate targets inside
these transformations. Python applies all sampled rates to an ephemeral plan,
recomputes each affected complete output once, updates the derivation snapshot,
and then invokes the ordinary model validator. The portable validator and native
Rust boundary independently enforce exact event-basis binding and positive gamma,
lognormal, or uniform distributions. Schemas `0.4.0` through `0.7.0` may correlate 2–32 scalar
lognormal members through an evidence-bound, symmetric, strictly positive-definite
latent log-scale matrix and deterministic lower-triangular Cholesky multiplication.

Analysis-plan schema `0.6.0` admits
`parametric_survival_to_transition_schedule` only for a complete two-state
strategy schedule. Exponential parameters use a positive annual rate; Weibull
uses the declared scale-in-years and shape parameterization. Python, Rust, the
portable validator, and TypeScript independently evaluate cumulative hazard at
each cycle boundary, convert its increment with stable `expm1` arithmetic, and
compare every emitted matrix with the current schedule and derivation snapshot.
Each parameter binds exactly one extraction or proposed assumption. Uncertainty
schemas `0.5.0` through `0.7.0` may target the exact positive exponential rate or Weibull shape or
scale value. Python applies all replacements, recomputes the complete schedule
and derivation snapshot, then invokes ordinary validation; portable and native
audits independently enforce the same target, basis, and distribution contract.
The engine does not fit, select, reconstruct covariance for, or clinically
validate curves; those gaps stay visible to Human-in-the-loop review.

Analysis-plan schema `0.7.0` admits
`single_event_probability_time_conversion` on a complete strategy matrix or
schedule. Every row declares `event: null` or one target with a source
probability strictly inside `(0,1)`, a positive source interval, and one exact
extraction or proposed-assumption basis. Python, Rust, the portable validator,
and TypeScript independently compute
`1 - exp(log(1-p) * cycle_length / source_interval)` with stable log/exponential
primitives and compare the complete output with the current transition input
and derivation snapshot. Uncertainty schema `0.6.0` or `0.7.0` may target only the exact
source probability, accepts Beta or Uniform strictly inside `(0,1)`, and
recomputes the complete affected transformation before normal validation.
Competing events, time-varying hazards, certain events, relative effects outside the dedicated bounded RR/OR adapter,
composite endpoints, and probability-parameter dependence remain blocked.
Group order, member order, matrix, bases, and rationale are artifact data; Python,
Rust, and the portable validator reject reused members, unsupported marginals,
unlinked bases, singular/perfect matrices, and fields outside the contract. The
implementation deliberately excludes
general CTMC exponentiation, relative-effect application outside that adapter, within-cycle
multi-step paths, arbitrary copulas, rank correlation,
empirical posterior draws, and transformation-space structural scenarios.

Analysis-plan schema `0.9.0` admits
`background_plus_excess_mortality_to_transition_schedule` only for a complete
two-state strategy schedule. The exact transformation contains cycle length,
state indices, `life_table`, `excess_mortality_rate_per_year`, and the exact
`population_exchangeability` and `no_double_counting` review bases. The life
table records jurisdiction, year, population, sex, start age, and one
`{cycle, attained_age_years, annual_probability}` record per horizon cycle.
Every annual probability and the excess rate has a value plus exactly one
extraction or proposed-assumption basis; each review basis has exactly one basis
and no approval/status authority.

Python, Rust, TypeScript, the standalone Skill validator, and portable provenance
audit independently require `attained_age_years = floor(start_age_years +
(cycle-1)*cycle_length_years)` and compute
`1-exp(-(-ln(1-q_annual)+h_excess)*cycle_length_years)` with stable primitives.
Any finite positive cycle length is supported; annual probability is converted
to hazard before time scaling. Stale schedules, mismatched jurisdiction,
unsupported fields, invalid bases, endpoint probabilities, non-finite arithmetic,
and state-count drift fail closed.

Uncertainty schema `0.8.0`, paired only with analysis `0.9.0`, permits only the
exact positive `excess_mortality_rate_per_year.value` parameter target. It fixes
life-table metadata and probabilities, review bases, operation, and other
transformation internals; ordinary external allowlisted structural scenarios
remain required. Under `0.8.0`, those scenarios are limited to cost or utility
scalars, discount rates, or half-cycle correction; cycle count/length and
transition matrices/schedules are rejected because they would invalidate the
fixed mortality transformation. Additive-versus-multiplicative/SMR mortality stays explicit
Human-in-the-loop structural uncertainty. Already all-cause inputs,
cause-specific/subdistribution mixing, calendar improvement, age/sex mixtures,
time-varying excess hazards, competing non-death events, and partitioned survival
remain blocked.

Survival fitting review is a separate, non-calculation artifact. The bundled
`$heor-survival-extrapolation-review` validates external-import schema `0.2.0`
or first-party-execution schema `0.3.0` files containing
one absolute time-to-first-event curve, 2–8 pre-specified standard parametric
families, exact local data/command/session/output hashes, visible failed fits,
common observed and extrapolated survival/hazard landmarks, diagnostic plot
hashes, external and clinical plausibility assessments, limitations, and at
least two structural scenarios. The validator checks file hashes when given the
workspace root and rejects model-order drift, invalid or incomparable landmarks,
fewer than two converged candidates, and embedded approval or selection fields.
The artifact also names the exact analysis ID and parametric-survival provenance
path. The portable validator and native Rust auditor require the plan-selected
distribution to be a converged pre-specified candidate. One target uses the
fixed review path. Plans with 2–32 targets use the schema `0.1.0` fixed collection
manifest, whose entries must exactly match plan target count and order and bind
one safely named schema `0.2.0` or `0.3.0` review per target. The artifact state
remains `awaiting_human_selection`; only the app-owned analysis-plan gate can
authorize downstream use, and that event binds either the exact single review or
the manifest plus every referenced review hash. The review pane exposes required/
not-required, collection coverage, target, selected family, convergence,
scenarios, recommendation, and blocking errors without turning the recommendation
into authority. `$heor-survival-fit-execution` now provides the bounded optional
backend for one authorized local UTF-8 two-column time/event CSV: it preflights
classification, hashes, counts, candidates and exact installed package versions;
runs a fixed intercept-only MLE adapter without installation; preserves every
attempted fit and diagnostic; independently recalculates every converged admitted
family in Python and native Rust; and emits result schema `0.2.0` with one hash-bound
estimation-scale covariance artifact per converged model. Both auditors require
exact order/transforms, finite symmetric positive-definite covariance, and recovery
of the bound natural parameters. The artifact explicitly has within-one-curve scope
and no joint-curve-draw authority. The review schema `0.3.0` must exactly
reproduce this eligible bundle. `survHE` remains user-installed and GPL code is
not bundled or linked into the deterministic core. The local system R lacks the
required packages, while a temporary network-disabled Linux container validated
R 4.6.1, survHE 2.0.51 and flexsurv 2.3.2. The collection
audits independently fitted curves; it does not establish PFS/OS consistency,
arm alignment, joint covariance, or partitioned-survival validity.

Network meta-analysis is a separate evidence-synthesis execution and review
boundary. `$heor-network-meta-analysis` schema `0.1.0` accepts one outcome and
timepoint, a connected 3–32-node network, and one independent two-arm randomized
contrast per study. A fixed `Rscript --vanilla` adapter runs only against a
Human-supplied existing isolated library containing `netmeta`, `meta`, and
`metafor`; environment profiles, package installation, network requests,
arbitrary R, and serialized model objects are excluded. The request binds the
exact effect scale, reference, favorable direction, common or common-tau REML
random-effects model, transitivity/effect-modifier assessment, evidence and
study provenance, adapter hash, and package versions.

The result preserves five raw backend outputs and normalizes the complete
ordered league table. Dependency-free Python and native Rust independently
rebuild the contrast design and WLS estimates; for random effects this check is
conditional on backend tau rather than a second REML estimator. The desktop
stores an immutable workspace review record plus a private unanchored SHA-256
event chain over the exact ten-artifact graph. Acceptance requires all eight
Human checks and only makes the result eligible for later evidence selection;
it does not auto-populate a model or establish transitivity, evidence certainty,
clinical validity, transportability, ranking superiority, or reimbursement.

RWE causal analysis is a separate observational-design execution and review
boundary. `$heor-rwe-causal-analysis` schema `0.2.0` accepts only a Human-defined
active-comparator new-user target trial already represented as one pseudonymous
baseline row per eligible person. Exactly two strategies share time zero; the
fixed-horizon binary outcome has an explicit observation indicator; the estimand
is the source-cohort ATE risk difference if nobody's outcome were lost; and 1–12
baseline treatment-outcome common causes plus a prespecified observation-predictor
subset are selected and justified by the researcher before analysis. Upstream
cohort construction remains outside the evaluator and must be reviewed rather
than inferred from the CSV.

The standard-library Python evaluator fits unpenalized main-effects Logistic
treatment and observation models, applies uncapped/untrimmed stabilized
ATE-IPTW×IPOW to observed outcomes, and reports complete-case and weighted risks,
follow-up, overlap, separate/combined weight distributions, observed-row ESS, and
pre/treatment/combined SMD without automatic scientific acceptance thresholds. A fixed PCG32 stream
resamples rows within treatment arms and repeats the complete fit in every
bootstrap replicate; any failure is retained and blocks review. Portable replay
repeats all bootstrap work. Native Rust independently refits both point models and
checks coefficients, standardization, balance, overlap, weights, ESS, and effects
against current bytes, with a shared synthetic golden case; its declared scope
excludes uncertainty replay. The desktop binds an immutable Human accept/reject
snapshot and private event chain to the exact six-artifact graph. Neither numeric
agreement nor Human acceptance creates a causal-validity, regulatory, treatment,
economic-model, reimbursement, or policy claim.

Analysis-plan schema `0.10.0` admits only
`relative_effect_to_transition_schedule` for a complete two-state schedule with
one absorbing event. The exact transformation declares cycle and effect
intervals, state indices, `risk_ratio` or `odds_ratio`, one value-plus-basis
baseline risk per cycle, one value-plus-basis relative effect, and exactly the
`endpoint_alignment`, `population_transportability`, and
`effect_constancy_over_cycles` review bases. Intervals must be equal. Python,
Rust, TypeScript, the standalone Skill, and portable provenance audit independently
recompute `p=q*RR` or `p=q*OR/(1-q+q*OR)` for every cycle and compare the complete
schedule and derivation snapshot.

Uncertainty schema `0.9.0` pairs only with analysis `0.10.0` and targets only
`relative_effect.value`. For RR, DSA and bounded Uniform PSA highs must remain
strictly below `1/max(q>0)`; unbounded RR distributions fail closed. OR permits
Lognormal or strictly positive bounded Uniform PSA. Baselines, measure, intervals,
operation, and review bases remain fixed. HR, rate ratio, risk difference,
competing events, and treatment-effect extrapolation remain blocked by this
operation; eligible constant HR work routes to `$heor-hazard-ratio-adapter`.

Analysis-plan schema `0.11.0` adds the bounded
`hazard_ratio_to_transition_schedule` operation. It accepts exactly two states,
one absorbing time-to-first event, one positive constant HR, one non-negative
and non-decreasing baseline cumulative-hazard value at every model-cycle end,
and exact endpoint, population, proportional-hazards, effect-duration, and
treatment-switching review bases. With `H0(0)=0`, Python, Rust, TypeScript, the
standalone Skill, and portable provenance independently recompute every complete
matrix using `p=-expm1(-HR*(H0(i)-H0(i-1)))`.

Uncertainty schema `0.10.0` pairs only with analysis `0.11.0` and targets only
`hazard_ratio.value`. It admits strictly positive DSA bounds and bounded Uniform
PSA whose high values reproduce finite probabilities below one. Baseline hazards,
operation, indices, review bases, and schedule structure remain fixed. Unbounded
HR distributions, time-varying or non-proportional effects, stopping/waning,
unresolved switching, competing/recurrent events, fitting/selection, and PFS/OS
partitioned survival remain blocked.

`heor/analysis-plan.json` carries the input-selection contract directly: a root
`evidence_synthesis` binding plus `extraction_ids` on each source-based
`input_provenance` mapping. The approval path independently checks synthesis
structure, current bytes, extraction eligibility, exact target, record/source
link, two distinct app-owned confirmations, and absence of rejection. Its approval event binds the synthesis digest
alongside uncertainty and budget-impact artifacts. This avoids a second
workspace artifact and circular hashes while ensuring a plan approval covers
the exact evidence-to-input choices. The engine, uncertainty runner, and budget
impact runner repeat the audit and invalidate stale approval bindings.

Budget-impact plan schema `0.2.0` is an alternate dynamic contract rather than
an in-place reinterpretation of static `0.1.0`. Python calculates one annual-
boundary stock ledger per without/with-access scenario using an exact event
order: opening stocks, incident cohort, incident-first capacity allocation,
comparator displacement, full-year costs, common mortality, treatment-specific
persistence, and fixed discontinuation destinations. The result records every
requested, delivered and unmet start plus opening/closing stocks, deaths, exits,
category costs and impact. The dependency-free Skill validator and native Rust
audit independently enforce the schema, exact input provenance, safe sensitivity
targets and zero intervention flow in the without-access scenario; native
execution still invokes the bundled deterministic Python core and verifies both
input hashes before writing the result. Static `0.1.0` remains byte- and result-
compatible. The same analysis-plan, validation, report and release graph binds
either schema; no new Agent-authored approval surface is introduced.

Analysis-plan schema `0.2.0` introduced a root `economic_basis`; schemas
`0.3.0` through `0.13.0` retain it and executable extraction-to-model derivations. Schema
`0.8.0` adds 2–16 explicitly ordered strategy IDs, a declared pairwise baseline,
fully incremental dominance/frontier output, and dynamic evidence paths. Each monetary
mapping contains element-level source values and adjustment factors so the
portable Python validator, native Rust approval boundary, and TypeScript review
preview can all reject mixed or unreproducible currency/price-year inputs. The
deterministic engine returns the declared basis with base-case and uncertainty
results; legacy `0.1.0` inputs remain readable but return a null basis and stay
exploratory. No layer owns an implicit exchange-rate or inflation-data service.

Reference-case profiles are immutable packaged resources loaded by ID, never
workspace-supplied policy. The audit validates profile schema, HTTPS source,
source SHA-256, checked/effective dates, unique requirements, supported
applicability rules, and an allowlist of native checks before it considers the
researcher's matrix. The current registry contains China 2020 current, China
2026 consultation draft, and `NICE-PMG36-2026-current`. The NICE adapter binds
the official 31 March 2026 PDF digest and adds deterministic checks for England,
NHS plus personal social services, 3.5% equal discounting, and structured
EQ-5D/UK-3L metadata. It is an executable subset, not a copy of PMG36 or an
agency-compliance claim.

The uncertainty engine owns decision-uncertainty calculations rather than the
language model or UI. Schemas `0.2.0` through `0.8.0` bind a declared threshold grid to the
analysis plan; the Python core uses one seeded PSA draw set for expected
incremental NMB, intervention/comparator/tie probabilities, CEAF, and
per-person EVPI with Monte Carlo error. Rust independently audits the grid and
records its primary threshold and count. The portable validator implements the
same fail-closed contract. The report package must copy the complete
`decision_uncertainty` object exactly when present. Schema `0.7.0`, paired only
with analysis schema `0.8.0`, records aligned per-strategy costs/QALYs, each
strategy's unique-optimal probability, ties, CEAF, and multi-strategy EVPI;
legacy results remain
legacy-shaped. The React review pane is a read-only accessible visualization
of these app-written values; it has no authority to calculate, choose, or alter
thresholds. Its method-review queue admits only current app-audited paired-bootstrap,
NMA, anchored-MAIC, RWE-causal, and advanced-VOI result bindings. It sorts rejected, awaiting,
blocked, and accepted states without rewriting their separate app-owned event chains;
pending judgments open the existing exact-result form, while preparation and repair
return to natural-language interaction.

Uncertainty engine `0.8.0` preserves prior schema draw behavior when no current
correlation groups exist. For a schema `0.4.0` through `0.8.0` group it draws standard normals in
declared group/member order, applies the validated lower Cholesky factor, then
uses each member's declared lognormal parameters. Groups are sampled before
ungrouped parameters. The result echoes every admitted group and matrix so
independent validation can reproduce the first draw and audit the exact joint
assumption. This is not a matrix-estimation or repair service.

### 6.4 MCP servers

AI4HEOR separates product-owned capabilities from arbitrary MCP processes:

1. `$heor-evidence-search` is a native fixed-endpoint PubMed and
   ClinicalTrials.gov metadata route with request-hash binding and Human network
   authorization. It is not MCP passthrough.
2. Jupyter is the only one-click managed local computation server.
3. Local or remote MCP servers manually added by a researcher remain compatible
   but unmanaged. Existing configured legacy servers are preserved on upgrade.

No third-party MCP is a default until a pinned, per-tool adapter passes license,
egress, rights, methods, adversarial, cross-platform, and kill-switch admission.
Paper Search MCP and BioMCP are registered as quarantined candidates; the
generic Materials Project, FRED, space-weather, Open-Meteo, and USGS entries are
retired from the AI4HEOR default catalog.

## 7. Execution layer

```text
Execution Layer
├── OpenCode tools (local, in the bundled runtime)
├── Docker sandbox            (optional, advanced)
├── SSH / Modal remote        (optional, advanced — later)
└── Jupyter Kernel Gateway    (later)
```

OpenCode executes its tools locally within the bundled runtime, gated by its permission
system. Heavier/remote execution (Docker sandbox, SSH, Modal) is optional and belongs in
an advanced "Remote Compute" area, never the default path.

**v1 default:** local execution + manual approval for high-risk actions. Do not
hard-depend on Docker Desktop or WSL in v1 — that raises the install barrier and is not
consumer-grade.

**v0.3 Jupyter Kernel Gateway** for a more notebook-like experience:

```text
Desktop App → Local Runtime Manager → Jupyter Kernel Gateway → Python / R kernel
→ stream output / figures / tables
```

Jupyter Kernel Gateway is a headless Jupyter kernel server addressable over REST /
WebSocket.

## 8. Local Runtime Manager

### 8.1 Why

The installer should not bundle every scientific dependency (huge installer, slow
updates, cross-platform pain, dependency conflicts, hard debugging). Instead: a
lightweight installer + a first-launch Runtime Manager + on-demand scientific env.

### 8.2 Responsibilities

Detect OpenCode; detect Python / uv / Node / Git; create the workspace; create isolated
environments; install base Python packages; manage scientific tool dependencies; start
the OpenCode server; start an optional Jupyter Gateway; monitor runtime health.

### 8.3 Runtime directory

```text
~/.ai4s-workbench/
  config/  runtime/{opencode,python,node}/  profiles/ai4s-workbench/
  workspaces/  logs/  cache/  secrets/
```

The compatibility identifier remains `com.ai4s.workbench`, so existing app-private
provider settings and review records stay in place across upgrades. The researcher-visible
default workspace is `~/Documents/AI4HEOR`. Hidden `.openscience` metadata paths remain a
storage-schema compatibility boundary; they are not the public product or workspace name.

## 9. Storage

### 9.1 Project structure

```text
workspace/
  project.json  plan.md
  data/{raw,processed}/  papers/  parsed/  scripts/  notebooks/
  heor/library/  heor/evidence-library.json
  .openscience/heor-library.sqlite
  figures/  reports/  artifacts/  reviews/
  provenance.jsonl  manifest.json
```

The local evidence import boundary is researcher-triggered. The native folder
picker copies supported files into a unique `heor/library/<selected-folder>/`
root while preserving relative paths. It does not follow links or auto-discover
outside the selected directory; hidden and unsupported entries are returned to
the UI as skipped, and source/workspace overlap fails closed before copying.
Directory creation is transactional at the imported-root level, so a failed
copy removes the incomplete root before any index rescan.

### 9.2 SQLite

Stores: project list, session index, artifact index, app-derived local evidence
pages and source bindings, tool-call state, user settings, runtime state. The
reviewable `heor/evidence-library.json` remains the source manifest; SQLite is a
rebuildable local index and never a substitute for exact source hashes.

### 9.3 JSONL

`provenance.jsonl` is an append-only execution record — easy to read, diff, recover,
export, and open-source friendly.

## 10. Artifact provenance

### 10.1 Manifest

```json
{
  "project_id": "bci-trends",
  "created_at": "",
  "artifacts": [
    {
      "id": "fig_year_trend",
      "type": "figure",
      "path": "figures/year_trend.png",
      "created_by_step": "step_004",
      "input_files": ["data/processed/corpus.csv"],
      "code_files": ["scripts/analyze.py"],
      "status": "reviewed"
    }
  ]
}
```

### 10.2 Provenance event

```json
{
  "event_id": "evt_001",
  "step_id": "step_004",
  "type": "code_execution",
  "tool": "python",
  "command": "python scripts/analyze.py",
  "input_files": ["data/processed/corpus.csv"],
  "output_files": ["figures/year_trend.png"],
  "started_at": "",
  "finished_at": "",
  "status": "success"
}
```

### 10.3 Reviewer rules (v1, deterministic)

Artifact exists; output is recorded in provenance; figure has a code file; table has
source data; report includes limitations; citation has a recognizable ID; script can
be re-run.

## 11. Security

### 11.1 Default permissions

The agent may only access the current workspace; command execution requires approval;
it cannot delete files outside the workspace; it cannot read the whole Home directory;
it cannot auto-upload files; it cannot silently install dependencies.

### 11.2 Approval levels

| Action | Default |
| --- | --- |
| Read current project files | Allow |
| Write current project files | Allow (shown) |
| Overwrite file | Ask |
| Delete file | Require approval |
| Shell command | Require approval |
| Install dependency | Require approval |
| Network access | First-time approval |
| Connect remote server | Require approval |
| Access files outside workspace | Require approval |

OpenCode has a per-tool permission system (allow / ask / deny per agent). The desktop
maps high-risk actions to "ask" and must never blanket-allow them.

### 11.3 API keys

Stored in macOS Keychain / Windows Credential Manager (fallback: encrypted local
secrets). Never enter provenance, logs, crash reports, git, or exported projects.

## 12. Packaging & release

### 12.1 macOS

Outputs: `AI4HEOR_*_aarch64.dmg`, `AI4HEOR_*_x64.dmg`, and a universal build later.
Code signing / notarization needs an Apple Developer account; a free account cannot
notarize. The implementation follows the current
[Tauri macOS signing contract](https://v2.tauri.app/distribute/sign/macos/) and Apple's
[notarization requirements](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

Native CI uses an explicit macOS 15 Apple Silicon runner for `aarch64` and an
explicit macOS 15 Intel runner for `x86_64`. After each build,
`scripts/release/verify_macos_package.py` mounts the DMG read-only; checks the exact
bundle name, identifier, version and executable; requires single-architecture Mach-O
main and sidecar binaries for the declared target; verifies pinned sidecar versions;
compares all configured scientific resources byte for byte; rejects resource links and
generated Python caches; and runs the deterministic HEOR suite against the mounted core.
Manual workflow runs stop there and remain explicitly unsigned. A `v*` tag adds a separate
fail-closed distribution mode. Before Tauri runs, it requires non-empty certificate,
certificate-password, Developer ID identity, Apple ID app-password, and Team ID secrets;
the values are never logged. Tauri receives those secrets only on tagged macOS jobs and
builds with explicit hardened runtime. The verifier then requires strict deep bundle and
per-Mach-O signatures, a shared Developer ID Application chain whose Team ID exactly
matches the credentialed notarization account, secure
timestamps, sealed resources, hardened runtime on every executable, no true
`com.apple.security.get-task-allow`, a valid stapled ticket, and Gatekeeper output from
`Notarized Developer ID`. The tag evidence schema requires the same named checks and proof
fields, so a missing workflow flag cannot be recorded as a trusted macOS release. It does
not install the app into `/Applications` or establish visual/first-start acceptance.

The current 0.1.31 arm64 DMG was additionally cross-built from clean source commit
`2834785e057ac54477a9633f07390bc173251644` on an Intel Mac. The 76,095,510-byte artifact
has SHA-256 `86b0583e36480affb90ec08b84d8c4276ec702b92e69ef90894f58c2888da42e`. Cross-host inspection
can prove bundle metadata, thin Mach-O architectures, exact sidecar/source bytes, exact
resource bytes, and the platform-independent HEOR suite. It cannot execute the arm64
sidecars or desktop binary. The native verifier therefore fails closed with `Bad CPU type`
and emits no formal evidence JSON; an Apple Silicon runner is still required. Separate
`codesign`/`spctl` inspection found only an ad-hoc linker signature with no Team ID,
sealed resources or stapled ticket, so strict signature verification and Gatekeeper both
reject it; this artifact is neither Developer-ID signed nor notarized.

### 12.2 Windows

Outputs: `AI4HEOR_*_x64-setup.exe` and `AI4HEOR_*_x64_en-US.msi`. Prefer the NSIS
`Setup.exe` in v1 for a familiar install experience. Unsigned apps run but may trigger
SmartScreen; formal release needs a code-signing certificate (EV certs earn SmartScreen
reputation faster). Early GitHub Release preview builds may be unsigned, but the README
must say so.

The Windows 2022 CI runner builds both formats and then runs
`scripts/release/verify-windows-package.ps1`. The verifier reads ProductName,
ProductVersion, and ProductCode from the MSI; administratively extracts it; rejects
reparse points and generated Python caches; requires x86-64 PE binaries; verifies the
pinned OpenCode and uv versions; compares every configured scientific resource with the
source tree; and runs the deterministic HEOR suite against the extracted core. It then
silently installs the NSIS package into a clean runner, starts the installed application,
and requires exactly one installed desktop process, one bundled OpenCode process, and a
new local workspace before cleanup. This is an automated host-level gate, not a visual or
non-technical-user acceptance test.

### 12.3 Linux

Outputs: `.deb` and `.rpm` for x86_64 Linux. AppImage remains disabled because
`linuxdeploy` invokes `ldd` on the bundled Bun-built OpenCode sidecar and aborts on
that valid standalone binary. RPM payloads use Tauri's supported `zstd` compression at
level 3; this avoids the substantially slower default gzip packaging path while remaining
readable by the Ubuntu 22.04 RPM toolchain.

The Linux CI job builds in Ubuntu 22.04 and then runs
`scripts/dev/verify_linux_packages.py`. The verifier checks `.deb`/`.rpm` metadata and
x86-64 ELF architecture; extracts RPM through the official `rpm2archive` tool; verifies
the pinned OpenCode and uv versions; compares all bundled scientific resources byte for
byte with the source tree; rejects links and generated Python caches; and runs the entire
deterministic HEOR Python suite independently from each extracted package. It also proves
that the two packages contain identical sidecars and main-program bytes apart from the
single expected Tauri bundle-type marker.
The job writes the same release-evidence schema as macOS and Windows, including both
package hashes and the deb/rpm parity result.

Version 0.1.30 was installed into brand-new native package environments. A non-root
headless X session on Ubuntu 22.04 after `.deb` installation reached exactly one
`ai4s-workbench` process and one bundled `opencode` process and created
`~/Documents/AI4HEOR`. A separate Fedora 42 RPM run started with a seeded
`~/Documents/OpenScience/legacy-fixture/marker.txt`, preserved its exact contents under
`~/Documents/AI4HEOR`, removed the legacy root, and reached the same single-process
boundary. A rename failure still reuses the legacy root rather than splitting data. The
independently extracted `.deb` and `.rpm` payloads each passed all 177 deterministic HEOR
tests and all 282 configured scientific resources matched the source bytes with aggregate
SHA-256 `94c80aa04d6f18661b1444c87396a9619b98a02952dde17929654f600ce13bad`.
This establishes clean native installation, migration and headless runtime startup for
both package formats, but it is not a visual desktop-session acceptance test. A real Linux
desktop session remains a release check.

### 12.4 Auto update

Tauri updater with GitHub Releases + `latest.json` + a Tauri updater signature (update
packages must be signed; signature verification cannot be disabled). v0.1 no forced
auto-update; v0.2 adds a GitHub Releases updater; v0.3 adds in-app update prompts.

### 12.5 CI/CD

GitHub Actions build matrix:

```yaml
macos-15:
  - aarch64-apple-darwin
macos-15-intel:
  - x86_64-apple-darwin
windows-2022:
  - x86_64-pc-windows-msvc
ubuntu-22.04:
  - x86_64-unknown-linux-gnu
```

The official Tauri GitHub Action builds native binaries for macOS / Linux / Windows.
Every target emits `ai4heor-release-evidence/v1`, binding the clean tracked source
commit, app version, target, exact package hashes, all source scientific-resource
records, bundled sidecar hashes/version outputs, runner identity, named checks, and
platform-verifier details. `scripts/release/release_evidence.py` rejects malformed
platform/target pairs, tampered packages, duplicate targets, mixed source commits, and
different resource inventories.

Only after all four build jobs pass does a separate Ubuntu job download the actual
workflow artifacts, re-hash every DMG/MSI/NSIS/deb/rpm, require all four explicit
targets from the same workflow run and attempt, and write
`ai4heor-release-manifest/v1`. Workflow artifacts retain the four
evidence files and manifest. Matrix builds never create or populate a GitHub Release.
Only after the final job validates the manifest and finds exactly four evidence files and
six installers may it create a new draft release and attach that exact set; an existing
release for the tag makes the step fail instead of merging stale assets. This is a
workflow-produced source/package association, not a reproducible-build proof, signed
provenance attestation, visual acceptance, or scientific-validity claim. The schema and
macOS/Linux verifier changes are locally tested, and the current commit now has bounded
cross-host arm64 package inspection in addition to native x64 macOS/Linux evidence. The
four-target current-commit manifest remains configured rather than executed until native
CI produces every target-eligible evidence file. On a tag, macOS evidence additionally
requires the complete distribution-trust proof above; no credentialed run has yet supplied
it, so the pipeline configuration is not itself a signed/notarized release claim.

## 13. Process model

### 13.1 Startup

```text
User opens app → Tauri starts → Frontend loads → Runtime Manager checks dependencies
→ Start OpenCode sidecar → Connect to Gateway → Load projects → Ready
```

### 13.2 Agent task

```text
User submits task → Frontend sends prompt to OpenCode → OpenCode plans
→ Frontend renders plan approval card → User approves → OpenCode executes tools
→ Tool events stream back → Runtime writes artifacts → Provenance service records events
→ Reviewer runs checks → Frontend updates artifact/review panels
```

## 14. High-performance design

### 14.1 UI

Layered state: UI state in Zustand, server/runtime state in TanStack Query, streaming
events in an event bus. Big-data optimizations: paginated CSV preview, virtualized log
viewer, lazy Markdown render, lazy artifact load. Render optimizations: memoized
tool-call cards, batched message chunks, `requestAnimationFrame` batching, background
task workers.

### 14.2 Runtime

Persistent OpenCode server; reused project sessions; incremental file index; artifact
hash cache; per-project reused Python env; literature metadata cache; cached PDF parse
results; figure preview thumbnails.

### 14.3 Startup targets

```text
App UI cold start: < 3s
Runtime ready: < 10s
First agent response: < 5s after runtime ready
```

Strategy: UI first, runtime after; show runtime-loading state on Home; a failed OpenCode
connection must not block the UI; first-time dependency install happens in onboarding.

## 15. Error handling

### 15.1 Runtime errors

OpenCode not started; Gateway start failure; port in use; missing API key; model
connection failure; workspace permission denied; broken Python env; Docker unavailable;
MCP server start failure. Each must provide: a human-readable explanation, collapsible
technical details, a one-click fix button, and a copy-logs button.

### 15.2 Agent errors

Tool-call failure; literature source rate-limited; dependency install failure; code run
failure; file permission failure; citation check failure. Must show: the failed step,
the cause, a fallback suggestion, a retry button, and an edit-plan button.

## 16. Repository structure

Monorepo:

```text
ai4s-workbench/
  apps/desktop/{src,src-tauri}/
  packages/{ui,shared,sdk}/
  runtime/{manager,opencode-profile,mcp,skills}/
  docs/{PRD.md,TECHNICAL_DESIGN.md}
  examples/bci-trends/
  scripts/{release,dev}/     # dev/fetch-opencode.sh fetches the pinned sidecar
```

- `apps/desktop` — Tauri + React desktop app; `src-tauri/src/runtime.rs` supervises the
  bundled OpenCode sidecar (`OpenCodeClient` lives in `packages/sdk`).
- `runtime/manager` — local runtime manager (detect deps, workspace, provenance, logs).
- `runtime/opencode-profile` — the AI4HEOR OpenCode config/skills bundle.
- `runtime/skills` — self-authored scientific skills.
- `examples` — the complete demo project.

## 17. v0.1 task breakdown

### 17.1 Day-one goals

1. Init Tauri + React.
2. Build the main layout.
3. Build a static onboarding page.
4. Build a static project workspace page.
5. Build tool-call card / artifact card / approval dialog.
6. Bundle + auto-start OpenCode; connect via `OpenCodeClient` (HTTP + SSE).
7. Ship the OpenCode config/skills bundle.
8. Write the 3 core skills.
9. Build static artifacts for the synthetic HEOR cost-effectiveness example.
10. Draft the GitHub Actions build.

### 17.2 v0.1 must deliver

macOS app runs; Windows and Linux packages build on native runners; README has
screenshots; a complete demo; API key
config; open a workspace; a bundled OpenCode the app auto-starts and drives (sessions,
streaming, history, skills); show plan / tool / artifact / review; export `report.md`.

## 18. Technical risks

### 18.1 OpenCode desktop integration

Risk: OpenCode API changes across versions. Mitigation: wrap `OpenCodeClient`; never call
OpenCode directly from the UI; **pin the OpenCode version** (`OPENCODE_VERSION`); bundle
the pinned binary so the app is not affected by the user's own OpenCode.

### 18.2 Windows environment complexity

Risk: WebView2, permissions, Defender, SmartScreen, PATH, missing Python / Git / Node.
Mitigation: the Runtime Manager detects the environment; do not hard-depend on system
Python early; provide a portable fallback; code-sign for formal releases.

### 18.3 Installer size

Risk: bundling a large runtime and scientific packages makes the installer huge.
Mitigation: OpenCode is a single ~44 MB-installer sidecar (cheap to bundle); keep the app
body light; install heavy scientific dependencies on demand as optional Science Packs;
defer Docker / Jupyter.

### 18.4 Agent safety

Risk: the agent runs commands, reads/writes files, accesses the network. Mitigation:
manual approval by default; workspace allowlist; isolated local secrets; dangerous-
command dialogs; optional Docker sandbox; full provenance recording.

## 19. Final stack

```text
Tauri 2
React + TypeScript + Vite
Tailwind + Radix UI
OpenCode as agent runtime (bundled single-binary sidecar, pinned OPENCODE_VERSION)
OpenCode HTTP + SSE API via OpenCodeClient (packages/sdk)
OpenCode skills/agents + optional third-party scientific skills
Local workspace + SQLite + JSONL provenance
DMG / NSIS / MSI installers via GitHub Actions
GitHub Releases (self-contained; sidecar fetched at build time)
```

One line:

**Use Tauri for a high-performance modern desktop shell, a bundled+isolated OpenCode as
the Claude Code alternative layer, scientific skills and MCP as the research capability
layer, and provenance/reviewer as the real moat of an open-source Claude Science alternative.**

## Partitioned-survival alpha contract (2026-07-15)

`heor/partitioned-survival-plan.json` schema `0.7.0` is an optional, hash-bound
analysis linked from structure-neutral analysis schema `0.15.0`. It requires the exact state order
`progression_free`, `progressed`, `dead`; a forward-only conceptual basis;
aligned time-zero and cycle-endpoint PFS/OS values with exact ordered review,
fit-output, and evaluator basis IDs;
and exact PFS/OS review-file hashes, logical strategy/endpoint targets, and
Human-selected converged families. It binds the exact schema `0.1.0`
`heor/survival-curve-materializations.json` bytes as immutable source curves and
the exact schema `0.1.0` `heor/treatment-effect-duration.json` bytes. Each source curve
binds a strict selected-fit output and one explicit `exponential_rate` or
`weibull_shape_scale_aft` parameterization, evaluator
`ai4heor-parametric-survival@0.1.0`, analysis grid, and reproduced values. The
portable materialization validator and native Rust independently read the
review and typed fit-output bytes and evaluate `exp(-rate*t)` or
`exp(-(t/scale)^shape)`; any hash, family, parameter, value, order, or copied-
basis drift fails closed. The duration contract admits exactly two ordered strategies
and requires endpoint-specific policies covering sustained, immediate-stop, and
log-linear-waning effects. Every scenario shares one explicit evidence horizon,
HR, and HR evidence basis per endpoint. After the evidence horizon, the intervention
curve is rebuilt from comparator cumulative-hazard increments; the engine never
infers duration from an HR point estimate, silently repairs crossing, or mutates the
source materialization. The native boundary reuses the full
survival-review audit and requires the bound review context to name the matching
PFS or OS endpoint. The dependency-free engine computes
occupancy directly as `(PFS, OS-PFS, 1-OS)` and applies the base plan's state
costs, utilities, half-cycle rule, discount rates, strategy ordering, and
threshold. It never constructs a transition matrix. Native Rust independently
reads every bound review byte and binds the PSM assets into analysis-plan
approval. The current release gate rejects linked PSM analyses until the model-
validation and report-package schemas are extended to bind the PSM plan and
result; this prevents an unsupported decision-ready claim. Analysis schema
`0.15.0` contains only common economic inputs for each strategy; transition
matrices, schedules, and initial distributions are forbidden rather than
silently ignored.

PSM `0.6.0` also binds exact schema `0.1.0`
`heor/utility-inputs.json` bytes. Each strategy/state item records measurement,
valuation, mapping, license, captured/excluded effects, overlap assessment,
source utility, optional explicit multiplicative cycle adjustments, and
uncertainty availability. Python, the dependency-free Skill validator, and
native Rust independently reproduce each cycle value and complete schedule;
the PSM engine consumes that schedule for QALYs. The generic engine does not
hard-code an instrument or value set. Human review retains those choices. PSM
`0.7.0` also binds schema `0.1.0` `heor/event-disutilities.json`; Python, a
dependency-free validator, and native Rust reproduce each supported event mode
and enforce exact utility exclusions. The calculation weights event losses by
state occupancy and the existing HCC and outcome-discount rules. Uncertainty
schema `0.13.0` executes bounded event/utility/cost component DSA and PSA through
the separately audited component artifacts. The analysis `state_utilities` must equal the first schedule
row, and legacy analysis `0.13.0` / PSM `0.5.0` remains readable.

PSM `0.5.0` also binds exact schema `0.1.0`
`heor/cost-input-normalization.json` bytes. Each annual state-cost item records
an evidence-bound annual quantity, compatible unit, source unit price, currency,
price year, jurisdiction, price basis, tax status, and every explicit inflation,
currency-conversion, or price-adjustment factor. Python, the dependency-free
Skill validator, and native Rust independently reproduce
`normalized_unit_price = source_unit_price * product(adjustment_factors)` and
`annual_item_cost = annual_quantity * normalized_unit_price`, then require the
strategy/state item sum to equal the analysis `state_costs`. Inflation is
required exactly when price years differ; currency conversion is required
exactly when currencies differ. The contract does not choose an index, exchange
rate, tax treatment, price concept, or transferability judgment. It currently
admits deterministic annual state-cost rates only; event, one-time, time-varying,
capital, dynamic-BIA, and societal-cost structures remain blocked. Component
uncertainty admits only annual quantity, unit price, and explicit adjustment
factors from this ledger. Legacy analysis `0.12.0` / PSM `0.4.0` remains
readable without this binding.

Paired uncertainty schema `0.11.0` hash-binds the fixed PSM plan, source materializations,
and duration artifact and runs DSA, PSA, and bounded economic structural
scenarios only over exact state-cost and state-utility scalars. The Python core,
portable validator, native Rust boundary, and browser result surface enforce the
same `partial_parameter_uncertainty` / `economic_inputs_only` classification.
Every strategy's PFS and OS curve must be named as an omitted parameter. Survival
parameter covariance and joint PFS/OS uncertainty therefore remain explicit
limitations of this compatibility path.

Uncertainty schema `0.12.0` and engine `0.13.0` add a bounded backend-neutral
joint-draw path through schema `0.2.0` `heor/joint-survival-uncertainty.json` and
`heor/joint-survival-draws.jsonl`. One row covers every strategy PFS then OS
curve on the exact analysis grid and is consumed intact in one PSA iteration,
together with sampled economic inputs. The admitted source is a reviewed joint
posterior or paired-patient bootstrap; current manifest `0.5.0` records the
strategy resampling design and between-strategy assumption. For a paired bootstrap
it also binds the exact app-owned accepted method-review record and result; prior-
current `0.4.0` and `0.3.0` remain readable but cannot newly authorize a paired
analysis. A joint
posterior may declare a source distribution spanning all curves. The shipped
paired bootstrap resamples whole patient rows within independent parallel arms,
preserves within-strategy PFS/OS dependence, and explicitly declares conditional
independence between strategies. Independent endpoint sampling, marginal-
interval covariance reconstruction, row filtering, crossing repair, and silent
draw replacement fail closed. Python, a standalone standard-library validator,
and native Rust independently verify hashes, source bytes, row count/order,
finite monotone survival, and PFS no greater than OS. The native paired-bootstrap
auditor additionally regenerates the exact PCG32 frequency plan and recalculates
every curve from reported natural parameters. It does not repeat the R statistical
refits. The desktop verifies the separate app-data review chain at analysis
approval and again before each uncertainty execution, so a later rejection for
the same execution invalidates an earlier acceptance. The output classification
is `joint_curve_draw_parameter_uncertainty` with scope
`joint_survival_curves_and_economic_inputs`. Curve-family selection,
extrapolation assumptions, source-model validity, and probabilistic integration across
duration alternatives remain explicit structural limitations. Independent validation is
Human-owned and must bind the exact current PSM methods, inputs, and results before release.
Treatment-effect duration is no longer a silent omission: the base policy is hash-bound
and all three alternatives are returned as separate deterministic cost/QALY scenarios;
conditional CEAC, CEAF, and per-person EVPI are not presented as complete PSM
uncertainty.

Uncertainty schema `0.13.0` and engine `0.14.0` pair only with analysis `0.15.0`
and PSM `0.7.0`. The plan hash-binds the PSM plan, curve materializations,
treatment-duration, cost-normalization, utility, and event artifacts. Targets
are restricted to allowlisted raw ingredients rather than aggregate state
rewards. Every DSA endpoint and PSA draw rebuilds normalized prices, annual
costs, utility schedules, per-event QALY losses, and strategy/cycle/state
aggregates before evaluating the fixed survival curves. Uniform, Gamma, and
Lognormal marginals are admitted independently; an evidence-bound,
Human-supplied latent-standard-normal Gaussian-copula matrix may combine only
Uniform and Lognormal members. Shared provenance does not imply correlation.
The output is `component_parameter_uncertainty` with scope
`cost_utility_event_components_only`; all PFS/OS curves must remain explicit
omissions, so it is not a complete PSM PSA.

Uncertainty schema `0.14.0` and engine `0.15.0` retain the same current PSM and
component bindings, then add exact joint-survival manifest `0.5.0` (with prior-current `0.4.0` and `0.3.0` readable) and JSONL
draw bindings. After fail-closed validation, every PSA iteration consumes one
complete cross-strategy PFS/OS row and one component draw, rebuilding every
affected cost, utility, and event aggregate before curve evaluation. The base
case, DSA, discount/half-cycle scenarios, and treatment-duration alternatives
retain reviewed deterministic curves. Output is
`joint_curve_and_component_parameter_uncertainty` with scope
`joint_survival_curves_and_cost_utility_event_components`. Curve-family choice,
extrapolation, source-model validity, probabilistic treatment-duration
alternatives, and independent validation remain outside the calculation.
Dependence is preserved within joint curve rows and admitted component groups,
but not between those two fragments; known cross-domain dependence remains a
Human-reviewed blocker rather than being silently treated as zero.

Advanced value-of-information schema `0.1.0` is a separate research-
prioritization graph. It binds the exact analysis plan, uncertainty plan, and
converged uncertainty result. The standard route admits odds-ratio uncertainty
`0.9.0` only when its EVSI target is an independent Lognormal parameter; the
current fixed-survival PSM route admits component uncertainty `0.13.0`. HR
uncertainty `0.10.0` is Uniform and therefore fails the declared log-scale
Normal-Normal EVSI contract rather than being approximated. Population EVPI
uses explicit annual affected populations and discounting. EVPPI and EVSI use
bounded nested Monte Carlo with reported MCSE; EVSI supports one Human-specified
Normal sample-mean likelihood and a finite candidate sample-size set. Python
emits an exact compact replay, native Rust verifies current model-input hashes
and independently recomputes population, EVPPI, EVSI, study-cost, and ENBS
summaries, and the desktop binds plan/result/replay into an app-owned eight-
check Human review chain. The release report graph does not absorb this result
implicitly.
The materializer does not fit data, transform backend coefficients, choose a
family, infer covariance, support other survival families, or establish clinical/external
validity. Treatment-effect application is limited to the separate duration contract above.
Those remain distinct contracts. Validation/report schema `0.2.0` now binds the
current PSM plan, five input artifacts, deterministic PSM and uncertainty results,
and BIA result. `heor_reproducibility.rs` independently audits the derived schema
`0.1.0` release companion: exact report inventory, three replay commands, current
AI4HEOR/platform/Python/result-engine identity, source availability, three exhibits,
and seven required claim links. The release gate replays all three calculations,
compares hashes, re-audits the companion, and appends one event binding the report
graph plus the companion. Runtime or artifact drift fails closed; no second approval
gate is introduced.

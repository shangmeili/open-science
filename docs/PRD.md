# AI4HEOR Desktop — Product Requirements

> **Status (AI4HEOR 0.1.56 internal test, 2026-07-20).** The runtime is **OpenCode**, bundled as an isolated
> sidecar (one-click, auto-started, does not touch a user's own OpenCode). Built: the
> three-column workbench UI, real multi-session chat with history, a real Skills/Agents
> view, BYOK key config, Intel macOS and Windows x64 test installers, and the first-party HEOR workflow described
> in `docs/HEOR_PRODUCT.md`. Generic Science Pack statements below remain platform
> lineage and roadmap; they do not override the narrower AI4HEOR product contract.

## 1. Positioning

**AI4HEOR** is a natural-language-first, local-first, model-agnostic desktop
workbench for pharmacoeconomics and HEOR on macOS, Windows, and Linux. Codex
Agent builds and verifies the product; inside the product, the Human researcher
leads the scientific work and the configured model/runtime assists under
explicit Human-in-the-loop gates.

It is not an ordinary paper-summarization tool. It is a local-first, model-agnostic,
reproducible, auditable research agent workbench that helps researchers do:

- Literature search
- Paper parsing
- Data analysis
- Code execution
- Figure generation
- Report writing
- Citation checking
- Artifact provenance
- Reusable research workflows

Product definition:

> AI4HEOR is developed by Codex Agent for Human-led pharmacoeconomic and HEOR
> research: natural-language first, local first, model agnostic, and
> Human-in-the-loop.

## 2. Goals

AI4HEOR specializes this platform for pharmacoeconomic and HEOR work. Natural
language is the primary interaction; forms, matrices, and charts are secondary
review and ambiguity-resolution surfaces. The human researcher leads the study:
the AI assists with retrieval, artifact preparation, execution, checking, and
explanation, but does not own the research question, method choices, evidence
selection, assumptions, interpretation, or release. Codex Agent leadership applies
to building and maintaining this product, not to conducting a user's HEOR study.
Decision calculations remain in
versioned deterministic engines. The base uncertainty result includes declared-
threshold CEAC/CEAF and per-person EVPI, with population EVPI and EVPPI
explicitly null. The optional advanced-VOI workflow separately produces
population EVPI, EVPPI, one-parameter EVSI, and ENBS only from explicit Human-
owned population and study-design inputs, deterministic replay, and an app-owned
Human method review; it does not claim optimal study design, reimbursement,
funding, or policy recommendations. Current
PSM component uncertainty recomputes reviewed raw cost, utility, and event
inputs under fixed survival; it is explicitly not a complete structural PSA.
The research-and-analysis pane consolidates only current app-audited paired-bootstrap,
NMA, anchored-MAIC, natural-history model-calibration, semi-Markov microsimulation,
RWE-causal, and advanced-VOI results into one method-review queue. Pending
results open the exact Human form; rejected or blocked results return to the
natural-language conversation for repair. The queue neither creates authority nor
turns scientific work into a form-led workflow.

### 2.1 Phase 1 goal

Phase 1 must be a genuinely installable desktop app, not a CLI tool.

Required support:

| Platform | Installer | Priority |
| --- | --- | --- |
| macOS Apple Silicon | `.dmg` / `.app` | P0 |
| macOS Intel | `.dmg` / `.app` | P1 |
| Windows x64 | `.exe` NSIS installer | P0 |
| Windows x64 | `.msi` installer | P1 |

Tauri officially supports macOS and Windows and can package `dmg`, `app`, `nsis`,
and `msi` targets; Windows can ship as `.msi` or an NSIS `setup.exe`.

### 2.2 Differentiation

Versus ordinary AI paper tools, AI4HEOR is different because it is:

1. A research workbench, not a chat box.
2. A generator of traceable artifacts, not just text.
3. Model-agnostic (BYOK / OpenRouter / OpenAI-compatible / local), not tied to one model.
4. Transparent — it keeps code, data, figures, reports, logs, and provenance — not a black box.
5. HEOR-specific by default — starters, examples, Skills, artifacts, and review
   boundaries use pharmacoeconomic methods and terminology rather than exposing
   the generic Open Science platform base.

## 3. Target users

### 3.1 Core users

1. **Pharmacoeconomics and HEOR researchers** — model design, evidence review,
   economic evaluation, uncertainty analysis, validation, and reporting.
2. **HTA and reimbursement analysts** — prepare auditable local work products
   while retaining Human ownership of jurisdictional interpretation and decisions.
3. **Students and methodologists** — learn or inspect HEOR methods through
   synthetic examples, deterministic calculations, provenance, and explicit limits.
4. **Open-source AI agent users** — already using OpenCode, Codex, Claude Code, Cursor,
   MCP, Agent Skills; want a research-focused desktop product.

### 3.2 Non-target users (Phase 1)

- Complete beginners who cannot configure an API key.
- Users needing clinical diagnosis or medical decisions.
- Institutions needing multi-user collaborative SaaS.
- Teams needing enterprise permissions, audit, or SSO.

## 4. Core product principles

### 4.1 Local-first

Runs on the user's machine by default. Project files, corpora, figures, reports, and
execution logs are stored in a local workspace.

### 4.2 Model-agnostic

No lock-in to Claude, OpenAI, or any single local model. Users can choose OpenRouter,
OpenAI-compatible APIs, the Anthropic API, or local models; Ollama / vLLM / LM Studio
support follows.

### 4.3 Reproducibility-first

Every important artifact must be traceable:

| Artifact | Must trace to |
| --- | --- |
| Figure | generating code, input data, parameters |
| Report | citation sources, data sources, analysis steps |
| Table | raw data, cleaning script |
| Conclusion | citations, data, model output |
| Agent action | time, tool, input, output, status |

### 4.4 Human-in-the-loop

High-risk actions — file writes, command execution, dependency installs, network
access, file deletion, remote compute — require user approval. The bundled OpenCode runtime provides
dangerous-command approval, container isolation, MCP credential filtering, and
cross-session isolation.

## 5. MVP scope

### 5.1 P0 features

#### 5.1.1 Install & first launch

After downloading and first opening, the user enters onboarding:

1. Choose a model provider.
2. Enter an API key.
3. Choose a workspace directory.
4. Verify that the AI assistant environment is ready.
5. Use the bundled assistant environment (auto-started; no separate install).
6. Start a standalone task or create the first research project.

First launch must clearly tell the user: data is stored locally by default; the agent
requests authorization before sensitive actions; the user must explicitly select a
model and configure credentials when its provider requires them; research results need
human verification and are not final conclusions.

The implemented first-use guide is deliberately not a setup wizard or scientific
form. It appears once above the still-visible natural-language HEOR entry, explains
local storage, provider choice, default approval boundaries, and Human scientific
authority, and links to model/privacy settings without selecting anything. Completion
is a local UI preference only and cannot authorize research, data transfer, or release.

#### 5.1.2 Default HEOR entry

The application opens on the AI4HEOR research workbench. The workbench orients
the researcher with projects, recent tasks, and HEOR starters; it is not a second
task-creation command. “New task” is the single explicit blank-task entry, while
project `+` starts a task whose files and context belong to that project. Named
HEOR projects remain available for work that should share files and context across
tasks. Neither path uses an inherited generic Open Science example.
The empty state offers pharmacoeconomics and HEOR tasks: local-knowledge-base
learning, decision-problem scoping, Human-authorized evidence search, model-input
research, and analysis-plan audit. Runtime, model, workspace, project, and task
state remain visible without displacing the research conversation. The main surface
labels this only as the “AI assistant” state. OpenCode is an implementation detail:
its engine name and local endpoint appear only in collapsed advanced diagnostics,
and its command or port is not exposed in the HEOR workspace.

The local-learning route includes an auxiliary, explicit install action for the
versioned Simplified-Chinese pharmacoeconomics learning library shipped with the
desktop package. The app verifies the manifest and every source SHA-256, preserves
the theory/methods versus dated-progress boundary, installs without a model or
network call, builds the existing local index, and never overwrites an edited or
conflicting installed copy. Researchers may instead add their own local folders.

Standalone tasks retain the same assistant, Skills, HEOR methods, local files,
review, and audit functions as project tasks. Their local scope is private to that
task instead of being shared. Creating a project asks only for its local display name, then pre-fills an unsent,
localized natural-language intake request. Scientific scope, methods, evidence,
assumptions, and approvals are not collected or chosen by the creation form.

#### 5.1.3 Research agent workspace

The main work area, in a three-column layout:

```text
Left:   projects / workflows / files
Middle: agent chat + plan + execution progress
Right:  artifacts / citations / review / run logs
```

Core interaction: user submits a task → agent produces a plan → user confirms →
agent runs tools → each step shows status → artifacts land in the Artifact panel →
reviewer checks automatically → user exports the report.

#### 5.1.4 Plan confirmation

For multi-step tasks the agent must produce a plan before executing.

```text
Goal:
Data sources:
Steps:
Expected artifacts:
Risks & limitations:
Actions requiring authorization:
```

User options: Approve · Edit Plan · Run Step by Step · Cancel.

#### 5.1.5 Literature search

AI4HEOR alpha ships a narrower, verified HEOR path: natural-language drafting
of an exact request followed by app-owned human authorization for fixed PubMed
and ClinicalTrials.gov metadata endpoints. The Agent cannot make the network
call. Each run binds request and response hashes, preserves source limitations,
and imports records only as `not_assessed` candidates for later screening and
appraisal.

AI4HEOR also ships a local evidence-library alpha. The desktop copies selected
PDF/TXT/Markdown/CSV/JSON files into `heor/library`, binds exact source SHA-256
values and the derived index SHA-256 in `heor/evidence-library.json`, extracts
searchable pages locally, and stores the serialized index under `.openscience`.
`$heor-local-evidence` verifies the manifest, index, source, and page bytes
before returning path/page/hash citations. Scanned
PDFs are marked `requires_ocr`; encryption, unsupported formats, extraction
failure, source changes, and symlink escapes remain visible and fail closed.

Decision-relevant extracted values cross a separate Human-in-the-loop boundary.
The app shows the exact value, target, record, source location, and applicability,
then records confirmed or rejected extraction IDs against the current synthesis
SHA-256 in an app-owned hash chain. Each selected extraction needs confirmations
from two distinct local reviewer labels; a duplicate label or any rejection
fails closed. The analysis plan binds that synthesis and maps each source-based
input to matching extraction IDs. Workspace `human_checked` text alone is never
accepted, and changing the synthesis invalidates every prior review decision.
The alpha does not claim authenticated identity or truly independent duplicate
extraction.

Reference-case selection is also natural-language first. The Agent can prepare
an analysis against China 2020 current, China 2026 consultation draft, or NICE
PMG36 updated 31 March 2026, but the desktop independently loads the exact
packaged profile and audits every matrix row. The NICE executable subset binds
the official PDF hash and checks England jurisdiction, NHS and personal social
services perspective, 3.5% discounting, and structured EQ-5D/UK-3L metadata.
Profile selection is never presented as jurisdictional compliance or agency
acceptance. CDA-AMC remains unbundled until its official source bytes can pass
the same reproducible source-hash admission gate.

The broader platform backlog—arXiv, Crossref, OpenAlex, Semantic Scholar,
`corpus.csv`, generic CSL XML processing, OCR, and complex layout/table
reconstruction—remains planned. Project-local RIS, bounded BibTeX, and CSL-JSON
import, deterministic deduplication, and exchange export are supplied by the
first-party `literature-review` Skill. The first-party `citation-formatting`
Skill and native renderer add three bounded AI4HEOR-owned profiles without
bundling third-party CSL style files or claiming journal certification. OpenAlex
currently needs an API key, so it requires a separate credential and consent
flow before admission.

#### 5.1.6 Skills library

The Skills page lists the **real** skills and agents OpenCode loaded and separately
shows the native third-party admission audit. Its natural-language action creates or
evaluates a candidate but never installs it directly. Skill sources are layered:

1. **OpenCode built-in** skills/agents (shipped with the runtime).
2. **AI4HEOR first-party Skills** — 52 pharmacoeconomics, evidence, analysis,
   validation, reporting, execution, capability-authoring, and preference-proposal
   Skills under `runtime/skills/core`, deployed only into the app-private profile.
3. **Third-party scientific skills** — inactive until a machine-validated,
   hash-locked `validated-adapter` entry passes license, security, methods,
   cross-platform, and Human-in-the-loop release evidence.
4. **Locally authored candidates** — bilingual, instruction-only, deny-by-default
   candidates under `capabilities/candidates/`. They are outside every active Skill
   discovery directory and remain inert until an app-owned Human review records
   admission for the exact validated hash.

Repeated non-sensitive work patterns may be written only as proposals under
`learning/proposals/` after at least two independent interactions. One interaction
cannot become policy; scientific choices and sensitive content are never preferences;
only researcher-accepted entries in `learning/preferences.json` are durable. The current
release ships candidate/proposal creation and validation, not silent activation or model
retraining.

#### 5.1.7 Code execution

v1 languages: Python, Shell (R later).

| Mode | Notes |
| --- | --- |
| Local | Run directly in the local workspace |
| Docker | Run in an isolated container |
| SSH | Remote server execution (later) |
| Modal | Cloud execution (later) |
| Jupyter Kernel | Notebook-style persistent kernel (later) |

OpenCode runs tools locally inside the bundled runtime by default; Docker sandbox and
SSH / Modal remote execution are optional advanced backends, so the desktop starts local
and expands later.

#### 5.1.8 Artifact panel

All outputs land here. Types: Markdown reports, source-bound XLSX/CSV research tables,
PNG / SVG figures, PDFs, Python scripts, notebooks, JSONL provenance, review reports.

Each artifact shows: filename, type, created time, generating step, input data,
generating code, review status, and export / copy / open actions.

#### 5.1.9 Provenance

Each project auto-generates `provenance.jsonl`, `manifest.json`, and `review.md`.

`provenance.jsonl` records each step, append-only:

```json
{
  "step_id": "step_001",
  "type": "literature_search",
  "tool": "openalex",
  "input": {},
  "output_files": ["data/corpus.csv"],
  "timestamp": "",
  "status": "success"
}
```

#### 5.1.10 Reviewer panel

v1 reviewer does basic checks: citations exist; DOI / PMID / arXiv IDs are
well-formed; figures have generating code; tables have source data; reports include
limitations; no untraced artifacts; no steps the agent claims but never ran.

## 6. UI design requirements

### 6.1 Keywords

Modern, restrained, refined, research feel, tool feel — not flashy, not a traditional
admin panel, not a low-quality AI wrapper. Reference vibes: Linear's simplicity,
Cursor's technical feel, Notion's information structure, Raycast's command palette,
Vercel's cleanliness, Claude's warmth.

### 6.2 Visual style

Light theme (default):

| Use | Suggestion |
| --- | --- |
| Background | warm white / soft gray |
| Primary | deep indigo / blue violet |
| Accent | teal / cyan |
| Success | soft green |
| Warning | amber |
| Error | soft red |
| Text | near black / slate |

Dark theme:

| Use | Suggestion |
| --- | --- |
| Background | near black / deep navy |
| Card | dark slate |
| Primary | blue violet |
| Accent | cyan |
| Text | soft white |

### 6.3 Main layout

```text
┌─────────────────────────────────────────────────────────┐
│ Top Bar: Project / Model / AI status / Sync / Settings  │
├──────────────┬──────────────────────────┬───────────────┤
│ Sidebar      │ Main Agent Workspace      │ Artifact Dock │
│ Projects     │ Chat / Plan / Execution   │ Files         │
│ Workflows    │ Progress Timeline         │ Figures       │
│ Skills       │ Code Blocks               │ Tables        │
│ Connectors   │ Reports                   │ Citations     │
│ Settings     │                          │ Review        │
└──────────────┴──────────────────────────┴───────────────┘
```

### 6.4 Core pages

- **Research workbench** — projects, recent tasks, researcher-led HEOR starters, AI assistant status, and model status. The AI4HEOR brand returns here; it is not duplicated in sidebar navigation.
- **New task** — one unconstrained natural-language entry for standalone work; every explicit click creates a visibly clean, focused draft.
- **Project Workspace** — agent chat, execution timeline, plan approval card, tool-call cards, artifact dock, review warnings.
- **Literature** — search, filter, list, abstract preview, PDF status, citation info, add to corpus, export BibTeX / CSV.
- **Data & Code** — file tree, Python scripts, notebook preview, CSV preview, run history, environment dependencies.
- **Artifacts** — figure gallery, report preview, table preview, provenance chain, download / export.
- **Review** — citation check, figure provenance check, data source check, reproducibility check, risk warnings, limitations.
- **Skills** — installed skills, recommended scientific skills, install from GitHub, enable / disable, view `SKILL.md`, check license, check dependencies.
- **Settings** — model provider, API keys, workspace path, AI assistant status, collapsed advanced runtime diagnostics, security approvals, update settings, appearance theme, data cleanup.

## 7. Key interactions

### 7.1 Plan card

Must be clean and clear. Contains: goal, step list, tools to call, expected artifacts,
risk notes, run buttons. Buttons: Approve & Run · Edit Plan · Run Step-by-step ·
Save as Workflow.

### 7.2 Tool-call card

Shows: tool name, status, input summary, output summary, duration, token / cost
(optional), view details, copy log. Status: Pending · Running · Waiting Approval ·
Success · Warning · Failed.

### 7.3 Approval dialog

For dangerous actions — delete file, overwrite file, install package, run shell,
network access, connect remote server, upload file — a dialog must confirm. Options:
Allow Once · Always Allow for This Project · Deny · View Details.

### 7.4 Command palette

Shortcut: `Cmd + K` (macOS) / `Ctrl + K` (Windows). Quick actions: new task, new project, search
literature, run reviewer, open settings, switch model, install skill, export report.

## 8. MVP example workflow

v1 must ship one bounded, synthetic HEOR example:

```text
Two-strategy, three-state cohort cost-effectiveness analysis
```

The bundled `examples/heor-cost-effectiveness/` inputs are teaching assumptions,
not clinical or economic evidence. The implemented default HEOR entry exposes
this example directly. Selecting it explicitly installs a local copy and fills an
unsent natural-language request; it never starts an Agent turn. The dependency-free,
versioned `run_analysis.py` verifies exact script, analysis-specification, and CSV hashes,
reproduces `expected/base-case-result.json` byte for byte, writes cycle traces,
and accepts only the declared intervention stable-state cost as its bounded
one-way sensitivity input. The conversational workflow must explain the decision
problem and ask the researcher whether to retain the teaching settings before
running that fixed code. As an auxiliary path, the desktop app may run only the
exact bundled case after a separate Human confirmation. That path must verify the
installed runner, specification, CSV, and expected-result bytes; write the base
case plus both declared sensitivity results; retain local run and provenance
records; require no configured model; and send no case content to a model provider.
Changed governed files fail closed and remain untouched. Neither path may substitute
model arithmetic or create
scientific approval, cost-effectiveness, reimbursement, or policy conclusions.

## 9. Roadmap

- **v0.1 Desktop MVP** — macOS / Windows installers, local workspace, bundled OpenCode runtime,
  model config, natural-language HEOR assistance, Human review, literature search,
  deterministic HEOR analysis, artifact panel, `provenance.jsonl`, and the synthetic
  cost-effectiveness example.
- **v0.2 Research Workflows** — K-Dense skills installer, PDF parsing, citation checker,
  Markdown report export, workflow template library, fuller review panel.
- **v0.3 Notebook Runtime** — Jupyter Kernel Gateway, persistent Python kernel, notebook
  preview, R support, Quarto / PDF / DOCX export.
- **v0.4 Advanced HEOR** — individually admitted HEOR source adapters, survival
  and evidence-synthesis execution, advanced uncertainty/VOI, dynamic BIA,
  reproducibility packages, and optional isolated R/Stata/HPC runners. No broad
  biomedical server becomes method or approval authority.

## 10. Non-functional requirements

### 10.1 Performance

Cold start < 3s (excluding first-time runtime init); no noticeable UI jank; streaming
agent output; live tool-call refresh; paginated large-file preview; lazy-loaded
figures; virtualized log lists.

### 10.2 Security

API keys encrypted locally; workspace sandbox isolation; dangerous-command approval;
no file upload by default; no full-disk access for the agent by default; access limited
to the current project directory; all network access auditable.

### 10.3 Maintainability

Frontend, desktop shell, and agent runtime decoupled; pluggable skills; configurable
MCP servers; extensible model providers; stable artifact schema; versioned workflow
templates.

### 10.4 Open-source friendliness

Clear first-screen README; one-click install; one-click demo; nice screenshots;
complete example results; clear license; separate note for third-party skill licenses.

## 11. One-liner

**AI4HEOR is an open-source pharmacoeconomics and HEOR research workbench with macOS and
Windows installers that uses OpenCode, MCP, scientific skills, and a reproducible
artifact system to weave literature, code, figures, reports, and review into one
local-first scientific workflow.**

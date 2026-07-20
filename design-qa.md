# AI4HEOR design QA

## New task surface · 2026-07-20

- Reference: `/var/folders/s1/c77rbrwj7_q6ppzdb394z2rw0000gn/T/codex-clipboard-a481fc1d-ff9a-4ccf-bf68-03f2d5638ca9.png` (1905×981).
- Implementation: `artifacts/design-qa/ai4heor-0.1.56-new-task-final.png` (1907×981, SHA-256 `0a9149ce55e6443af4e0673f9720a82676d59b0a525c634e2b2ccf5d6b67bef6`).
- Same-frame comparison: `artifacts/design-qa/new-task-reference-comparison.png` (SHA-256 `6e31c280d5b61f303eaa2c2efd27bb00557e18a26d26beb7c1d6bc7d03a6b635`).
- Interaction evidence: `artifacts/design-qa/ai4heor-0.1.56-new-task-prefill.png` (SHA-256 `5d1b2e70a6a583232228cd062ca4db249bb740ece25368782bdfa4865c75f416`).

### Comparison history

1. The first implementation placed the suggestion group near the top of the content area. At the reference viewport this was materially higher than the Codex task entry.
2. The empty-task section was changed to use the available task height. The final heading and four-card group now occupy the same central band as the reference, while the composer remains fixed near the bottom.
3. The large missing-model warning was removed from the blank task. Model state remains visible in the sidebar and in the composer placeholder; the user can still type freely, but Send remains disabled until a model is selected.
4. The reference's generic coding suggestions were replaced with four HEOR actions. Existing AI4HEOR typography, color tokens, Lucide icons, supplied logo, and sidebar were retained rather than cloning Codex branding.

### Functional checks

- `新建任务` resolves to `/heor/new` and renders one free-form textbox.
- All four suggestion cards are visible at the reference viewport.
- Clicking `查找与整理证据` fills the textbox with an editable Chinese HEOR request.
- The click does not create a task, change the route, or send a model request.
- A blank standalone task does not expose `研究与分析`; an established task does.

**Final result: passed.** No broken layout, clipping, unintended send, duplicate primary entry, or missing core control was observed at 1907×981.

# Open Science 0.2.1 selective sync

AI4HEOR was compared with `ai4s-research/open-science` tag `v0.2.1` (`2d3a0efa03384a76c2dd93b68df7d96a04db3a74`) on 2026-07-20. The merge base is `42c8101ab969011c2205fa1eacb96572ef309c18`.

## Integrated and adapted

| Upstream change | AI4HEOR use | Verification |
| --- | --- | --- |
| `c834935` long clarifying-question scrolling | Keeps multi-question Human review usable without clipping the submit action. | Interaction prompt tests |
| `ba6d2c3` LaTeX rendering | Renders ICER, QALY and other formulas in chat and Markdown previews; a lone currency `$` remains literal. | Markdown viewer tests |
| `28116ed` pasted images and native file drops | Adds screenshots and dropped files to the local task workspace after its scope is materialized. No upload or model request is triggered by attachment. | Composer attachment tests and Rust base64 tests |
| `c4acfb6` transparent launch-wrapper detection | Records local HEOR analyses run through `nohup`, `time`, `timeout`, or `stdbuf`, while retaining the exact original command. | Run-capture tests |

The upstream draft-file orphan repair (`b17e13f`) was not copied because AI4HEOR already enforces the same boundary through `beforeWorkspaceWrite` and `ensureStandaloneWorkspace` for attachments and teaching examples.

## Deliberately not imported

- Generic Open Science home screens and examples: they would reintroduce the product-direction error already removed from AI4HEOR.
- Goal/plan/multi-agent interface additions: useful platform work, but not required for the current HEOR testing path and not admitted as user-facing AI4HEOR capabilities in this release.
- Agent-browser sidecar: omitted from the test build until its execution, network, packaging, and licence record is admitted through AI4HEOR's asset policy.
- Theme expansion and unrelated visual changes: deferred to avoid changing the verified AI4HEOR design system during the release gate.
- Upstream project import changes: AI4HEOR already has a HEOR-specific project/task model and will assess the copy-safety fixes separately rather than replacing that model.

## Licence boundary

Open Science `v0.2.1` is MIT-licensed. The new runtime packages `katex 0.17.0`, `remark-math 6.0.0`, and `rehype-katex 7.0.1` also declare MIT licences. They must appear in the regenerated package inventory before release evidence is accepted. This note records provenance; it does not replace the repository-wide admission and legal checks.

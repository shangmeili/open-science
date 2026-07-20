---
name: research-presentation
description: Prepare and validate a source-bound scientific presentation manifest for deterministic AI4HEOR PPTX generation. Use when a researcher asks for slides, a deck, a briefing, a progress review, a methods presentation, a defence, or a PowerPoint/PPTX deliverable from local research materials. Preserve exact sources, limitations, and Human review; never invent results, silently change verified numbers, or claim that a generated deck is approved for external use.
---

# Research Presentation

Create `deliverables/research-presentation.json`; the desktop app renders its
validated content to `deliverables/research-presentation.pptx` without another
model call. Read `references/presentation-contract.md` before editing the
manifest.

## Workflow

1. Confirm the audience, purpose, language, time available, and desired length
   in the conversation. If the researcher has not specified them, propose a
   compact default and state it.
2. Copy `assets/research-presentation.template.json` when the manifest is
   absent. Do not edit a current deck silently; explain the proposed revision.
3. Bind every local source by safe workspace-relative path and lowercase
   SHA-256. Use app-owned result and report artifacts when they exist. Do not
   copy a number from memory or recompute a released result in prose.
4. Build one claim-led slide at a time. Keep the title slide first, a limitations
   slide before the end, and the closing slide last. Every evidence-bearing
   content, table, figure, or limitations slide must cite one or more declared
   source IDs.
5. Use `figure` slides only for local PNG or JPEG files with an exact hash and
   meaningful alt text. Use `$publication-figures` before creating a new chart.
6. Keep `human_review.status` equal to `awaiting_human_review`. Never add an
   approval, reviewer identity, policy recommendation, reimbursement decision,
   or claim that visual polish establishes scientific validity.
7. Run the validator from this Skill's exact runtime-reported base directory:

   ```bash
   python3 scripts/validate_research_presentation.py \
     "$WORKSPACE/deliverables/research-presentation.json" "$WORKSPACE"
   ```

8. Report the manifest path, slide and source counts, remaining validation
   errors, and the next action: open AI4HEOR's research-presentation card and
   generate the PPTX. The researcher must review the rendered deck before use.

## Boundaries

- The manifest controls content, not arbitrary OOXML, macros, scripts, fonts,
  links, or network resources.
- The app verifies structure, source bytes, image bytes, rendering limits, and
  output provenance. It does not verify that a source is true, licensed for
  external distribution, scientifically sufficient, or interpreted correctly.
- Keep negative, dominated, uncertain, inconclusive, and unaffordable results
  visible when they are decision-relevant. Never turn HEOR findings into a
  treatment, coverage, pricing, or reimbursement recommendation.

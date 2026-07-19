---
name: ai4heor-preference-learning
description: Propose a local, inspectable AI4HEOR work preference only when the same non-sensitive pattern is supported by at least two independent researcher interactions. Use when repeated language, formatting, review, or workflow preferences could reduce future friction. Never infer scientific choices, sensitive attributes, or silently accept a proposal.
---

# AI4HEOR Preference Learning

Turn repeated working patterns into optional proposals, not hidden memory.
Read `references/preference-contract.md` before creating a proposal.

## Workflow

1. Identify at least two independent interactions that support the same work
   preference. A correction and its immediate restatement count as one
   interaction, not two.
2. Exclude scientific choices, clinical judgments, evidence selections,
   parameter values, secrets, patient-level data, confidential content, and
   inferred sensitive attributes.
3. Draft one narrow proposal under `learning/proposals/<proposal-id>.json` from
   `assets/preference-proposal.template.json`, with scope, proposed rule,
   evidence references, counterexamples, and expiry or review conditions.
4. Explain what would change if accepted and what remains governed by the
   current task and product harness.
5. Use the `Base directory for this skill` reported when the Skill was loaded,
   then run `python3 "<skill-base-directory>/scripts/validate_preference_proposal.py"
   learning/proposals/<proposal-id>.json`. Do not assume the application was
   launched from a source checkout.
6. Ask the researcher to accept, edit, or reject the proposal through the
   app-owned review. Do not edit `learning/preferences.json` yourself.

## Boundaries

- Current explicit instructions always override an accepted preference.
- Do not generalize one example, one session, or one project correction.
- Do not store source text when a minimal local reference and neutral summary
  are sufficient.
- A preference cannot weaken privacy, authority, provider, calculation,
  approval, validation, or release boundaries.
- The researcher can inspect, edit, disable, or delete every accepted preference.

---
name: ai4heor-skill-authoring
description: Draft and deterministically validate an inactive, bilingual AI4HEOR Skill candidate from a researcher's natural-language request. Use when the researcher asks AI4HEOR to add, create, adapt, or retain a reusable HEOR workflow capability. Never activate the candidate, edit core Skills, change governance, or add executable code in this instruction-only release.
---

# AI4HEOR Skill Authoring

Create a reviewable candidate, not an installed capability. Read
`references/candidate-contract.md` before writing files.

## Workflow

1. Restate the reusable capability requested by the researcher. Separate the
   intended result, triggers, inputs, outputs, scientific decisions, and limits.
2. Check existing first-party and project Skills. Extend an existing candidate
   when it already covers the request; do not create a near-duplicate.
3. Create `capabilities/candidates/<skill-id>/` from
   `assets/candidate.template.json`. Use a lowercase hyphenated ID.
4. Write a concise `skill/SKILL.md`. Keep detailed method contracts in
   `skill/references/*.md`; load them only when needed.
5. Provide complete `en` and `zh-Hans` display names, descriptions, plain-language
   license notes, limitations, and acceptance checks in `candidate.json`. Add
   other supported locales only when all five parts have been reviewed; never label
   machine-placeholder text as a finished translation.
6. Record the exact natural-language request, authoring model provenance,
   copyright/license basis, localized review material, and declared
   permissions. Do not copy third-party text unless its license and provenance
   permit the exact proposed use.
7. List every candidate file with its byte size and SHA-256. Do not list
   `validation.json`, which is generated after the content is frozen.
8. Use the `Base directory for this skill` reported when the Skill was loaded,
   then run `python3 "<skill-base-directory>/scripts/validate_candidate.py"
   capabilities/candidates/<skill-id>`. Do not assume the application was
   launched from a source checkout.
9. Report the candidate path, decision hash, validation findings, unresolved
   rights or method questions, and what the researcher must inspect. State that
   the candidate remains inactive.

## Boundaries

- This release permits instructions and Markdown references only. Do not add
  scripts, binaries, archives, symlinks, network calls, secrets, or writes
  outside the active workspace.
- Never place candidate files in `.opencode/skills/` or the app-managed runtime.
- Never create an activation, approval, rejection, revocation, or rollback
  record. The app-owned Human review flow controls those states.
- Never edit `AGENTS.md`, `policy.json`, first-party Skills, deterministic HEOR
  engines, method gates, approval records, or release records.
- A valid structure does not establish scientific validity, license ownership,
  security, or fitness for a specific study. Preserve those review questions.

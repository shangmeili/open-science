---
name: heor-methods-watchlist
description: Maintain and audit a dated, local HEOR methods-source watchlist without redistributing restricted content. Use when a researcher asks whether HTA methods, reference cases, reporting standards, regulations, or technical guidance are current; when a source revision may require an AI4HEOR artifact or Skill to be revalidated; or when recording a licensed local snapshot and its provenance.
---

# HEOR Methods Watchlist

Keep method currency visible to the Human researcher. This Skill records dated checks and impact work; it does not decide whether a method is valid, approve an analysis, or fetch restricted source content.

## Workflow

1. Clarify the jurisdiction, decision context, method topics, and the researcher's currency date.
2. Start from `assets/methods-watchlist.template.json` and save the working artifact as `heor/methods-watchlist.json`.
3. Prefer the official canonical landing page. Record the organization, revision label, publication status, date last checked, and next check date.
4. Use `access_mode: link_only` unless the researcher has a lawful local copy. Never copy web content merely because it is publicly viewable.
5. For a local copy, record `rights_status`, a concise rights note, a path under `heor/method-sources/`, media type, and the exact SHA-256 digest.
6. When a revision is suspected or confirmed, record the changed sections, affected AI4HEOR contracts, required Human actions, and revalidation status. Do not silently rewrite downstream artifacts.
7. Run the validator and present overdue checks, unresolved changes, and limitations in plain language.
8. Ask the researcher to disposition changes and authorize any downstream revalidation. Forms may expose the same fields as an auxiliary view, but natural-language review remains primary.

## Validation

Run:

```bash
python3 runtime/skills/core/heor-methods-watchlist/scripts/validate_methods_watchlist.py \
  heor/methods-watchlist.json --workspace .
```

A valid `draft` may still be incomplete. `ready_for_human_review` is complete only when the artifact is structurally valid, every check is current as of `as_of_date`, and every recorded change has a resolved Human disposition and revalidation status.

Read `references/methods-watchlist-contract.md` before changing the schema or interpreting completion. Treat `as_of_date` as a reproducible snapshot boundary, not a claim that the file remains current today.

## Guardrails

- The Human researcher owns source selection, relevance judgments, change disposition, and revalidation decisions.
- Do not infer reuse rights. `permission_confirmed`, `open_licence`, and `personal_research` require a Human-supplied basis in `rights_note`.
- Do not use this artifact as regulatory, reimbursement, legal, or methodological approval.
- Do not auto-fetch, scrape, summarize, embed, or redistribute restricted content.
- Preserve prior revision evidence; add a change record instead of overwriting history without explanation.
- Keep calculations and validation deterministic and model-independent.

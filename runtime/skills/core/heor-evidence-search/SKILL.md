---
name: heor-evidence-search
description: Draft and reconcile app-authorized PubMed and ClinicalTrials.gov metadata searches for HEOR evidence work. Use when a pharmacoeconomic project needs a reproducible bibliographic or trial-registry search, an exact heor/evidence-search-request.json for Human-in-the-loop network authorization, or import of an app-written evidence-search run into heor/evidence-synthesis.json.
---

# HEOR Evidence Search

Draft a bounded search request; never make the network call yourself. Read `references/evidence-search-contract.md` before creating or changing a request.

## Workflow

1. Read the current decision problem, evidence synthesis, and unresolved evidence gaps.
2. Define the search purpose and an exact query. Preserve source-specific syntax only when it is valid for every selected source; otherwise create separate requests.
3. Copy `assets/evidence-search-request.template.json` to `heor/evidence-search-request.json` and complete every field.
4. Select only `pubmed`, `clinicaltrials`, or both. Do not add URLs, headers, credentials, API keys, local paths, or arbitrary providers.
5. Declare the exact egress fields and confirm in the artifact that the query contains no patient-level, personal, confidential, or otherwise sensitive data.
6. Run `scripts/validate_evidence_search_request.py`; set `status` to `ready_for_human_review` only after the query, dates, sources, purpose, and limitations are complete and the validator passes.
7. Ask the researcher to open the AI4HEOR review pane. The researcher—not the Agent—reviews the exact SHA-256, sources, and egress declaration and authorizes execution.
8. After the app writes a file under `heor/evidence-search-runs/`, use the review pane's deterministic import when available. It verifies the app-owned authorization chain, run path, and SHA-256, then adds only `not_assessed` candidates. Do not manually copy or rewrite an authorized run when this import path is available.
9. After import, use `$heor-evidence-synthesis` through natural-language work to screen and extract. Preserve every app-bound search field and existing research judgment; never treat retrieval as inclusion, appraisal, extraction, or verification.

## Boundaries

- Do not use shell, browser, web search, MCP, or another connector to bypass the app-owned authorization step.
- Do not put sensitive data, credentials, proprietary database syntax, or patient identifiers in a public-source query.
- Treat PubMed results as bibliographic metadata and ClinicalTrials.gov results as registry records. Neither proves full-text availability, peer review, methodological quality, results validity, or review completeness.
- Do not silently broaden queries, substitute sources, paginate beyond the approved cap, or rerun a changed request under an old authorization.
- Do not perform economic calculations, evidence grading, automated inclusion, human approval, or reimbursement interpretation.
- Preserve zero-result searches and source failures as evidence. Do not invent records, counts, authorization bindings, or run hashes.

## Handoff

Report the request path and hash, selected sources, date range, result cap, disclosed egress fields, and material limitations. After execution, report the app-written run path, source counts, candidate records, and the remaining screening/full-text/appraisal work.

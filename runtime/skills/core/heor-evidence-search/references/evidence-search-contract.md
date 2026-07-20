# Evidence-search contract

## Request artifact

The Agent may write `heor/evidence-search-request.json`. The application independently audits its exact bytes and accepts only:

- `schema_version`: `0.1.0`.
- `request_id`: 1–80 ASCII letters, digits, hyphens, or underscores.
- `status`: `ready_for_human_review` before authorization.
- `purpose`: why the metadata search is needed.
- `query`: 1–500 characters without control characters.
- `sources`: a unique non-empty subset of `pubmed` and `clinicaltrials`.
- `max_results_per_source`: integer from 1 to 50.
- `date_from`, `date_to`: optional valid `YYYY-MM-DD` calendar dates in ascending order.
- `data_egress.contains_sensitive_data`: `false`.
- `data_egress.fields`: exactly `query`, `date_from`, and `date_to`.
- `data_egress.justification`: why sending those fields to the selected public sources is necessary.
- `limitations`: at least one material limitation.

Unknown fields fail closed. Dynamic URLs, headers, credentials, local paths, provider-specific secrets, output paths, and tool names are not part of the schema.

## Human authorization

The review pane shows the exact request SHA-256, query, sources, date range, result cap, and sensitivity declaration. Execution requires a human reviewer label, rationale, and explicit confirmation that the query contains no sensitive data. The app re-reads and re-hashes the request immediately before execution; changed bytes invalidate authorization.

Authorization events live outside the Agent workspace in an app-owned append-only SHA-256 chain. This detects partial or inconsistent edits but is not OS-backed identity proof.

## Fixed network behavior

The native connector uses HTTPS, fixed hosts, no redirects, 10-second connect and 25-second total timeouts, a 5 MiB response cap, JSON content-type checks, and no telemetry.

- PubMed: NCBI ESearch followed by ESummary. The date range is sent as publication-date bounds. The result contains metadata and identifiers, not full text or outcome extraction.
- ClinicalTrials.gov: API v2 `/studies` with a fixed field list. The API returns one bounded page; an optional date range is applied locally to the first-posted date. Registry presence is not peer review or results validation.

The app writes a new, never-overwritten JSON artifact under `heor/evidence-search-runs/`. It records exact request URLs, response hashes, source counts, normalized records, limitations, the bound request hash, and the app-owned authorization event identifier.

## Upstream adaptation provenance

The source-selection and bounded-search design was informed by HEORAgent MCP revision `19f5f0eea5764d7a2695c372f3ec8f3aa0f53dd8` (MIT, Copyright 2026 mnaumov). AI4HEOR does not bundle or execute the upstream Node package: its 48-tool authority surface, direct multi-source network access, global default knowledge root, optional PostHog integration, and unresolved dependency vulnerabilities exceed this connector's boundary.

The AI4HEOR implementation is a first-party rewrite around fixed public APIs, app-owned authorization, local artifacts, and no calculation or approval authority. The upstream MIT notice is preserved in `references/heoragent-mit-license.txt`.

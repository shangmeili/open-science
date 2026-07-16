# Methods watchlist contract

Schema version: `0.1.0`

Canonical artifact: `heor/methods-watchlist.json`

## Authority boundary

The artifact is a dated research-control record. It answers: what official method source was checked, which revision was observed, when it must be checked again, and what downstream contracts may need Human-led revalidation. It never grants approval or establishes legal permission.

`complete` is computed by the validator and is not stored in the artifact. Completion means only that the dated watchlist snapshot is structurally valid, contains at least one source, has no checks overdue relative to `as_of_date`, and has no unresolved change records.

## Source rules

- `source_order` must contain every `sources` key exactly once.
- `canonical_url` must be HTTPS and should resolve to an official landing page.
- `link_only` requires `rights_status: link_only` and `snapshot: null`.
- `local_snapshot` requires a non-link-only rights status and a regular, non-symlink file under `heor/method-sources/` with an exact lowercase SHA-256 digest.
- A `last_checked_on` date cannot follow `as_of_date`. A `next_check_due` before `as_of_date` is overdue.
- `publication_status: unknown` is visible as uncertainty but is not a schema error.

## Change rules

- `change_order` must contain every `changes` key exactly once.
- Every change references one declared source and cannot be detected after `as_of_date`.
- `suspected` and `confirmed` changes remain unresolved until the Human disposition is non-pending and revalidation is `complete` or `not_required`.
- A `dismissed` change requires `human_disposition: rejected` and `revalidation_status: not_required`.
- Change evidence paths, when used, stay under `heor/method-sources/` and must identify regular, non-symlink local files.

## Compatibility

Consumers must reject unknown fields. A schema change requires a version change, updated portable and native validators, new contract tests, and Human review of affected platform assets.

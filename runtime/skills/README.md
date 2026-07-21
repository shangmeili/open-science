# runtime/skills

Scientific skills, layered:

```text
skills/
  core/      # self-authored skills specific to this app (traceability-review;
             # other dirs are roadmap placeholders until they get a SKILL.md)
  user/      # user-installed / custom skills (live in the runtime workspace)
```

Core skills are bundled as the `skills-core/` app resource. Third-party source
trees are not bundled merely because they were fetched. On every sidecar start,
`runtime.rs::deploy_bundled_skills` loads the packaged
`asset-admission-registry.json`, verifies its contract, and deploys only an exact
tree hash whose status is `validated-adapter`. Invalid or missing registry data
fails closed and stale external skills are removed from the app-managed profile.

The registry is release-only: unfinished rewrites and excluded sources are not
stored in it or shown as user choices. Useful external ideas are re-specified
against AI4HEOR's Human authority, artifact, localization, and test contracts,
then implemented under `core/` as first-party work. External code is admitted
only as a completed, hash-locked adapter with all release evidence present.

## Excluded document sources

The previously reviewed external `docx`, `pdf`, `pptx`, and `xlsx` Skill sources
at revision `9d2f1ae187231d8199c64b5b762e1bdf2244733d` are not retained, fetched, or
bundled. Their per-directory `LICENSE.txt` files are service-linked
source-available terms, not Apache-2.0, and prohibit copying, derivatives, and
redistribution. AI4HEOR uses its first-party
`research-presentation` implementation for PPTX and builds any DOCX, PDF, or
XLSX generation independently from product requirements.

## Project-created skills

The Skills page may draft a narrow, instruction-only project Skill from a
researcher's natural-language request. It remains inactive until the app-owned
Human review validates the exact bytes and records the decision. Project-created
content never becomes a bundled first-party or external release asset implicitly.

Each skill directory must contain a `SKILL.md`.

`core/heor-evidence-search` is the first-party public-metadata search boundary.
The Agent drafts a validated request, while only the desktop app can execute
the exact human-authorized bytes against fixed PubMed and ClinicalTrials.gov
endpoints. Its outputs are candidate metadata and never bypass screening,
appraisal, or evidence-synthesis review.

`core/heor-local-evidence` is the first-party local knowledge-base retrieval
boundary. The desktop owns source import, page extraction, SHA-256 manifesting,
and index rebuilds; the Skill verifies those bindings and returns compact
path/page/hash citations without network access. OCR-required and failed files
are excluded rather than treated as reviewed evidence.

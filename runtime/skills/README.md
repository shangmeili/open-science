# runtime/skills

Scientific skills, layered:

```text
skills/
  core/      # self-authored skills specific to this app (traceability-review;
             # other dirs are roadmap placeholders until they get a SKILL.md)
  external/  # third-party review cache, fetched by script — git-ignored/inactive
  user/      # user-installed / custom skills (live in the runtime workspace)
```

Core skills are bundled as the `skills-core/` app resource. Third-party source
trees are not bundled merely because they were fetched. On every sidecar start,
`runtime.rs::deploy_bundled_skills` loads the packaged
`asset-admission-registry.json`, verifies its contract, and deploys only an exact
tree hash whose status is `validated-adapter`. Invalid or missing registry data
fails closed and stale external skills are removed from the app-managed profile.

## Candidate pack: ai4s-skills (not bundled)

The default scientific skills come from
[ai4s-research/ai4s-skills](https://github.com/ai4s-research/ai4s-skills)
(research-explorer, literature-survey, experiment-suite, paper-writer,
integrity-auditor, mindmap-render, ai4s-agent).

How they are evaluated:

1. `scripts/dev/fetch-skills.sh` downloads a pinned revision into the ignored
   `external/ai4s-skills/` review cache.
2. Each Skill has its own quarantined entry in
   `runtime/assets/asset-admission-registry.json` with license, boundary,
   adaptation, test, review, platform, and blocker fields.
3. A code-reviewed update may add a first-party derivative or an isolated
   `skills-admitted-*` resource only after all release evidence is complete and
   its deterministic tree hash is locked.

Fetching or bumping the review cache never changes the released capability set.

## Rejected source-available document skills

The `docx`, `pdf`, `pptx`, and `xlsx` directories in
[anthropics/skills](https://github.com/anthropics/skills) are source-available,
not Apache-2.0. Their per-skill license prohibits retaining, copying, deriving,
and distributing the materials. AI4HEOR therefore neither fetches nor bundles
them. Their registry records are `rejected`; only independently written,
compatibly licensed document capabilities may replace the product need.

## Third-party skills

Do **not** enable third-party collections by default. Discovery and a passing
upstream test are evidence, not admission. The Skills page starts a
natural-language industrialization review and keeps the candidate inactive;
only the native registry controls the bundled production inventory.

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

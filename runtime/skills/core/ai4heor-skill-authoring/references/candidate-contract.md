# Candidate contract

The candidate directory must contain `candidate.json`, `skill/SKILL.md`,
optional Markdown files under `skill/references/`, and the generated
`validation.json`. No other file type is admitted in the instruction-only
release.

`candidate.json` uses schema `ai4heor-skill-candidate/v2` and status
`candidate`. The directory name, manifest `id`, and SKILL.md frontmatter `name`
must match. The manifest includes:

- the exact natural-language request;
- localized display names, descriptions, plain-language license notes,
  limitations, and concrete Human acceptance checks, including complete `en`
  and `zh-Hans` entries;
- authoring provider, model, and local session reference;
- source kind, copyright holder, rights basis, SPDX identifier or explicit
  LicenseRef, and a plain-language license note;
- a deny-by-default permission declaration;
- exact file paths, byte sizes, and SHA-256 values.

The deterministic validator rejects traversal, symlinks, hidden content,
unexpected files, oversized files, hash drift, incomplete bilingual review material,
active permissions, executable content, and common secret patterns. The output
contains a decision hash over the exact candidate manifest and Skill files.

Passing validation means only that the candidate meets this packaging contract.
It remains inactive until the app-owned Human review flow records a decision for
the exact decision hash.

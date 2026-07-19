# Candidate contract

The candidate directory must contain `candidate.json`, `skill/SKILL.md`,
optional Markdown files under `skill/references/`, and the generated
`validation.json`. No other file type is admitted in the instruction-only
release.

`candidate.json` uses schema `ai4heor-skill-candidate/v1` and status
`candidate`. The directory name, manifest `id`, and SKILL.md frontmatter `name`
must match. The manifest includes:

- the exact natural-language request;
- localized display names and descriptions, including `en` and `zh-Hans`;
- authoring provider, model, and local session reference;
- source kind, copyright holder, rights basis, SPDX identifier or explicit
  LicenseRef, and a plain-language license note;
- a deny-by-default permission declaration;
- exact file paths, byte sizes, and SHA-256 values;
- limitations and concrete Human acceptance checks.

The deterministic validator rejects traversal, symlinks, hidden content,
unexpected files, oversized files, hash drift, missing bilingual metadata,
active permissions, executable content, and common secret patterns. The output
contains a decision hash over the exact candidate manifest and Skill files.

Passing validation means only that the candidate meets this packaging contract.
It remains inactive until the app-owned Human review flow records a decision for
the exact decision hash.

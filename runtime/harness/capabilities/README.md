# Local capability candidates

AI4HEOR can turn a researcher's natural-language request into a reviewable
Skill candidate. Candidates stay under `candidates/<skill-id>/` and are never
loaded by the runtime from this location.

Each candidate contains:

- `candidate.json`: request, localized descriptions, provenance, license basis,
  permissions, file hashes, limitations, and acceptance checks;
- `skill/SKILL.md`: the proposed Skill instructions;
- optional Markdown references under `skill/references/`;
- `validation.json`: deterministic validation output for the exact files.

The first release accepts instruction-only candidates. Executable scripts,
binaries, symlinks, network access, secrets, and writes outside the active
workspace require a later adapter and security review. A researcher reviews the
exact validated bytes before an app-owned activation, rejection, revocation, or
rollback record is created.

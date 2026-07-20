# Local capability candidates

AI4HEOR can turn a researcher's natural-language request into a reviewable
Skill candidate. Candidates stay under `candidates/<skill-id>/` and are never
loaded by the runtime from this location.

Each candidate contains:

- `candidate.json`: request, localized names, descriptions, license notes,
  limitations and acceptance checks, provenance, license basis, permissions,
  and file hashes;
- `skill/SKILL.md`: the proposed Skill instructions;
- optional Markdown references under `skill/references/`;
- `validation.json`: deterministic validation output for the exact files.

The first release accepts instruction-only candidates. Executable scripts,
binaries, symlinks, network access, secrets, and writes outside the active
workspace require a later adapter and security review. A researcher reviews the
exact validated bytes before an app-owned activation, rejection, revocation, or
rollback record is created. The desktop app independently repeats the validation,
requires a reviewer label, rationale, and exact-hash confirmation, then records a
hash-linked event and project snapshot. Candidates must include complete English
and Simplified Chinese review material; older or incomplete candidates stay
inactive until regenerated. Activation copies only the reviewed
instruction files into this project's `.opencode/skills/<skill-id>/`. Revocation
removes that copy only if its bytes still match the activation record; changed or
same-name unmanaged content is never overwritten or deleted automatically.

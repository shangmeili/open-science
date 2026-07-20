# scripts

Repo tooling.

- `release/` — fail-closed native package verification and hash-bound release
  evidence. macOS verifies mounted DMGs; Windows verifies MSI payloads, silent
  NSIS installation, and first launch; Linux package verification lives in
  `dev/`. All four native targets must assemble into one source-bound manifest.
- `dev/` — local development helpers (bootstrap, run the app, seed the demo workspace).

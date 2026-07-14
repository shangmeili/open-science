---
name: heor-local-evidence
description: Search and cite the AI4HEOR project-local evidence library using its app-generated SHA-256 manifest and deterministic SQLite text index. Use for questions about local pharmacoeconomics or HEOR PDFs and text sources, local knowledge-base retrieval, source-grounded summaries, evidence gap checks, or claims that require exact local path, source hash, and page citations. Never use it to imply that failed, stale, unsupported, or OCR-required documents were reviewed.
---

# HEOR local evidence

1. Require `heor/evidence-library.json`. If it is missing or stale, ask the user to add or rescan sources in the AI4HEOR review pane; do not build an unofficial replacement index.
2. Run the deterministic search from the workspace root:

   ```bash
   python3 <skill-dir>/scripts/search_library.py --query "<research question>" --limit 10
   ```

3. Treat each result as extracted source text, not a validated research conclusion. Open the cited local source when closer context is needed and the format is readable.
4. Cite every factual claim as `path, page, SHA-256`. Preserve the page reported by the index. For single-page text sources, use page 1.
5. Separate three layers in the answer: extracted evidence, interpretation, and unresolved limitations or conflicts.
6. Report zero matches honestly. Refine the query only when the terms are too broad or too narrow; never invent semantic matches.
7. Do not use the network. Do not search outside the current workspace. Do not cite documents marked `requires_ocr`, `failed`, or `unsupported`.
8. If source bytes changed, stop and request an app-owned rescan. A stale hash is a hard provenance failure, not a warning to ignore.

For machine-readable output, add `--json`.

The packaged parser license notice is `references/pdf-extract-MIT.txt`.

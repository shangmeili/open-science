---
name: research-tables
description: Prepare and validate typed, source-bound research table manifests for deterministic AI4HEOR XLSX and CSV generation. Use when a researcher asks for analysis tables, evidence tables, parameter tables, appendices, tabular results, or spreadsheet deliverables from local HEOR materials. Preserve units, exact sources, assumptions, and Human review; never invent values, recalculate released results, or treat generated tables as approved.
---

# Research Tables

Create `deliverables/research-tables.json`; the desktop app validates it and
generates `deliverables/research-tables.xlsx` plus one CSV file per table without
another model call. Read `references/research-tables-contract.md` before editing
the manifest.

## Workflow

1. Confirm the tables' purpose, intended readers, language, required columns,
   units, and rows in the conversation. Use natural-language questions; do not
   require the researcher to fill a large form.
2. Copy `assets/research-tables.template.json` when the manifest is absent.
   Do not silently replace a current table plan.
3. Bind 1–32 local source files by safe workspace-relative path and exact
   lowercase SHA-256. Prefer current app-owned result and evidence artifacts.
4. Give every column an explicit type. Numeric columns must declare their unit;
   non-numeric columns must not. Keep currency price year and perspective in
   the label or unit when they matter.
5. Mark every row as `evidence`, `analysis_output`, or `assumption`.
   Evidence and analysis-output rows need exact source IDs and meaningful
   locators. Assumption rows need an explicit note and no source reference.
6. Copy released results; do not recompute them in the manifest or workbook.
   Preserve dominated, negative, uncertain, missing, and unfavourable results.
7. Keep `human_review.status` equal to `awaiting_human_review`.
8. Run the portable validator from this Skill's exact runtime-reported base
   directory:

   ```bash
   python3 scripts/validate_research_tables.py \
     "$WORKSPACE/deliverables/research-tables.json" "$WORKSPACE"
   ```

9. Report the manifest path, table, row and source counts, assumptions and
   remaining errors. The researcher then opens the AI4HEOR research-table card,
   generates XLSX/CSV, and reviews every table before use.

## Boundaries

- The manifest controls bounded cells and metadata, not formulas, macros,
  scripts, external links, arbitrary OOXML, or network resources.
- The native app rechecks structure, file hashes, types, units, paths and
  overwrite safety. Identical valid inputs produce identical workbook bytes.
- Formula-like text is neutralised in CSV exports. No formula is emitted to the
  XLSX workbook.
- Successful validation or generation does not approve evidence selection,
  methods, interpretation, submission, pricing, reimbursement, or release.

## 中文说明

本 Skill 用于把研究者已经确认的表格结构和本地材料整理成可校验的清单。
应用只负责按清单生成 XLSX 和 CSV，不在表格中重算模型。每一列要写清类型和
单位，每一行要区分证据、分析输出或假设；生成后仍由研究者逐表核对。

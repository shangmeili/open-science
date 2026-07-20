# Citation-formatting contract

## Input artifacts

The canonical bibliography source is the validated local
`references/library.json` artifact with schema
`ai4heor-reference-library/v1`. The plan is
`references/citation-plan.json`:

```json
{
  "schema_version": "ai4heor-citation-plan/v1",
  "document_id": "cea-manuscript",
  "title": "Cost-effectiveness manuscript references",
  "language": "zh-Hans",
  "style_id": "ai4heor-cn-medical-numeric-v1",
  "library": {
    "path": "references/library.json",
    "sha256": "64 lowercase hexadecimal characters"
  },
  "citations": [
    {
      "id": "methods-reference-case",
      "reference_ids": ["doi-10.0000-example"],
      "locator": { "label": "page", "value": "12-13" }
    }
  ],
  "bibliography": { "include_uncited": false },
  "human_review_status": "awaiting_human_review"
}
```

Supported languages are `zh-Hans` and `en`. A citation cluster contains 1 to
100 distinct existing reference IDs. A locator is allowed only for a
single-reference cluster; supported labels are `page`, `chapter`, `section`,
`figure`, `table`, and `supplement`.

## Built-in profiles

- `ai4heor-cn-medical-numeric-v1`: product-authored numbered output using common
  Chinese medical-research punctuation and publication-type labels.
- `ai4heor-vancouver-numeric-v1`: product-authored compact numbered biomedical
  output.
- `ai4heor-author-date-v1`: product-authored author-date output with
  deterministic same-author/year suffixes.

These profiles consume the supported CSL-JSON-compatible fields in the local
library. They do not interpret CSL XML, reproduce an official CSL style, or
certify conformance with GB/T 7714, AMA, Vancouver recommendations, or a
specific journal. The target journal's current author instructions remain the
submission authority.

## Output and audit

The app writes `deliverables/references.md` and
`deliverables/references.audit.json`. The output contains named in-text
citation clusters, the bibliography, metadata warnings, the library and plan
hashes, the selected profile, and `awaiting_human_review` status.

Generation fails if the bound library changed, an ID is unknown, the plan has
unsupported fields or values, a symbolic link resolves outside the project, or
an existing Human-edited output no longer matches its AI4HEOR audit record.
The formatter never mutates the reference library.

## Format and licensing basis

- CSL 1.0.2 specification:
  <https://docs.citationstyles.org/en/v1.0.2/specification.html>
- CSL schema and CSL-JSON schema, MIT:
  <https://github.com/citation-style-language/schema>
- Official CSL styles repository, CC BY-SA 3.0:
  <https://github.com/citation-style-language/styles>

AI4HEOR does not bundle files from the official styles repository in this
capability. If a future release distributes a third-party `.csl` file, it must
pass asset admission separately, preserve style metadata, provide required
attribution, and disclose ShareAlike obligations.

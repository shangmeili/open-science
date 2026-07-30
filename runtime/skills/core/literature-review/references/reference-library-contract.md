# Reference library contract

## Artifact

The canonical project artifact is `references/library.json` with schema
`ai4heor-reference-library/v1`. It contains normalized citation records plus
source bindings. Each binding records the project-relative import path, source
SHA-256, exchange format, and source record key. The artifact has no generated
timestamp so an identical import is byte-identical.

Record identity is recalculated in this order:

1. normalized DOI;
2. normalized PMID;
3. a SHA-256-derived key from normalized title, issued year, and first author.

Title-and-year matching is used only when DOI and PMID values do not conflict.
Different DOI or PMID values therefore remain separate records. When compatible
duplicates contain different non-identity metadata, the tool selects the same
deterministic canonical value regardless of import order and preserves every
alternative under `conflicts` for Human review.

## Supported exchange subset

- **RIS:** bounded tagged records starting with `TY` and ending with `ER`.
  Common type, author, title, container, date, volume, issue, page, DOI, PMID,
  URL, publisher, abstract, keyword, language, and identifier tags are mapped.
  Unknown well-formed tags are reported and not imported.
- **BibTeX:** ordinary `@article`, `@book`, `@inproceedings`/`@conference`,
  `@incollection`, `@techreport`, `@phdthesis`, `@mastersthesis`,
  `@unpublished`, and `@misc` entries with braced, quoted, or numeric values.
  `@string`, `@preamble`, macros, cross-file expansion, and `#` concatenation
  are deliberately rejected rather than interpreted incompletely.
- **CSL-JSON:** a JSON array whose records contain `id`, `type`, `title`, and a
  bounded set of standard CSL 1.0.2 name, date, identifier, publication, and
  descriptive fields. Unknown fields fail closed so the user can convert them
  deliberately instead of losing metadata silently.

Export produces the same bounded RIS and BibTeX subsets or standard CSL-JSON
item data. Internal `source_bindings` and `conflicts` are never placed in the
CSL-JSON export.

## Safety and authority

- Input and output must be ordinary files inside the selected project. Symlink
  paths and files larger than 10 MiB are rejected. A single import is capped at
  10,000 records.
- Existing different export bytes are preserved. Library updates use an atomic
  same-directory replacement after parsing and validation succeeds.
- `reference_library.py` does not call a network service, resolve a DOI, fetch
  full text, apply a citation style, screen a record, or approve scientific
  use. `open_full_text.py` is a separate, explicit network step.
- The open-full-text queue uses schema `ai4heor-full-text-queue/v1` and binds
  the exact current `references/library.json` SHA-256. It tries Europe PMC open
  article XML, then (for DOI records) Unpaywall's reported best open PDF. It
  records source, licence/version when provided, retrieval time, local path,
  and downloaded SHA-256. It does not persist the Unpaywall email.
- A direct public PDF that is actually used to support a claim is stored under
  `references/source-files/` and registered in
  `references/source-files.json` with schema
  `ai4heor-source-file-archive/v1`. Its identity binds the original source URL
  to the downloaded content SHA-256, so changed bytes at the same URL create a
  new immutable record. The manifest records original and final URL, title,
  publisher and licence when known, rights basis, retrieval time, local path,
  reported and verified media type, and SHA-256.
- Downloads are capped at 50 MiB, must resolve only to public HTTP(S) hosts,
  validate redirects, refuse symbolic links and workspace escape, verify XML
  or PDF signatures, and never overwrite different existing bytes.
- `queued`, `running`, `needs_input`, `downloaded`, `unavailable`, and `failed`
  are execution states. None is a screening decision, evidence appraisal,
  scientific confirmation, or Human approval.
- The researcher remains responsible for metadata correction, duplicate review,
  inclusion decisions, citation style selection, and external release.

## Format references

- CSL 1.0.2 specification and input-data schema:
  <https://docs.citationstyles.org/en/v1.0.2/specification.html> and
  <https://github.com/citation-style-language/schema/tree/v1.0.2/schemas/input>
- Clarivate Web of Science RIS import requirements:
  <https://webofscience.help.clarivate.com/en-us/Content/wos-researcher-profile-adding-removing-publications.html>
- BibTeX user documentation distributed by CTAN:
  <https://ctan.org/tex-archive/biblio/bibtex/contrib/doc>
- Europe PMC REST web service and open-access downloads:
  <https://europepmc.org/RestfulWebService> and <https://europepmc.org/downloads>
- Unpaywall API and response data format:
  <https://unpaywall.org/api> and <https://unpaywall.org/data-format>

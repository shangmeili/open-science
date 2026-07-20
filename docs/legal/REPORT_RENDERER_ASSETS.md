# AI4HEOR research-report renderer asset record

Audit date: 2026-07-20
Scope: first-party DOCX/PDF report export for the Intel macOS internal build

## Source Han Sans CN

- Upstream: `adobe-fonts/source-han-sans`
- Release: `2.005R`
- Release asset: `19_SourceHanSansCN.zip`
- Release asset SHA-256: `3a769d1b082ebd813cdb4c06ea57d29b340bce548edcc8e61976b78ca28e6236`
- Included file: `SourceHanSansCN-Regular.otf`
- Included file SHA-256: `e2bc8a2e7f37474b774fff8db758681ece40bb6947a90d571bce9dd60671a8e4`
- License: SIL Open Font License 1.1
- Included license SHA-256: `fcac737e761ec63dbfbdce11030a1780161920d80315edba9c8beff1c2bac5a2`
- Upstream release: <https://github.com/adobe-fonts/source-han-sans/releases/tag/2.005R>
- Upstream license: <https://github.com/adobe-fonts/source-han-sans/blob/2.005R/LICENSE.txt>

The original font bytes are compiled into the native renderer. PDF output
embeds the OpenType font directly. DOCX output embeds the same bytes as an
OOXML obfuscated-font part using a fixed document font key. The full font is
embedded; the font file is not renamed or modified in the source tree.

## printpdf

- Crate: `printpdf`
- Version: `0.11.3`
- License declared by the crate: MIT
- Repository: <https://github.com/fschutt/printpdf>
- Build: `default-features = false`
- Role: deterministic native PDF composition; it does not fetch fonts,
  templates, content, or other network resources.

The exact resolved package and transitive dependency metadata is recorded in
`cargo-lock-components.json`. The report source, manifest and audited HEOR
report package are read locally; generated DOCX/PDF files remain explicitly
marked as awaiting human review.

`printpdf` resolves `lopdf` 0.44.0. The existing local-evidence extractor
`pdf-extract` 0.12.0 resolves `lopdf` 0.42.0, so the lockfile intentionally
contains two PDF parser versions. Both are at or above the reviewed RustSec
fixed baseline. A fail-closed contract permits only this exact pair and binds
each version to its expected direct consumer; adding or downgrading either
version fails the development gate. The two chains should be unified when an
upstream-compatible `pdf-extract` release exists rather than through an
unmaintained private fork.

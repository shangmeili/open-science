# AI4HEOR OpenCode patch

AI4HEOR builds its OpenCode sidecar from the pinned OpenCode 1.17.13 source
commit recorded in `manifest.json`. The reviewed patch adds one bounded audit
field to persisted assistant messages: a SHA-256 of the exact ordered system
blocks after OpenCode plugins have transformed them and before the provider
request starts.

The field contains only the contract identifier, lowercase SHA-256 and block
count. It does not store instruction text, prompts, responses, URLs or
credentials, and it is not added to the provider request. Auxiliary calls that
do not own a persisted assistant message do not receive the callback and cannot
be associated by timing or queue order.

The source archive, patch and Bun toolchain are pinned. The build fails if the
source or patch bytes drift, the patch no longer applies, the focused upstream
tests fail, or the patched binary reports an unexpected version.

OpenCode remains licensed under the included MIT license. This directory and
the bundled release notices must remain with redistributed patched binaries.

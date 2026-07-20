# Conceptual-model diagram export contract

AI4HEOR renders a review view from the exact current bytes of `heor/conceptual-model.json`. The JSON remains the scientific and semantic authority.

## Outputs

- `deliverables/conceptual-model-layout.json`: node coordinates only, bound to the model ID and source SHA-256.
- `deliverables/conceptual-model.svg`: deterministic, accessible, non-executable visual review copy.
- `deliverables/conceptual-model.graphml`: editable graph with the exact state IDs, labels, definitions, absorbing flags, transitions, triggers, and saved coordinates.
- `deliverables/conceptual-model.audit.json`: generator identity and SHA-256 bindings for all three outputs.

All outputs remain `awaiting_human_review`. Exporting or rearranging them is not model approval.

## Semantic boundary

The layout editor may change only `x` and `y` coordinates for every existing state. It cannot add, remove, rename, redefine, or reconnect states and transitions. Those changes must be made in `heor/conceptual-model.json`, then pass the portable and native conceptual-model audits before another export.

The native exporter accepts at most 24 states and 128 transitions, requires each state exactly once, bounds coordinates to its canvas, escapes all model text, and emits no script or external link. It reads and writes only bounded regular files under the current workspace.

## Currentness and overwrite rules

The app reports a diagram as current only when the model, layout, SVG, GraphML, generator version, paths, counts, and audit hashes all match. A model change makes the previous diagram stale.

AI4HEOR never overwrites a layout, SVG, or GraphML file that no longer matches its last generation record. Move or rename an externally edited copy before exporting a replacement.

GraphML is an interchange view, not a reverse-import format. Edits made in another graph editor do not alter the model contract and are not imported into `heor/conceptual-model.json`.

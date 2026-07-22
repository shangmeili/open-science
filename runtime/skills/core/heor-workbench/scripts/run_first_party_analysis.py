#!/usr/bin/env python3
"""Run the bundled AI4HEOR deterministic base-case engine.

This helper is the agent-accessible counterpart of the desktop review-panel
button. It uses only the app-owned ``heor_core`` resource selected by the
desktop runtime and writes the watched base-case result atomically.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


OUTPUT_PATH = Path("heor/results/base-case.json")
OUTPUT_CAP_BYTES = 25 * 1024 * 1024
PROVENANCE_VALIDATOR = (
    Path(__file__).resolve().parents[2]
    / "heor-input-provenance/scripts/validate_input_provenance.py"
)


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"path is outside the active workspace: {path}")
    return resolved


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan",
        default="heor/analysis-plan.json",
        help="validated first-party analysis plan inside the active workspace",
    )
    return parser


def _validate_research_contract(root: Path, plan: Path) -> None:
    """Require the same portable provenance contract used by the review pane.

    ``heor_core`` intentionally calculates from numerical inputs and does not
    decide whether research evidence is complete. The agent-facing runner must
    therefore run the separate first-party provenance validator before it can
    create a watched result.
    """
    if not PROVENANCE_VALIDATOR.is_file():
        raise RuntimeError("AI4HEOR input-provenance validator is unavailable")
    specification = importlib.util.spec_from_file_location(
        "ai4heor_input_provenance_validator",
        PROVENANCE_VALIDATOR,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("AI4HEOR input-provenance validator could not be loaded")
    validator = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(validator)

    plan_payload = json.loads(plan.read_bytes())
    mappings = plan_payload.get("input_provenance")
    if isinstance(mappings, list):
        legacy = [
            item for item in mappings
            if isinstance(item, dict) and "input_path" in item and "path" not in item
        ]
        if legacy:
            raise ValueError(
                "analysis plan uses the legacy input_provenance.input_path contract; "
                "migrate the existing values and evidence links to the current bundled "
                "analysis-plan template before running. Do not inspect or modify the "
                "bundled engine source"
            )
    synthesis_path = root / "heor/evidence-synthesis.json"
    if synthesis_path.is_file():
        synthesis_raw = synthesis_path.read_bytes()
        synthesis = json.loads(synthesis_raw)
    else:
        synthesis_raw = b"{}\n"
        synthesis = {}
    audit = validator.audit(
        plan_payload,
        synthesis,
        hashlib.sha256(synthesis_raw).hexdigest(),
    )
    if audit.get("complete"):
        return
    gaps = [
        *audit.get("errors", []),
        *audit.get("invalid_mappings", []),
        *[f"unsupported input: {path}" for path in audit.get("unsupported_inputs", [])],
        *[f"unresolved assumption: {item}" for item in audit.get("unresolved_assumptions", [])],
    ]
    detail = "; ".join(str(item) for item in gaps[:8])
    if len(gaps) > 8:
        detail += f"; and {len(gaps) - 8} more gap(s)"
    raise ValueError(f"analysis plan is not structurally ready for review: {detail}")


def main() -> int:
    args = _parser().parse_args()
    root = Path.cwd().resolve()
    plan = _inside(root, Path(args.plan))
    output = _inside(root, OUTPUT_PATH)
    if not plan.is_file():
        raise ValueError(f"analysis plan not found: {plan.relative_to(root)}")

    _validate_research_contract(root, plan)

    core_raw = os.environ.get("AI4HEOR_HEOR_CORE_PATH", "").strip()
    if not core_raw:
        raise RuntimeError("AI4HEOR first-party engine path is unavailable")
    core = Path(core_raw).resolve()
    if not (core / "heor_core" / "__main__.py").is_file():
        raise RuntimeError("AI4HEOR first-party engine resource is incomplete")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(core)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-m", "heor_core", str(plan)],
        cwd=root,
        env=env,
        capture_output=True,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"AI4HEOR engine exited with {completed.returncode}")
    if len(completed.stdout) > OUTPUT_CAP_BYTES:
        raise RuntimeError("AI4HEOR engine output exceeds the 25 MB limit")

    result = json.loads(completed.stdout)
    expected = hashlib.sha256(plan.read_bytes()).hexdigest()
    if result.get("input_sha256") != expected:
        raise RuntimeError("AI4HEOR engine input hash does not match the analysis plan")

    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    with tempfile.NamedTemporaryFile(
        dir=output.parent,
        prefix=".base-case-",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(rendered)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, output)

    print(
        json.dumps(
            {
                "status": "calculation_only",
                "plan": str(plan.relative_to(root)),
                "input_sha256": expected,
                "result": str(output.relative_to(root)),
                "engine_version": result.get("engine_version"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"AI4HEOR deterministic run failed: {error}", file=sys.stderr)
        raise SystemExit(1)

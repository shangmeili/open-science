#!/usr/bin/env python3
"""Audit one paired survival bootstrap result and its current source bindings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from paired_bootstrap_contract import audit_result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    errors, facts = audit_result(args.manifest, args.workspace.resolve())
    output = {"complete": not errors, "errors": errors, **facts}
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if not errors and facts.get("eligible_for_joint_packaging") else 1


if __name__ == "__main__":
    raise SystemExit(main())

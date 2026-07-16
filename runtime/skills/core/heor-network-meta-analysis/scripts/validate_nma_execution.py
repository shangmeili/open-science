#!/usr/bin/env python3
"""Audit a bounded AI4HEOR NMA execution manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nma_contract import audit_result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    audit = audit_result(args.manifest, args.workspace)
    print(json.dumps(audit, indent=2))
    return 0 if audit["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

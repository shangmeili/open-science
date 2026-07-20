#!/usr/bin/env python3
"""Verify one downloaded sidecar archive against its unique pinned SHA-256."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(arguments: list[str]) -> int:
    if len(arguments) not in {4, 5}:
        print(
            "usage: verify_sidecar_checksum.py FILE PRODUCT VERSION ASSET [CHECKSUM_FILE]",
            file=sys.stderr,
        )
        return 2

    archive = Path(arguments[0])
    product, version, asset = arguments[1:4]
    checksums = (
        Path(arguments[4])
        if len(arguments) == 5
        else Path(__file__).with_name("sidecar-checksums.sha256")
    )
    key = f"{product}/{version}/{asset}"
    matches: list[str] = []
    for raw in checksums.read_text(encoding="utf-8").splitlines():
        fields = raw.split()
        if len(fields) == 2 and fields[1] == key:
            matches.append(fields[0])
    if len(matches) != 1 or re.fullmatch(r"[0-9a-f]{64}", matches[0]) is None:
        print(f"No unique pinned SHA-256 for {key}", file=sys.stderr)
        return 1

    actual = sha256(archive)
    if actual != matches[0]:
        print(
            f"SHA-256 mismatch for {key}: expected {matches[0]}, got {actual}",
            file=sys.stderr,
        )
        return 1
    print(f"Verified SHA-256 for {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Fail closed before a tagged macOS build can access release credentials."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping


REQUIRED_ENVIRONMENT = (
    "APPLE_CERTIFICATE",
    "APPLE_CERTIFICATE_PASSWORD",
    "APPLE_SIGNING_IDENTITY",
    "APPLE_ID",
    "APPLE_PASSWORD",
    "APPLE_TEAM_ID",
)


def inspect_environment(environment: Mapping[str, str]) -> dict[str, str]:
    missing = [name for name in REQUIRED_ENVIRONMENT if not environment.get(name)]
    if missing:
        raise AssertionError(
            "tagged macOS releases require these non-empty secrets: "
            + ", ".join(missing)
        )
    team_id = environment["APPLE_TEAM_ID"]
    if re.fullmatch(r"[A-Z0-9]{10}", team_id) is None:
        raise AssertionError("APPLE_TEAM_ID must be a ten-character Apple Team ID")
    identity = environment["APPLE_SIGNING_IDENTITY"]
    match = re.fullmatch(r"Developer ID Application:.+\(([A-Z0-9]{10})\)", identity)
    if match is None:
        raise AssertionError(
            "APPLE_SIGNING_IDENTITY must name a Developer ID Application certificate "
            "and include its Team ID"
        )
    if match.group(1) != team_id:
        raise AssertionError(
            "APPLE_SIGNING_IDENTITY Team ID does not match APPLE_TEAM_ID"
        )
    return {
        "authentication": "apple-id-app-password",
        "certificate": "present",
        "signing_identity": "developer-id-application",
        "team_id": "present",
    }


def main() -> None:
    summary = inspect_environment(os.environ)
    print("macOS tag-release credential preflight passed: " + json.dumps(summary))


if __name__ == "__main__":
    main()

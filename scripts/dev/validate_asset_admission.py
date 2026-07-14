#!/usr/bin/env python3
"""Portable fail-closed validator for AI4HEOR third-party asset admission."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

RELEASE_STATUS = "validated-adapter"
VALID_STATUSES = {RELEASE_STATUS, "quarantined", "rejected"}
VALID_KINDS = {"skill", "mcp", "package"}
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$")
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: Any) -> bool:
    return isinstance(value, list) and all(nonempty(item) for item in value)


def validate_registry(registry: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(registry, dict):
        return ["asset registry must be a JSON object"]
    if registry.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(registry.get("policy_revision", ""))):
        errors.append("policy_revision must be YYYY-MM-DD")
    if registry.get("release_statuses") != [RELEASE_STATUS]:
        errors.append("release_statuses must contain only validated-adapter")
    assets = registry.get("assets")
    if not isinstance(assets, list) or not assets:
        return errors + ["assets must be a non-empty array"]

    seen: set[str] = set()
    deployments: set[tuple[str, str]] = set()
    for index, asset in enumerate(assets):
        prefix = f"assets[{index}]"
        if not isinstance(asset, dict):
            errors.append(f"{prefix} must be an object")
            continue
        asset_id = asset.get("asset_id")
        status = asset.get("status")
        kind = asset.get("kind")
        if not nonempty(asset_id) or not SAFE_ID.fullmatch(asset_id):
            errors.append(f"{prefix}.asset_id is unsafe")
        elif asset_id in seen:
            errors.append(f"{prefix}.asset_id is duplicated")
        else:
            seen.add(asset_id)
        if not nonempty(asset.get("display_name")):
            errors.append(f"{prefix}.display_name is required")
        if kind not in VALID_KINDS:
            errors.append(f"{prefix}.kind is invalid")
        if status not in VALID_STATUSES:
            errors.append(f"{prefix}.status is invalid")
        if asset.get("release_eligible") is not (status == RELEASE_STATUS):
            errors.append(
                f"{prefix}.release_eligible must exactly match validated-adapter status"
            )

        source = asset.get("source")
        if not isinstance(source, dict):
            source = {}
            errors.append(f"{prefix}.source must be an object")
        if not str(source.get("repository", "")).startswith("https://"):
            errors.append(f"{prefix}.source.repository must use HTTPS")
        if not COMMIT.fullmatch(str(source.get("revision", ""))):
            errors.append(f"{prefix}.source.revision must be a lowercase full commit")
        if not nonempty(source.get("license_spdx")):
            errors.append(f"{prefix}.source.license_spdx is required")
        if not str(source.get("license_evidence_url", "")).startswith("https://"):
            errors.append(f"{prefix}.source.license_evidence_url must use HTTPS")
        if not isinstance(source.get("license_compatible"), bool):
            errors.append(f"{prefix}.source.license_compatible must be boolean")

        boundary = asset.get("capability_boundary")
        if not isinstance(boundary, dict):
            boundary = {}
            errors.append(f"{prefix}.capability_boundary must be an object")
        for field in ("workspace_access", "network_egress", "execution"):
            if not nonempty(boundary.get(field)):
                errors.append(f"{prefix}.capability_boundary.{field} is required")
        if boundary.get("authority") != "no-approval-or-decision-authority":
            errors.append(f"{prefix}.capability_boundary.authority is invalid")

        industrial = asset.get("industrialization")
        if not isinstance(industrial, dict):
            industrial = {}
            errors.append(f"{prefix}.industrialization must be an object")
        for field in ("adaptation_mode", "delta_record", "security_review", "methods_review"):
            if not nonempty(industrial.get(field)):
                errors.append(f"{prefix}.industrialization.{field} is required")
        for field in ("contract_tests", "adversarial_tests", "platforms", "upstream_evidence"):
            if not string_list(industrial.get(field)):
                errors.append(
                    f"{prefix}.industrialization.{field} must contain only non-empty strings"
                )
        if not isinstance(industrial.get("kill_switch"), bool):
            errors.append(f"{prefix}.industrialization.kill_switch must be boolean")
        blockers = asset.get("blockers")
        if not string_list(blockers):
            errors.append(f"{prefix}.blockers must contain only non-empty strings")
            blockers = []

        distribution = asset.get("distribution")
        if status == RELEASE_STATUS:
            complete = (
                source.get("license_compatible") is True
                and industrial.get("adaptation_mode")
                in {"first-party-derivative", "isolated-adapter"}
                and bool(industrial.get("contract_tests"))
                and bool(industrial.get("adversarial_tests"))
                and set(industrial.get("platforms", [])) == {"macos", "windows", "linux"}
                and industrial.get("security_review") == "passed"
                and industrial.get("methods_review") == "passed"
                and industrial.get("kill_switch") is True
                and not blockers
            )
            if not complete:
                errors.append(f"{prefix} is not industrially complete enough for validated-adapter")
            if not isinstance(distribution, dict):
                errors.append(f"{prefix}.distribution must be a hash-locked object")
                continue
            pack = distribution.get("resource_pack")
            entry = distribution.get("entry")
            digest = distribution.get("content_sha256")
            if (
                kind != "skill"
                or not isinstance(pack, str)
                or not SAFE_SEGMENT.fullmatch(pack)
                or not pack.startswith("skills-admitted-")
                or not isinstance(entry, str)
                or not SAFE_SEGMENT.fullmatch(entry)
                or not isinstance(digest, str)
                or not SHA256.fullmatch(digest)
            ):
                errors.append(
                    f"{prefix}.distribution must name a hash-locked admitted skill resource"
                )
            elif (pack, entry) in deployments:
                errors.append(f"{prefix}.distribution duplicates an admitted resource")
            else:
                deployments.add((pack, entry))
        elif distribution is not None or not blockers:
            errors.append(f"{prefix} non-admitted assets must be non-distributed and blocked")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "registry",
        nargs="?",
        type=Path,
        default=Path("runtime/assets/asset-admission-registry.json"),
    )
    args = parser.parse_args()
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"asset admission failed closed: {exc}", file=sys.stderr)
        return 1
    errors = validate_registry(registry)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    assets = registry["assets"]
    admitted = sum(asset["status"] == RELEASE_STATUS for asset in assets)
    quarantined = sum(asset["status"] == "quarantined" for asset in assets)
    rejected = sum(asset["status"] == "rejected" for asset in assets)
    print(
        f"asset admission valid: {len(assets)} reviewed, {admitted} admitted, "
        f"{quarantined} quarantined, {rejected} rejected"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

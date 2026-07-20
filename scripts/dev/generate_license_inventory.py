#!/usr/bin/env python3
"""Generate path-free npm and Cargo license inventories from locked local state."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGAL = ROOT / "docs" / "legal"


def run(*command: str) -> str:
    return subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True).stdout


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def npm_inventory() -> dict:
    raw = json.loads(run("pnpm", "licenses", "list", "--prod", "--json"))
    components = []
    for license_expression, entries in sorted(raw.items()):
        for entry in entries:
            components.append(
                {
                    "name": entry["name"],
                    "versions": sorted(entry.get("versions", [])),
                    "license": license_expression,
                    "author": entry.get("author"),
                    "homepage": entry.get("homepage"),
                }
            )
    components.sort(key=lambda item: (item["name"], item["versions"]))
    return {
        "schema": "ai4heor-npm-license-inventory/v1",
        "generated_on": date.today().isoformat(),
        "scope": "pnpm production dependency universe resolved from the lockfile",
        "lockfile_sha256": file_hash(ROOT / "pnpm-lock.yaml"),
        "components": components,
    }


def cargo_inventory() -> dict:
    raw = json.loads(
        run(
            "cargo",
            "metadata",
            "--format-version=1",
            "--locked",
            "--manifest-path",
            "apps/desktop/src-tauri/Cargo.toml",
        )
    )
    components = []
    for package in raw["packages"]:
        components.append(
            {
                "name": package["name"],
                "version": package["version"],
                "license": package.get("license") or "Unknown",
                "source": package.get("source") or "workspace",
                "repository": package.get("repository"),
            }
        )
    components.sort(key=lambda item: (item["name"], item["version"], item["source"]))
    return {
        "schema": "ai4heor-cargo-license-inventory/v1",
        "generated_on": date.today().isoformat(),
        "scope": "Cargo.lock package universe; conservative superset of one target build",
        "lockfile_sha256": file_hash(ROOT / "apps" / "desktop" / "src-tauri" / "Cargo.lock"),
        "components": components,
    }


def write(name: str, value: dict) -> None:
    LEGAL.mkdir(parents=True, exist_ok=True)
    (LEGAL / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    write("npm-production-components.json", npm_inventory())
    write("cargo-lock-components.json", cargo_inventory())


if __name__ == "__main__":
    main()

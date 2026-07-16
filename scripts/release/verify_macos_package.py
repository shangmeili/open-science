#!/usr/bin/env python3
"""Verify one native AI4HEOR macOS DMG and its scientific resources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TARGET_ARCH = {
    "aarch64-apple-darwin": ("arm64", "aarch64"),
    "x86_64-apple-darwin": ("x86_64", "x64"),
}


def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(command, check=True, **kwargs)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise AssertionError(f"required macOS package verification tool is missing: {name}")


def clean_files(root: Path) -> dict[Path, Path]:
    files: dict[Path, Path] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise AssertionError(f"scientific resource contains a symlink: {path}")
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            raise AssertionError(f"scientific resource contains a Python cache: {path}")
        if path.is_file():
            files[path.relative_to(root)] = path
    return files


def compare_tree(source: Path, packaged: Path) -> int:
    source_files = clean_files(source)
    packaged_files = clean_files(packaged)
    if set(source_files) != set(packaged_files):
        missing = sorted(str(path) for path in set(source_files) - set(packaged_files))
        extra = sorted(str(path) for path in set(packaged_files) - set(source_files))
        raise AssertionError(
            f"packaged resource tree differs for {packaged}: missing={missing}, extra={extra}"
        )
    for relative, source_file in source_files.items():
        if sha256(source_file) != sha256(packaged_files[relative]):
            raise AssertionError(f"packaged resource bytes differ: {packaged / relative}")
    return len(source_files)


def verify_resources(app: Path, source_root: Path) -> tuple[Path, int]:
    resource_root = app / "Contents/Resources"
    registry = resource_root / "asset-admission-registry.json"
    if not registry.is_file():
        raise AssertionError("packaged asset admission registry is missing")
    config_path = source_root / "apps/desktop/src-tauri/tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config_root = config_path.parent
    count = 0
    for raw_source, raw_destination in config["bundle"]["resources"].items():
        source = (config_root / raw_source).resolve()
        destination = resource_root / raw_destination.rstrip("/")
        if source.is_dir():
            if not destination.is_dir():
                raise AssertionError(f"packaged resource directory is missing: {destination}")
            count += compare_tree(source, destination)
        else:
            if not destination.is_file():
                raise AssertionError(f"packaged resource file is missing: {destination}")
            if source.is_symlink() or destination.is_symlink():
                raise AssertionError(f"packaged resource is linked: {destination}")
            if sha256(source) != sha256(destination):
                raise AssertionError(f"packaged resource bytes differ: {destination}")
            count += 1
    clean_files(resource_root)
    return resource_root, count


def binary_version(path: Path) -> str:
    completed = run([str(path), "--version"], capture_output=True, text=True)
    return (completed.stdout or completed.stderr).strip()


def verify_binaries(app: Path, expected_arch: str) -> dict[str, str]:
    executable_root = app / "Contents/MacOS"
    binaries = {
        "main": executable_root / "ai4s-workbench",
        "opencode": executable_root / "opencode",
        "uv": executable_root / "uv",
    }
    for name, path in binaries.items():
        if not path.is_file() or path.is_symlink() or not os.access(path, os.X_OK):
            raise AssertionError(f"packaged {name} binary is missing, linked, or not executable")
        architectures = run(
            ["lipo", "-archs", str(path)], capture_output=True, text=True
        ).stdout.split()
        if architectures != [expected_arch]:
            raise AssertionError(f"unexpected {name} architectures: {architectures}")
    versions = {
        "opencode": binary_version(binaries["opencode"]),
        "uv": binary_version(binaries["uv"]),
    }
    if "1.17.13" not in versions["opencode"]:
        raise AssertionError(f"unexpected OpenCode version: {versions['opencode']}")
    if "0.11.26" not in versions["uv"]:
        raise AssertionError(f"unexpected uv version: {versions['uv']}")
    return versions


def run_packaged_heor_tests(resource_root: Path, source_root: Path) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(resource_root / "heor-core/src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(source_root / "python/heor_core/tests"),
            "-q",
        ],
        env=environment,
    )


def mount_dmg(dmg: Path) -> tuple[str, Path]:
    completed = run(
        ["hdiutil", "attach", "-readonly", "-nobrowse", "-plist", str(dmg)],
        capture_output=True,
    )
    plist = plistlib.loads(completed.stdout)
    entities = plist.get("system-entities", [])
    mounts = [entity for entity in entities if entity.get("mount-point")]
    if len(mounts) != 1:
        raise AssertionError(f"expected one mounted DMG volume, found {mounts}")
    device = mounts[0].get("dev-entry")
    if not isinstance(device, str) or not device:
        raise AssertionError("mounted DMG did not report a device")
    return device, Path(mounts[0]["mount-point"])


def verify_info(app: Path, expected_version: str) -> dict[str, str]:
    with (app / "Contents/Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    expected = {
        "CFBundleDisplayName": "AI4HEOR",
        "CFBundleExecutable": "ai4s-workbench",
        "CFBundleIdentifier": "com.ai4s.workbench",
        "CFBundleShortVersionString": expected_version,
        "CFBundleVersion": expected_version,
    }
    for key, value in expected.items():
        if info.get(key) != value:
            raise AssertionError(f"unexpected {key}: {info.get(key)!r}")
    return expected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--target", choices=tuple(TARGET_ARCH), required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--verification-json", type=Path, required=True)
    arguments = parser.parse_args()
    if sys.platform != "darwin":
        raise AssertionError("macOS package verification must run on macOS")
    for tool in ("hdiutil", "lipo"):
        require_tool(tool)
    dmg = arguments.dmg.resolve()
    source_root = arguments.source_root.resolve()
    expected_arch, filename_arch = TARGET_ARCH[arguments.target]
    if not dmg.is_file() or dmg.is_symlink():
        raise AssertionError(f"DMG is missing or linked: {dmg}")
    if re.fullmatch(rf"AI4HEOR_.+_{filename_arch}\.dmg", dmg.name) is None:
        raise AssertionError(f"unexpected DMG filename for {arguments.target}: {dmg.name}")
    config = json.loads(
        (source_root / "apps/desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    )
    device: str | None = None
    try:
        device, mount = mount_dmg(dmg)
        apps = [path for path in mount.iterdir() if path.suffix == ".app" and path.is_dir()]
        if len(apps) != 1 or apps[0].name != "AI4HEOR.app":
            raise AssertionError(f"expected one AI4HEOR.app in DMG, found {apps}")
        app = apps[0]
        info = verify_info(app, config["version"])
        versions = verify_binaries(app, expected_arch)
        resource_root, resource_count = verify_resources(app, source_root)
        run_packaged_heor_tests(resource_root, source_root)
        verification = {
            "bundle": {
                "dmg_sha256": sha256(dmg),
                "filename": dmg.name,
                "target": arguments.target,
            },
            "info_plist": info,
            "payload": {
                "architecture": expected_arch,
                "opencode_version": versions["opencode"],
                "resource_files": resource_count,
                "uv_version": versions["uv"],
            },
        }
        arguments.verification_json.parent.mkdir(parents=True, exist_ok=True)
        arguments.verification_json.write_text(
            json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            "Verified AI4HEOR macOS package: "
            f"dmg_sha256={sha256(dmg)}, target={arguments.target}, "
            f"resource_files={resource_count}"
        )
    finally:
        if device is not None:
            run(["hdiutil", "detach", device], capture_output=True, text=True)


if __name__ == "__main__":
    main()

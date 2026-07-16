#!/usr/bin/env python3
"""Verify the native AI4HEOR Linux packages and their scientific resources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_NAME = "ai4heor"
BINARY_NAME = "ai4s-workbench"


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, **kwargs)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise AssertionError(f"required package verification tool is missing: {name}")


def package_metadata(deb: Path, rpm: Path, expected_version: str) -> None:
    deb_fields = run(
        ["dpkg-deb", "--field", str(deb), "Package", "Version", "Architecture"],
        capture_output=True,
    ).stdout.splitlines()
    if deb_fields != [
        f"Package: {PACKAGE_NAME}",
        f"Version: {expected_version}",
        "Architecture: amd64",
    ]:
        raise AssertionError(f"unexpected deb metadata: {deb_fields}")

    rpm_fields = run(
        ["rpm", "-qp", "--qf", "%{NAME}\n%{VERSION}\n%{ARCH}\n", str(rpm)],
        capture_output=True,
    ).stdout.splitlines()
    if rpm_fields != [PACKAGE_NAME, expected_version, "x86_64"]:
        raise AssertionError(f"unexpected rpm metadata: {rpm_fields}")


def extract_deb(package: Path, destination: Path) -> None:
    run(["dpkg-deb", "--extract", str(package), str(destination)])


def extract_rpm(package: Path, destination: Path) -> None:
    copied_package = destination.parent / "verification-package.rpm"
    shutil.copy2(package, copied_package)
    run(["rpm2archive", "--nocompression", str(copied_package)])
    archive = Path(f"{copied_package}.tar")
    with tarfile.open(archive, "r:") as handle:
        for member in handle.getmembers():
            parts = Path(member.name).parts
            if member.name.startswith("/") or ".." in parts:
                raise AssertionError(f"unsafe RPM archive path: {member.name}")
            if member.issym() or member.islnk():
                raise AssertionError(f"RPM archive contains a link: {member.name}")
    run(["tar", "--extract", "--file", str(archive), "--directory", str(destination)])


def unique_file(root: Path, name: str) -> Path:
    matches = [path for path in root.rglob(name) if path.is_file()]
    if len(matches) != 1:
        raise AssertionError(f"expected one {name} in {root}, found {matches}")
    return matches[0]


def assert_no_links(root: Path) -> None:
    links = [path for path in root.rglob("*") if path.is_symlink()]
    if links:
        raise AssertionError(f"package payload contains links: {links}")


def clean_files(root: Path) -> dict[Path, Path]:
    files: dict[Path, Path] = {}
    for path in root.rglob("*"):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise AssertionError(f"scientific resource contains a symlink: {path}")
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


def verify_resources(extracted: Path, source_root: Path) -> tuple[Path, int]:
    registry = unique_file(extracted, "asset-admission-registry.json")
    resource_root = registry.parent
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
            if sha256(source) != sha256(destination):
                raise AssertionError(f"packaged resource bytes differ: {destination}")
            count += 1
    generated = [
        path
        for path in resource_root.rglob("*")
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}
    ]
    if generated:
        raise AssertionError(f"generated Python caches were packaged: {generated}")
    return resource_root, count


def verify_binaries(extracted: Path) -> tuple[dict[str, Path], dict[str, str]]:
    binaries = {
        BINARY_NAME: unique_file(extracted, BINARY_NAME),
        "opencode": unique_file(extracted, "opencode"),
        "uv": unique_file(extracted, "uv"),
    }
    for name, path in binaries.items():
        if not os.access(path, os.X_OK):
            raise AssertionError(f"packaged binary is not executable: {path}")
        description = run(["file", "--brief", str(path)], capture_output=True).stdout
        if "ELF 64-bit" not in description or "x86-64" not in description:
            raise AssertionError(f"unexpected {name} binary architecture: {description.strip()}")
    versions = {
        "opencode": run([str(binaries["opencode"]), "--version"], capture_output=True).stdout,
        "uv": run([str(binaries["uv"]), "--version"], capture_output=True).stdout,
    }
    if "1.17.13" not in versions["opencode"]:
        raise AssertionError(f"unexpected OpenCode version: {versions['opencode'].strip()}")
    if "0.11.26" not in versions["uv"]:
        raise AssertionError(f"unexpected uv version: {versions['uv'].strip()}")
    return binaries, {name: output.strip() for name, output in versions.items()}


def normalized_main_binary(path: Path, bundle_type: str) -> bytes:
    data = path.read_bytes()
    marker = f"__TAURI_BUNDLE_TYPE_VAR_{bundle_type}".encode()
    if data.count(marker) != 1:
        raise AssertionError(f"main binary does not contain one {bundle_type} bundle marker")
    return data.replace(marker, b"__TAURI_BUNDLE_TYPE_VAR_PKG")


def run_packaged_heor_tests(resource_root: Path, source_root: Path) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(resource_root / "heor-core/src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    run(
        [
            "python3",
            "-m",
            "unittest",
            "discover",
            "-s",
            str(source_root / "python/heor_core/tests"),
            "-q",
        ],
        env=environment,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deb", type=Path, required=True)
    parser.add_argument("--rpm", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--verification-json", type=Path)
    arguments = parser.parse_args()
    deb = arguments.deb.resolve()
    rpm = arguments.rpm.resolve()
    source_root = arguments.source_root.resolve()
    for package in (deb, rpm):
        if not package.is_file():
            raise AssertionError(f"package does not exist: {package}")
    for tool in ("dpkg-deb", "rpm", "rpm2archive", "tar", "file"):
        require_tool(tool)

    config = json.loads(
        (source_root / "apps/desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    )
    package_metadata(deb, rpm, config["version"])
    with tempfile.TemporaryDirectory(prefix="ai4heor-linux-packages-") as temporary:
        temporary_root = Path(temporary)
        extracted = {"deb": temporary_root / "deb", "rpm": temporary_root / "rpm"}
        for root in extracted.values():
            root.mkdir()
        extract_deb(deb, extracted["deb"])
        extract_rpm(rpm, extracted["rpm"])

        verified: dict[str, tuple[dict[str, Path], dict[str, str], int]] = {}
        for kind, root in extracted.items():
            assert_no_links(root)
            binaries, versions = verify_binaries(root)
            resources, count = verify_resources(root, source_root)
            run_packaged_heor_tests(resources, source_root)
            verified[kind] = (binaries, versions, count)

        if normalized_main_binary(
            verified["deb"][0][BINARY_NAME], "DEB"
        ) != normalized_main_binary(verified["rpm"][0][BINARY_NAME], "RPM"):
            raise AssertionError("deb and rpm main binaries differ outside the Tauri bundle marker")
        for binary in ("opencode", "uv"):
            if sha256(verified["deb"][0][binary]) != sha256(verified["rpm"][0][binary]):
                raise AssertionError(f"deb and rpm package different {binary} bytes")
        if verified["deb"][2] != verified["rpm"][2]:
            raise AssertionError("deb and rpm verified different resource counts")

    if arguments.verification_json is not None:
        verification = {
            "bundles": {
                "deb": {"filename": deb.name, "sha256": sha256(deb)},
                "rpm": {"filename": rpm.name, "sha256": sha256(rpm)},
            },
            "metadata": {
                "architecture": "x86_64",
                "package_name": PACKAGE_NAME,
                "version": config["version"],
            },
            "payload": {
                "deb_rpm_main_binary_parity": True,
                "deb_rpm_sidecar_parity": True,
                "opencode_version": verified["deb"][1]["opencode"],
                "resource_files": verified["deb"][2],
                "uv_version": verified["deb"][1]["uv"],
            },
        }
        arguments.verification_json.parent.mkdir(parents=True, exist_ok=True)
        arguments.verification_json.write_text(
            json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    print(
        "Verified AI4HEOR Linux packages: "
        f"deb_sha256={sha256(deb)}, rpm_sha256={sha256(rpm)}, "
        f"resource_files={verified['deb'][2]}"
    )


if __name__ == "__main__":
    main()

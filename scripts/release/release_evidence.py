#!/usr/bin/env python3
"""Create and validate hash-bound AI4HEOR release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_SCHEMA = "ai4heor-release-evidence/v1"
MANIFEST_SCHEMA = "ai4heor-release-manifest/v1"
SUPPORTED_TARGETS = {
    "aarch64-apple-darwin": "macos",
    "x86_64-apple-darwin": "macos",
    "x86_64-pc-windows-msvc": "windows",
    "x86_64-unknown-linux-gnu": "linux",
}
RUNNER_OS_BY_PLATFORM = {"macos": "macOS", "windows": "Windows", "linux": "Linux"}
MACOS_DISTRIBUTION_CHECKS = {
    "developer-id-signature",
    "gatekeeper-assessment",
    "hardened-runtime",
    "notarization-ticket",
}
FIRST_LAUNCH_CHECKS = {"first-launch-process", "workspace-created"}
MACOS_WORKSPACE_MIGRATION_CHECK = "workspace-migrated"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def source_identity(root: Path) -> tuple[str, str]:
    commit = git(root, "rev-parse", "HEAD")
    dirty = git(root, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise AssertionError(f"tracked source is dirty:\n{dirty}")
    github_sha = os.environ.get("GITHUB_SHA")
    if github_sha and github_sha != commit:
        raise AssertionError(f"GITHUB_SHA {github_sha} does not match HEAD {commit}")
    config = read_json(root / "apps/desktop/src-tauri/tauri.conf.json")
    return commit, config["version"]


def clean_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise AssertionError(f"release resource contains a symlink: {path}")
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            raise AssertionError(f"release resource contains a Python cache: {path}")
        if path.is_file():
            yield path


def resource_inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    config_path = root / "apps/desktop/src-tauri/tauri.conf.json"
    config = read_json(config_path)
    config_root = config_path.parent
    files: list[dict[str, Any]] = []
    for raw_source, raw_destination in sorted(config["bundle"]["resources"].items()):
        source = (config_root / raw_source).resolve()
        if not source.exists():
            raise AssertionError(f"configured release resource does not exist: {source}")
        if source.is_symlink():
            raise AssertionError(f"configured release resource is a symlink: {source}")
        candidates = clean_files(source) if source.is_dir() else [source]
        for path in candidates:
            relative = path.relative_to(source).as_posix() if source.is_dir() else path.name
            destination = (
                f"{raw_destination.rstrip('/')}/{relative}"
                if source.is_dir()
                else raw_destination
            )
            files.append(
                {
                    "destination": destination,
                    "sha256": sha256(path),
                    "size": path.stat().st_size,
                    "source": path.relative_to(root).as_posix(),
                }
            )
    files.sort(key=lambda item: (item["destination"], item["source"]))
    return {
        "aggregate_sha256": canonical_sha256(files),
        "file_count": len(files),
        "files": files,
        "total_bytes": sum(item["size"] for item in files),
    }


def binary_version(path: Path) -> str:
    completed = subprocess.run(
        [str(path), "--version"], check=True, capture_output=True, text=True
    )
    return (completed.stdout or completed.stderr).strip()


def sidecar_inventory(root: Path, target: str) -> list[dict[str, Any]]:
    suffix = ".exe" if "windows" in target else ""
    binary_root = root / "apps/desktop/src-tauri/binaries"
    result = []
    for name in ("opencode", "uv"):
        path = binary_root / f"{name}-{target}{suffix}"
        if not path.is_file() or path.is_symlink():
            raise AssertionError(f"release sidecar is missing or linked: {path}")
        result.append(
            {
                "name": name,
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256(path),
                "size": path.stat().st_size,
                "version_output": binary_version(path),
            }
        )
    return result


def parse_bundle(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("bundle must use KIND=PATH")
    kind, raw_path = value.split("=", 1)
    if not kind or not raw_path:
        raise argparse.ArgumentTypeError("bundle must use non-empty KIND=PATH")
    return kind, Path(raw_path)


def runner_identity() -> dict[str, str]:
    names = (
        "RUNNER_OS",
        "ImageOS",
        "ImageVersion",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_WORKFLOW_REF",
        "GITHUB_REF_TYPE",
    )
    return {name: os.environ[name] for name in names if os.environ.get(name)}


def artifact_record(kind: str, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise AssertionError(f"release artifact is missing or linked: {resolved}")
    return {
        "filename": resolved.name,
        "kind": kind,
        "sha256": sha256(resolved),
        "size": resolved.stat().st_size,
    }


def validate_evidence(value: Any, artifact_root: Path | None = None) -> None:
    if not isinstance(value, dict) or value.get("schema") != EVIDENCE_SCHEMA:
        raise AssertionError("unsupported release evidence schema")
    for field in (
        "source",
        "platform",
        "target",
        "artifacts",
        "checks",
        "resources",
        "sidecars",
        "verification",
    ):
        if not value.get(field):
            raise AssertionError(f"release evidence is missing {field}")
    source = value["source"]
    if not re.fullmatch(r"[0-9a-f]{40}", source.get("commit", "")) or not source.get(
        "version"
    ):
        raise AssertionError("release evidence has an invalid source identity")
    if SUPPORTED_TARGETS.get(value["target"]) != value["platform"]:
        raise AssertionError("release evidence has an unsupported platform/target pair")
    if value["checks"] != sorted(set(value["checks"])):
        raise AssertionError("release checks must be unique and sorted")
    files = value["resources"].get("files", [])
    if value["resources"].get("aggregate_sha256") != canonical_sha256(files):
        raise AssertionError("release resource inventory digest does not match its files")
    if value["resources"].get("file_count") != len(files) or value["resources"].get(
        "total_bytes"
    ) != sum(item.get("size", -1) for item in files):
        raise AssertionError("release resource inventory counts do not match its files")
    if len(value["artifacts"]) != len(
        {item["kind"] for item in value["artifacts"]}
    ):
        raise AssertionError("release evidence contains duplicate artifact kinds")
    for item in [*value["artifacts"], *value["sidecars"]]:
        if item.get("size", 0) < 1 or not re.fullmatch(
            r"[0-9a-f]{64}", item.get("sha256", "")
        ):
            raise AssertionError("release evidence contains an invalid byte record")
    if {item.get("name") for item in value["sidecars"]} != {"opencode", "uv"}:
        raise AssertionError("release evidence must bind exactly OpenCode and uv")
    if any(not item.get("version_output") for item in value["sidecars"]):
        raise AssertionError("release evidence has a sidecar without version output")
    declared_first_launch = FIRST_LAUNCH_CHECKS & set(value["checks"])
    if declared_first_launch:
        missing_checks = sorted(FIRST_LAUNCH_CHECKS - set(value["checks"]))
        if missing_checks:
            raise AssertionError(
                f"first-launch evidence is missing paired checks: {missing_checks}"
            )
        first_launch = value["verification"].get("first_launch")
        if (
            not isinstance(first_launch, dict)
            or not isinstance(first_launch.get("app_process_id"), int)
            or first_launch["app_process_id"] < 1
            or not first_launch.get("app_executable")
            or not isinstance(first_launch.get("opencode_process_id"), int)
            or first_launch["opencode_process_id"] < 1
            or not first_launch.get("opencode_executable")
            or not first_launch.get("workspace")
        ):
            raise AssertionError("first-launch process/workspace proof is incomplete")
    if MACOS_WORKSPACE_MIGRATION_CHECK in value["checks"]:
        if value["platform"] != "macos":
            raise AssertionError("workspace migration evidence is currently macOS-only")
        migration = value["verification"].get("first_launch", {}).get(
            "workspace_migration"
        )
        if (
            not isinstance(migration, dict)
            or not isinstance(migration.get("app_process_id"), int)
            or migration["app_process_id"] < 1
            or not isinstance(migration.get("opencode_process_id"), int)
            or migration["opencode_process_id"] < 1
            or not str(migration.get("workspace", "")).endswith("/Documents/AI4HEOR")
            or not str(migration.get("legacy_workspace", "")).endswith(
                "/Documents/OpenScience"
            )
            or migration.get("legacy_workspace_removed") is not True
            or not migration.get("marker_preserved")
            or migration.get("cleanup_verified") is not True
        ):
            raise AssertionError("workspace migration proof is incomplete")
    if (
        value["platform"] == "macos"
        and value.get("runner", {}).get("GITHUB_REF_TYPE") == "tag"
    ):
        missing_checks = sorted(MACOS_DISTRIBUTION_CHECKS - set(value["checks"]))
        if missing_checks:
            raise AssertionError(
                f"tagged macOS release evidence is missing trust checks: {missing_checks}"
            )
        distribution = value["verification"].get("distribution")
        if not isinstance(distribution, dict):
            raise AssertionError("tagged macOS release evidence has no distribution proof")
        if (
            not str(distribution.get("developer_id", "")).startswith(
                "Developer ID Application:"
            )
            or re.fullmatch(
                r"[A-Z0-9]{10}", str(distribution.get("team_identifier", ""))
            )
            is None
            or distribution.get("gatekeeper") != "accepted"
            or distribution.get("hardened_runtime") is not True
            or distribution.get("notarization_ticket") != "stapled"
            or distribution.get("sealed_resources") is not True
            or distribution.get("secure_timestamp") is not True
            or not isinstance(distribution.get("mach_o_files"), int)
            or distribution["mach_o_files"] < 3
        ):
            raise AssertionError("tagged macOS distribution proof is incomplete")
        if not distribution["developer_id"].endswith(
            f"({distribution['team_identifier']})"
        ):
            raise AssertionError(
                "tagged macOS Developer ID does not match its TeamIdentifier"
            )
    if artifact_root is not None:
        for item in value["artifacts"]:
            path = artifact_root / item["filename"]
            if not path.is_file():
                raise AssertionError(f"recorded artifact is missing: {path}")
            if path.stat().st_size != item["size"] or sha256(path) != item["sha256"]:
                raise AssertionError(f"recorded artifact bytes changed: {path}")


def validate_downloaded_artifacts(value: dict[str, Any], artifact_root: Path) -> None:
    for item in value["artifacts"]:
        matches = [
            path
            for path in artifact_root.rglob(item["filename"])
            if path.is_file() and not path.is_symlink()
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"expected one downloaded {item['filename']}, found {len(matches)}"
            )
        path = matches[0]
        if path.stat().st_size != item["size"] or sha256(path) != item["sha256"]:
            raise AssertionError(f"downloaded artifact bytes changed: {path}")


def record(arguments: argparse.Namespace) -> None:
    root = arguments.source_root.resolve()
    commit, version = source_identity(root)
    artifacts = sorted(
        [artifact_record(kind, path) for kind, path in arguments.bundle],
        key=lambda item: item["kind"],
    )
    if len(artifacts) != len({item["kind"] for item in artifacts}):
        raise AssertionError("each release artifact kind must be unique")
    verification = read_json(arguments.verification_json)
    value = {
        "artifacts": artifacts,
        "checks": sorted(set(arguments.check)),
        "platform": arguments.platform,
        "resources": resource_inventory(root),
        "runner": runner_identity(),
        "schema": EVIDENCE_SCHEMA,
        "sidecars": sidecar_inventory(root, arguments.target),
        "source": {"commit": commit, "version": version},
        "target": arguments.target,
        "verification": verification,
    }
    validate_evidence(value)
    write_json(arguments.output, value)


def verify(arguments: argparse.Namespace) -> None:
    value = read_json(arguments.evidence)
    validate_evidence(value, arguments.artifact_root)


def assemble(arguments: argparse.Namespace) -> None:
    evidence_files = [path.resolve() for path in arguments.evidence]
    values = [read_json(path) for path in evidence_files]
    for value in values:
        validate_evidence(value)
    targets = [value["target"] for value in values]
    platforms = [value["platform"] for value in values]
    if len(targets) != len(set(targets)):
        raise AssertionError("release manifest requires unique target evidence")
    sources = {json.dumps(value["source"], sort_keys=True) for value in values}
    resources = {value["resources"]["aggregate_sha256"] for value in values}
    if len(sources) != 1 or len(resources) != 1:
        raise AssertionError("release evidence does not bind one source and resource inventory")
    run_keys = ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_WORKFLOW_REF")
    run_identities = {
        tuple(value.get("runner", {}).get(key) for key in run_keys) for value in values
    }
    if len(run_identities) != 1 or None in next(iter(run_identities)):
        raise AssertionError("release evidence does not bind one complete workflow run")
    for value in values:
        runner = value.get("runner", {})
        if runner.get("RUNNER_OS") != RUNNER_OS_BY_PLATFORM[value["platform"]]:
            raise AssertionError("release evidence platform does not match its runner OS")
        if not runner.get("ImageOS") or not runner.get("ImageVersion"):
            raise AssertionError("release evidence is missing runner image identity")
    missing = sorted(set(arguments.require_platform) - set(platforms))
    if missing:
        raise AssertionError(f"required platform evidence is missing: {missing}")
    missing_targets = sorted(set(arguments.require_target) - set(targets))
    if missing_targets:
        raise AssertionError(f"required target evidence is missing: {missing_targets}")
    if arguments.artifact_root is not None:
        artifact_root = arguments.artifact_root.resolve()
        if not artifact_root.is_dir():
            raise AssertionError(f"artifact root is missing: {artifact_root}")
        for value in values:
            validate_downloaded_artifacts(value, artifact_root)
    records = []
    for path, value in sorted(zip(evidence_files, values), key=lambda pair: pair[1]["target"]):
        records.append(
            {
                "artifacts": value["artifacts"],
                "checks": value["checks"],
                "evidence_filename": path.name,
                "evidence_sha256": sha256(path),
                "platform": value["platform"],
                "target": value["target"],
            }
        )
    manifest = {
        "evidence": records,
        "resource_inventory_sha256": next(iter(resources)),
        "schema": MANIFEST_SCHEMA,
        "source": values[0]["source"],
    }
    write_json(arguments.output, manifest)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    subparsers = result.add_subparsers(dest="command", required=True)

    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--platform", required=True, choices=("macos", "windows", "linux"))
    record_parser.add_argument("--target", required=True)
    record_parser.add_argument("--bundle", type=parse_bundle, action="append", required=True)
    record_parser.add_argument("--check", action="append", required=True)
    record_parser.add_argument("--verification-json", type=Path, required=True)
    record_parser.add_argument("--source-root", type=Path, default=ROOT)
    record_parser.add_argument("--output", type=Path, required=True)
    record_parser.set_defaults(handler=record)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("evidence", type=Path)
    verify_parser.add_argument("--artifact-root", type=Path)
    verify_parser.set_defaults(handler=verify)

    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument("evidence", type=Path, nargs="+")
    assemble_parser.add_argument("--require-platform", action="append", default=[])
    assemble_parser.add_argument("--require-target", action="append", default=[])
    assemble_parser.add_argument("--artifact-root", type=Path)
    assemble_parser.add_argument("--output", type=Path, required=True)
    assemble_parser.set_defaults(handler=assemble)
    return result


def main() -> None:
    arguments = parser().parse_args()
    arguments.handler(arguments)


if __name__ == "__main__":
    main()

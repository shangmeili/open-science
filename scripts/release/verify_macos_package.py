#!/usr/bin/env python3
"""Verify one native AI4HEOR macOS DMG and its scientific resources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


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


def parse_process_table(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        parts = raw_line.strip().split(maxsplit=2)
        if len(parts) != 3:
            continue
        try:
            pid = int(parts[0])
            parent_pid = int(parts[1])
        except ValueError:
            continue
        rows.append({"pid": pid, "parent_pid": parent_pid, "command": parts[2]})
    return rows


def current_processes() -> list[dict[str, Any]]:
    completed = run(
        ["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True
    )
    return parse_process_table(completed.stdout)


def command_executable(command: str) -> str:
    return command.split(maxsplit=1)[0] if command else ""


def classify_first_launch_processes(
    rows: list[dict[str, Any]],
    main_executable: Path,
    opencode_executable: Path,
    launched_pid: int | None,
) -> dict[str, Any] | None:
    main = [
        row
        for row in rows
        if command_executable(str(row["command"])) == str(main_executable)
    ]
    opencode = [
        row
        for row in rows
        if command_executable(str(row["command"])) == str(opencode_executable)
    ]
    if (
        len(main) != 1
        or len(opencode) != 1
        or (launched_pid is not None and main[0]["pid"] != launched_pid)
    ):
        return None
    return {
        "app_executable": str(main_executable),
        "app_process_id": main[0]["pid"],
        "opencode_executable": str(opencode_executable),
        "opencode_parent_process_id": opencode[0]["parent_pid"],
        "opencode_process_id": opencode[0]["pid"],
    }


def matching_processes(rows: list[dict[str, Any]], executables: set[str]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if command_executable(str(row["command"])) in executables
    ]


def terminate_packaged_processes(
    executables: set[str], timeout_seconds: float = 10.0
) -> None:
    rows = matching_processes(current_processes(), executables)
    for row in rows:
        try:
            os.kill(row["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
    graceful_deadline = time.monotonic() + min(5.0, timeout_seconds)
    while time.monotonic() < graceful_deadline:
        if not matching_processes(current_processes(), executables):
            return
        time.sleep(0.2)
    for row in matching_processes(current_processes(), executables):
        try:
            os.kill(row["pid"], signal.SIGKILL)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not matching_processes(current_processes(), executables):
            return
        time.sleep(0.2)
    remaining = matching_processes(current_processes(), executables)
    if remaining:
        for row in remaining:
            try:
                os.kill(row["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
    raise AssertionError(f"first-launch cleanup left packaged processes running: {remaining}")


def launch_isolated_app(
    installed_app: Path,
    main_executable: Path,
    opencode_executable: Path,
    expected_arch: str,
    home: Path,
    workspace: Path,
    readiness: Callable[[], bool],
    label: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    temporary_dir = home / "tmp"
    for directory in (
        home / "Documents",
        home / "Library/Application Support",
        home / "Library/Caches",
        temporary_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(home),
            "TMPDIR": str(temporary_dir),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_STATE_HOME": str(home / ".local/state"),
        }
    )
    stdout_path = home.parent / f"{label}.stdout.log"
    stderr_path = home.parent / f"{label}.stderr.log"
    proof: dict[str, Any] | None = None
    executables = {str(main_executable), str(opencode_executable)}
    try:
        launch = [
            "open",
            "-F",
            "-n",
            "-g",
            "--arch",
            expected_arch,
            "--stdout",
            str(stdout_path),
            "--stderr",
            str(stderr_path),
        ]
        for name in (
            "HOME",
            "TMPDIR",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
        ):
            launch.extend(("--env", f"{name}={environment[name]}"))
        launch.append(str(installed_app))
        run(launch, cwd=home, env=environment, capture_output=True, text=True)
        deadline = time.monotonic() + timeout_seconds
        seen_main = False
        while time.monotonic() < deadline:
            processes = current_processes()
            main_rows = matching_processes(processes, {str(main_executable)})
            seen_main = seen_main or bool(main_rows)
            proof = classify_first_launch_processes(
                processes, main_executable, opencode_executable, None
            )
            if proof is not None and readiness():
                break
            if seen_main and not main_rows:
                stderr = (
                    stderr_path.read_text(encoding="utf-8", errors="replace")
                    if stderr_path.is_file()
                    else ""
                )
                raise AssertionError(
                    f"installed app exited before {label} readiness: {stderr[-2000:]}"
                )
            time.sleep(0.5)
        else:
            raise AssertionError(
                f"{label} did not reach one installed app process, one bundled "
                "OpenCode process, and the required workspace state before timeout"
            )
    except Exception as error:
        detail = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in (stdout_path, stderr_path)
            if path.is_file()
        )[-4000:]
        suffix = f"; app log tail: {detail}" if detail else ""
        raise AssertionError(f"{error}{suffix}") from error
    finally:
        terminate_packaged_processes(executables)

    if proof is None:
        raise AssertionError(f"{label} process proof was not captured")
    proof.update(
        {
            "cleanup_verified": True,
            "install_mode": "temporary-app-copy",
            "installed_app": str(installed_app),
            "launch_mode": "launch-services",
            "workspace": str(workspace),
        }
    )
    return proof


def verify_first_launch(
    source_app: Path, expected_arch: str, timeout_seconds: float = 60.0
) -> dict[str, Any]:
    host_arch = platform.machine()
    if host_arch != expected_arch:
        raise AssertionError(
            f"first-launch verification requires native {expected_arch} macOS; host is {host_arch}"
        )
    active_apps = [
        row
        for row in current_processes()
        if Path(command_executable(str(row["command"]))).name == "ai4s-workbench"
    ]
    if active_apps:
        raise AssertionError(
            f"first-launch verification requires no existing AI4HEOR process: {active_apps}"
        )

    with tempfile.TemporaryDirectory(prefix="ai4heor-macos-first-launch-") as temporary:
        # LaunchServices reports canonical executable paths (`/private/var/...` on
        # macOS) even when tempfile returned the `/var/...` alias. Resolve once so
        # readiness and cleanup compare the same exact path the process table uses.
        root = Path(temporary).resolve()
        installed_app = root / "Applications/AI4HEOR.app"
        installed_app.parent.mkdir(parents=True)
        run(["ditto", "--rsrc", "--extattr", str(source_app), str(installed_app)])
        main_executable = installed_app / "Contents/MacOS/ai4s-workbench"
        opencode_executable = installed_app / "Contents/MacOS/opencode"
        if not main_executable.is_file() or not opencode_executable.is_file():
            raise AssertionError("temporary app copy is missing required executables")

        fresh_home = root / "fresh-home"
        fresh_workspace = fresh_home / "Documents/AI4HEOR"
        if fresh_workspace.exists():
            raise AssertionError(
                f"isolated first-launch workspace already exists: {fresh_workspace}"
            )
        proof = launch_isolated_app(
            installed_app,
            main_executable,
            opencode_executable,
            expected_arch,
            fresh_home,
            fresh_workspace,
            fresh_workspace.is_dir,
            "first-launch",
            timeout_seconds,
        )

        migration_home = root / "migration-home"
        legacy_workspace = migration_home / "Documents/OpenScience"
        migrated_workspace = migration_home / "Documents/AI4HEOR"
        marker = Path("2026-07-17-legacy/marker.txt")
        (legacy_workspace / marker).parent.mkdir(parents=True)
        (legacy_workspace / marker).write_text("preserve-me\n", encoding="utf-8")
        migration = launch_isolated_app(
            installed_app,
            main_executable,
            opencode_executable,
            expected_arch,
            migration_home,
            migrated_workspace,
            lambda: (
                (migrated_workspace / marker).read_text(encoding="utf-8")
                == "preserve-me\n"
                and not legacy_workspace.exists()
            )
            if (migrated_workspace / marker).is_file()
            else False,
            "workspace-migration",
            timeout_seconds,
        )
        migration.update(
            {
                "legacy_workspace": str(legacy_workspace),
                "legacy_workspace_removed": True,
                "marker_preserved": str(marker),
            }
        )
        proof["workspace_migration"] = migration
        return proof


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


def combined_text(completed: Any) -> str:
    parts = []
    for value in (completed.stdout, completed.stderr):
        if isinstance(value, bytes):
            parts.append(value.decode("utf-8", errors="replace"))
        elif isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def run_checked(
    command: list[str], label: str, **kwargs: Any
) -> subprocess.CompletedProcess[Any]:
    try:
        return run(command, **kwargs)
    except subprocess.CalledProcessError as error:
        detail = combined_text(error).strip()
        suffix = f": {detail}" if detail else ""
        raise AssertionError(f"{label} failed{suffix}") from error


def parse_codesign_details(output: str) -> dict[str, Any]:
    details: dict[str, Any] = {"Authority": []}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("CodeDirectory "):
            details["CodeDirectory"] = line
            continue
        if line.startswith("Sealed Resources "):
            details["Sealed Resources"] = line
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "Authority":
            details["Authority"].append(value)
        else:
            details[key] = value
    return details


def validate_signature_details(
    details: dict[str, Any],
    label: str,
    *,
    require_runtime: bool,
    require_resources: bool,
) -> tuple[str, str]:
    authorities = details.get("Authority")
    if (
        not isinstance(authorities, list)
        or not authorities
        or not authorities[0].startswith("Developer ID Application:")
        or "Developer ID Certification Authority" not in authorities
        or "Apple Root CA" not in authorities
    ):
        raise AssertionError(f"{label} is not signed by a Developer ID Application chain")
    team = details.get("TeamIdentifier")
    if not isinstance(team, str) or re.fullmatch(r"[A-Z0-9]{10}", team) is None:
        raise AssertionError(f"{label} has no valid TeamIdentifier")
    if not authorities[0].endswith(f"({team})"):
        raise AssertionError(f"{label} Developer ID authority does not match TeamIdentifier")
    if (
        details.get("Signature") == "adhoc"
        or not details.get("Signature size")
        or not details.get("Timestamp")
    ):
        raise AssertionError(f"{label} lacks a non-ad-hoc signature with secure timestamp")
    code_directory = details.get("CodeDirectory", "")
    if require_runtime and "runtime" not in code_directory:
        raise AssertionError(f"{label} does not enable hardened runtime")
    if require_resources and not details.get("Sealed Resources"):
        raise AssertionError(f"{label} has no sealed resources")
    return team, authorities[0]


def validate_entitlements(payload: bytes, label: str) -> dict[str, Any]:
    xml_start = payload.find(b"<?xml")
    binary_start = payload.find(b"bplist00")
    starts = [offset for offset in (xml_start, binary_start) if offset >= 0]
    if not starts:
        return {}
    start = min(starts)
    candidate = payload[start:]
    if start == xml_start:
        closing = candidate.find(b"</plist>")
        if closing < 0:
            raise AssertionError(f"{label} has unterminated XML entitlements")
        candidate = candidate[: closing + len(b"</plist>")]
    try:
        entitlements = plistlib.loads(candidate)
    except Exception as error:
        raise AssertionError(f"{label} has malformed entitlements: {error}") from error
    if not isinstance(entitlements, dict):
        raise AssertionError(f"{label} entitlements are not a dictionary")
    if entitlements.get("com.apple.security.get-task-allow") is True:
        raise AssertionError(f"{label} enables forbidden get-task-allow entitlement")
    return entitlements


def codesign_details(path: Path) -> dict[str, Any]:
    completed = run_checked(
        ["codesign", "-dv", "--verbose=4", str(path)],
        f"codesign details for {path}",
        capture_output=True,
        text=True,
    )
    return parse_codesign_details(combined_text(completed))


def codesign_entitlements(path: Path, label: str) -> dict[str, Any]:
    completed = run_checked(
        ["codesign", "-d", "--entitlements", ":-", str(path)],
        f"entitlement inspection for {label}",
        capture_output=True,
    )
    payload = b""
    for value in (completed.stdout, completed.stderr):
        if isinstance(value, bytes):
            payload += value + b"\n"
        elif isinstance(value, str):
            payload += value.encode("utf-8") + b"\n"
    return validate_entitlements(payload, label)


def verify_distribution_trust(app: Path, expected_team_id: str) -> dict[str, Any]:
    run_checked(
        ["codesign", "--verify", "--deep", "--strict", "--verbose=4", str(app)],
        f"strict app signature verification for {app.name}",
        capture_output=True,
        text=True,
    )
    app_details = codesign_details(app)
    team, authority = validate_signature_details(
        app_details,
        app.name,
        require_runtime=True,
        require_resources=True,
    )
    if team != expected_team_id:
        raise AssertionError(
            f"{app.name} TeamIdentifier {team} does not match expected Apple team"
        )
    codesign_entitlements(app, app.name)

    macho_files: list[tuple[Path, str]] = []
    for path in sorted(app.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        classification = run_checked(
            ["file", "-b", str(path)],
            f"file classification for {path}",
            capture_output=True,
            text=True,
        ).stdout.strip()
        if classification.startswith("Mach-O"):
            macho_files.append((path, classification))
    required = {
        (app / "Contents/MacOS" / name).resolve()
        for name in ("ai4s-workbench", "opencode", "uv")
    }
    present = {path.resolve() for path, _ in macho_files}
    if not required.issubset(present):
        raise AssertionError("signed app is missing one or more required Mach-O payloads")

    for path, classification in macho_files:
        label = str(path.relative_to(app))
        run_checked(
            ["codesign", "--verify", "--strict", "--verbose=4", str(path)],
            f"strict nested signature verification for {label}",
            capture_output=True,
            text=True,
        )
        details = codesign_details(path)
        nested_team, nested_authority = validate_signature_details(
            details,
            label,
            require_runtime="executable" in classification,
            require_resources=False,
        )
        if nested_team != team or nested_authority != authority:
            raise AssertionError(f"{label} does not share the app Developer ID identity")
        codesign_entitlements(path, label)

    run_checked(
        ["xcrun", "stapler", "validate", str(app)],
        "stapled notarization ticket validation",
        capture_output=True,
        text=True,
    )
    gatekeeper = run_checked(
        ["spctl", "--assess", "--type", "execute", "--verbose=4", str(app)],
        "Gatekeeper assessment",
        capture_output=True,
        text=True,
    )
    gatekeeper_output = combined_text(gatekeeper)
    if "source=Notarized Developer ID" not in gatekeeper_output:
        raise AssertionError(
            "Gatekeeper did not report acceptance from Notarized Developer ID"
        )
    return {
        "developer_id": authority,
        "gatekeeper": "accepted",
        "hardened_runtime": True,
        "mach_o_files": len(macho_files),
        "notarization_ticket": "stapled",
        "sealed_resources": True,
        "secure_timestamp": True,
        "team_identifier": team,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--target", choices=tuple(TARGET_ARCH), required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--verification-json", type=Path, required=True)
    parser.add_argument("--verify-first-launch", action="store_true")
    parser.add_argument("--require-distribution-trust", action="store_true")
    parser.add_argument("--expected-team-id")
    arguments = parser.parse_args()
    if sys.platform != "darwin":
        raise AssertionError("macOS package verification must run on macOS")
    tools = ["hdiutil", "lipo"]
    if arguments.verify_first_launch:
        tools.extend(("ditto", "ps"))
    if arguments.require_distribution_trust:
        if re.fullmatch(r"[A-Z0-9]{10}", arguments.expected_team_id or "") is None:
            raise AssertionError(
                "--require-distribution-trust also requires a valid --expected-team-id"
            )
        tools.extend(("codesign", "file", "spctl", "xcrun"))
    elif arguments.expected_team_id is not None:
        raise AssertionError("--expected-team-id is only valid for distribution trust")
    for tool in tools:
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
        first_launch = (
            verify_first_launch(app, expected_arch)
            if arguments.verify_first_launch
            else None
        )
        distribution = (
            verify_distribution_trust(app, arguments.expected_team_id)
            if arguments.require_distribution_trust
            else None
        )
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
        if distribution is not None:
            verification["distribution"] = distribution
        if first_launch is not None:
            verification["first_launch"] = first_launch
        arguments.verification_json.parent.mkdir(parents=True, exist_ok=True)
        arguments.verification_json.write_text(
            json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            "Verified AI4HEOR macOS package: "
            f"dmg_sha256={sha256(dmg)}, target={arguments.target}, "
            f"resource_files={resource_count}, first_launch={first_launch is not None}"
        )
    finally:
        if device is not None:
            run(["hdiutil", "detach", device], capture_output=True, text=True)


if __name__ == "__main__":
    main()

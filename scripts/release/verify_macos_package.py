#!/usr/bin/env python3
"""Verify one native AI4HEOR macOS DMG and its scientific resources."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
import platform
import plistlib
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator


ROOT = Path(__file__).resolve().parents[2]
MACOS_ACCESSIBILITY_PROBE = Path(__file__).with_name(
    "verify_macos_accessibility.swift"
)
INSTALLED_TASK_UI_PROOF_KEYS = {
    "window_visible",
    "new_task_navigation",
    "composer_editable",
    "task_files_navigation_available",
    "skills_navigation_available",
}
INSTALLED_TASK_REPLY_PROOF_KEYS = {
    "new_task_conversation_created",
    "prompt_submitted",
    "assistant_reply_visible",
}
INSTALLED_TASK_REPLY_PROMPT = (
    "AI4HEOR installed application reply-chain smoke. Return the fixture marker."
)
TARGET_ARCH = {
    "aarch64-apple-darwin": ("arm64", "aarch64"),
    "x86_64-apple-darwin": ("x86_64", "x64"),
}
FRONTEND_BOOTSTRAP_START = re.compile(
    r"^\d+ bootstrap: starting bundled runtime$", re.MULTILINE
)
FRONTEND_BOOTSTRAP_READY = re.compile(
    r"^\d+ bootstrap: runtime at http://127\.0\.0\.1:(\d+)$", re.MULTILINE
)


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


def verify_binaries(
    app: Path,
    expected_arch: str,
    target: str,
    source_root: Path,
) -> dict[str, str]:
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
    if platform.machine() == expected_arch:
        versions = {
            "opencode": binary_version(binaries["opencode"]),
            "uv": binary_version(binaries["uv"]),
            "verification": "executed_on_matching_architecture",
        }
    else:
        source_binaries = {
            "opencode": source_root / f"apps/desktop/src-tauri/binaries/opencode-{target}",
            "uv": source_root / f"apps/desktop/src-tauri/binaries/uv-{target}",
        }
        for name, source in source_binaries.items():
            if not source.is_file() or source.is_symlink():
                raise AssertionError(f"reviewed {name} sidecar is missing or linked: {source}")
            if sha256(source) != sha256(binaries[name]):
                raise AssertionError(f"packaged {name} differs from the reviewed target sidecar")
        versions = {
            "opencode": "1.17.13-ai4heor.2",
            "uv": "0.11.26",
            "verification": "static_sha256_against_reviewed_target_sidecars",
        }
    if "1.17.13-ai4heor.2" not in versions["opencode"]:
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
            "-B",
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


def opencode_server_port(command: str) -> int | None:
    try:
        arguments = shlex.split(command)
    except ValueError:
        return None
    for index, argument in enumerate(arguments[:-1]):
        if argument != "--port":
            continue
        try:
            port = int(arguments[index + 1])
        except ValueError:
            return None
        return port if 1 <= port <= 65535 else None
    return None


def probe_authenticated_opencode_http(
    port: int, timeout_seconds: float = 1.0
) -> dict[str, Any] | None:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout_seconds)
    try:
        connection.request("GET", "/global/health")
        response = connection.getresponse()
        response.read(1024)
        if response.status != 401:
            return None
        return {
            "authentication_enforced": True,
            "path": "/global/health",
            "unauthenticated_status": 401,
        }
    except (OSError, http.client.HTTPException):
        return None
    finally:
        connection.close()


def frontend_bootstrap_proof(log_path: Path) -> dict[str, bool] | None:
    """Return bounded proof that the installed webview reached Tauri runtime IPC."""

    if not log_path.is_file() or log_path.is_symlink():
        return None
    with log_path.open("rb") as handle:
        handle.seek(max(0, log_path.stat().st_size - 65536))
        text = handle.read(65536).decode("utf-8", errors="replace")
    ready = FRONTEND_BOOTSTRAP_READY.search(text)
    if FRONTEND_BOOTSTRAP_START.search(text) is None or ready is None:
        return None
    port = int(ready.group(1))
    if not 1 <= port <= 65535:
        return None
    return {
        "app_shell_mounted": True,
        "javascript_executed": True,
        "tauri_runtime_command_returned": True,
    }


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
    frontend_log: Path,
    workspace: Path,
    readiness: Callable[[], bool],
    label: str,
    timeout_seconds: float,
    verify_task_ui: bool = False,
    task_reply_verifier: Callable[[int], dict[str, bool]] | None = None,
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
        if frontend_log.exists():
            raise AssertionError(
                f"isolated frontend bootstrap log already exists: {frontend_log}"
            )
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
            if proof is not None:
                opencode_rows = [
                    row
                    for row in processes
                    if row["pid"] == proof["opencode_process_id"]
                ]
                port = (
                    opencode_server_port(str(opencode_rows[0]["command"]))
                    if len(opencode_rows) == 1
                    else None
                )
                opencode_http = (
                    probe_authenticated_opencode_http(port)
                    if port is not None
                    else None
                )
                frontend_bootstrap = frontend_bootstrap_proof(frontend_log)
                if (
                    opencode_http is not None
                    and frontend_bootstrap is not None
                    and readiness()
                ):
                    proof["opencode_http"] = opencode_http
                    proof["frontend_bootstrap"] = frontend_bootstrap
                    if verify_task_ui:
                        proof["installed_task_ui"] = verify_installed_task_ui(
                            proof["app_process_id"]
                        )
                    if task_reply_verifier is not None:
                        proof["installed_task_reply"] = task_reply_verifier(
                            proof["app_process_id"]
                        )
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
                "OpenCode process with authenticated HTTP readiness, frontend bootstrap "
                "through Tauri IPC, and the required workspace state before timeout"
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


def verify_installed_task_ui(process_id: int) -> dict[str, bool]:
    if not isinstance(process_id, int) or process_id < 1:
        raise AssertionError("installed task UI verification requires a process id")
    if (
        not MACOS_ACCESSIBILITY_PROBE.is_file()
        or MACOS_ACCESSIBILITY_PROBE.is_symlink()
    ):
        raise AssertionError("installed task UI Accessibility probe is unavailable")
    completed = subprocess.run(
        ["swift", str(MACOS_ACCESSIBILITY_PROBE), str(process_id)],
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2000:]
        raise AssertionError(f"installed task UI verification failed: {detail}")
    try:
        proof = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError("installed task UI proof is not valid JSON") from error
    if (
        not isinstance(proof, dict)
        or set(proof) != INSTALLED_TASK_UI_PROOF_KEYS
        or any(value is not True for value in proof.values())
    ):
        raise AssertionError("installed task UI proof is incomplete or unbounded")
    return proof


def verify_installed_task_reply(
    process_id: int, prompt: str, response_marker: str
) -> dict[str, bool]:
    if not isinstance(process_id, int) or process_id < 1:
        raise AssertionError("installed task reply verification requires a process id")
    if not prompt or not response_marker:
        raise AssertionError("installed task reply verification requires bounded fixture text")
    completed = subprocess.run(
        [
            "swift",
            str(MACOS_ACCESSIBILITY_PROBE),
            str(process_id),
            prompt,
            response_marker,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2000:]
        raise AssertionError(f"installed task reply verification failed: {detail}")
    try:
        proof = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError("installed task reply proof is not valid JSON") from error
    if (
        not isinstance(proof, dict)
        or set(proof) != INSTALLED_TASK_REPLY_PROOF_KEYS
        or any(value is not True for value in proof.values())
    ):
        raise AssertionError("installed task reply proof is incomplete or unbounded")
    return proof


def prepare_installed_task_reply_runtime(
    home: Path,
    bundle_identifier: str,
    provider_url: str,
    provider_id: str,
    model_id: str,
    credential: str,
) -> None:
    runtime_root = (
        home
        / "Library/Application Support"
        / bundle_identifier
        / "runtime"
    )
    config = runtime_root / "xdg-config/opencode/opencode.json"
    auth = runtime_root / "xdg-data/opencode/auth.json"
    config.parent.mkdir(parents=True, mode=0o700)
    auth.parent.mkdir(parents=True, mode=0o700)
    config.write_text(
        json.dumps(
            {
                "provider": {
                    provider_id: {
                        "name": "AI4HEOR local installed-app fixture",
                        "npm": "@ai-sdk/anthropic",
                        "options": {"baseURL": provider_url},
                        "models": {model_id: {"name": model_id}},
                    }
                },
                "model": f"{provider_id}/{model_id}",
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    auth.write_text(
        json.dumps(
            {provider_id: {"type": "api", "key": credential}},
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    for private in (runtime_root, config.parent, auth.parent):
        private.chmod(0o700)
    config.chmod(0o600)
    auth.chmod(0o600)


@contextmanager
def local_installed_task_reply_fixture() -> Iterator[tuple[Any, str, str, str, str, str]]:
    import verify_packaged_opencode_fixture as fixture

    state = fixture.FixtureState()
    provider = ThreadingHTTPServer(("127.0.0.1", 0), fixture.handler(state))
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    try:
        url = f"http://127.0.0.1:{provider.server_address[1]}/anthropic/v1"
        yield (
            state,
            url,
            fixture.PROVIDER_ID,
            fixture.MODEL_ID,
            fixture.CREDENTIAL,
            fixture.MARKER,
        )
    finally:
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=5)


def single_instance_socket_path(bundle_identifier: str) -> Path:
    safe_identifier = bundle_identifier.replace(".", "_").replace("-", "_")
    return Path("/tmp") / f"{safe_identifier}_si.sock"


@contextmanager
def isolate_single_instance_socket(socket_path: Path) -> Iterator[bool]:
    """Temporarily reserve the product socket for an exact-path test copy.

    Renaming a Unix-domain socket preserves the running listener. The installed
    app therefore keeps running while the temporary candidate owns the canonical
    path. The original socket is restored byte-for-byte by rename in `finally`.
    """

    if not socket_path.exists():
        yield False
        return
    if not stat.S_ISSOCK(socket_path.lstat().st_mode):
        raise AssertionError(f"single-instance path is not a socket: {socket_path}")
    backup = socket_path.with_name(
        f"{socket_path.name}.verification-{os.getpid()}-{time.time_ns()}"
    )
    os.replace(socket_path, backup)
    try:
        yield True
    finally:
        unexpected: Path | None = None
        if socket_path.exists():
            if stat.S_ISSOCK(socket_path.lstat().st_mode):
                socket_path.unlink()
            else:
                unexpected = backup.with_name(f"{backup.name}.unexpected")
                os.replace(socket_path, unexpected)
        if not backup.exists():
            raise AssertionError(
                "original single-instance socket disappeared during verification"
            )
        os.replace(backup, socket_path)
        if unexpected is not None:
            raise AssertionError(
                "verification preserved an unexpected non-socket single-instance path at "
                f"{unexpected}"
            )


def _verify_first_launch_workspaces(
    source_app: Path,
    expected_arch: str,
    bundle_identifier: str,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    host_arch = platform.machine()
    if host_arch != expected_arch:
        raise AssertionError(
            f"first-launch verification requires native {expected_arch} macOS; host is {host_arch}"
        )
    with tempfile.TemporaryDirectory(prefix="ai4heor-macos-first-launch-") as temporary:
        # LaunchServices reports canonical executable paths (`/private/var/...` on
        # macOS) even when tempfile returned the `/var/...` alias. Resolve once so
        # readiness and cleanup compare the same exact path the process table uses.
        # An already installed AI4HEOR may keep running: process proof and cleanup
        # are both scoped to this temporary app copy's two exact executable paths.
        root = Path(temporary).resolve()
        installed_app = root / "Applications/AI4HEOR.app"
        installed_app.parent.mkdir(parents=True)
        run(["ditto", "--rsrc", "--extattr", str(source_app), str(installed_app)])
        main_executable = installed_app / "Contents/MacOS/ai4s-workbench"
        opencode_executable = installed_app / "Contents/MacOS/opencode"
        if not main_executable.is_file() or not opencode_executable.is_file():
            raise AssertionError("temporary app copy is missing required executables")

        fresh_home = root / "fresh-home"
        fresh_frontend_log = (
            fresh_home / "Library/Application Support" / bundle_identifier / "debug.log"
        )
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
            fresh_frontend_log,
            fresh_workspace,
            fresh_workspace.is_dir,
            "first-launch",
            timeout_seconds,
            verify_task_ui=True,
        )

        coexistence_home = root / "coexistence-home"
        coexistence_frontend_log = (
            coexistence_home
            / "Library/Application Support"
            / bundle_identifier
            / "debug.log"
        )
        open_science_workspace = coexistence_home / "Documents/OpenScience"
        ai4heor_workspace = coexistence_home / "Documents/AI4HEOR"
        marker = Path("2026-07-17-open-science/marker.txt")
        (open_science_workspace / marker).parent.mkdir(parents=True)
        (open_science_workspace / marker).write_text("preserve-me\n", encoding="utf-8")
        isolation = launch_isolated_app(
            installed_app,
            main_executable,
            opencode_executable,
            expected_arch,
            coexistence_home,
            coexistence_frontend_log,
            ai4heor_workspace,
            lambda: (
                (open_science_workspace / marker).read_text(encoding="utf-8")
                == "preserve-me\n"
                and open_science_workspace.is_dir()
                and ai4heor_workspace.is_dir()
            )
            if (open_science_workspace / marker).is_file()
            else False,
            "workspace-isolation",
            timeout_seconds,
        )
        isolation.update(
            {
                "open_science_workspace": str(open_science_workspace),
                "open_science_workspace_preserved": True,
                "marker_preserved": str(marker),
            }
        )
        proof["workspace_isolation"] = isolation

        with local_installed_task_reply_fixture() as fixture:
            (
                fixture_state,
                provider_url,
                provider_id,
                model_id,
                credential,
                response_marker,
            ) = fixture
            reply_home = root / "task-reply-home"
            prepare_installed_task_reply_runtime(
                reply_home,
                bundle_identifier,
                provider_url,
                provider_id,
                model_id,
                credential,
            )
            reply_frontend_log = (
                reply_home
                / "Library/Application Support"
                / bundle_identifier
                / "debug.log"
            )
            reply_workspace = reply_home / "Documents/AI4HEOR"
            reply_launch = launch_isolated_app(
                installed_app,
                main_executable,
                opencode_executable,
                expected_arch,
                reply_home,
                reply_frontend_log,
                reply_workspace,
                reply_workspace.is_dir,
                "installed-task-reply",
                timeout_seconds,
                task_reply_verifier=lambda process_id: verify_installed_task_reply(
                    process_id,
                    INSTALLED_TASK_REPLY_PROMPT,
                    response_marker,
                ),
            )
            reply_proof = reply_launch.get("installed_task_reply")
            if not isinstance(reply_proof, dict):
                raise AssertionError("installed task reply proof was not captured")
            with fixture_state.lock:
                provider_request_received = fixture_state.message_requests > 0
            if not provider_request_received:
                raise AssertionError(
                    "installed task reply did not reach the local fixture provider"
                )
            proof["installed_task_reply"] = {
                **reply_proof,
                "provider_request_received": True,
            }
        return proof


def verify_first_launch(
    source_app: Path, expected_arch: str, timeout_seconds: float = 60.0
) -> dict[str, Any]:
    with (source_app / "Contents/Info.plist").open("rb") as handle:
        bundle_identifier = plistlib.load(handle).get("CFBundleIdentifier")
    if not isinstance(bundle_identifier, str) or not bundle_identifier:
        raise AssertionError("first-launch verification requires a bundle identifier")
    socket_path = single_instance_socket_path(bundle_identifier)
    with isolate_single_instance_socket(socket_path) as isolated_existing_socket:
        proof = _verify_first_launch_workspaces(
            source_app, expected_arch, bundle_identifier, timeout_seconds
        )
    proof["existing_single_instance_socket_isolated"] = isolated_existing_socket
    return proof


def verify_info(app: Path, expected_version: str) -> dict[str, str]:
    with (app / "Contents/Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    expected = {
        "CFBundleDisplayName": "AI4HEOR",
        "CFBundleExecutable": "ai4s-workbench",
        "CFBundleIdentifier": "com.ai4s.ai4heor",
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
        tools.extend(("ditto", "ps", "swift"))
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
        versions = verify_binaries(app, expected_arch, arguments.target, source_root)
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
                "sidecar_version_verification": versions["verification"],
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

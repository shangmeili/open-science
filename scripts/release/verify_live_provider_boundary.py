#!/usr/bin/env python3
"""Verify one real model turn without exporting or retaining its credential.

This macOS-only release harness reads an already-authorized credential from the
user's Keychain, starts the OpenCode binary from an exact DMG in an isolated
profile, and uses the same HTTP boundaries as the desktop app:

* provider metadata -> PATCH /global/config
* provider credential -> PUT /auth/:provider

Only fixed booleans, versions, counts, and artifact hashes are reported. Raw
provider responses, log lines, paths inside the temporary profile, and secret
values are never printed or written to the verification record.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import plistlib
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "ai4heor-live-provider-verification/v1"
DEFAULT_PROVIDER_ID = "minimax-cn-token-plan"
DEFAULT_PROVIDER_NAME = "MiniMax China Token Plan"
DEFAULT_NPM = "@ai-sdk/anthropic"
DEFAULT_BASE_URL = "https://api.minimaxi.com/anthropic/v1"
DEFAULT_MODEL = "MiniMax-M3"
DEFAULT_MARKER = "AI4HEOR_MINIMAX_LIVE_OK"

SAFE_FAILURE_PATTERNS = (
    ("authentication_failed", (b"unauthorized", b"invalid api key", b"authentication", b"status=401", b" 401")),
    ("quota_or_rate_limit", (b"rate limit", b"too many requests", b"insufficient balance", b"quota", b"status=429", b" 429")),
    ("model_unavailable", (b"model not found", b"unknown model", b"unsupported model")),
    ("provider_unavailable", (b"service unavailable", b"bad gateway", b"gateway timeout", b"status=502", b"status=503", b"status=504")),
    ("adapter_load_failed", (b"cannot find package", b"module not found", b"failed to load provider")),
    ("network_timeout", (b"timed out", b"timeout", b"fetch failed", b"connection reset")),
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
        raise AssertionError(f"required macOS live-provider tool is missing: {name}")


def mount_dmg(dmg: Path) -> tuple[str, Path]:
    completed = run(
        ["hdiutil", "attach", "-readonly", "-nobrowse", "-plist", str(dmg)],
        capture_output=True,
    )
    payload = plistlib.loads(completed.stdout)
    mounts = [
        entity
        for entity in payload.get("system-entities", [])
        if entity.get("mount-point")
    ]
    if len(mounts) != 1:
        raise AssertionError("the DMG did not produce exactly one mounted volume")
    device = mounts[0].get("dev-entry")
    if not isinstance(device, str) or not device:
        raise AssertionError("the mounted DMG did not report a device")
    return device, Path(mounts[0]["mount-point"])


def detach_dmg(device: str) -> None:
    run(["hdiutil", "detach", device], capture_output=True)


def keychain_credential(service: str, account: str) -> bytes:
    completed = run(
        [
            "security",
            "find-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
        ],
        capture_output=True,
    )
    credential = completed.stdout.strip()
    if not credential:
        raise AssertionError("the selected macOS Keychain item is empty")
    return credential


def provider_catalog_probe(base_url: str, model: str, credential: bytes) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/models",
        headers={"X-Api-Key": credential.decode("utf-8")},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30.0) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise AssertionError(
            f"the provider catalog rejected the Keychain credential (HTTP {error.code})"
        ) from None
    except urllib.error.URLError:
        raise AssertionError("the provider catalog could not be reached") from None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise AssertionError("the provider catalog returned a non-JSON response") from None
    rows = payload.get("data") if isinstance(payload, dict) else None
    identifiers = {
        row.get("id")
        for row in rows or []
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    if model not in identifiers:
        raise AssertionError("the configured model is absent from the provider catalog")
    return {"catalog_reachable": True, "credential_accepted": True, "model_listed": True}


def private_child_setup() -> None:
    os.umask(0o077)
    os.setsid()


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def http_json(
    base_url: str,
    auth_header: str,
    method: str,
    path: str,
    body: Any | None = None,
    timeout: float = 30.0,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Authorization": auth_header}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        # Never echo the provider/server body: it can include request details.
        raise AssertionError(f"{method} {path} returned HTTP {error.code}") from None
    except urllib.error.URLError:
        raise AssertionError(f"{method} {path} could not reach the isolated runtime") from None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise AssertionError(f"{method} {path} returned a non-JSON response") from None


def wait_for_runtime(base_url: str, auth_header: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            http_json(base_url, auth_header, "GET", "/global/config", timeout=2.0)
            return
        except AssertionError:
            time.sleep(0.2)
    raise AssertionError("the isolated packaged OpenCode runtime did not become ready")


def wait_for_workspace_provider(
    base_url: str,
    auth_header: str,
    directory: Path,
    provider_id: str,
    model: str,
    timeout: float = 30.0,
) -> None:
    query = urllib.parse.quote(str(directory), safe="")
    expected_model = f"{provider_id}/{model}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            config = http_json(
                base_url, auth_header, "GET", f"/config?directory={query}", timeout=3.0
            )
            providers = http_json(
                base_url,
                auth_header,
                "GET",
                f"/config/providers?directory={query}",
                timeout=3.0,
            )
            rows = providers.get("providers") if isinstance(providers, dict) else None
            provider = next(
                (
                    row
                    for row in rows or []
                    if isinstance(row, dict) and row.get("id") == provider_id
                ),
                None,
            )
            models = provider.get("models") if isinstance(provider, dict) else None
            if (
                isinstance(config, dict)
                and config.get("model") == expected_model
                and isinstance(models, dict)
                and model in models
            ):
                return
        except AssertionError:
            pass
        time.sleep(0.25)
    raise AssertionError(
        "the rebuilt workspace instance did not expose the configured provider and model"
    )


class EventStream:
    """Keep the workspace instance/event path alive without exposing frames."""

    def __init__(
        self,
        base_url: str,
        auth_header: str,
        directory: Path,
        timeout: float,
    ) -> None:
        self.url = (
            f"{base_url}/event?directory="
            f"{urllib.parse.quote(str(directory), safe='')}"
        )
        self.auth_header = auth_header
        self.timeout = timeout
        self.ready = threading.Event()
        self.finished = threading.Event()
        self.response: Any | None = None
        self.material = bytearray()
        self.error_category = "no_assistant_completion"
        self.thread = threading.Thread(target=self._read, daemon=True)

    def _read(self) -> None:
        request = urllib.request.Request(
            self.url,
            headers={"Accept": "text/event-stream", "Authorization": self.auth_header},
        )
        try:
            self.response = urllib.request.urlopen(request, timeout=self.timeout)
            self.ready.set()
            while True:
                line = self.response.readline()
                if not line:
                    break
                if len(self.material) < 256 * 1024:
                    self.material.extend(line[: 256 * 1024 - len(self.material)])
        except (AttributeError, OSError, ValueError, urllib.error.URLError):
            self.error_category = "event_stream_closed"
        finally:
            self.ready.set()
            self.finished.set()

    def start(self) -> None:
        self.thread.start()
        if not self.ready.wait(timeout=10.0) or self.response is None:
            raise AssertionError("the workspace event stream did not become ready")

    def close(self) -> None:
        if self.response is not None:
            self.response.close()
        self.finished.wait(timeout=5.0)


def assistant_text(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    chunks: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        info = message.get("info")
        if not isinstance(info, dict) or info.get("role") != "assistant":
            continue
        parts = message.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if (
                isinstance(part, dict)
                and part.get("type") == "text"
                and isinstance(part.get("text"), str)
            ):
                chunks.append(part["text"])
    return "\n".join(chunks)


def classify_failure(material: bytes, credential: bytes) -> str:
    lowered = material.replace(credential, b"[redacted]").lower()
    for category, patterns in SAFE_FAILURE_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            return category
    return "no_assistant_completion"


def credential_hit_paths(roots: Iterable[Path], credential: bytes) -> list[Path]:
    hits: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if path.is_symlink() or not path.is_file():
                continue
            try:
                if credential in path.read_bytes():
                    hits.append(path.resolve())
            except OSError:
                continue
    return sorted(set(hits))


def tracked_credential_hits(source_root: Path, credential: bytes) -> int:
    completed = run(
        ["git", "ls-files", "-z"],
        cwd=source_root,
        capture_output=True,
    )
    hits = 0
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        path = source_root / os.fsdecode(raw)
        try:
            if path.is_file() and credential in path.read_bytes():
                hits += 1
        except OSError:
            continue
    return hits


def credential_boundary(
    hits: list[Path], expected_auth_file: Path, data_root: Path
) -> dict[str, Any]:
    expected = expected_auth_file.resolve()
    exact_auth_file_only = hits == [expected]
    auth_file_mode = stat.S_IMODE(expected_auth_file.stat().st_mode)
    data_root_mode = stat.S_IMODE(data_root.stat().st_mode)
    if not exact_auth_file_only:
        raise AssertionError(
            "the provider credential was persisted outside the isolated auth file"
        )
    if auth_file_mode & 0o077 and data_root_mode & 0o077:
        raise AssertionError("the isolated credential path is readable outside its owner")
    return {
        "credential_hits": 1,
        "credential_location": "isolated_auth_json_only",
        "auth_file_owner_only": auth_file_mode & 0o077 == 0,
        "data_root_owner_only": data_root_mode & 0o077 == 0,
    }


def write_verification(path: Path, proof: dict[str, Any], credential: bytes) -> None:
    encoded = (json.dumps(proof, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if credential in encoded:
        raise AssertionError("the verification record contains the provider credential")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def stop_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def verify_live_provider(args: argparse.Namespace) -> dict[str, Any]:
    if os.uname().sysname != "Darwin":
        raise AssertionError("live-provider DMG verification requires macOS")
    for tool in ("hdiutil", "security", "git"):
        require_tool(tool)
    dmg = args.dmg.resolve()
    source_root = args.source_root.resolve()
    if not dmg.is_file():
        raise AssertionError("the requested DMG does not exist")

    credential = keychain_credential(args.keychain_service, args.keychain_account)
    if tracked_credential_hits(source_root, credential):
        raise AssertionError("the provider credential exists in a tracked source file")
    provider_preflight = provider_catalog_probe(args.base_url, args.model, credential)

    with tempfile.TemporaryDirectory(
        prefix="ai4heor-live-provider-", dir="/private/tmp"
    ) as temporary:
        root = Path(temporary)
        for name in ("bin", "home", "config", "data", "cache", "state", "work"):
            directory = root / name
            directory.mkdir(mode=0o700)
            directory.chmod(0o700)

        device = ""
        try:
            device, mount = mount_dmg(dmg)
            app = mount / "AI4HEOR.app"
            with (app / "Contents/Info.plist").open("rb") as handle:
                info = plistlib.load(handle)
            version = info.get("CFBundleShortVersionString")
            if version != args.expected_version:
                raise AssertionError(
                    f"expected AI4HEOR {args.expected_version}, found {version}"
                )
            packaged = app / "Contents/MacOS/opencode"
            if not packaged.is_file() or packaged.is_symlink():
                raise AssertionError("the packaged OpenCode binary is missing or linked")
            binary = root / "bin/opencode"
            shutil.copy2(packaged, binary)
            binary.chmod(0o700)
        finally:
            if device:
                detach_dmg(device)

        version_result = run([str(binary), "--version"], capture_output=True, text=True)
        opencode_version = (version_result.stdout or version_result.stderr).strip()
        port = free_local_port()
        password = secrets.token_urlsafe(24)
        auth_token = base64.b64encode(f"opencode:{password}".encode()).decode()
        auth_header = f"Basic {auth_token}"
        base_url = f"http://127.0.0.1:{port}"
        environment = os.environ.copy()
        environment.update(
            {
                "HOME": str(root / "home"),
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_DATA_HOME": str(root / "data"),
                "XDG_CACHE_HOME": str(root / "cache"),
                "XDG_STATE_HOME": str(root / "state"),
                "OPENCODE_SERVER_PASSWORD": password,
                "OPENCODE_DISABLE_AUTOUPDATE": "1",
                "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
                "OPENCODE_DISABLE_PRUNE": "1",
                "NO_COLOR": "1",
            }
        )
        stdout_path = root / "runtime.stdout"
        stderr_path = root / "runtime.stderr"
        auth_saved = False
        process: subprocess.Popen[Any] | None = None
        event_stream: EventStream | None = None
        proof: dict[str, Any] = {}
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(
                    [
                        str(binary),
                        "serve",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    cwd=root / "work",
                    env=environment,
                    stdout=stdout,
                    stderr=stderr,
                    preexec_fn=private_child_setup,
                )
            wait_for_runtime(base_url, auth_header)

            provider = {
                args.provider_id: {
                    "name": args.provider_name,
                    "npm": args.npm,
                    "options": {"baseURL": args.base_url},
                    "models": {args.model: {"name": args.model}},
                }
            }
            http_json(
                base_url,
                auth_header,
                "PATCH",
                "/global/config",
                {"provider": provider},
            )
            http_json(
                base_url,
                auth_header,
                "PUT",
                f"/auth/{urllib.parse.quote(args.provider_id, safe='')}",
                {"type": "api", "key": credential.decode("utf-8")},
            )
            auth_saved = True
            http_json(base_url, auth_header, "POST", "/instance/dispose", {})
            http_json(
                base_url,
                auth_header,
                "PATCH",
                "/global/config",
                {"model": f"{args.provider_id}/{args.model}"},
            )
            config_response = http_json(
                base_url, auth_header, "GET", "/global/config"
            )
            if credential in json.dumps(config_response).encode("utf-8"):
                raise AssertionError("the global provider config contains the credential")
            if not isinstance(config_response, dict) or config_response.get("model") != (
                f"{args.provider_id}/{args.model}"
            ):
                raise AssertionError("the global provider config did not retain the selected model")

            wait_for_workspace_provider(
                base_url,
                auth_header,
                root / "work",
                args.provider_id,
                args.model,
            )

            event_stream = EventStream(
                base_url,
                auth_header,
                root / "work",
                args.turn_timeout + 30.0,
            )
            event_stream.start()

            auth_file = root / "data/opencode/auth.json"
            deadline = time.monotonic() + 10
            while not auth_file.is_file() and time.monotonic() < deadline:
                time.sleep(0.1)
            if not auth_file.is_file():
                raise AssertionError("the isolated auth file was not created")
            persistence = credential_boundary(
                credential_hit_paths(
                    [
                        root / "config",
                        root / "data",
                        root / "cache",
                        root / "state",
                        root / "work",
                        stdout_path,
                        stderr_path,
                    ],
                    credential,
                ),
                auth_file,
                root / "data",
            )

            directory = urllib.parse.quote(str(root / "work"), safe="")
            session = http_json(
                base_url,
                auth_header,
                "POST",
                f"/session?directory={directory}",
                {},
            )
            session_id = session.get("id") if isinstance(session, dict) else None
            if not isinstance(session_id, str) or not session_id:
                raise AssertionError("the isolated runtime did not create a session")
            prompt = (
                "This is an AI4HEOR local provider compatibility test and contains no "
                f"research data. Reply with exactly {args.marker} and nothing else."
            )
            http_json(
                base_url,
                auth_header,
                "POST",
                f"/session/{urllib.parse.quote(session_id, safe='')}/prompt_async",
                {"parts": [{"type": "text", "text": prompt}]},
            )
            deadline = time.monotonic() + args.turn_timeout
            marker_found = False
            messages: Any = []
            while time.monotonic() < deadline:
                messages = http_json(
                    base_url,
                    auth_header,
                    "GET",
                    f"/session/{urllib.parse.quote(session_id, safe='')}/message",
                )
                marker_found = args.marker in assistant_text(messages)
                if marker_found:
                    break
                if process.poll() is not None:
                    raise AssertionError("the isolated runtime exited during the model turn")
                time.sleep(0.5)
            if not marker_found:
                diagnostic_material = json.dumps(messages).encode("utf-8")
                for path in (stdout_path, stderr_path):
                    try:
                        diagnostic_material += path.read_bytes()
                    except OSError:
                        pass
                if event_stream is not None:
                    diagnostic_material += bytes(event_stream.material)
                category = classify_failure(diagnostic_material, credential)
                raise AssertionError(
                    f"the real model turn did not return the expected marker ({category})"
                )

            http_json(
                base_url,
                auth_header,
                "DELETE",
                f"/auth/{urllib.parse.quote(args.provider_id, safe='')}",
            )
            auth_saved = False
            http_json(base_url, auth_header, "POST", "/instance/dispose", {})
            deadline = time.monotonic() + 10
            remaining_hits: list[Path] = []
            while time.monotonic() < deadline:
                remaining_hits = credential_hit_paths(
                    [
                        root / "config",
                        root / "data",
                        root / "cache",
                        root / "state",
                        root / "work",
                        stdout_path,
                        stderr_path,
                    ],
                    credential,
                )
                if not remaining_hits:
                    break
                time.sleep(0.1)
            if remaining_hits:
                raise AssertionError("the provider credential remained after auth deletion")

            proof = {
                "schema": SCHEMA,
                "artifact": {
                    "filename": dmg.name,
                    "sha256": sha256(dmg),
                    "app_version": version,
                    "opencode_version": opencode_version,
                },
                "provider": {
                    "id": args.provider_id,
                    "model": args.model,
                    "adapter": args.npm,
                    "metadata_and_auth_separate": True,
                    **provider_preflight,
                },
                "turn": {
                    "real_network_request": True,
                    "research_data_included": False,
                    "response_marker_found": True,
                },
                "credential": {
                    "source": "macOS_Keychain",
                    **persistence,
                    "removed_after_turn": True,
                    "temporary_profile_hits_after_delete": 0,
                    "tracked_source_hits": 0,
                    "verification_record_contains_credential": False,
                },
                "cleanup": {
                    "runtime_stopped": False,
                    "temporary_profile_removed": False,
                },
            }
        finally:
            if auth_saved and process is not None and process.poll() is None:
                try:
                    http_json(
                        base_url,
                        auth_header,
                        "DELETE",
                        f"/auth/{urllib.parse.quote(args.provider_id, safe='')}",
                        timeout=5,
                    )
                except AssertionError:
                    pass
            if event_stream is not None:
                event_stream.close()
            if process is not None:
                stop_process(process)

        if not proof:
            raise AssertionError("live-provider verification produced no proof")
        proof["cleanup"]["runtime_stopped"] = process is not None and process.poll() is not None
        if credential_hit_paths(
            [
                root / "config",
                root / "data",
                root / "cache",
                root / "state",
                root / "work",
                stdout_path,
                stderr_path,
            ],
            credential,
        ):
            raise AssertionError("the stopped temporary profile still contains the credential")
    proof["cleanup"]["temporary_profile_removed"] = True
    if args.verification_json:
        write_verification(args.verification_json, proof, credential)
    return proof


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--keychain-service", required=True)
    parser.add_argument("--keychain-account", required=True)
    parser.add_argument("--provider-id", default=DEFAULT_PROVIDER_ID)
    parser.add_argument("--provider-name", default=DEFAULT_PROVIDER_NAME)
    parser.add_argument("--npm", default=DEFAULT_NPM)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--marker", default=DEFAULT_MARKER)
    parser.add_argument("--turn-timeout", type=float, default=180.0)
    parser.add_argument("--verification-json", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    proof = verify_live_provider(args)
    print(
        "Verified live provider boundary: "
        f"artifact={proof['artifact']['filename']}, "
        f"model={proof['provider']['id']}/{proof['provider']['model']}, "
        "marker=True, credential_removed=True, tracked_source_hits=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

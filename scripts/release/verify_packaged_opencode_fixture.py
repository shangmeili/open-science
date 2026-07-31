#!/usr/bin/env python3
"""Run the packaged OpenCode against a hermetic Anthropic-compatible fixture."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import verify_live_provider_boundary as live


PROVIDER_ID = "ai4heor-local-fixture"
MODEL_ID = "fixture-model"
MARKER = "AI4HEOR_PACKAGED_OPENCODE_OK"
CREDENTIAL = "fixture-credential-not-a-secret"


class FixtureState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.catalog_requests = 0
        self.message_requests = 0
        self.last_stream = False
        self.message_bodies: list[dict[str, Any]] = []
        self._next_main_reply_gate: tuple[threading.Event, threading.Event] | None = None

    def record_catalog(self) -> None:
        with self.lock:
            self.catalog_requests += 1

    def record_message(self, stream: bool, body: dict[str, Any]) -> None:
        with self.lock:
            self.message_requests += 1
            self.last_stream = stream
            self.message_bodies.append(body)

    def pause_next_main_reply(self) -> tuple[threading.Event, threading.Event]:
        waiting = threading.Event()
        release = threading.Event()
        with self.lock:
            if self._next_main_reply_gate is not None:
                raise RuntimeError("a fixture main reply is already paused")
            self._next_main_reply_gate = (waiting, release)
        return waiting, release

    def wait_before_reply(self, stream: bool, body: dict[str, Any]) -> bool:
        if not stream or not isinstance(body.get("tools"), list) or not body["tools"]:
            return True
        with self.lock:
            gate = self._next_main_reply_gate
            self._next_main_reply_gate = None
        if gate is None:
            return True
        waiting, release = gate
        waiting.set()
        return release.wait(timeout=30.0)


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def anthropic_stream() -> bytes:
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_fixture",
                    "type": "message",
                    "role": "assistant",
                    "model": MODEL_ID,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 8, "output_tokens": 0},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": MARKER},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 1},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return b"".join(
        b"event: " + name.encode() + b"\ndata: " + json_bytes(payload) + b"\n\n"
        for name, payload in events
    )


def handler(state: FixtureState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def send_payload(self, status: int, payload: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            if urllib.parse.urlsplit(self.path).path == "/anthropic/v1/models":
                state.record_catalog()
                self.send_payload(
                    200,
                    json_bytes(
                        {
                            "data": [
                                {
                                    "id": MODEL_ID,
                                    "created_at": "2026-01-01T00:00:00Z",
                                    "display_name": MODEL_ID,
                                    "type": "model",
                                }
                            ],
                            "has_more": False,
                        }
                    ),
                    "application/json",
                )
                return
            self.send_payload(404, b"{}", "application/json")

        def do_POST(self) -> None:  # noqa: N802
            if urllib.parse.urlsplit(self.path).path != "/anthropic/v1/messages":
                self.send_payload(404, b"{}", "application/json")
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self.send_payload(400, b"{}", "application/json")
                return
            stream = body.get("stream") is True if isinstance(body, dict) else False
            if not isinstance(body, dict) or body.get("model") != MODEL_ID:
                self.send_payload(400, b"{}", "application/json")
                return
            state.record_message(stream, body)
            if not state.wait_before_reply(stream, body):
                self.send_payload(504, b"{}", "application/json")
                return
            if stream:
                self.send_payload(200, anthropic_stream(), "text/event-stream")
                return
            self.send_payload(
                200,
                json_bytes(
                    {
                        "id": "msg_fixture",
                        "type": "message",
                        "role": "assistant",
                        "model": MODEL_ID,
                        "content": [{"type": "text", "text": MARKER}],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 8, "output_tokens": 1},
                    }
                ),
                "application/json",
            )

    return Handler


def request_system_blocks(body: dict[str, Any]) -> list[str]:
    value = body.get("system")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        blocks: list[str] = []
        for item in value:
            if not isinstance(item, dict) or item.get("type") != "text" or not isinstance(item.get("text"), str):
                raise AssertionError("fixture provider received unsupported system block")
            blocks.append(item["text"])
        return blocks
    raise AssertionError("fixture provider did not receive a system prompt")


def verify_system_context_audit(
    messages: Any,
    provider_bodies: list[dict[str, Any]],
) -> dict[str, Any]:
    assistants = [
        item
        for item in messages
        if isinstance(item, dict)
        and isinstance(item.get("info"), dict)
        and item["info"].get("role") == "assistant"
        and MARKER in live.assistant_text([item])
    ] if isinstance(messages, list) else []
    if len(assistants) != 1:
        raise AssertionError("fixture did not produce one completed assistant message")
    context = assistants[0]["info"].get("systemContext")
    if not isinstance(context, dict) or set(context) != {"contract", "sha256", "blockCount"}:
        raise AssertionError("assistant message is missing the bounded system-context audit field")
    main_bodies = [
        body
        for body in provider_bodies
        if isinstance(body.get("tools"), list)
        and body["tools"]
        and "Reply with the marker." in json.dumps(body, ensure_ascii=False)
    ]
    if len(main_bodies) != 1:
        raise AssertionError("could not distinguish the main provider request from auxiliary calls")
    blocks = request_system_blocks(main_bodies[0])
    canonical = json.dumps(blocks, ensure_ascii=False, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if context != {
        "contract": "ai4heor.system-context/v1",
        "sha256": expected,
        "blockCount": len(blocks),
    }:
        raise AssertionError("assistant system-context fingerprint does not match its provider request")
    return {
        "contract": context["contract"],
        "sha256": context["sha256"],
        "block_count": context["blockCount"],
    }


def run_fixture(dmg: Path, expected_version: str, timeout: float) -> dict[str, Any]:
    state = FixtureState()
    provider = ThreadingHTTPServer(("127.0.0.1", 0), handler(state))
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    provider_url = f"http://127.0.0.1:{provider.server_address[1]}/anthropic/v1"

    try:
        with tempfile.TemporaryDirectory(
            prefix="ai4heor-opencode-fixture-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            for name in ("bin", "home", "config", "data", "cache", "state", "work"):
                path = root / name
                path.mkdir(mode=0o700)
                path.chmod(0o700)

            device = ""
            try:
                device, mount = live.mount_dmg(dmg)
                app = mount / "AI4HEOR.app"
                with (app / "Contents/Info.plist").open("rb") as handle:
                    import plistlib

                    version = plistlib.load(handle).get("CFBundleShortVersionString")
                if version != expected_version:
                    raise AssertionError(
                        f"expected AI4HEOR {expected_version}, found {version}"
                    )
                source = app / "Contents/MacOS/opencode"
                binary = root / "bin/opencode"
                shutil.copy2(source, binary)
                binary.chmod(0o700)
            finally:
                if device:
                    live.detach_dmg(device)

            port = live.free_local_port()
            password = secrets.token_urlsafe(24)
            token = base64.b64encode(f"opencode:{password}".encode()).decode()
            auth_header = f"Basic {token}"
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
            process: subprocess.Popen[Any] | None = None
            events: live.EventStream | None = None
            auth_saved = False
            try:
                with (root / "stdout").open("wb") as stdout, (root / "stderr").open(
                    "wb"
                ) as stderr:
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
                        preexec_fn=live.private_child_setup,
                    )
                live.wait_for_runtime(base_url, auth_header)
                live.http_json(
                    base_url,
                    auth_header,
                    "PATCH",
                    "/global/config",
                    {
                        "provider": {
                            PROVIDER_ID: {
                                "name": "AI4HEOR local fixture",
                                "npm": "@ai-sdk/anthropic",
                                "options": {"baseURL": provider_url},
                                "models": {MODEL_ID: {"name": MODEL_ID}},
                            }
                        },
                        "model": f"{PROVIDER_ID}/{MODEL_ID}",
                    },
                )
                live.http_json(
                    base_url,
                    auth_header,
                    "PUT",
                    f"/auth/{PROVIDER_ID}",
                    {"type": "api", "key": CREDENTIAL},
                )
                auth_saved = True
                live.http_json(base_url, auth_header, "POST", "/instance/dispose", {})
                live.wait_for_workspace_provider(
                    base_url,
                    auth_header,
                    root / "work",
                    PROVIDER_ID,
                    MODEL_ID,
                )
                events = live.EventStream(base_url, auth_header, root / "work", timeout + 20)
                events.start()
                directory = urllib.parse.quote(str(root / "work"), safe="")
                session = live.http_json(
                    base_url, auth_header, "POST", f"/session?directory={directory}", {}
                )
                session_id = session.get("id") if isinstance(session, dict) else None
                if not isinstance(session_id, str):
                    raise AssertionError("fixture session was not created")
                live.http_json(
                    base_url,
                    auth_header,
                    "POST",
                    f"/session/{urllib.parse.quote(session_id, safe='')}/prompt_async",
                    {"parts": [{"type": "text", "text": "Reply with the marker."}]},
                )
                deadline = time.monotonic() + timeout
                messages: Any = []
                while time.monotonic() < deadline:
                    messages = live.http_json(
                        base_url,
                        auth_header,
                        "GET",
                        f"/session/{urllib.parse.quote(session_id, safe='')}/message",
                    )
                    if MARKER in live.assistant_text(messages):
                        break
                    time.sleep(0.1)
                if MARKER not in live.assistant_text(messages):
                    roles = [
                        item.get("info", {}).get("role")
                        for item in messages
                        if isinstance(item, dict)
                    ] if isinstance(messages, list) else []
                    assistant_errors = [
                        item.get("info", {}).get("error")
                        for item in messages
                        if isinstance(item, dict)
                        and item.get("info", {}).get("role") == "assistant"
                    ] if isinstance(messages, list) else []
                    raise AssertionError(
                        "packaged OpenCode fixture turn did not complete: "
                        f"provider_requests={state.message_requests}, roles={roles}, "
                        f"assistant_errors={json.dumps(assistant_errors, separators=(',', ':'))[:2000]}, "
                        f"event_category={live.classify_failure(bytes(events.material), CREDENTIAL.encode())}"
                    )
                context_proof = verify_system_context_audit(messages, state.message_bodies)
                return {
                    "app_version": version,
                    "provider_catalog_requests": state.catalog_requests,
                    "provider_message_requests": state.message_requests,
                    "provider_streaming": state.last_stream,
                    "assistant_marker_found": True,
                    "system_context": context_proof,
                }
            finally:
                if auth_saved and process is not None and process.poll() is None:
                    try:
                        live.http_json(
                            base_url,
                            auth_header,
                            "DELETE",
                            f"/auth/{PROVIDER_ID}",
                            timeout=5,
                        )
                    except AssertionError:
                        pass
                if events is not None:
                    events.close()
                if process is not None:
                    live.stop_process(process)
    finally:
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    result = run_fixture(args.dmg.resolve(), args.expected_version, args.timeout)
    print(
        "Verified packaged OpenCode fixture: "
        f"version={result['app_version']}, "
        f"message_requests={result['provider_message_requests']}, "
        f"streaming={result['provider_streaming']}, marker=True, "
        f"system_context={result['system_context']['contract']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

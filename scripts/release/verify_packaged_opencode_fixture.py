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
QUESTION_TEXT = "Which checked continuation should AI4HEOR use?"
QUESTION_HEADER = "E2E check"
QUESTION_OPTION = "Continue safely"
QUESTION_DESCRIPTION = "Continue the local deterministic E2E run."
BASH_COMMAND = "rm -f ai4heor-e2e-permission-sentinel"
AUDIT_RUN_COMMAND = "python3 -c 'print(1)'"
BASH_ALWAYS_SENTINEL = "ai4heor-e2e-permission-always-sentinel"
BASH_ALWAYS_COMMAND = f"rm -f {BASH_ALWAYS_SENTINEL}"
BASH_REJECT_SENTINEL = "ai4heor-e2e-permission-reject-sentinel"
BASH_REJECT_COMMAND = f"rm -f {BASH_REJECT_SENTINEL}"
PROVIDER_ERROR_MESSAGE = "AI4HEOR E2E provider rejected the request"


class FixtureState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.catalog_requests = 0
        self.message_requests = 0
        self.last_stream = False
        self.message_bodies: list[dict[str, Any]] = []
        self._next_main_reply_gate: tuple[threading.Event, threading.Event] | None = None
        self._next_main_reply_kind: str | None = None
        self._bash_always_reply_count = 0

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

    def question_next_main_reply(self) -> None:
        with self.lock:
            if self._next_main_reply_kind is not None:
                raise RuntimeError("a fixture main reply is already configured")
            self._next_main_reply_kind = "question"

    def bash_next_main_reply(self) -> None:
        with self.lock:
            if self._next_main_reply_kind is not None:
                raise RuntimeError("a fixture main reply is already configured")
            self._next_main_reply_kind = "bash"

    def audit_run_next_main_reply(self) -> None:
        with self.lock:
            if self._next_main_reply_kind is not None:
                raise RuntimeError("a fixture main reply is already configured")
            self._next_main_reply_kind = "audit_run"

    def bash_rejection_next_main_reply(self) -> None:
        with self.lock:
            if self._next_main_reply_kind is not None:
                raise RuntimeError("a fixture main reply is already configured")
            self._next_main_reply_kind = "bash_reject"

    def bash_always_next_main_reply(self) -> None:
        with self.lock:
            if self._next_main_reply_kind is not None:
                raise RuntimeError("a fixture main reply is already configured")
            self._bash_always_reply_count += 1
            self._next_main_reply_kind = f"bash_always_{self._bash_always_reply_count}"

    def provider_error_next_main_reply(self) -> None:
        with self.lock:
            if self._next_main_reply_kind is not None:
                raise RuntimeError("a fixture main reply is already configured")
            self._next_main_reply_kind = "provider_error"

    def take_reply_kind(self, stream: bool, body: dict[str, Any]) -> str:
        if not stream or not isinstance(body.get("tools"), list) or not body["tools"]:
            return "text"
        with self.lock:
            kind = self._next_main_reply_kind
            self._next_main_reply_kind = None
        return kind or "text"


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


def anthropic_provider_error() -> bytes:
    return json_bytes(
        {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": PROVIDER_ERROR_MESSAGE,
            },
        }
    )


def anthropic_question_stream() -> bytes:
    question_input = {
        "questions": [
            {
                "question": QUESTION_TEXT,
                "header": QUESTION_HEADER,
                "options": [
                    {
                        "label": QUESTION_OPTION,
                        "description": QUESTION_DESCRIPTION,
                    }
                ],
                "multiple": False,
            }
        ]
    }
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_fixture_question",
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
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_fixture_question",
                    "name": "question",
                    "input": {},
                },
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": json.dumps(question_input, separators=(",", ":")),
                },
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                "usage": {"output_tokens": 1},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return b"".join(
        b"event: " + name.encode() + b"\ndata: " + json_bytes(payload) + b"\n\n"
        for name, payload in events
    )


def anthropic_bash_stream(
    command: str = BASH_COMMAND,
    message_id: str = "msg_fixture_bash",
    tool_id: str = "toolu_fixture_bash",
) -> bytes:
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": message_id,
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
                "content_block": {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": "bash",
                    "input": {},
                },
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": json.dumps(
                        {"command": command},
                        separators=(",", ":"),
                    ),
                },
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use", "stop_sequence": None},
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
            reply_kind = state.take_reply_kind(stream, body)
            if not state.wait_before_reply(stream, body):
                self.send_payload(504, b"{}", "application/json")
                return
            if reply_kind == "provider_error":
                self.send_payload(
                    400,
                    anthropic_provider_error(),
                    "application/json",
                )
                return
            if stream:
                if reply_kind == "question":
                    payload = anthropic_question_stream()
                elif reply_kind == "bash":
                    payload = anthropic_bash_stream()
                elif reply_kind == "audit_run":
                    payload = anthropic_bash_stream(
                        command=AUDIT_RUN_COMMAND,
                        message_id="msg_fixture_audit_run",
                        tool_id="toolu_fixture_audit_run",
                    )
                elif reply_kind == "bash_reject":
                    payload = anthropic_bash_stream(
                        command=BASH_REJECT_COMMAND,
                        message_id="msg_fixture_bash_reject",
                        tool_id="toolu_fixture_bash_reject",
                    )
                elif reply_kind.startswith("bash_always_"):
                    sequence = reply_kind.removeprefix("bash_always_")
                    payload = anthropic_bash_stream(
                        command=BASH_ALWAYS_COMMAND,
                        message_id=f"msg_fixture_bash_always_{sequence}",
                        tool_id=f"toolu_fixture_bash_always_{sequence}",
                    )
                else:
                    payload = anthropic_stream()
                self.send_payload(200, payload, "text/event-stream")
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


def verify_saved_permission_records(
    value: Any,
    *,
    action: str,
    resource: str,
) -> dict[str, str]:
    if not isinstance(value, list) or len(value) != 1:
        raise AssertionError("packaged runtime did not return exactly one saved permission")
    record = value[0]
    if not isinstance(record, dict) or set(record) != {
        "id",
        "projectID",
        "action",
        "resource",
    }:
        raise AssertionError("packaged runtime returned an invalid saved permission record")
    if (
        not isinstance(record["id"], str)
        or not record["id"]
        or not isinstance(record["projectID"], str)
        or not record["projectID"]
        or record["action"] != action
        or record["resource"] != resource
    ):
        raise AssertionError("packaged runtime broadened or mis-scoped the saved permission")
    return {"id": record["id"], "project_id": record["projectID"]}


def start_runtime(
    binary: Path,
    root: Path,
    environment: dict[str, str],
    auth_header: str,
) -> tuple[subprocess.Popen[Any], str]:
    port = live.free_local_port()
    base_url = f"http://127.0.0.1:{port}"
    with (root / "stdout").open("ab") as stdout, (root / "stderr").open(
        "ab"
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
    return process, base_url


def create_prompted_session(
    base_url: str,
    auth_header: str,
    directory: Path,
    prompt: str,
) -> str:
    query = urllib.parse.quote(str(directory), safe="")
    session = live.http_json(
        base_url,
        auth_header,
        "POST",
        f"/session?directory={query}",
        {},
    )
    session_id = session.get("id") if isinstance(session, dict) else None
    if not isinstance(session_id, str) or not session_id:
        raise AssertionError("permission fixture session was not created")
    live.http_json(
        base_url,
        auth_header,
        "POST",
        f"/session/{urllib.parse.quote(session_id, safe='')}/prompt_async",
        {"parts": [{"type": "text", "text": prompt}]},
    )
    return session_id


def wait_for_pending_permission(
    base_url: str,
    auth_header: str,
    directory: Path,
    *,
    action: str,
    resource: str,
    timeout: float,
) -> str:
    query = urllib.parse.quote(str(directory), safe="")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = live.http_json(
            base_url,
            auth_header,
            "GET",
            f"/permission?directory={query}",
            timeout=3.0,
        )
        if isinstance(value, list) and len(value) == 1:
            request = value[0]
            if (
                isinstance(request, dict)
                and request.get("permission") == action
                and request.get("patterns") == [resource]
                and isinstance(request.get("id"), str)
            ):
                return request["id"]
        time.sleep(0.1)
    raise AssertionError("packaged runtime did not ask for the exact command permission")


def wait_for_session_marker(
    base_url: str,
    auth_header: str,
    session_id: str,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages = live.http_json(
            base_url,
            auth_header,
            "GET",
            f"/session/{urllib.parse.quote(session_id, safe='')}/message",
            timeout=3.0,
        )
        if MARKER in live.assistant_text(messages):
            return
        time.sleep(0.1)
    raise AssertionError("packaged permission fixture turn did not complete")


def wait_for_missing_path(path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not path.exists():
            return
        time.sleep(0.1)
    raise AssertionError("packaged runtime did not execute the allowed exact command")


def verify_packaged_permission_persistence(
    *,
    state: FixtureState,
    binary: Path,
    root: Path,
    environment: dict[str, str],
    auth_header: str,
    process: subprocess.Popen[Any],
    base_url: str,
    timeout: float,
) -> tuple[dict[str, Any], subprocess.Popen[Any], str]:
    directory = root / "work"
    query = urllib.parse.quote(str(directory), safe="")
    sentinel = directory / BASH_ALWAYS_SENTINEL
    current = process
    current_url = base_url
    try:
        sentinel.write_text("remove after explicit permission\n", encoding="utf-8")
        state.bash_always_next_main_reply()
        session_id = create_prompted_session(
            current_url,
            auth_header,
            directory,
            "Run the fixed packaged permission probe once.",
        )
        request_id = wait_for_pending_permission(
            current_url,
            auth_header,
            directory,
            action="bash",
            resource=BASH_ALWAYS_COMMAND,
            timeout=timeout,
        )
        live.http_json(
            current_url,
            auth_header,
            "POST",
            f"/permission/{urllib.parse.quote(request_id, safe='')}/reply?directory={query}",
            {"reply": "always"},
        )
        wait_for_missing_path(sentinel, timeout)
        wait_for_session_marker(current_url, auth_header, session_id, timeout)
        saved = verify_saved_permission_records(
            live.http_json(
                current_url,
                auth_header,
                "GET",
                f"/permission/saved?directory={query}",
            ),
            action="bash",
            resource=BASH_ALWAYS_COMMAND,
        )

        live.stop_process(current)
        current, current_url = start_runtime(
            binary,
            root,
            environment,
            auth_header,
        )
        live.wait_for_workspace_provider(
            current_url,
            auth_header,
            directory,
            PROVIDER_ID,
            MODEL_ID,
        )
        restarted = verify_saved_permission_records(
            live.http_json(
                current_url,
                auth_header,
                "GET",
                f"/permission/saved?directory={query}",
            ),
            action="bash",
            resource=BASH_ALWAYS_COMMAND,
        )
        if restarted != saved:
            raise AssertionError("saved permission identity changed after runtime restart")

        sentinel.write_text("remove automatically after restart\n", encoding="utf-8")
        state.bash_always_next_main_reply()
        restarted_session = create_prompted_session(
            current_url,
            auth_header,
            directory,
            "Run the same packaged permission probe after restart.",
        )
        wait_for_missing_path(sentinel, timeout)
        wait_for_session_marker(current_url, auth_header, restarted_session, timeout)
        pending = live.http_json(
            current_url,
            auth_header,
            "GET",
            f"/permission?directory={query}",
        )
        if pending != []:
            raise AssertionError("remembered exact permission asked again after restart")

        removed = live.http_json(
            current_url,
            auth_header,
            "DELETE",
            f"/permission/saved/{urllib.parse.quote(saved['id'], safe='')}?directory={query}",
        )
        if removed is not True:
            raise AssertionError("packaged runtime did not revoke the saved permission")
        remaining = live.http_json(
            current_url,
            auth_header,
            "GET",
            f"/permission/saved?directory={query}",
        )
        if remaining != []:
            raise AssertionError("revoked packaged permission remained visible")

        sentinel.write_text("must remain after revocation\n", encoding="utf-8")
        state.bash_always_next_main_reply()
        create_prompted_session(
            current_url,
            auth_header,
            directory,
            "Run the packaged permission probe after revocation.",
        )
        revoked_request = wait_for_pending_permission(
            current_url,
            auth_header,
            directory,
            action="bash",
            resource=BASH_ALWAYS_COMMAND,
            timeout=timeout,
        )
        if not sentinel.is_file():
            raise AssertionError("revoked permission executed before renewed confirmation")
        live.http_json(
            current_url,
            auth_header,
            "POST",
            f"/permission/{urllib.parse.quote(revoked_request, safe='')}/reply?directory={query}",
            {"reply": "reject"},
        )
        time.sleep(0.2)
        if sentinel.read_text(encoding="utf-8") != "must remain after revocation\n":
            raise AssertionError("rejected post-revocation command changed the sentinel")
        return (
            {
                "exact_project_rule": True,
                "restart_reused": True,
                "revoked": True,
                "reprompted_after_revoke": True,
            },
            current,
            current_url,
        )
    except BaseException:
        if current.poll() is None:
            live.stop_process(current)
        raise


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
            subprocess.run(
                ["git", "init", "--quiet"],
                cwd=root / "work",
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            (root / "work/README.md").write_text(
                "# Isolated packaged permission fixture\n",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=AI4HEOR Fixture",
                    "-c",
                    "user.email=fixture@localhost.invalid",
                    "add",
                    "README.md",
                ],
                cwd=root / "work",
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=AI4HEOR Fixture",
                    "-c",
                    "user.email=fixture@localhost.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "Initialize fixture workspace",
                ],
                cwd=root / "work",
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

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

            password = secrets.token_urlsafe(24)
            token = base64.b64encode(f"opencode:{password}".encode()).decode()
            auth_header = f"Basic {token}"
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
                process, base_url = start_runtime(
                    binary,
                    root,
                    environment,
                    auth_header,
                )
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
                        "permission": {"bash": "ask"},
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
                events.close()
                events = None
                permission_proof, process, base_url = verify_packaged_permission_persistence(
                    state=state,
                    binary=binary,
                    root=root,
                    environment=environment,
                    auth_header=auth_header,
                    process=process,
                    base_url=base_url,
                    timeout=timeout,
                )
                return {
                    "app_version": version,
                    "provider_catalog_requests": state.catalog_requests,
                    "provider_message_requests": state.message_requests,
                    "provider_streaming": state.last_stream,
                    "assistant_marker_found": True,
                    "system_context": context_proof,
                    "permission_persistence": permission_proof,
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


def bounded_release_proof(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise AssertionError("packaged OpenCode fixture result is not an object")
    context = result.get("system_context")
    permission = result.get("permission_persistence")
    expected_permission = {
        "exact_project_rule",
        "restart_reused",
        "revoked",
        "reprompted_after_revoke",
    }
    if (
        result.get("assistant_marker_found") is not True
        or result.get("provider_streaming") is not True
        or not isinstance(context, dict)
        or set(context) != {"contract", "sha256", "block_count"}
        or context.get("contract") != "ai4heor.system-context/v1"
        or not isinstance(context.get("sha256"), str)
        or len(context["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in context["sha256"])
        or not isinstance(context.get("block_count"), int)
        or context["block_count"] < 1
        or not isinstance(permission, dict)
        or set(permission) != expected_permission
        or any(value is not True for value in permission.values())
    ):
        raise AssertionError("packaged OpenCode fixture proof is incomplete")
    return {
        "assistant_reply_completed": True,
        "provider_streaming": True,
        "system_context": {
            "contract": "ai4heor.system-context/v1",
            "fingerprint_matched_provider_request": True,
        },
        "permission_persistence": dict(permission),
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_target_dmg_binding(verification_path: Path, dmg: Path) -> None:
    if not dmg.is_file() or dmg.is_symlink():
        raise AssertionError("fixture target DMG is missing or linked")
    if not verification_path.is_file() or verification_path.is_symlink():
        raise AssertionError("macOS verification JSON is missing or linked")
    try:
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AssertionError("macOS verification JSON is unreadable") from error
    bundle = verification.get("bundle") if isinstance(verification, dict) else None
    if (
        not isinstance(bundle, dict)
        or set(bundle) != {"dmg_sha256", "filename", "target"}
        or bundle.get("filename") != dmg.name
        or bundle.get("dmg_sha256") != file_sha256(dmg)
        or bundle.get("target")
        not in {"aarch64-apple-darwin", "x86_64-apple-darwin"}
    ):
        raise AssertionError("macOS verification DMG binding is incomplete or mismatched")


def append_release_proof(path: Path, proof: dict[str, Any]) -> None:
    if not path.is_file() or path.is_symlink():
        raise AssertionError("macOS verification JSON is missing or linked")
    try:
        verification = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AssertionError("macOS verification JSON is unreadable") from error
    if not isinstance(verification, dict) or not verification:
        raise AssertionError("macOS verification JSON is not an object")
    if "packaged_opencode_fixture" in verification:
        raise AssertionError("macOS verification JSON already contains fixture proof")
    verification["packaged_opencode_fixture"] = proof
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise AssertionError("temporary verification proof path already exists")
    try:
        temporary.write_text(
            json.dumps(verification, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--verification-json", type=Path, required=True)
    args = parser.parse_args()
    dmg = args.dmg.resolve()
    verification_json = args.verification_json.resolve()
    verify_target_dmg_binding(verification_json, dmg)
    result = run_fixture(dmg, args.expected_version, args.timeout)
    append_release_proof(
        verification_json,
        bounded_release_proof(result),
    )
    print(
        "Verified packaged OpenCode fixture: "
        f"version={result['app_version']}, "
        f"message_requests={result['provider_message_requests']}, "
        f"streaming={result['provider_streaming']}, marker=True, "
        f"system_context={result['system_context']['contract']}, "
        "permission_restart=True, permission_revoke=True"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

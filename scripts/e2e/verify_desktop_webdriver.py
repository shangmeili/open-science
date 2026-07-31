#!/usr/bin/env python3
"""Drive real AI4HEOR controls through the test-only embedded WebDriver.

This smoke test intentionally uses only Python's standard library. It launches
the debug binary with an isolated user home, drives rendered sidebar and file
controls, and proves that navigation and passive HTML preview run inside Tauri
rather than a browser preview.
"""

from __future__ import annotations

import json
import os
import platform
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "apps/desktop/src-tauri/target/debug/ai4s-workbench"
BUNDLE_IDENTIFIER = "com.ai4s.ai4heor"
ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"
RELEASE_SCRIPTS = ROOT / "scripts/release"
if str(RELEASE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(RELEASE_SCRIPTS))

from verify_packaged_opencode_fixture import (  # noqa: E402
    CREDENTIAL as FIXTURE_CREDENTIAL,
    MARKER as FIXTURE_MARKER,
    MODEL_ID as FIXTURE_MODEL_ID,
    PROVIDER_ID as FIXTURE_PROVIDER_ID,
    FixtureState,
    handler as fixture_handler,
)


PROJECT_NAME = "AI4HEOR E2E project"
TASK_PROMPT = "AI4HEOR E2E standalone task"


def prepare_local_fixture_runtime(home: Path, provider_url: str) -> Path:
    runtime_root = (
        home
        / "Library/Application Support"
        / BUNDLE_IDENTIFIER
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
                    FIXTURE_PROVIDER_ID: {
                        "name": "AI4HEOR local E2E fixture",
                        "npm": "@ai-sdk/anthropic",
                        "options": {"baseURL": provider_url},
                        "models": {
                            FIXTURE_MODEL_ID: {"name": FIXTURE_MODEL_ID},
                        },
                    }
                },
                "model": f"{FIXTURE_PROVIDER_ID}/{FIXTURE_MODEL_ID}",
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    auth.write_text(
        json.dumps(
            {
                FIXTURE_PROVIDER_ID: {
                    "type": "api",
                    "key": FIXTURE_CREDENTIAL,
                }
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    for private in (runtime_root, config.parent, auth.parent):
        private.chmod(0o700)
    config.chmod(0o600)
    auth.chmod(0o600)
    return runtime_root


@contextmanager
def local_fixture_provider() -> Iterator[tuple[FixtureState, str]]:
    state = FixtureState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), fixture_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_address[1]}/anthropic/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class LocalRequestObserver:
    def __init__(self) -> None:
        self.requested = threading.Event()
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen()
        self._listener.settimeout(0.2)
        self.port = int(self._listener.getsockname()[1])
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                self.requested.set()
                try:
                    connection.recv(4096)
                    connection.sendall(
                        b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n"
                    )
                except OSError:
                    pass

    def close(self) -> None:
        self._stop.set()
        self._listener.close()
        self._thread.join(timeout=1.0)


def local_request_observer() -> LocalRequestObserver:
    return LocalRequestObserver()


def request_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise AssertionError(f"WebDriver {method} {path} failed: {error.code} {detail}") from error
    if not body:
        return None
    decoded = json.loads(body)
    return decoded.get("value", decoded)


def wait_for_status(base_url: str, process: subprocess.Popen[str], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"AI4HEOR exited before WebDriver readiness ({process.returncode})")
        try:
            request_json(base_url, "GET", "/status", timeout=1.0)
            return
        except (AssertionError, URLError, TimeoutError, ConnectionError) as error:
            last_error = error
            time.sleep(0.2)
    raise AssertionError(f"WebDriver did not become ready: {last_error}")


def execute(base_url: str, session_id: str, script: str) -> Any:
    return request_json(
        base_url,
        "POST",
        f"/session/{session_id}/execute/sync",
        {"script": script, "args": []},
    )


def wait_for_script_value(
    base_url: str,
    session_id: str,
    script: str,
    expected: Any,
    timeout: float = 15.0,
) -> None:
    deadline = time.monotonic() + timeout
    last_value: Any = None
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            last_value = execute(base_url, session_id, script)
            last_error = None
            if last_value == expected:
                return
        except (AssertionError, URLError, TimeoutError, ConnectionError) as error:
            last_error = error
        time.sleep(0.2)
    if last_error is not None:
        raise AssertionError(
            f"script did not return {expected!r} before timeout; last error was {last_error}"
        ) from last_error
    raise AssertionError(
        f"script did not return {expected!r} before timeout; last value was {last_value!r}"
    )


def find_element(base_url: str, session_id: str, xpath: str, timeout: float = 15.0) -> str:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = request_json(
                base_url,
                "POST",
                f"/session/{session_id}/element",
                {"using": "xpath", "value": xpath},
            )
            if isinstance(value, dict) and value.get(ELEMENT_KEY):
                return str(value[ELEMENT_KEY])
        except AssertionError as error:
            last_error = error
        time.sleep(0.2)
    raise AssertionError(f"element not found for {xpath}: {last_error}")


def find_stable_element(
    base_url: str,
    session_id: str,
    xpath: str,
    stable_for: float = 1.0,
    timeout: float = 15.0,
) -> str:
    deadline = time.monotonic() + timeout
    script = (
        "const node = document.evaluate("
        + json.dumps(xpath)
        + ", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; "
        "const now = Date.now(); "
        "const state = window.__ai4heorE2EStableElement; "
        "if (!node) { window.__ai4heorE2EStableElement = null; return false; } "
        "if (!state || state.node !== node) { "
        "window.__ai4heorE2EStableElement = { node: node, since: now }; return false; } "
        f"return now - state.since >= {int(stable_for * 1000)};"
    )
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if execute(base_url, session_id, script) is True:
                return find_element(base_url, session_id, xpath, timeout=2.0)
            last_error = None
        except (AssertionError, URLError, TimeoutError, ConnectionError) as error:
            last_error = error
        time.sleep(0.2)
    if last_error is not None:
        raise AssertionError(
            f"element did not remain stable for {stable_for:.1f}s; last error: {last_error}"
        ) from last_error
    raise AssertionError(f"element did not remain stable for {stable_for:.1f}s: {xpath}")


def click(base_url: str, session_id: str, element_id: str) -> None:
    request_json(
        base_url,
        "POST",
        f"/session/{session_id}/element/{element_id}/click",
        {},
    )


def send_keys(base_url: str, session_id: str, element_id: str, text: str) -> None:
    request_json(
        base_url,
        "POST",
        f"/session/{session_id}/element/{element_id}/value",
        {"text": text, "value": list(text)},
    )


def clear_element(base_url: str, session_id: str, element_id: str) -> None:
    request_json(
        base_url,
        "POST",
        f"/session/{session_id}/element/{element_id}/clear",
        {},
    )


def press_key(base_url: str, session_id: str, value: str) -> None:
    request_json(
        base_url,
        "POST",
        f"/session/{session_id}/actions",
        {
            "actions": [
                {
                    "type": "key",
                    "id": "keyboard",
                    "actions": [
                        {"type": "keyDown", "value": value},
                        {"type": "keyUp", "value": value},
                    ],
                }
            ]
        },
    )
    request_json(base_url, "DELETE", f"/session/{session_id}/actions")


def element_attribute(base_url: str, session_id: str, element_id: str, name: str) -> Any:
    return request_json(
        base_url,
        "GET",
        f"/session/{session_id}/element/{element_id}/attribute/{name}",
    )


def assert_no_admitted_asset_deployment_errors(log_path: Path) -> None:
    if not log_path.is_file():
        raise AssertionError("native desktop log is missing")
    log = log_path.read_text(encoding="utf-8", errors="replace")
    if "failed to deploy admitted asset" in log:
        raise AssertionError("admitted asset deployment failed in the native desktop runtime")


def wait_for_location(base_url: str, session_id: str, pathname: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if execute(base_url, session_id, "return window.location.pathname") == pathname:
            return
        time.sleep(0.2)
    raise AssertionError(f"page did not navigate to {pathname}")


def wait_for_task_location(
    base_url: str,
    session_id: str,
    timeout: float = 30.0,
) -> str:
    deadline = time.monotonic() + timeout
    last_path: Any = None
    while time.monotonic() < deadline:
        last_path = execute(base_url, session_id, "return window.location.pathname")
        if (
            isinstance(last_path, str)
            and last_path.startswith("/heor/")
            and last_path != "/heor/new"
        ):
            return last_path
        time.sleep(0.2)
    raise AssertionError(
        f"page did not navigate to a task; last path was {last_path!r}"
    )


def wait_for_body_text(
    base_url: str,
    session_id: str,
    expected: str,
    timeout: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = execute(base_url, session_id, "return document.body.innerText")
        if isinstance(body, str) and expected in body:
            return
        time.sleep(0.2)
    raise AssertionError(f"rendered desktop UI did not show {expected!r}")


def fill_composer(
    base_url: str,
    session_id: str,
    xpath: str,
    expected: str,
    timeout: float = 30.0,
) -> None:
    ready_script = (
        "const input = document.querySelector('textarea[aria-label=\"Ask anything\"], "
        "textarea[aria-label=\"描述研究问题或要处理的工作\"]'); "
        "const send = document.querySelector('button[aria-label=\"Send\"], "
        "button[aria-label=\"发送\"]'); "
        f"return Boolean(input && input.value === {json.dumps(expected)} "
        "&& send && !send.disabled);"
    )
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            element_id = find_element(base_url, session_id, xpath, timeout=2.0)
            current = element_attribute(base_url, session_id, element_id, "value")
            if current != expected:
                if current:
                    clear_element(base_url, session_id, element_id)
                send_keys(base_url, session_id, element_id, expected)
            if execute(base_url, session_id, ready_script) is True:
                return
            last_error = None
        except (AssertionError, URLError, TimeoutError, ConnectionError) as error:
            last_error = error
        time.sleep(0.2)
    visible = execute(base_url, session_id, "return document.body.innerText")
    raise AssertionError(
        "composer did not become sendable with the expected text; "
        f"last_error={last_error}, visible UI excerpt: {str(visible)[-2000:]}"
    )


def is_main_task_request(body: dict[str, Any]) -> bool:
    return (
        isinstance(body.get("tools"), list)
        and bool(body["tools"])
        and TASK_PROMPT in json.dumps(body.get("messages"), ensure_ascii=False)
    )


def choose_fixture_model_if_required(
    base_url: str,
    session_id: str,
) -> bool:
    choose_xpath = (
        '//button[@aria-label="选择模型" or @aria-label="Choose a model"]'
    )
    try:
        choose_id = find_element(base_url, session_id, choose_xpath, timeout=1.0)
    except AssertionError:
        return False
    click(base_url, session_id, choose_id)
    wait_for_location(base_url, session_id, "/settings")
    models_xpath = '//a[@href="/settings/models"]'
    click(base_url, session_id, find_element(base_url, session_id, models_xpath))
    wait_for_location(base_url, session_id, "/settings/models")
    fixture_model_xpath = (
        '//*[@role="listitem"]//button['
        'contains(translate(normalize-space(.), '
        '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), '
        '"fixture-model")]'
    )
    model_id = find_element(base_url, session_id, fixture_model_xpath, timeout=30.0)
    click(base_url, session_id, model_id)
    current_fixture_xpath = fixture_model_xpath[:-1] + ' and @aria-current="true"]'
    find_element(base_url, session_id, current_fixture_xpath, timeout=30.0)
    back_xpath = (
        '//button[normalize-space()="返回应用" '
        'or normalize-space()="Back to app"]'
    )
    click(base_url, session_id, find_element(base_url, session_id, back_xpath))
    wait_for_location(base_url, session_id, "/heor", timeout=30.0)
    return True


def single_instance_socket_path() -> Path:
    safe_identifier = BUNDLE_IDENTIFIER.replace(".", "_").replace("-", "_")
    return Path("/tmp") / f"{safe_identifier}_si.sock"


@contextmanager
def isolate_single_instance_socket(socket_path: Path) -> Iterator[None]:
    if not socket_path.exists():
        yield
        return
    if not stat.S_ISSOCK(socket_path.lstat().st_mode):
        raise AssertionError(f"single-instance path is not a socket: {socket_path}")
    backup = socket_path.with_name(f"{socket_path.name}.desktop-e2e-{os.getpid()}-{time.time_ns()}")
    os.replace(socket_path, backup)
    try:
        yield
    finally:
        if socket_path.exists():
            if not stat.S_ISSOCK(socket_path.lstat().st_mode):
                raise AssertionError(f"unexpected non-socket at {socket_path}")
            socket_path.unlink()
        os.replace(backup, socket_path)


def terminate(process: subprocess.Popen[str]) -> None:
    descendants: list[int] = []
    pending = [process.pid]
    while pending:
        parent = pending.pop()
        listed = subprocess.run(
            ["pgrep", "-P", str(parent)],
            check=False,
            capture_output=True,
            text=True,
        )
        children = [
            int(value)
            for value in listed.stdout.splitlines()
            if value.strip().isdigit()
        ]
        descendants.extend(children)
        pending.extend(children)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    for pid in reversed(descendants):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        alive = []
        for pid in descendants:
            try:
                os.kill(pid, 0)
                alive.append(pid)
            except ProcessLookupError:
                pass
        if not alive:
            return
        time.sleep(0.1)
    for pid in alive:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main() -> int:
    if platform.system() != "Darwin":
        raise SystemExit("native desktop E2E currently requires macOS")
    if not BINARY.is_file():
        raise SystemExit(f"test binary not found: {BINARY}")

    port = free_local_port()
    base_url = f"http://127.0.0.1:{port}"
    session_id: str | None = None
    process: subprocess.Popen[str] | None = None

    with tempfile.TemporaryDirectory(prefix="ai4heor-desktop-e2e-", dir="/private/tmp") as temporary:
        home = Path(temporary).resolve()
        provider_context = local_fixture_provider()
        fixture_state, provider_url = provider_context.__enter__()
        runtime_root = prepare_local_fixture_runtime(home, provider_url)
        blocked_request = local_request_observer()
        workspace = home / "Documents" / "AI4HEOR"
        workspace.mkdir(parents=True)
        (workspace / "untrusted-e2e.html").write_text(
            "<!doctype html><html><head><title>Passive preview fixture</title></head>"
            '<body><h1 id="passive-preview-sentinel">Passive preview content</h1>'
            f'<script src="http://127.0.0.1:{blocked_request.port}/should-not-load.js"></script>'
            '<script>document.documentElement.setAttribute('
            '"data-ai4heor-script-executed", "true")</script></body></html>',
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "TMPDIR": str(home / "tmp"),
                "XDG_CONFIG_HOME": str(home / "xdg-config"),
                "XDG_DATA_HOME": str(home / "xdg-data"),
                "XDG_CACHE_HOME": str(home / "xdg-cache"),
                "OPENCODE_CONFIG_CONTENT": (
                    runtime_root / "xdg-config/opencode/opencode.json"
                ).read_text(encoding="utf-8"),
                "TAURI_WEBDRIVER_PORT": str(port),
            }
        )
        for key in ("TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            Path(env[key]).mkdir(parents=True, exist_ok=True)

        log_path = home / "desktop-e2e.log"
        try:
            with isolate_single_instance_socket(single_instance_socket_path()):
                with log_path.open("w", encoding="utf-8") as log:
                    process = subprocess.Popen(
                        [str(BINARY)],
                        cwd=ROOT,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                wait_for_status(base_url, process)

                session = request_json(
                    base_url,
                    "POST",
                    "/session",
                    {"capabilities": {"alwaysMatch": {}}},
                )
                if not isinstance(session, dict) or not session.get("sessionId"):
                    raise AssertionError(f"WebDriver returned no session id: {session!r}")
                session_id = str(session["sessionId"])

                wait_for_script_value(
                    base_url,
                    session_id,
                    "return Boolean(window.__TAURI_INTERNALS__)",
                    True,
                )

                new_project_xpath = (
                    '//button[@aria-label="新建项目" '
                    'or @aria-label="New project"]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, new_project_xpath),
                )
                project_name_xpath = (
                    '//input[@placeholder="项目名称" '
                    'or @placeholder="Project name"]'
                )
                send_keys(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, project_name_xpath),
                    PROJECT_NAME,
                )
                press_key(base_url, session_id, "\ue007")
                project_xpath = (
                    f'//div[@data-project-id][.//span[normalize-space()={json.dumps(PROJECT_NAME)}]]'
                )
                try:
                    find_element(base_url, session_id, project_xpath, timeout=30.0)
                except AssertionError as error:
                    visible = execute(base_url, session_id, "return document.body.innerText")
                    raise AssertionError(
                        "project creation did not complete; "
                        f"visible UI excerpt: {str(visible)[-2000:]}"
                    ) from error
                wait_for_location(base_url, session_id, "/heor/new", timeout=30.0)

                new_task_xpath = (
                    '//button[.//span[normalize-space()="新建任务" '
                    'or normalize-space()="New task"]]'
                )
                click(base_url, session_id, find_element(base_url, session_id, new_task_xpath))
                wait_for_location(base_url, session_id, "/heor/new")
                if choose_fixture_model_if_required(base_url, session_id):
                    click(
                        base_url,
                        session_id,
                        find_element(base_url, session_id, new_task_xpath),
                    )
                    wait_for_location(base_url, session_id, "/heor/new")

                composer_xpath = (
                    '//textarea[@aria-label="描述研究问题或要处理的工作" '
                    'or @aria-label="Ask anything"]'
                )
                fill_composer(
                    base_url,
                    session_id,
                    composer_xpath,
                    TASK_PROMPT,
                )
                send_xpath = (
                    '//button[@aria-label="发送" or @aria-label="Send"]'
                )
                click(base_url, session_id, find_element(base_url, session_id, send_xpath))
                try:
                    task_path = wait_for_task_location(base_url, session_id)
                except AssertionError as error:
                    visible = execute(base_url, session_id, "return document.body.innerText")
                    with fixture_state.lock:
                        fixture_counts = {
                            "catalog": fixture_state.catalog_requests,
                            "messages": fixture_state.message_requests,
                        }
                    pointer = runtime_root / "active-workspace.txt"
                    pointer_value = (
                        pointer.read_text(encoding="utf-8", errors="replace").strip()
                        if pointer.is_file()
                        else "missing"
                    )
                    raise AssertionError(
                        "standalone task creation did not complete; "
                        f"fixture={fixture_counts}, active_workspace={pointer_value!r}, "
                        f"visible UI excerpt: {str(visible)[-3000:]}"
                    ) from error
                task_id = task_path.removeprefix("/heor/")
                wait_for_body_text(base_url, session_id, FIXTURE_MARKER)

                active_pointer = runtime_root / "active-workspace.txt"
                if not active_pointer.is_file():
                    raise AssertionError("standalone task did not persist its active workspace")
                standalone_workspace = Path(
                    active_pointer.read_text(encoding="utf-8").strip()
                ).resolve()
                if standalone_workspace.parent != workspace.resolve():
                    raise AssertionError(
                        "standalone task was not created below the configured base folder"
                    )
                scope_meta = json.loads(
                    (
                        standalone_workspace
                        / ".openscience/project.json"
                    ).read_text(encoding="utf-8")
                )
                if scope_meta.get("kind") != "session":
                    raise AssertionError("new task did not create a standalone research scope")
                project_dirs = []
                for candidate in workspace.iterdir():
                    metadata = candidate / ".openscience/project.json"
                    if not metadata.is_file():
                        continue
                    value = json.loads(metadata.read_text(encoding="utf-8"))
                    if value.get("kind") == "heor" and value.get("name") == PROJECT_NAME:
                        project_dirs.append(candidate.resolve())
                if len(project_dirs) != 1 or project_dirs[0] == standalone_workspace:
                    raise AssertionError("project and standalone task scopes are not isolated")

                task_attribute = "data-" + "task-" + "id"
                task_row_xpath = (
                    f'//div[@{task_attribute}={json.dumps(task_id)}]'
                )
                find_element(base_url, session_id, task_row_xpath, timeout=30.0)
                standalone_row = execute(
                    base_url,
                    session_id,
                    "const row = document.querySelector("
                    + json.dumps(f'[{task_attribute}="{task_id}"]')
                    + "); return Boolean(row && !row.closest('[data-project-id]'));",
                )
                if standalone_row is not True:
                    raise AssertionError("global new task was incorrectly grouped under a project")
                with fixture_state.lock:
                    main_requests = [
                        body
                        for body in fixture_state.message_bodies
                        if is_main_task_request(body)
                    ]
                if len(main_requests) != 1:
                    raise AssertionError(
                        "local fixture did not receive exactly one standalone task request"
                    )

                (standalone_workspace / "untrusted-e2e.html").write_text(
                    "<!doctype html><html><head><title>Passive preview fixture</title></head>"
                    '<body><h1 id="passive-preview-sentinel">Passive preview content</h1>'
                    f'<script src="http://127.0.0.1:{blocked_request.port}/should-not-load.js"></script>'
                    '<script>document.documentElement.setAttribute('
                    '"data-ai4heor-script-executed", "true")</script></body></html>',
                    encoding="utf-8",
                )

                skills_xpath = (
                    '//button[.//span[normalize-space()="插件与技能" '
                    'or normalize-space()="Plugins & skills"]]'
                )
                click(base_url, session_id, find_element(base_url, session_id, skills_xpath))
                wait_for_location(base_url, session_id, "/skills")
                body_text = execute(base_url, session_id, "return document.body.innerText")
                if not isinstance(body_text, str) or not any(
                    heading in body_text for heading in ("插件与技能", "Plugins & skills")
                ):
                    raise AssertionError("skills page did not render its researcher-facing heading")

                files_xpath = (
                    '//button[.//span[normalize-space()="任务文件" '
                    'or normalize-space()="Task files"]]'
                )
                click(base_url, session_id, find_element(base_url, session_id, files_xpath))
                wait_for_location(base_url, session_id, "/files")

                fixture_xpath = (
                    '//button[.//span[normalize-space()="untrusted-e2e.html"]]'
                )
                fixture_id = find_stable_element(base_url, session_id, fixture_xpath)
                execute(
                    base_url,
                    session_id,
                    "window.__ai4heorE2ELastClick = null; "
                    "document.addEventListener('click', function capture(event) { "
                    "window.__ai4heorE2ELastClick = "
                    "event.target instanceof Element ? event.target.outerHTML : String(event.target); "
                    "}, { once: true }); return true;",
                )
                click(base_url, session_id, fixture_id)
                frame_xpath = '//iframe[@title="HTML 预览" or @title="HTML preview"]'
                try:
                    frame_id = find_element(base_url, session_id, frame_xpath)
                except AssertionError as error:
                    visible = execute(base_url, session_id, "return document.body.innerText")
                    excerpt = visible[-2000:] if isinstance(visible, str) else repr(visible)
                    click_target = execute(
                        base_url,
                        session_id,
                        "return window.__ai4heorE2ELastClick || ''",
                    )
                    raise AssertionError(
                        "HTML preview frame did not appear; "
                        f"captured click target: {click_target}; visible UI excerpt: {excerpt}"
                    ) from error
                if element_attribute(base_url, session_id, frame_id, "sandbox") != "":
                    raise AssertionError("HTML preview iframe unexpectedly grants sandbox capabilities")
                frame_src = element_attribute(base_url, session_id, frame_id, "src")
                if not isinstance(frame_src, str) or not frame_src.startswith("http://127.0.0.1:"):
                    raise AssertionError("HTML preview did not use its loopback file server")
                with urlopen(Request(frame_src, method="HEAD"), timeout=5.0) as response:
                    csp = response.headers.get("Content-Security-Policy", "")
                    referrer_policy = response.headers.get("Referrer-Policy", "")
                if "script-src 'none'" not in csp or "connect-src 'none'" not in csp:
                    raise AssertionError("HTML preview response is missing its passive-document CSP")
                if referrer_policy != "no-referrer":
                    raise AssertionError("HTML preview response may disclose its source URL")

                load_listener_installed = execute(
                    base_url,
                    session_id,
                    "const frame = document.querySelector("
                    "'iframe[title=\"HTML preview\"], iframe[title=\"HTML 预览\"]'); "
                    "if (!frame) return false; "
                    "window.__ai4heorE2EHtmlLoaded = false; "
                    "frame.addEventListener('load', () => { "
                    "window.__ai4heorE2EHtmlLoaded = true; }, { once: true }); "
                    "frame.setAttribute('src', frame.getAttribute('src')); return true;",
                )
                if load_listener_installed is not True:
                    raise AssertionError("could not observe the HTML preview frame load")
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return window.__ai4heorE2EHtmlLoaded === true",
                    True,
                )
                if blocked_request.requested.wait(timeout=1.0):
                    raise AssertionError("untrusted HTML requested an external script")
                assert_no_admitted_asset_deployment_errors(log_path)

                print(
                    "native desktop E2E passed: Tauri bridge, navigation, "
                    "task files and passive HTML preview"
                )
        except Exception as error:
            tail = ""
            if log_path.is_file():
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
            raise AssertionError(f"{error}; app log tail: {tail}") from error
        finally:
            if session_id is not None:
                try:
                    request_json(base_url, "DELETE", f"/session/{session_id}")
                except Exception:
                    pass
            if process is not None:
                terminate(process)
            blocked_request.close()
            provider_context.__exit__(None, None, None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Drive real AI4HEOR controls through the test-only embedded WebDriver.

This smoke test intentionally uses only Python's standard library. It launches
the debug binary with an isolated user home, clicks two rendered sidebar items,
and proves that the page is running inside Tauri rather than a browser preview.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import stat
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "apps/desktop/src-tauri/target/debug/ai4s-workbench"
BUNDLE_IDENTIFIER = "com.ai4s.ai4heor"
ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


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
    while time.monotonic() < deadline:
        last_value = execute(base_url, session_id, script)
        if last_value == expected:
            return
        time.sleep(0.2)
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


def click(base_url: str, session_id: str, element_id: str) -> None:
    request_json(
        base_url,
        "POST",
        f"/session/{session_id}/element/{element_id}/click",
        {},
    )


def wait_for_location(base_url: str, session_id: str, pathname: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if execute(base_url, session_id, "return window.location.pathname") == pathname:
            return
        time.sleep(0.2)
    raise AssertionError(f"page did not navigate to {pathname}")


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
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


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
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "TMPDIR": str(home / "tmp"),
                "XDG_CONFIG_HOME": str(home / "xdg-config"),
                "XDG_DATA_HOME": str(home / "xdg-data"),
                "XDG_CACHE_HOME": str(home / "xdg-cache"),
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

                new_task_xpath = (
                    '//button[.//span[normalize-space()="新建任务" '
                    'or normalize-space()="New task"]]'
                )
                click(base_url, session_id, find_element(base_url, session_id, new_task_xpath))
                wait_for_location(base_url, session_id, "/heor/new")

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

                print("native desktop E2E passed: Tauri bridge, new task, plugins and skills")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

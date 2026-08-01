#!/usr/bin/env python3
"""Drive real AI4HEOR controls through the test-only embedded WebDriver.

This smoke test intentionally uses only Python's standard library. It launches
the debug binary with an isolated user home, drives rendered sidebar and file
controls, and proves that navigation and passive HTML preview run inside Tauri
rather than a browser preview.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import signal
import socket
import sqlite3
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
    AUDIT_RUN_COMMAND as FIXTURE_AUDIT_RUN_COMMAND,
    BASH_ALWAYS_COMMAND as FIXTURE_BASH_ALWAYS_COMMAND,
    BASH_ALWAYS_SENTINEL as FIXTURE_BASH_ALWAYS_SENTINEL,
    BASH_COMMAND as FIXTURE_BASH_COMMAND,
    BASH_REJECT_COMMAND as FIXTURE_BASH_REJECT_COMMAND,
    BASH_REJECT_SENTINEL as FIXTURE_BASH_REJECT_SENTINEL,
    CREDENTIAL as FIXTURE_CREDENTIAL,
    MARKER as FIXTURE_MARKER,
    MODEL_ID as FIXTURE_MODEL_ID,
    PROVIDER_ERROR_MESSAGE as FIXTURE_PROVIDER_ERROR_MESSAGE,
    PROVIDER_ID as FIXTURE_PROVIDER_ID,
    QUESTION_OPTION as FIXTURE_QUESTION_OPTION,
    QUESTION_TEXT as FIXTURE_QUESTION_TEXT,
    FixtureState,
    handler as fixture_handler,
)


PROJECT_NAME = "AI4HEOR E2E project"
TASK_PROMPT = "AI4HEOR E2E standalone task"
QUEUE_PROMPTS = (
    "AI4HEOR E2E queued first",
    "AI4HEOR E2E queued second",
    "AI4HEOR E2E queued third",
)
QUESTION_TRIGGER_PROMPT = "AI4HEOR E2E request researcher input"
QUESTION_QUEUED_PROMPT = "AI4HEOR E2E queued behind researcher input"
PERMISSION_TRIGGER_PROMPT = "AI4HEOR E2E request one-time command permission"
PERMISSION_QUEUED_PROMPT = "AI4HEOR E2E queued behind command permission"
AUDIT_RUN_TRIGGER_PROMPT = "AI4HEOR E2E record one harmless local analysis run"
PERMISSION_REJECT_TRIGGER_PROMPT = "AI4HEOR E2E reject command permission"
PERMISSION_REJECT_QUEUED_PROMPT = "AI4HEOR E2E queued behind rejected permission"
PERMISSION_ALWAYS_TRIGGER_PROMPT = "AI4HEOR E2E remember exact command permission"
PERMISSION_ALWAYS_REPEAT_PROMPT = "AI4HEOR E2E repeat remembered command permission"
PERMISSION_AFTER_RESTART_PROMPT = "AI4HEOR E2E reuse remembered permission after restart"
PERMISSION_AFTER_REVOKE_PROMPT = "AI4HEOR E2E ask again after remembered permission revoke"
PROVIDER_FAILURE_TRIGGER_PROMPT = "AI4HEOR E2E trigger one provider failure"
PROVIDER_FAILURE_QUEUED_PROMPT = "AI4HEOR E2E queued after provider failure"
IMPORTED_PROJECT_NAME = "AI4HEOR E2E imported project"
IMPORTED_PROJECT_TASK_PROMPT = "AI4HEOR E2E task inside imported project"


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def snapshot_source_tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def prepare_import_export_fixture(parent: Path) -> Path:
    """Create bounded synthetic report inputs, never research evidence."""
    source = parent / IMPORTED_PROJECT_NAME
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/dev/create_heor_acceptance_fixture.py"),
            str(source),
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    heor = source / "heor"
    results = heor / "results"
    deliverables = source / "deliverables"
    results.mkdir(parents=True, exist_ok=True)
    deliverables.mkdir(parents=True)
    (source / "SOURCE-MUST-NOT-CHANGE.txt").write_text(
        "Synthetic native acceptance source; AI4HEOR must only change its imported copy.\n",
        encoding="utf-8",
    )

    analysis_raw = (heor / "analysis-plan.json").read_bytes()
    uncertainty_plan_raw = (heor / "uncertainty-plan.json").read_bytes()
    budget_plan_raw = (heor / "budget-impact-plan.json").read_bytes()
    analysis_id = str(json.loads(analysis_raw)["analysis_id"])
    base_case = {
        "analysis_id": analysis_id,
        "input_sha256": sha256(analysis_raw),
        "economic_basis": {"currency": "CNY", "price_year": 2026},
        "strategy_order": ["standard", "treatment"],
        "baseline_strategy_id": "standard",
        "strategies": {
            "standard": {"name": "Standard", "total_cost": 10000, "total_qaly": 1, "net_monetary_benefit": 90000},
            "treatment": {"name": "Treatment", "total_cost": 20000, "total_qaly": 1.5, "net_monetary_benefit": 130000},
        },
        "pairwise_vs_baseline": {"treatment": {"delta_cost": 10000, "delta_qaly": 0.5, "icer": 20000}},
        "fully_incremental_analysis": [
            {"strategy_id": "standard", "status": "frontier", "icer": None},
            {"strategy_id": "treatment", "status": "frontier", "icer": 20000},
        ],
        "optimal_at_primary_threshold": {"strategy_id": "treatment"},
    }
    uncertainty_result = {
        "analysis_id": analysis_id,
        "base_analysis_sha256": sha256(analysis_raw),
        "uncertainty_plan_sha256": sha256(uncertainty_plan_raw),
        "probabilistic_analysis": {
            "iterations": 1000,
            "strategy_order": ["standard", "treatment"],
            "primary_threshold_strategy_optimal_probabilities": {"standard": 0.2, "treatment": 0.8},
            "primary_threshold_tie_probability": 0,
            "mean_net_monetary_benefit_by_strategy": {"standard": 90000, "treatment": 130000},
            "net_monetary_benefit_mcse_by_strategy": {"standard": 100, "treatment": 120},
            "decision_uncertainty": {"strategy_order": ["standard", "treatment"], "threshold_results": []},
        },
    }
    budget_result = {
        "analysis_id": analysis_id,
        "analysis_plan_sha256": sha256(analysis_raw),
        "budget_impact_plan_sha256": sha256(budget_plan_raw),
        "base_case": {"annual_net_budget_impact": [1, 2, 3], "cumulative_net_budget_impact": 6},
    }
    report_template = json.loads(
        (ROOT / "runtime/skills/core/heor-reporting/assets/report-package.template.json")
        .read_text(encoding="utf-8")
    )
    report_items = []
    report_sections = []
    for index, item in enumerate(report_template["items"], start=1):
        section_id = item["section_id"]
        report_sections.append(
            f"<!-- report-section:{section_id} -->\n## {index}. Synthetic acceptance section\n"
            "This content validates native export plumbing only; it is not research evidence.\n"
        )
        report_items.append(
            {
                **item,
                "status": "reported",
                "rationale": "Synthetic content exercises the native export contract.",
                "artifact_paths": ["heor/report.md"],
            }
        )
    report_raw = "\n".join(report_sections).encode("utf-8")

    artifacts = {
        "heor/report.md": report_raw,
        "heor/analysis-plan.json": analysis_raw,
        "heor/conceptual-model.json": (heor / "conceptual-model.json").read_bytes(),
        "heor/uncertainty-plan.json": uncertainty_plan_raw,
        "heor/budget-impact-plan.json": budget_plan_raw,
        "heor/model-validation.json": json_bytes({"analysis_id": analysis_id}),
        "heor/results/base-case.json": json_bytes(base_case),
        "heor/results/uncertainty.json": json_bytes(uncertainty_result),
        "heor/results/budget-impact.json": json_bytes(budget_result),
    }
    for relative, raw in artifacts.items():
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    result_summary = {
        "cost_effectiveness": {
            "economic_basis": base_case["economic_basis"],
            "strategy_order": base_case["strategy_order"],
            "baseline_strategy_id": base_case["baseline_strategy_id"],
            "strategies": base_case["strategies"],
            "pairwise_vs_baseline": base_case["pairwise_vs_baseline"],
            "fully_incremental_analysis": base_case["fully_incremental_analysis"],
            "optimal_at_primary_threshold": base_case["optimal_at_primary_threshold"],
        },
        "uncertainty": {
            "iterations": 1000,
            "cost_effective_probability": None,
            "mean_incremental_net_monetary_benefit": None,
            "decision_uncertainty": uncertainty_result["probabilistic_analysis"]["decision_uncertainty"],
            "strategy_order": ["standard", "treatment"],
            "primary_threshold_strategy_optimal_probabilities": {"standard": 0.2, "treatment": 0.8},
            "primary_threshold_tie_probability": 0,
            "mean_net_monetary_benefit_by_strategy": {"standard": 90000, "treatment": 130000},
            "net_monetary_benefit_mcse_by_strategy": {"standard": 100, "treatment": 120},
        },
        "budget_impact": {"annual_net_budget_impact": [1, 2, 3], "cumulative_net_budget_impact": 6},
    }
    report_package = {
        "schema_version": "0.1.0",
        "package_id": "native-import-export-report",
        "analysis_id": analysis_id,
        "version": "1.0",
        "status": "ready_for_release_review",
        "prepared_on": "2026-08-01",
        "intended_audience": "AI4HEOR native acceptance test",
        "release_owner_label": "Synthetic acceptance reviewer",
        "reporting_profiles": report_template["reporting_profiles"],
        "bindings": {
            key: {"path": binding["path"], "content_sha256": sha256(artifacts[binding["path"]])}
            for key, binding in report_template["bindings"].items()
        },
        "items": report_items,
        "result_summary": result_summary,
        "disclosures": {
            "funding": "Synthetic acceptance fixture",
            "conflicts_of_interest": "Synthetic acceptance fixture",
            "agent_contributions": "Synthetic acceptance fixture",
            "model_providers": "Local deterministic fixture provider",
            "data_and_model_availability": "Generated inside an isolated temporary directory",
            "patient_and_public_involvement": "Not applicable to this synthetic fixture",
        },
        "limitations": ["The fixture validates product controls and makes no scientific claim."],
        "release_notes": ["Native import and export acceptance fixture."],
    }
    package_raw = json_bytes(report_package)
    (heor / "report-package.json").write_bytes(package_raw)
    export_manifest = {
        "schema_version": "0.1.0",
        "document_id": "native-import-export-report",
        "title": "AI4HEOR native import and export acceptance report",
        "subtitle": "Synthetic product test; not research evidence",
        "language": "en",
        "prepared_on": "2026-08-01",
        "audience": "AI4HEOR native acceptance test",
        "purpose": "Verify that imported project results can be exported deterministically.",
        "style": "ai4heor-formal-report",
        "report_package": {"path": "heor/report-package.json", "sha256": sha256(package_raw)},
        "report_document": {"path": "heor/report.md", "sha256": sha256(report_raw)},
        "human_review": {"status": "awaiting_human_review"},
    }
    (deliverables / "heor-report-export.json").write_bytes(json_bytes(export_manifest))
    return source


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


def invoke_tauri(
    base_url: str,
    session_id: str,
    command: str,
    arguments: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> Any:
    slot = "__ai4heorE2EInvoke"
    started = execute(
        base_url,
        session_id,
        f"window.{slot} = {{state: 'pending'}}; "
        f"window.__TAURI_INTERNALS__.invoke({json.dumps(command)}, "
        f"{json.dumps(arguments or {})}).then((value) => {{ "
        f"window.{slot} = {{state: 'done', value}}; "
        f"}}).catch((error) => {{ window.{slot} = {{state: 'error', "
        "error: String(error)}; }); return true;",
    )
    if started is not True:
        raise AssertionError(f"could not start native command {command}")
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = execute(base_url, session_id, f"return window.{slot}")
        if isinstance(last, dict) and last.get("state") == "done":
            return last.get("value")
        if isinstance(last, dict) and last.get("state") == "error":
            raise AssertionError(f"native command {command} failed: {last.get('error')}")
        time.sleep(0.2)
    raise AssertionError(f"native command {command} timed out; last state was {last!r}")


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
    action_xpath: str,
    timeout: float = 30.0,
) -> str:
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
            action_id = find_element(
                base_url,
                session_id,
                action_xpath,
                timeout=2.0,
            )
            disabled = element_attribute(
                base_url,
                session_id,
                action_id,
                "disabled",
            )
            if (
                element_attribute(base_url, session_id, element_id, "value") == expected
                and disabled not in (True, "true")
            ):
                return action_id
            last_error = None
        except (AssertionError, URLError, TimeoutError, ConnectionError) as error:
            last_error = error
        time.sleep(0.2)
    visible = execute(base_url, session_id, "return document.body.innerText")
    raise AssertionError(
        "composer did not become sendable with the expected text; "
        f"last_error={last_error}, visible UI excerpt: {str(visible)[-2000:]}"
    )


def is_main_provider_request(body: dict[str, Any]) -> bool:
    return isinstance(body.get("tools"), list) and bool(body["tools"])


def latest_user_text(body: dict[str, Any]) -> str:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                part["text"]
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
    return ""


def is_main_task_request(body: dict[str, Any]) -> bool:
    return is_main_provider_request(body) and TASK_PROMPT in latest_user_text(body)


def wait_for_main_request_prompts(
    state: FixtureState,
    expected: list[str],
    timeout: float = 60.0,
) -> None:
    deadline = time.monotonic() + timeout
    observed: list[str] = []
    candidates = [
        TASK_PROMPT,
        *QUEUE_PROMPTS,
        QUESTION_TRIGGER_PROMPT,
        QUESTION_QUEUED_PROMPT,
        PERMISSION_TRIGGER_PROMPT,
        PERMISSION_QUEUED_PROMPT,
        AUDIT_RUN_TRIGGER_PROMPT,
        PERMISSION_REJECT_TRIGGER_PROMPT,
        PERMISSION_REJECT_QUEUED_PROMPT,
        PERMISSION_ALWAYS_TRIGGER_PROMPT,
        PERMISSION_ALWAYS_REPEAT_PROMPT,
        PERMISSION_AFTER_RESTART_PROMPT,
        PERMISSION_AFTER_REVOKE_PROMPT,
    ]
    while time.monotonic() < deadline:
        with state.lock:
            bodies = list(state.message_bodies)
        observed = []
        for body in bodies:
            if not is_main_provider_request(body):
                continue
            user_text = latest_user_text(body)
            matched = next((prompt for prompt in candidates if prompt in user_text), None)
            if matched is not None:
                observed.append(matched)
        if observed == expected:
            return
        time.sleep(0.2)
    raise AssertionError(
        f"local fixture received main prompts in {observed!r}, expected {expected!r}"
    )


def wait_for_saved_permission(
    runtime_root: Path,
    action: str,
    resource: str,
    timeout: float = 30.0,
) -> str:
    data_dir = runtime_root / "xdg-data/opencode"
    deadline = time.monotonic() + timeout
    observed: dict[str, list[tuple[Any, ...]]] = {}
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        for database_path in sorted(data_dir.glob("opencode*.db")):
            try:
                with sqlite3.connect(
                    f"file:{database_path}?mode=ro",
                    uri=True,
                    timeout=1.0,
                ) as database:
                    rows = database.execute(
                        "SELECT project_id, action, resource "
                        "FROM permission ORDER BY project_id, action, resource"
                    ).fetchall()
                observed[str(database_path)] = rows
                if len(rows) != 1:
                    continue
                project_id, saved_action, saved_resource = rows[0]
                if (
                    isinstance(project_id, str)
                    and project_id
                    and saved_action == action
                    and saved_resource == resource
                ):
                    return project_id
            except sqlite3.Error as error:
                last_error = error
        time.sleep(0.2)
    raise AssertionError(
        "OpenCode did not persist exactly one project-bound permission rule; "
        f"observed={observed!r}, last_error={last_error}"
    )


def wait_for_no_saved_permissions(
    runtime_root: Path,
    timeout: float = 30.0,
) -> None:
    data_dir = runtime_root / "xdg-data/opencode"
    deadline = time.monotonic() + timeout
    observed: dict[str, list[tuple[Any, ...]]] = {}
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        observed.clear()
        for database_path in sorted(data_dir.glob("opencode*.db")):
            try:
                with sqlite3.connect(
                    f"file:{database_path}?mode=ro",
                    uri=True,
                    timeout=1.0,
                ) as database:
                    rows = database.execute(
                        "SELECT project_id, action, resource "
                        "FROM permission ORDER BY project_id, action, resource"
                    ).fetchall()
                observed[str(database_path)] = rows
            except sqlite3.Error as error:
                last_error = error
        if observed and all(not rows for rows in observed.values()):
            return
        time.sleep(0.2)
    raise AssertionError(
        "OpenCode did not remove the project-bound permission rule; "
        f"observed={observed!r}, last_error={last_error}"
    )


def wait_for_session_project(
    runtime_root: Path,
    session_id: str,
    expected_project_id: str,
    timeout: float = 30.0,
) -> None:
    data_dir = runtime_root / "xdg-data/opencode"
    deadline = time.monotonic() + timeout
    observed: dict[str, list[tuple[Any, ...]]] = {}
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        for database_path in sorted(data_dir.glob("opencode*.db")):
            try:
                with sqlite3.connect(
                    f"file:{database_path}?mode=ro",
                    uri=True,
                    timeout=1.0,
                ) as database:
                    rows = database.execute(
                        "SELECT project_id, directory FROM session WHERE id = ?",
                        (session_id,),
                    ).fetchall()
                observed[str(database_path)] = rows
                if any(row[0] == expected_project_id for row in rows):
                    return
            except sqlite3.Error as error:
                last_error = error
        time.sleep(0.2)
    raise AssertionError(
        "reopened session did not resolve to the saved permission project; "
        f"observed={observed!r}, expected={expected_project_id!r}, last_error={last_error}"
    )


def wait_for_session_directory(
    runtime_root: Path,
    session_id: str,
    expected_directory: Path,
    timeout: float = 30.0,
) -> None:
    data_dir = runtime_root / "xdg-data/opencode"
    deadline = time.monotonic() + timeout
    observed: dict[str, list[tuple[Any, ...]]] = {}
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        for database_path in sorted(data_dir.glob("opencode*.db")):
            try:
                with sqlite3.connect(
                    f"file:{database_path}?mode=ro",
                    uri=True,
                    timeout=1.0,
                ) as database:
                    rows = database.execute(
                        "SELECT project_id, directory FROM session WHERE id = ?",
                        (session_id,),
                    ).fetchall()
                observed[str(database_path)] = rows
                if any(
                    Path(str(row[1])).resolve() == expected_directory.resolve()
                    for row in rows
                ):
                    return
            except sqlite3.Error as error:
                last_error = error
        time.sleep(0.2)
    raise AssertionError(
        "session did not retain the imported project directory; "
        f"observed={observed!r}, expected={str(expected_directory)!r}, "
        f"last_error={last_error}"
    )


def permission_database_snapshot(runtime_root: Path) -> dict[str, dict[str, list[tuple[Any, ...]]]]:
    snapshot: dict[str, dict[str, list[tuple[Any, ...]]]] = {}
    for database_path in sorted((runtime_root / "xdg-data/opencode").glob("opencode*.db")):
        tables: dict[str, list[tuple[Any, ...]]] = {}
        try:
            with sqlite3.connect(
                f"file:{database_path}?mode=ro",
                uri=True,
                timeout=1.0,
            ) as database:
                tables["permission"] = database.execute(
                    "SELECT id, project_id, action, resource FROM permission ORDER BY project_id"
                ).fetchall()
                tables["session"] = database.execute(
                    "SELECT id, project_id, directory FROM session ORDER BY id"
                ).fetchall()
                tables["project"] = database.execute(
                    "SELECT id, worktree, vcs FROM project ORDER BY id"
                ).fetchall()
                tables["project_directory"] = database.execute(
                    "SELECT project_id, directory FROM project_directory ORDER BY project_id, directory"
                ).fetchall()
        except sqlite3.Error as error:
            tables["error"] = [(str(error),)]
        snapshot[str(database_path)] = tables
    return snapshot


def wait_for_path_missing(path: Path, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not path.exists():
            return
        time.sleep(0.2)
    raise AssertionError(f"path was not removed before timeout: {path}")


def wait_for_export_outputs(workspace: Path, timeout: float = 60.0) -> None:
    expected = [
        workspace / "deliverables/heor-report.docx",
        workspace / "deliverables/heor-report.pdf",
        workspace / "deliverables/heor-report.xlsx",
    ]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(path.is_file() and path.stat().st_size > 0 for path in expected):
            return
        time.sleep(0.2)
    state = {str(path): path.stat().st_size if path.is_file() else None for path in expected}
    raise AssertionError(f"native report outputs were not generated: {state}")


def wait_for_active_workspace(
    pointer: Path,
    expected: Path,
    timeout: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout
    observed: str | None = None
    while time.monotonic() < deadline:
        if pointer.is_file():
            observed = pointer.read_text(encoding="utf-8").strip()
            if observed and Path(observed).resolve() == expected.resolve():
                return
        time.sleep(0.2)
    raise AssertionError(
        f"desktop did not switch back to the task workspace; observed={observed!r}, "
        f"expected={str(expected)!r}"
    )


def main_provider_requests(state: FixtureState) -> list[dict[str, Any]]:
    with state.lock:
        return [
            body
            for body in state.message_bodies
            if is_main_provider_request(body)
        ]


def wait_for_main_request_count(
    state: FixtureState,
    expected: int,
    timeout: float = 60.0,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    requests: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        requests = main_provider_requests(state)
        if len(requests) == expected:
            return requests
        if len(requests) > expected:
            break
        time.sleep(0.2)
    with state.lock:
        all_requests = list(state.message_bodies)
    recent = [
        {
            "main": is_main_provider_request(body),
            "user": latest_user_text(body)[-200:],
            "tools": len(body.get("tools", [])) if isinstance(body.get("tools"), list) else None,
        }
        for body in all_requests[-5:]
    ]
    raise AssertionError(
        f"local fixture received {len(requests)} main requests, expected {expected}; "
        f"recent requests={recent!r}"
    )


def assert_prompt_not_sent(
    state: FixtureState,
    prompt: str,
    duration: float = 1.0,
) -> None:
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        if any(prompt in latest_user_text(body) for body in main_provider_requests(state)):
            raise AssertionError(f"queued prompt was sent while Human input was pending: {prompt}")
        time.sleep(0.1)


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


def start_desktop_session(
    base_url: str,
    env: dict[str, str],
    log_path: Path,
    append_log: bool = False,
) -> tuple[subprocess.Popen[str], str]:
    with log_path.open("a" if append_log else "w", encoding="utf-8") as log:
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
        terminate(process)
        raise AssertionError(f"WebDriver returned no session id: {session!r}")
    return process, str(session["sessionId"])


def restart_desktop_session(
    base_url: str,
    session_id: str,
    process: subprocess.Popen[str],
    env: dict[str, str],
    log_path: Path,
) -> tuple[subprocess.Popen[str], str]:
    try:
        request_json(base_url, "DELETE", f"/session/{session_id}")
    except Exception:
        pass
    terminate(process)
    socket_path = single_instance_socket_path()
    if socket_path.exists():
        if not stat.S_ISSOCK(socket_path.lstat().st_mode):
            raise AssertionError(f"unexpected non-socket at {socket_path}")
        socket_path.unlink()
    return start_desktop_session(base_url, env, log_path, append_log=True)


def main() -> int:
    if platform.system() != "Darwin":
        raise SystemExit("native desktop E2E currently requires macOS")
    if not BINARY.is_file():
        raise SystemExit(f"test binary not found: {BINARY}")

    port = free_local_port()
    base_url = f"http://127.0.0.1:{port}"
    session_id: str | None = None
    process: subprocess.Popen[str] | None = None
    release_provider_failure: threading.Event | None = None

    with tempfile.TemporaryDirectory(prefix="ai4heor-desktop-e2e-", dir="/private/tmp") as temporary:
        home = Path(temporary).resolve()
        provider_context = local_fixture_provider()
        fixture_state, provider_url = provider_context.__enter__()
        main_reply_waiting, release_main_reply = fixture_state.pause_next_main_reply()
        runtime_root = prepare_local_fixture_runtime(home, provider_url)
        blocked_request = local_request_observer()
        imported_source = prepare_import_export_fixture(home / "External")
        imported_source_snapshot = snapshot_source_tree(imported_source)
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
                process, session_id = start_desktop_session(base_url, env, log_path)

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
                send_xpath = (
                    '//button[@aria-label="发送" or @aria-label="Send"]'
                )
                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        TASK_PROMPT,
                        send_xpath,
                    ),
                )
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
                if not main_reply_waiting.wait(timeout=30.0):
                    raise AssertionError(
                        "local fixture did not pause the standalone task reply"
                    )

                queue_add_xpath = (
                    '//button[@aria-label="加入待发送队列" '
                    'or @aria-label="Add to send queue"]'
                )
                for prompt in QUEUE_PROMPTS:
                    click(
                        base_url,
                        session_id,
                        fill_composer(
                            base_url,
                            session_id,
                            composer_xpath,
                            prompt,
                            queue_add_xpath,
                        ),
                    )
                    wait_for_body_text(base_url, session_id, prompt)

                move_third_up_xpath = (
                    '//button[@aria-label="将第 3 条消息上移" '
                    'or @aria-label="Move message 3 up"]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, move_third_up_xpath),
                )
                remove_first_xpath = (
                    '//button[@aria-label="删除第 1 条待发送消息" '
                    'or @aria-label="Remove queued message 1"]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, remove_first_xpath),
                )
                queue_items_script = (
                    "const section = [...document.querySelectorAll('section')].find((node) => "
                    "['待发送', 'Waiting to send'].includes(node.getAttribute('aria-label'))); "
                    "return section ? [...section.querySelectorAll('ol > li p[title]')]"
                    ".map((node) => node.getAttribute('title')) : null;"
                )
                expected_queue = [QUEUE_PROMPTS[2], QUEUE_PROMPTS[1]]
                wait_for_script_value(
                    base_url,
                    session_id,
                    queue_items_script,
                    expected_queue,
                )

                release_main_reply.set()
                wait_for_main_request_prompts(
                    fixture_state,
                    [TASK_PROMPT, *expected_queue],
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    queue_items_script,
                    None,
                    timeout=60.0,
                )
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
                task_link_xpath = f"{task_row_xpath}//a"
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

                provider_failure_waiting, release_provider_failure = (
                    fixture_state.pause_next_main_reply()
                )
                fixture_state.provider_error_next_main_reply()
                provider_failure_request_count = len(
                    main_provider_requests(fixture_state)
                )
                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        PROVIDER_FAILURE_TRIGGER_PROMPT,
                        send_xpath,
                    ),
                )
                if not provider_failure_waiting.wait(timeout=30.0):
                    raise AssertionError(
                        "local fixture did not pause the provider failure"
                    )
                failed_requests = wait_for_main_request_count(
                    fixture_state,
                    provider_failure_request_count + 1,
                )
                if PROVIDER_FAILURE_TRIGGER_PROMPT not in latest_user_text(
                    failed_requests[-1]
                ):
                    raise AssertionError(
                        "provider failure was not bound to the triggering turn"
                    )
                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        PROVIDER_FAILURE_QUEUED_PROMPT,
                        queue_add_xpath,
                    ),
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    queue_items_script,
                    [PROVIDER_FAILURE_QUEUED_PROMPT],
                )
                assert_prompt_not_sent(
                    fixture_state,
                    PROVIDER_FAILURE_QUEUED_PROMPT,
                )
                release_provider_failure.set()
                wait_for_body_text(
                    base_url,
                    session_id,
                    FIXTURE_PROVIDER_ERROR_MESSAGE,
                    timeout=60.0,
                )
                try:
                    recovered_requests = wait_for_main_request_count(
                        fixture_state,
                        provider_failure_request_count + 2,
                    )
                except AssertionError as error:
                    visible = execute(base_url, session_id, "return document.body.innerText")
                    queue_state = execute(base_url, session_id, queue_items_script)
                    interaction_state = execute(
                        base_url,
                        session_id,
                        "const input = document.querySelector('textarea'); "
                        "return { path: location.pathname, inputDisabled: input ? input.disabled : null, "
                        "inputReadOnly: input ? input.readOnly : null, "
                        "hasStop: Boolean(document.querySelector("
                        "'button[aria-label=\"停止\"], button[aria-label=\"Stop\"]')) };",
                    )
                    raise AssertionError(
                        "provider failure queue did not recover; "
                        f"queue={queue_state!r}, interaction={interaction_state!r}, "
                        f"visible={str(visible)[-2500:]}"
                    ) from error
                if PROVIDER_FAILURE_QUEUED_PROMPT not in latest_user_text(
                    recovered_requests[-1]
                ):
                    raise AssertionError(
                        "provider failure did not release exactly one queued turn"
                    )
                wait_for_script_value(
                    base_url,
                    session_id,
                    queue_items_script,
                    None,
                    timeout=60.0,
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return !document.querySelector("
                    "'button[aria-label=\"停止\"], button[aria-label=\"Stop\"]')",
                    True,
                    timeout=60.0,
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    "const input = document.querySelector('textarea'); "
                    "return Boolean(input && !input.disabled && !input.readOnly)",
                    True,
                    timeout=30.0,
                )
                time.sleep(1.0)
                if len(main_provider_requests(fixture_state)) != provider_failure_request_count + 2:
                    raise AssertionError(
                        "provider failure did not release exactly one queued turn"
                    )

                fixture_state.question_next_main_reply()
                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        QUESTION_TRIGGER_PROMPT,
                        send_xpath,
                    ),
                )
                wait_for_body_text(
                    base_url,
                    session_id,
                    FIXTURE_QUESTION_TEXT,
                    timeout=60.0,
                )
                wait_for_main_request_prompts(
                    fixture_state,
                    [
                        TASK_PROMPT,
                        QUEUE_PROMPTS[2],
                        QUEUE_PROMPTS[1],
                        QUESTION_TRIGGER_PROMPT,
                    ],
                )
                question_request_count = len(main_provider_requests(fixture_state))

                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        QUESTION_QUEUED_PROMPT,
                        queue_add_xpath,
                    ),
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    queue_items_script,
                    [QUESTION_QUEUED_PROMPT],
                )
                assert_prompt_not_sent(
                    fixture_state,
                    QUESTION_QUEUED_PROMPT,
                )

                question_option_xpath = (
                    f'//button[.//span[normalize-space()={json.dumps(FIXTURE_QUESTION_OPTION)}]]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, question_option_xpath),
                )
                submit_question_xpath = (
                    '//button[normalize-space()="提交" or normalize-space()="Submit"]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, submit_question_xpath),
                )
                continued_requests = wait_for_main_request_count(
                    fixture_state,
                    question_request_count + 1,
                )
                if FIXTURE_QUESTION_OPTION not in json.dumps(
                    continued_requests[-1].get("messages"),
                    ensure_ascii=False,
                ):
                    raise AssertionError(
                        "researcher answer did not reach the resumed model request"
                    )
                wait_for_main_request_prompts(
                    fixture_state,
                    [
                        TASK_PROMPT,
                        QUEUE_PROMPTS[2],
                        QUEUE_PROMPTS[1],
                        QUESTION_TRIGGER_PROMPT,
                        QUESTION_QUEUED_PROMPT,
                    ],
                )
                wait_for_main_request_count(
                    fixture_state,
                    question_request_count + 2,
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    queue_items_script,
                    None,
                    timeout=60.0,
                )

                fixture_state.bash_next_main_reply()
                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        PERMISSION_TRIGGER_PROMPT,
                        send_xpath,
                    ),
                )
                wait_for_body_text(
                    base_url,
                    session_id,
                    FIXTURE_BASH_COMMAND,
                    timeout=60.0,
                )
                wait_for_main_request_prompts(
                    fixture_state,
                    [
                        TASK_PROMPT,
                        QUEUE_PROMPTS[2],
                        QUEUE_PROMPTS[1],
                        QUESTION_TRIGGER_PROMPT,
                        QUESTION_QUEUED_PROMPT,
                        PERMISSION_TRIGGER_PROMPT,
                    ],
                )
                permission_request_count = len(main_provider_requests(fixture_state))

                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        PERMISSION_QUEUED_PROMPT,
                        queue_add_xpath,
                    ),
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    queue_items_script,
                    [PERMISSION_QUEUED_PROMPT],
                )
                assert_prompt_not_sent(
                    fixture_state,
                    PERMISSION_QUEUED_PROMPT,
                )

                allow_once_xpath = (
                    '//button[normalize-space()="仅允许一次" '
                    'or normalize-space()="Allow once"]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, allow_once_xpath),
                )
                permission_continuation = wait_for_main_request_count(
                    fixture_state,
                    permission_request_count + 1,
                )[-1]
                permission_messages = json.dumps(
                    permission_continuation.get("messages"),
                    ensure_ascii=False,
                )
                if (
                    "tool_result" not in permission_messages
                    or "toolu_fixture_bash" not in permission_messages
                ):
                    raise AssertionError(
                        "one-time command permission did not execute and resume the original turn"
                    )
                wait_for_main_request_prompts(
                    fixture_state,
                    [
                        TASK_PROMPT,
                        QUEUE_PROMPTS[2],
                        QUEUE_PROMPTS[1],
                        QUESTION_TRIGGER_PROMPT,
                        QUESTION_QUEUED_PROMPT,
                        PERMISSION_TRIGGER_PROMPT,
                        PERMISSION_QUEUED_PROMPT,
                    ],
                )
                wait_for_main_request_count(
                    fixture_state,
                    permission_request_count + 2,
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    queue_items_script,
                    None,
                    timeout=60.0,
                )

                fixture_state.audit_run_next_main_reply()
                audit_run_request_count = len(main_provider_requests(fixture_state))
                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        AUDIT_RUN_TRIGGER_PROMPT,
                        send_xpath,
                    ),
                )
                wait_for_body_text(
                    base_url,
                    session_id,
                    FIXTURE_AUDIT_RUN_COMMAND,
                    timeout=60.0,
                )
                wait_for_main_request_prompts(
                    fixture_state,
                    [
                        TASK_PROMPT,
                        QUEUE_PROMPTS[2],
                        QUEUE_PROMPTS[1],
                        QUESTION_TRIGGER_PROMPT,
                        QUESTION_QUEUED_PROMPT,
                        PERMISSION_TRIGGER_PROMPT,
                        PERMISSION_QUEUED_PROMPT,
                        AUDIT_RUN_TRIGGER_PROMPT,
                    ],
                )
                audit_run_continuation = wait_for_main_request_count(
                    fixture_state,
                    audit_run_request_count + 2,
                )[-1]
                audit_run_messages = json.dumps(
                    audit_run_continuation.get("messages"),
                    ensure_ascii=False,
                )
                if (
                    "tool_result" not in audit_run_messages
                    or "toolu_fixture_audit_run" not in audit_run_messages
                ):
                    raise AssertionError(
                        "recordable local run did not execute and resume the original turn"
                    )
                runs_toggle_xpath = (
                    '//button[.//span[normalize-space()="运行记录" '
                    'or normalize-space()="Run history"]]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, runs_toggle_xpath, timeout=30.0),
                )
                run_row_xpath = (
                    '//button[@aria-label="关闭运行面板" '
                    'or @aria-label="Close runs"]'
                    '/ancestor::div[contains(@class,"flex-col")][1]'
                    '//li/button[@aria-expanded]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, run_row_xpath, timeout=60.0),
                )
                model_call_audit_xpath = (
                    '//button[normalize-space()="模型调用记录" '
                    'or normalize-space()="Model call record"]'
                )
                try:
                    click(
                        base_url,
                        session_id,
                        find_element(
                            base_url,
                            session_id,
                            model_call_audit_xpath,
                            timeout=30.0,
                        ),
                    )
                    wait_for_body_text(
                        base_url,
                        session_id,
                        f"{FIXTURE_PROVIDER_ID} / {FIXTURE_MODEL_ID}",
                        timeout=30.0,
                    )
                except AssertionError as error:
                    raise AssertionError(
                        "real run did not expose its linked model-call audit"
                    ) from error
                open_conversation_xpath = (
                    '//button[normalize-space()="打开对话" '
                    'or normalize-space()="Open conversation"]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(
                        base_url,
                        session_id,
                        open_conversation_xpath,
                        timeout=30.0,
                    ),
                )
                try:
                    wait_for_script_value(
                        base_url,
                        session_id,
                        "const target = document.querySelector("
                        "'[data-conversation-source-target=\"true\"]'); "
                        "const scroller = target?.closest("
                        "'[data-conversation-scroll=\"true\"]'); "
                        "const closeRuns = document.querySelector("
                        "'button[aria-label=\"关闭运行面板\"], "
                        "button[aria-label=\"Close runs\"]'); "
                        "if (!target || !scroller || closeRuns || !target.offsetParent) "
                        "return false; "
                        "const targetRect = target.getBoundingClientRect(); "
                        "const scrollRect = scroller.getBoundingClientRect(); "
                        f"return target.innerText.includes({json.dumps(FIXTURE_AUDIT_RUN_COMMAND)}) "
                        "&& targetRect.top >= scrollRect.top "
                        "&& targetRect.bottom <= scrollRect.bottom;",
                        True,
                        timeout=30.0,
                    )
                except AssertionError as error:
                    raise AssertionError(
                        "linked run did not return to its exact conversation source"
                    ) from error

                reject_sentinel = standalone_workspace / FIXTURE_BASH_REJECT_SENTINEL
                reject_sentinel.write_text(
                    "must remain after rejection\n",
                    encoding="utf-8",
                )
                fixture_state.bash_rejection_next_main_reply()
                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        PERMISSION_REJECT_TRIGGER_PROMPT,
                        send_xpath,
                    ),
                )
                wait_for_body_text(
                    base_url,
                    session_id,
                    FIXTURE_BASH_REJECT_COMMAND,
                    timeout=60.0,
                )
                wait_for_main_request_prompts(
                    fixture_state,
                    [
                        TASK_PROMPT,
                        QUEUE_PROMPTS[2],
                        QUEUE_PROMPTS[1],
                        QUESTION_TRIGGER_PROMPT,
                        QUESTION_QUEUED_PROMPT,
                        PERMISSION_TRIGGER_PROMPT,
                        PERMISSION_QUEUED_PROMPT,
                        AUDIT_RUN_TRIGGER_PROMPT,
                        PERMISSION_REJECT_TRIGGER_PROMPT,
                    ],
                )
                permission_reject_request_count = len(
                    main_provider_requests(fixture_state)
                )

                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        PERMISSION_REJECT_QUEUED_PROMPT,
                        queue_add_xpath,
                    ),
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    queue_items_script,
                    [PERMISSION_REJECT_QUEUED_PROMPT],
                )
                assert_prompt_not_sent(
                    fixture_state,
                    PERMISSION_REJECT_QUEUED_PROMPT,
                )

                reject_xpath = (
                    '//button[normalize-space()="拒绝" '
                    'or normalize-space()="Reject"]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, reject_xpath),
                )
                permission_reject_queued_request = wait_for_main_request_count(
                    fixture_state,
                    permission_reject_request_count + 1,
                )[-1]
                permission_reject_messages = json.dumps(
                    permission_reject_queued_request.get("messages"),
                    ensure_ascii=False,
                )
                if (
                    "tool_result" not in permission_reject_messages
                    or "toolu_fixture_bash_reject" not in permission_reject_messages
                ):
                    raise AssertionError(
                        "queued turn did not retain the rejected command result in history"
                    )
                if PERMISSION_REJECT_QUEUED_PROMPT not in latest_user_text(
                    permission_reject_queued_request
                ):
                    raise AssertionError(
                        "rejected permission did not release the next queued turn"
                    )
                if (
                    not reject_sentinel.is_file()
                    or reject_sentinel.read_text(encoding="utf-8")
                    != "must remain after rejection\n"
                ):
                    raise AssertionError("rejected command permission executed the command")
                wait_for_main_request_prompts(
                    fixture_state,
                    [
                        TASK_PROMPT,
                        QUEUE_PROMPTS[2],
                        QUEUE_PROMPTS[1],
                        QUESTION_TRIGGER_PROMPT,
                        QUESTION_QUEUED_PROMPT,
                        PERMISSION_TRIGGER_PROMPT,
                        PERMISSION_QUEUED_PROMPT,
                        AUDIT_RUN_TRIGGER_PROMPT,
                        PERMISSION_REJECT_TRIGGER_PROMPT,
                        PERMISSION_REJECT_QUEUED_PROMPT,
                    ],
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    queue_items_script,
                    None,
                    timeout=60.0,
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return !document.querySelector("
                    "'button[aria-label=\"停止\"], button[aria-label=\"Stop\"]')",
                    True,
                    timeout=60.0,
                )
                if not reject_sentinel.is_file():
                    raise AssertionError(
                        "rejected command executed while the queued turn drained"
                    )

                always_sentinel = standalone_workspace / FIXTURE_BASH_ALWAYS_SENTINEL
                always_sentinel.write_text(
                    "remove only after an explicit remembered permission\n",
                    encoding="utf-8",
                )
                fixture_state.bash_always_next_main_reply()
                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        PERMISSION_ALWAYS_TRIGGER_PROMPT,
                        send_xpath,
                    ),
                )
                wait_for_body_text(
                    base_url,
                    session_id,
                    FIXTURE_BASH_ALWAYS_COMMAND,
                    timeout=60.0,
                )
                wait_for_main_request_prompts(
                    fixture_state,
                    [
                        TASK_PROMPT,
                        QUEUE_PROMPTS[2],
                        QUEUE_PROMPTS[1],
                        QUESTION_TRIGGER_PROMPT,
                        QUESTION_QUEUED_PROMPT,
                        PERMISSION_TRIGGER_PROMPT,
                        PERMISSION_QUEUED_PROMPT,
                        AUDIT_RUN_TRIGGER_PROMPT,
                        PERMISSION_REJECT_TRIGGER_PROMPT,
                        PERMISSION_REJECT_QUEUED_PROMPT,
                        PERMISSION_ALWAYS_TRIGGER_PROMPT,
                    ],
                )
                permission_always_request_count = len(
                    main_provider_requests(fixture_state)
                )
                always_allow_xpath = (
                    '//button[normalize-space()="始终允许" '
                    'or normalize-space()="Always allow"]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, always_allow_xpath),
                )
                permission_always_continuation = wait_for_main_request_count(
                    fixture_state,
                    permission_always_request_count + 1,
                )[-1]
                permission_always_messages = json.dumps(
                    permission_always_continuation.get("messages"),
                    ensure_ascii=False,
                )
                if (
                    "tool_result" not in permission_always_messages
                    or "toolu_fixture_bash_always_1" not in permission_always_messages
                ):
                    raise AssertionError(
                        "remembered command permission did not execute and resume the original turn"
                    )
                wait_for_path_missing(always_sentinel)
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return !document.querySelector("
                    "'button[aria-label=\"停止\"], button[aria-label=\"Stop\"]')",
                    True,
                    timeout=60.0,
                )
                saved_project_id = wait_for_saved_permission(
                    runtime_root,
                    "bash",
                    FIXTURE_BASH_ALWAYS_COMMAND,
                )

                always_sentinel.write_text(
                    "remove automatically using the remembered permission\n",
                    encoding="utf-8",
                )
                fixture_state.bash_always_next_main_reply()
                permission_repeat_request_count = len(
                    main_provider_requests(fixture_state)
                )
                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        PERMISSION_ALWAYS_REPEAT_PROMPT,
                        send_xpath,
                    ),
                )
                permission_repeat_continuation = wait_for_main_request_count(
                    fixture_state,
                    permission_repeat_request_count + 2,
                )[-1]
                permission_repeat_messages = json.dumps(
                    permission_repeat_continuation.get("messages"),
                    ensure_ascii=False,
                )
                if (
                    "tool_result" not in permission_repeat_messages
                    or "toolu_fixture_bash_always_2" not in permission_repeat_messages
                ):
                    raise AssertionError(
                        "the exact remembered command did not execute and resume automatically"
                    )
                wait_for_path_missing(always_sentinel)
                wait_for_main_request_prompts(
                    fixture_state,
                    [
                        TASK_PROMPT,
                        QUEUE_PROMPTS[2],
                        QUEUE_PROMPTS[1],
                        QUESTION_TRIGGER_PROMPT,
                        QUESTION_QUEUED_PROMPT,
                        PERMISSION_TRIGGER_PROMPT,
                        PERMISSION_QUEUED_PROMPT,
                        AUDIT_RUN_TRIGGER_PROMPT,
                        PERMISSION_REJECT_TRIGGER_PROMPT,
                        PERMISSION_REJECT_QUEUED_PROMPT,
                        PERMISSION_ALWAYS_TRIGGER_PROMPT,
                        PERMISSION_ALWAYS_REPEAT_PROMPT,
                    ],
                )
                if wait_for_saved_permission(
                    runtime_root,
                    "bash",
                    FIXTURE_BASH_ALWAYS_COMMAND,
                ) != saved_project_id:
                    raise AssertionError(
                        "the remembered command permission changed project scope"
                    )
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return ![...document.querySelectorAll('button')].some((button) => "
                    "['始终允许', 'Always allow'].includes(button.textContent.trim()))",
                    True,
                    timeout=60.0,
                )

                process, session_id = restart_desktop_session(
                    base_url,
                    session_id,
                    process,
                    env,
                    log_path,
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return Boolean(window.__TAURI_INTERNALS__)",
                    True,
                )
                current_path = execute(base_url, session_id, "return window.location.pathname")
                if not (
                    isinstance(current_path, str)
                    and current_path.startswith("/heor/")
                    and current_path != "/heor/new"
                ):
                    click(
                        base_url,
                        session_id,
                        find_element(base_url, session_id, task_link_xpath, timeout=30.0),
                    )
                    wait_for_task_location(base_url, session_id)
                wait_for_active_workspace(active_pointer, standalone_workspace)
                wait_for_session_project(
                    runtime_root,
                    task_id,
                    saved_project_id,
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return !document.querySelector('[aria-busy=\"true\"]')",
                    True,
                    timeout=60.0,
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return !document.querySelector("
                    "'button[aria-label=\"停止\"], button[aria-label=\"Stop\"]')",
                    True,
                    timeout=60.0,
                )

                settings_xpath = (
                    '//button[@aria-label="设置" or @aria-label="Settings"]'
                )
                privacy_xpath = '//a[@href="/settings/privacy"]'
                back_xpath = (
                    '//button[normalize-space()="返回应用" '
                    'or normalize-space()="Back to app"]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, settings_xpath),
                )
                wait_for_location(base_url, session_id, "/settings")
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, privacy_xpath),
                )
                wait_for_location(base_url, session_id, "/settings/privacy")
                try:
                    wait_for_body_text(
                        base_url,
                        session_id,
                        FIXTURE_BASH_ALWAYS_COMMAND,
                        timeout=10.0,
                    )
                except AssertionError as error:
                    visible = execute(base_url, session_id, "return document.body.innerText")
                    raise AssertionError(
                        "saved permission was not visible after desktop restart; "
                        f"saved_project_id={saved_project_id!r}, "
                        f"database={permission_database_snapshot(runtime_root)!r}, "
                        f"visible={str(visible)[-2000:]}"
                    ) from error
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, back_xpath),
                )
                wait_for_location(base_url, session_id, "/heor")
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, task_link_xpath, timeout=30.0),
                )
                wait_for_task_location(base_url, session_id)
                wait_for_active_workspace(active_pointer, standalone_workspace)
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return !document.querySelector('[aria-busy=\"true\"]')",
                    True,
                    timeout=60.0,
                )

                always_sentinel.write_text(
                    "remove automatically after a full desktop restart\n",
                    encoding="utf-8",
                )
                fixture_state.bash_always_next_main_reply()
                restart_request_count = len(main_provider_requests(fixture_state))
                find_stable_element(
                    base_url,
                    session_id,
                    composer_xpath,
                    stable_for=2.0,
                    timeout=30.0,
                )
                fill_composer(
                    base_url,
                    session_id,
                    composer_xpath,
                    PERMISSION_AFTER_RESTART_PROMPT,
                    send_xpath,
                )
                click(
                    base_url,
                    session_id,
                    find_stable_element(
                        base_url,
                        session_id,
                        send_xpath,
                        stable_for=1.0,
                        timeout=15.0,
                    ),
                )
                try:
                    wait_for_body_text(
                        base_url,
                        session_id,
                        PERMISSION_AFTER_RESTART_PROMPT,
                        timeout=10.0,
                    )
                except AssertionError as error:
                    visible = execute(base_url, session_id, "return document.body.innerText")
                    composer_value = execute(
                        base_url,
                        session_id,
                        "const input = document.querySelector('textarea'); "
                        "return input ? input.value : null;",
                    )
                    raise AssertionError(
                        "restarted task did not render the submitted prompt; "
                        f"composer={composer_value!r}, visible={str(visible)[-2000:]}"
                    ) from error
                restart_continuation = wait_for_main_request_count(
                    fixture_state,
                    restart_request_count + 2,
                )[-1]
                restart_messages = json.dumps(
                    restart_continuation.get("messages"),
                    ensure_ascii=False,
                )
                if (
                    "tool_result" not in restart_messages
                    or "toolu_fixture_bash_always_3" not in restart_messages
                ):
                    raise AssertionError(
                        "the exact remembered command did not resume automatically after restart"
                    )
                wait_for_path_missing(always_sentinel)
                if wait_for_saved_permission(
                    runtime_root,
                    "bash",
                    FIXTURE_BASH_ALWAYS_COMMAND,
                ) != saved_project_id:
                    raise AssertionError(
                        "the remembered command permission changed project scope after restart"
                    )

                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, settings_xpath),
                )
                wait_for_location(base_url, session_id, "/settings")
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, privacy_xpath),
                )
                wait_for_location(base_url, session_id, "/settings/privacy")
                wait_for_body_text(
                    base_url,
                    session_id,
                    FIXTURE_BASH_ALWAYS_COMMAND,
                    timeout=30.0,
                )
                revoke_xpath = '//button[@data-testid="saved-permission-revoke"]'
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, revoke_xpath),
                )
                wait_for_no_saved_permissions(runtime_root)
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return !document.querySelector('[data-testid=\"saved-permission-revoke\"]')",
                    True,
                    timeout=30.0,
                )

                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, back_xpath),
                )
                wait_for_location(base_url, session_id, "/heor")
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, task_link_xpath, timeout=30.0),
                )
                wait_for_task_location(base_url, session_id)
                wait_for_active_workspace(active_pointer, standalone_workspace)
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return !document.querySelector('[aria-busy=\"true\"]')",
                    True,
                    timeout=60.0,
                )

                always_sentinel.write_text(
                    "must remain after the saved permission is revoked\n",
                    encoding="utf-8",
                )
                fixture_state.bash_always_next_main_reply()
                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        PERMISSION_AFTER_REVOKE_PROMPT,
                        send_xpath,
                    ),
                )
                wait_for_body_text(
                    base_url,
                    session_id,
                    FIXTURE_BASH_ALWAYS_COMMAND,
                    timeout=60.0,
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, reject_xpath),
                )
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return !document.querySelector("
                    "'button[aria-label=\"停止\"], button[aria-label=\"Stop\"]')",
                    True,
                    timeout=60.0,
                )
                if (
                    not always_sentinel.is_file()
                    or always_sentinel.read_text(encoding="utf-8")
                    != "must remain after the saved permission is revoked\n"
                ):
                    raise AssertionError(
                        "revoked remembered permission still executed the command"
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

                imported = invoke_tauri(
                    base_url,
                    session_id,
                    "import_project",
                    {"path": str(imported_source)},
                )
                if not isinstance(imported, dict):
                    raise AssertionError(f"native import returned an invalid project: {imported!r}")
                if (
                    imported.get("name") != IMPORTED_PROJECT_NAME
                    or Path(str(imported.get("importedFrom", ""))).resolve()
                    != imported_source.resolve()
                ):
                    raise AssertionError(f"native import lost source provenance: {imported!r}")
                imported_workspace = Path(str(imported.get("path", ""))).resolve()
                if imported_workspace == imported_source.resolve() or imported_workspace.parent != workspace.resolve():
                    raise AssertionError(
                        "native import did not create an app-managed project copy"
                    )

                execute(base_url, session_id, "window.location.reload(); return true;")
                wait_for_script_value(
                    base_url,
                    session_id,
                    "return Boolean(window.__TAURI_INTERNALS__)",
                    True,
                    timeout=30.0,
                )
                wait_for_body_text(base_url, session_id, IMPORTED_PROJECT_NAME, timeout=30.0)
                opened_imported_draft = execute(
                    base_url,
                    session_id,
                    "const project = [...document.querySelectorAll('[data-project-id]')]"
                    f".find((node) => node.dataset.projectId === {json.dumps(str(imported['id']))}); "
                    "const action = project ? [...project.querySelectorAll('button')]"
                    f".find((button) => (button.getAttribute('aria-label') || '').includes({json.dumps(IMPORTED_PROJECT_NAME)})) : null; "
                    "if (action) action.click(); return Boolean(action);",
                )
                if opened_imported_draft is not True:
                    raise AssertionError("imported project did not expose its new-task action")
                wait_for_location(base_url, session_id, "/heor/new", timeout=30.0)
                active_pointer = runtime_root / "active-workspace.txt"
                wait_for_active_workspace(active_pointer, imported_workspace)

                imported_request_count = len(main_provider_requests(fixture_state))
                click(
                    base_url,
                    session_id,
                    fill_composer(
                        base_url,
                        session_id,
                        composer_xpath,
                        IMPORTED_PROJECT_TASK_PROMPT,
                        send_xpath,
                    ),
                )
                imported_task_path = wait_for_task_location(base_url, session_id)
                imported_task_id = imported_task_path.removeprefix("/heor/")
                imported_requests = wait_for_main_request_count(
                    fixture_state,
                    imported_request_count + 1,
                )
                if IMPORTED_PROJECT_TASK_PROMPT not in latest_user_text(imported_requests[-1]):
                    raise AssertionError("imported-project task did not reach the model adapter")
                wait_for_body_text(base_url, session_id, FIXTURE_MARKER, timeout=60.0)
                wait_for_active_workspace(active_pointer, imported_workspace)
                wait_for_session_directory(
                    runtime_root,
                    imported_task_id,
                    imported_workspace,
                )
                imported_task_attribute = "data-" + "task-" + "id"
                imported_task_grouped = execute(
                    base_url,
                    session_id,
                    "const task = document.querySelector("
                    + json.dumps(f'[{imported_task_attribute}="{imported_task_id}"]')
                    + "); const project = task ? task.closest('[data-project-id]') : null; "
                    f"return project ? project.dataset.projectId === {json.dumps(str(imported['id']))} : false;",
                )
                if imported_task_grouped is not True:
                    raise AssertionError("imported-project task was not grouped under its project")

                pre_export_audit = invoke_tauri(
                    base_url,
                    session_id,
                    "audit_research_report",
                )
                if (
                    not isinstance(pre_export_audit, dict)
                    or pre_export_audit.get("readyToGenerate") is not True
                ):
                    raise AssertionError(
                        f"imported report fixture is not ready to generate: {pre_export_audit!r}"
                    )

                review_xpath = (
                    '//button[.//span[normalize-space()="研究与分析" '
                    'or normalize-space()="Research & analysis"]]'
                )
                click(
                    base_url,
                    session_id,
                    find_element(base_url, session_id, review_xpath, timeout=30.0),
                )
                generate_report_xpath = (
                    '//button[normalize-space()="生成 DOCX、PDF 和 XLSX" '
                    'or normalize-space()="Generate DOCX, PDF, and XLSX"]'
                )
                try:
                    generate_report_id = find_element(
                        base_url,
                        session_id,
                        generate_report_xpath,
                        timeout=60.0,
                    )
                except AssertionError as error:
                    visible = execute(base_url, session_id, "return document.body.innerText")
                    raise AssertionError(
                        "ready native report did not expose its generate action; "
                        f"audit={pre_export_audit!r}, visible={str(visible)[-5000:]}"
                    ) from error
                click(base_url, session_id, generate_report_id)
                wait_for_export_outputs(imported_workspace, timeout=60.0)
                report_audit = invoke_tauri(
                    base_url,
                    session_id,
                    "audit_research_report",
                )
                if not isinstance(report_audit, dict) or report_audit.get("outputsCurrent") is not True:
                    raise AssertionError(
                        f"native report outputs are not current: {report_audit!r}"
                    )
                if snapshot_source_tree(imported_source) != imported_source_snapshot:
                    raise AssertionError("imported source changed during the native workflow")
                assert_no_admitted_asset_deployment_errors(log_path)

                print(
                    "native desktop E2E passed: Tauri bridge, navigation, "
                    "queued prompts, Human input, one-time and rejected permissions, remembered "
                    "permission reuse after restart, visible revocation and re-prompt, provider "
                    "failure queue recovery, task files, passive HTML preview, and imported-project "
                    "task execution with deterministic DOCX/PDF/XLSX export"
                )
        except Exception as error:
            tail = ""
            if log_path.is_file():
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
            raise AssertionError(f"{error}; app log tail: {tail}") from error
        finally:
            release_main_reply.set()
            if release_provider_failure is not None:
                release_provider_failure.set()
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

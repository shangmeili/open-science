#!/usr/bin/env python3
"""Native conversation file-link regression; synthetic data and loopback model only."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import tempfile

import verify_desktop_webdriver as native


REPLY = """## File preview acceptance

Report: `heor/link-preview.md`

Results: [Open JSON](heor/link-result.json)

Created later: `heor/late-report.md`

中文文件：`heor/中文 报告.md`

[External reference](https://example.org/research)

```text
heor/code-only.md
```

FILE_LINK_REPLY_COMPLETE
"""


def main() -> int:
    evidence = Path(os.environ.get("AI4HEOR_E2E_EVIDENCE_DIR") or tempfile.mkdtemp(prefix="ai4heor-file-link-evidence-"))
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ai4heor-file-links-", dir="/private/tmp") as temporary:
        home = Path(temporary)
        with native.local_fixture_provider() as (state, provider_url):
            runtime_root = native.prepare_local_fixture_runtime(home, provider_url)
            port = native.free_local_port()
            base = f"http://127.0.0.1:{port}"
            env = {**os.environ, "HOME": str(home), "TMPDIR": str(home / "tmp"),
                   "XDG_CONFIG_HOME": str(home / "config"), "XDG_DATA_HOME": str(home / "data"),
                   "XDG_CACHE_HOME": str(home / "cache"), "TAURI_WEBDRIVER_PORT": str(port),
                   "OPENCODE_CONFIG_CONTENT": (runtime_root / "xdg-config/opencode/opencode.json").read_text()}
            for key in ("TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
                Path(env[key]).mkdir(parents=True)
            log = evidence / "native-file-links.log"
            process = None
            session = None
            with native.isolate_single_instance_socket(native.single_instance_socket_path()):
                try:
                    process, session = native.start_desktop_session(base, env, log)
                    # Establish a ready workspace through the same native UI
                    # setup used by the full desktop acceptance harness.
                    native.click(base, session, native.find_element(base, session, '//button[@aria-label="新建项目" or @aria-label="New project"]'))
                    native.send_keys(base, session, native.find_element(base, session, '//input[@placeholder="项目名称" or @placeholder="Project name"]'), "File preview acceptance")
                    native.press_key(base, session, "\ue007")
                    native.find_element(base, session, '//div[@data-project-id][.//span[normalize-space()="File preview acceptance"]]', timeout=30)
                    native.wait_for_location(base, session, "/heor/new")
                    new_task = '//button[.//span[normalize-space()="新建任务" or normalize-space()="New task"]]'
                    native.click(base, session, native.find_element(base, session, new_task))
                    native.wait_for_location(base, session, "/heor/new")
                    if native.choose_fixture_model_if_required(base, session):
                        native.click(base, session, native.find_element(base, session, new_task))
                    native.execute(base, session, "window.__fileLinkErrors = []; window.addEventListener('error', e => window.__fileLinkErrors.push(e.message)); window.addEventListener('unhandledrejection', e => window.__fileLinkErrors.push(String(e.reason))); return true;")
                    composer = '//textarea[@aria-label="描述研究问题或要处理的工作" or @aria-label="Ask anything"]'
                    send = '//button[@aria-label="发送" or @aria-label="Send"]'
                    state.text_next_main_reply(REPLY)
                    waiting, release = state.pause_next_main_reply()
                    native.click(base, session, native.fill_composer(base, session, composer, "Show the synthetic file preview acceptance report.", send))
                    route = native.wait_for_task_location(base, session)
                    if not waiting.wait(30):
                        raise AssertionError("local model did not receive the task")
                    for path, content in (
                        ("heor/link-preview.md", "# Native Markdown preview passed\n\nSynthetic report only."),
                        ("heor/link-result.json", '{"native_json_preview": "passed"}'),
                        ("heor/中文 报告.md", "# 中文路径预览通过\n\nSynthetic report only."),
                    ):
                        native.invoke_tauri(base, session, "write_workspace_file", {"path": path, "content": content})
                    release.set()
                    native.wait_for_body_text(base, session, "FILE_LINK_REPLY_COMPLETE")

                    def click_path(path: str) -> None:
                        xpath = f'//button[@data-workspace-path={json.dumps(path, ensure_ascii=False)}]'
                        element = native.find_element(base, session, xpath)
                        native.execute(base, session, "const e = document.querySelector('button[data-workspace-path=' + CSS.escape(" + json.dumps(path) + ") + ']'); e.scrollIntoView({block: 'center'}); return true;")
                        native.click(base, session, element)

                    def screenshot(name: str) -> None:
                        encoded = native.request_json(base, "GET", f"/session/{session}/screenshot")
                        (evidence / f"{name}.png").write_bytes(base64.b64decode(encoded))

                    click_path("heor/link-preview.md")
                    native.wait_for_body_text(base, session, "Native Markdown preview passed")
                    screenshot("01-inline-markdown-preview")
                    click_path("heor/link-result.json")
                    native.wait_for_body_text(base, session, '"native_json_preview"')
                    screenshot("02-markdown-link-json-preview")
                    click_path("heor/中文 报告.md")
                    native.wait_for_body_text(base, session, "中文路径预览通过")
                    native.find_element(base, session, '//button[normalize-space()="中文 报告.md"]')
                    screenshot("03-chinese-space-path")
                    click_path("heor/late-report.md")
                    native.wait_for_script_value(base, session, "return document.body.innerText.includes('当前工作区中未找到文件') || document.body.innerText.includes('File not found in the current workspace')", True)
                    native.wait_for_script_value(base, session, "return [...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'late-report.md')", False)
                    native.invoke_tauri(base, session, "write_workspace_file", {"path": "heor/late-report.md", "content": "# Late file cache refresh passed"})
                    # A real successful tool event must refresh the OLD answer's
                    # attachment chips; do not mutate React state from the test.
                    state.audit_run_next_main_reply()
                    native.click(base, session, native.fill_composer(base, session, composer, native.AUDIT_RUN_TRIGGER_PROMPT, send))
                    native.wait_for_script_value(base, session, "return [...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'late-report.md')", True, timeout=60)
                    chip = native.find_element(base, session, '//button[normalize-space()="late-report.md"]')
                    native.click(base, session, chip)
                    native.wait_for_body_text(base, session, "Late file cache refresh passed")
                    native.find_element(base, session, send, timeout=60)
                    native.wait_for_script_value(base, session, "return document.body.innerText.includes('File not found in the current workspace') || document.body.innerText.includes('当前工作区中未找到文件')", False, timeout=15)
                    screenshot("04-refreshed-attachment-preview")
                    native.wait_for_script_value(base, session, "return document.querySelectorAll('pre button').length", 0)
                    native.wait_for_script_value(base, session, "return document.querySelector('a[href=\"https://example.org/research\"]') !== null", True)
                    native.wait_for_script_value(base, session, "return window.location.pathname", route)
                    native.wait_for_script_value(base, session, "return window.__fileLinkErrors", [])
                    native.wait_for_script_value(base, session, "return document.querySelector('vite-error-overlay') === null", True)
                    details = native.execute(base, session, "return {title: document.title, route: location.pathname, width: innerWidth, height: innerHeight, bridge: !!window.__TAURI_INTERNALS__, errors: window.__fileLinkErrors};")
                    (evidence / "verification.json").write_text(json.dumps({"passed": True, "environment": details, "checks": ["inline-markdown-preview", "markdown-link-json-preview", "unicode-space-path", "missing-file-feedback", "attachment-refresh-after-tool", "attachment-click-preview", "fenced-code-unchanged", "external-link-preserved", "no-navigation", "no-runtime-errors"]}, indent=2) + "\n")
                    print(f"Native file-link UI regression passed; evidence: {evidence}")
                except Exception:
                    if session is not None:
                        details = native.execute(base, session, "return {body: document.body.innerText, path: location.pathname, errors: window.__fileLinkErrors};")
                        (evidence / "failure.json").write_text(json.dumps(details, ensure_ascii=False, indent=2))
                        encoded = native.request_json(base, "GET", f"/session/{session}/screenshot")
                        (evidence / "failure.png").write_bytes(base64.b64decode(encoded))
                        print(f"Native UI failure evidence: {evidence}; fixture requests: {state.message_requests}")
                    raise
                finally:
                    if 'release' in locals():
                        release.set()
                    if session is not None:
                        native.request_json(base, "DELETE", f"/session/{session}")
                    if process is not None:
                        native.terminate(process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

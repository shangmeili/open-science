#!/usr/bin/env python3
"""Unit contracts for the packaged OpenCode system-context fixture proof."""

from __future__ import annotations

import hashlib
import inspect
import json
import tempfile
import unittest
from pathlib import Path

import verify_packaged_opencode_fixture as fixture


class PackagedOpenCodeFixtureTests(unittest.TestCase):
    def test_release_proof_is_bounded_and_appended_to_existing_verification(self) -> None:
        result = {
            "app_version": "1.0.0",
            "provider_catalog_requests": 1,
            "provider_message_requests": 2,
            "provider_streaming": True,
            "assistant_marker_found": True,
            "system_context": {
                "contract": "ai4heor.system-context/v1",
                "sha256": "a" * 64,
                "block_count": 3,
            },
            "permission_persistence": {
                "exact_project_rule": True,
                "restart_reused": True,
                "revoked": True,
                "reprompted_after_revoke": True,
            },
        }
        proof = fixture.bounded_release_proof(result)
        self.assertEqual(
            proof,
            {
                "assistant_reply_completed": True,
                "provider_streaming": True,
                "system_context": {
                    "contract": "ai4heor.system-context/v1",
                    "fingerprint_matched_provider_request": True,
                },
                "permission_persistence": result["permission_persistence"],
            },
        )
        self.assertNotIn("sha256", json.dumps(proof))
        self.assertNotIn("provider_message_requests", json.dumps(proof))

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "verification.json"
            path.write_text('{"payload":{"resource_files":1}}\n', encoding="utf-8")
            fixture.append_release_proof(path, proof)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["packaged_opencode_fixture"], proof)
            self.assertEqual(saved["payload"], {"resource_files": 1})
            with self.assertRaisesRegex(AssertionError, "already contains"):
                fixture.append_release_proof(path, proof)

    def test_fixture_can_fail_exactly_one_main_reply_with_a_visible_provider_error(self) -> None:
        state = fixture.FixtureState()
        main = {"tools": [{"name": "read"}]}
        state.provider_error_next_main_reply()
        self.assertEqual(state.take_reply_kind(True, main), "provider_error")
        self.assertEqual(state.take_reply_kind(True, main), "text")
        payload = json.loads(fixture.anthropic_provider_error())
        self.assertEqual(payload["type"], "error")
        self.assertEqual(payload["error"]["type"], "invalid_request_error")
        self.assertEqual(payload["error"]["message"], fixture.PROVIDER_ERROR_MESSAGE)

    def test_packaged_fixture_verifies_permission_restart_and_revoke(self) -> None:
        source = inspect.getsource(fixture.run_fixture)
        self.assertIn("verify_packaged_permission_persistence", source)
        self.assertIn('"permission_persistence": permission_proof', source)

    def test_saved_permission_proof_is_exact_and_project_bound(self) -> None:
        proof = fixture.verify_saved_permission_records(
            [
                {
                    "id": "psv_fixture",
                    "projectID": "project_fixture",
                    "action": "bash",
                    "resource": fixture.BASH_ALWAYS_COMMAND,
                }
            ],
            action="bash",
            resource=fixture.BASH_ALWAYS_COMMAND,
        )
        self.assertEqual(
            proof,
            {"id": "psv_fixture", "project_id": "project_fixture"},
        )
        with self.assertRaises(AssertionError):
            fixture.verify_saved_permission_records(
                [
                    {
                        "id": "psv_fixture",
                        "projectID": "project_fixture",
                        "action": "bash",
                        "resource": "*",
                    }
                ],
                action="bash",
                resource=fixture.BASH_ALWAYS_COMMAND,
            )

    def test_fixture_can_emit_two_distinct_bash_always_probes(self) -> None:
        state = fixture.FixtureState()
        main = {"tools": [{"name": "bash"}]}
        state.bash_always_next_main_reply()
        self.assertEqual(state.take_reply_kind(True, main), "bash_always_1")
        state.bash_always_next_main_reply()
        self.assertEqual(state.take_reply_kind(True, main), "bash_always_2")
        self.assertEqual(state.take_reply_kind(True, main), "text")
        first = fixture.anthropic_bash_stream(
            command=fixture.BASH_ALWAYS_COMMAND,
            message_id="msg_fixture_bash_always_1",
            tool_id="toolu_fixture_bash_always_1",
        ).decode("utf-8")
        second = fixture.anthropic_bash_stream(
            command=fixture.BASH_ALWAYS_COMMAND,
            message_id="msg_fixture_bash_always_2",
            tool_id="toolu_fixture_bash_always_2",
        ).decode("utf-8")
        self.assertIn('"id":"toolu_fixture_bash_always_1"', first)
        self.assertNotIn('"id":"toolu_fixture_bash_always_2"', first)
        self.assertIn('"id":"toolu_fixture_bash_always_2"', second)
        self.assertIn(fixture.BASH_ALWAYS_COMMAND, first)
        self.assertIn(fixture.BASH_ALWAYS_COMMAND, second)

    def test_fixture_can_emit_a_distinct_bash_rejection_probe(self) -> None:
        state = fixture.FixtureState()
        state.bash_rejection_next_main_reply()
        main = {"tools": [{"name": "bash"}]}
        self.assertEqual(state.take_reply_kind(True, main), "bash_reject")
        self.assertEqual(state.take_reply_kind(True, main), "text")
        payload = fixture.anthropic_bash_stream(
            command=fixture.BASH_REJECT_COMMAND,
            message_id="msg_fixture_bash_reject",
            tool_id="toolu_fixture_bash_reject",
        ).decode("utf-8")
        self.assertIn('"id":"toolu_fixture_bash_reject"', payload)
        self.assertIn(fixture.BASH_REJECT_COMMAND, payload)

    def test_fixture_can_emit_exactly_one_bash_tool_reply(self) -> None:
        state = fixture.FixtureState()
        state.bash_next_main_reply()
        main = {"tools": [{"name": "bash"}]}
        self.assertEqual(state.take_reply_kind(True, main), "bash")
        self.assertEqual(state.take_reply_kind(True, main), "text")
        self.assertEqual(state.take_reply_kind(False, main), "text")
        payload = fixture.anthropic_bash_stream().decode("utf-8")
        self.assertIn('"name":"bash"', payload)
        self.assertIn(fixture.BASH_COMMAND, payload)

    def test_fixture_can_emit_exactly_one_question_tool_reply(self) -> None:
        state = fixture.FixtureState()
        state.question_next_main_reply()
        main = {"tools": [{"name": "question"}]}
        self.assertEqual(state.take_reply_kind(True, main), "question")
        self.assertEqual(state.take_reply_kind(True, main), "text")
        self.assertEqual(state.take_reply_kind(False, main), "text")

    def test_main_provider_system_is_bound_to_the_matching_assistant(self) -> None:
        blocks = ["system one", "system two"]
        digest = hashlib.sha256(
            json.dumps(blocks, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        messages = [
            {
                "info": {
                    "role": "assistant",
                    "systemContext": {
                        "contract": "ai4heor.system-context/v1",
                        "sha256": digest,
                        "blockCount": 2,
                    },
                },
                "parts": [{"type": "text", "text": fixture.MARKER}],
            }
        ]
        bodies = [
            {"system": "title system", "messages": [{"content": "Reply with the marker."}]},
            {
                "system": [{"type": "text", "text": value} for value in blocks],
                "messages": [{"content": "Reply with the marker."}],
                "tools": [{"name": "read"}],
            },
        ]
        proof = fixture.verify_system_context_audit(messages, bodies)
        self.assertEqual(proof["sha256"], digest)
        self.assertEqual(proof["block_count"], 2)

    def test_mismatch_or_unbounded_fields_fail_closed(self) -> None:
        messages = [
            {
                "info": {
                    "role": "assistant",
                    "systemContext": {
                        "contract": "ai4heor.system-context/v1",
                        "sha256": "a" * 64,
                        "blockCount": 1,
                        "content": "must not be retained",
                    },
                },
                "parts": [{"type": "text", "text": fixture.MARKER}],
            }
        ]
        bodies = [{"system": "actual", "tools": [{}], "messages": [{"content": "Reply with the marker."}]}]
        with self.assertRaises(AssertionError):
            fixture.verify_system_context_audit(messages, bodies)


if __name__ == "__main__":
    unittest.main()

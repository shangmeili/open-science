#!/usr/bin/env python3
"""Unit contracts for the packaged OpenCode system-context fixture proof."""

from __future__ import annotations

import hashlib
import json
import unittest

import verify_packaged_opencode_fixture as fixture


class PackagedOpenCodeFixtureTests(unittest.TestCase):
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

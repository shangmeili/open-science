#!/usr/bin/env python3
"""Unit contracts for the packaged OpenCode system-context fixture proof."""

from __future__ import annotations

import hashlib
import json
import unittest

import verify_packaged_opencode_fixture as fixture


class PackagedOpenCodeFixtureTests(unittest.TestCase):
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

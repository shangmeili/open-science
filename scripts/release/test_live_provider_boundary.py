#!/usr/bin/env python3
"""Unit tests for the credential-safe live-provider release harness."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def load_verifier():
    path = Path(__file__).with_name("verify_live_provider_boundary.py")
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = load_verifier()


class LiveProviderBoundaryTests(unittest.TestCase):
    def test_http_timeout_is_treated_as_a_retryable_runtime_probe_failure(self) -> None:
        with mock.patch.object(
            verifier.urllib.request,
            "urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            with self.assertRaisesRegex(AssertionError, "could not reach"):
                verifier.http_json(
                    "http://127.0.0.1:1",
                    "Basic fixture",
                    "GET",
                    "/global/config",
                    timeout=0.01,
                )

    def test_minimax_defaults_match_the_ai_sdk_request_prefix(self) -> None:
        self.assertEqual(
            verifier.DEFAULT_BASE_URL,
            "https://api.minimaxi.com/anthropic/v1",
        )
        self.assertEqual(verifier.DEFAULT_MODEL, "MiniMax-M3")

    def test_assistant_marker_never_matches_the_user_prompt(self) -> None:
        messages = [
            {
                "info": {"role": "user"},
                "parts": [{"type": "text", "text": verifier.DEFAULT_MARKER}],
            },
            {
                "info": {"role": "assistant"},
                "parts": [{"type": "text", "text": "not the marker"}],
            },
        ]
        self.assertNotIn(verifier.DEFAULT_MARKER, verifier.assistant_text(messages))
        messages[1]["parts"][0]["text"] = verifier.DEFAULT_MARKER
        self.assertIn(verifier.DEFAULT_MARKER, verifier.assistant_text(messages))

    def test_credential_scan_and_boundary_require_only_auth_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            auth = data / "opencode/auth.json"
            auth.parent.mkdir(parents=True)
            data.chmod(0o700)
            credential = b"fixture-provider-credential"
            auth.write_bytes(b'{"key":"' + credential + b'"}')
            auth.chmod(0o600)
            hits = verifier.credential_hit_paths([root], credential)
            proof = verifier.credential_boundary(hits, auth, data)
            self.assertEqual(proof["credential_location"], "isolated_auth_json_only")
            self.assertTrue(proof["auth_file_owner_only"])

            other = root / "config/opencode.json"
            other.parent.mkdir(parents=True)
            other.write_bytes(credential)
            with self.assertRaisesRegex(AssertionError, "outside"):
                verifier.credential_boundary(
                    verifier.credential_hit_paths([root], credential), auth, data
                )

    def test_verification_writer_rejects_the_secret_and_writes_safe_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proof.json"
            credential = b"fixture-provider-credential"
            proof = {"schema": verifier.SCHEMA, "credential_removed": True}
            verifier.write_verification(path, proof, credential)
            self.assertEqual(json.loads(path.read_text()), proof)
            with self.assertRaisesRegex(AssertionError, "contains"):
                verifier.write_verification(
                    path, {"unsafe": credential.decode()}, credential
                )

    def test_failure_classifier_returns_only_a_safe_category(self) -> None:
        credential = b"fixture-provider-credential"
        material = b"request used " + credential + b" and returned status=401"
        self.assertEqual(
            verifier.classify_failure(material, credential),
            "authentication_failed",
        )
        self.assertEqual(
            verifier.classify_failure(b"unrecognized provider output", credential),
            "no_assistant_completion",
        )

    def test_workspace_provider_gate_requires_both_provider_and_model(self) -> None:
        responses = iter(
            [
                {"model": "example/model-a"},
                {"providers": [{"id": "example", "models": {}}]},
                {"model": "example/model-a"},
                {"providers": [{"id": "example", "models": {"model-a": {}}}]},
            ]
        )
        original = verifier.http_json
        verifier.http_json = lambda *_args, **_kwargs: next(responses)
        try:
            verifier.wait_for_workspace_provider(
                "http://127.0.0.1:1",
                "Basic fixture",
                Path("/tmp/work"),
                "example",
                "model-a",
                timeout=1.0,
            )
        finally:
            verifier.http_json = original

    def test_private_boundary_accepts_private_parent_when_auth_file_is_rewritten(self) -> None:
        if os.name == "nt":
            self.skipTest("Unix permission modes are required")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            auth = data / "opencode/auth.json"
            auth.parent.mkdir(parents=True)
            data.chmod(0o700)
            auth.write_text("credential", encoding="utf-8")
            auth.chmod(0o644)
            proof = verifier.credential_boundary([auth.resolve()], auth, data)
            self.assertFalse(proof["auth_file_owner_only"])
            self.assertTrue(proof["data_root_owner_only"])


if __name__ == "__main__":
    unittest.main()

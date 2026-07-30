#!/usr/bin/env python3
"""Keep provider configuration separate from local credentials."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "apps/desktop/src/app/routes/SettingsPage.tsx"
CLIENT = ROOT / "packages/sdk/src/OpenCodeClient.ts"
TAURI = ROOT / "apps/desktop/src/lib/tauri.ts"
RUST_LIB = ROOT / "apps/desktop/src-tauri/src/lib.rs"
RUST_RUNTIME = ROOT / "apps/desktop/src-tauri/src/runtime.rs"
LOCALES = ("en", "zh-Hans", "ja", "es", "de", "fr", "ko")


class ProviderCredentialContractTests(unittest.TestCase):
    def test_legacy_plaintext_provider_command_is_not_exposed(self) -> None:
        for source in (TAURI, RUST_LIB, RUST_RUNTIME):
            text = source.read_text(encoding="utf-8")
            self.assertNotIn("configure_opencode", text, source)
            self.assertNotIn("configureOpenCode", text, source)

    def test_custom_provider_metadata_and_credentials_use_separate_calls(self) -> None:
        settings = SETTINGS.read_text(encoding="utf-8")
        client = CLIENT.read_text(encoding="utf-8")
        self.assertIn("client.addCustomProvider(id", settings)
        self.assertIn("client.setProviderApiKey(id, cKey.trim())", settings)
        self.assertNotIn("apiKey: cKey", settings)
        custom_provider = client[client.index("async addCustomProvider") :]
        custom_provider = custom_provider[: custom_provider.index("async listCustomProviderIds")]
        self.assertNotIn("apiKey", custom_provider)

    def test_custom_provider_profile_is_general_and_contains_no_credential(self) -> None:
        settings = SETTINGS.read_text(encoding="utf-8")
        self.assertIn('const [cNpm, setCNpm] = useState("@ai-sdk/openai-compatible")', settings)
        self.assertIn("npm: cNpm", settings)
        self.assertIsNone(re.search(r"sk-[A-Za-z0-9_-]{40,}", settings))

    def test_provider_credential_boundary_is_localized_in_every_ui_language(self) -> None:
        for locale in LOCALES:
            path = ROOT / f"apps/desktop/src/i18n/locales/{locale}/settings.json"
            providers = json.loads(path.read_text(encoding="utf-8"))["providers"]
            self.assertTrue(providers["customEndpoint"].strip(), locale)
            self.assertTrue(providers["customEndpointHint"].strip(), locale)
            self.assertTrue(providers["customNamePlaceholder"].strip(), locale)
            self.assertTrue(providers["customUrlPlaceholder"].strip(), locale)
            self.assertTrue(providers["customKeyPlaceholder"].strip(), locale)
            self.assertTrue(providers["customModelsPlaceholder"].strip(), locale)
            self.assertTrue(providers["customCredentialHint"].strip(), locale)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Release contracts for AI4HEOR's reviewed OpenCode system-context patch."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATCH_ROOT = ROOT / "runtime/opencode-patch"
MANIFEST = PATCH_ROOT / "manifest.json"
PATCH = PATCH_ROOT / "ai4heor-system-context.patch"
BUILD = ROOT / "scripts/dev/build-opencode.sh"
FETCH = ROOT / "scripts/dev/fetch-opencode.sh"
WORKFLOW = ROOT / ".github/workflows/build.yml"
SDK_CLIENT = ROOT / "packages/sdk/src/OpenCodeClient.ts"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PatchedOpenCodeTests(unittest.TestCase):
    def test_source_and_patch_are_immutable_and_content_addressed(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        build = BUILD.read_text(encoding="utf-8")
        self.assertEqual(manifest["schemaVersion"], "ai4heor-opencode-patch/v1")
        self.assertEqual(manifest["upstreamVersion"], "1.17.13")
        self.assertEqual(
            manifest["upstreamCommit"],
            "10c894bdeef3618f5666fb506ef7f9491bb964d8",
        )
        self.assertRegex(manifest["sourceArchiveSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(manifest["patchedVersion"], "1.17.13-ai4heor.2")
        self.assertEqual(manifest["patchSha256"], sha256(PATCH))
        self.assertEqual(
            manifest["systemContextContract"],
            "ai4heor.system-context/v1",
        )
        for field in (
            "upstreamCommit",
            "sourceArchiveSha256",
            "patchSha256",
            "patchedVersion",
            "bunVersion",
        ):
            self.assertIn(manifest[field], build, f"build script drifted from {field}")

    def test_patch_changes_only_the_reviewed_context_and_permission_surface(self) -> None:
        text = PATCH.read_text(encoding="utf-8")
        touched = set(re.findall(r"^\+\+\+ b/(.+)$", text, flags=re.MULTILINE))
        self.assertEqual(
            touched,
            {
                "packages/schema/src/v1/session.ts",
                "packages/opencode/src/session/llm.ts",
                "packages/opencode/src/session/processor.ts",
                "packages/opencode/src/session/llm/system-context.ts",
                "packages/opencode/test/session/system-context.test.ts",
                "packages/opencode/test/session/processor-effect.test.ts",
                "packages/opencode/src/permission/index.ts",
                "packages/opencode/src/project/project.ts",
                "packages/opencode/src/server/routes/instance/httpapi/groups/permission.ts",
                "packages/opencode/src/server/routes/instance/httpapi/handlers/permission.ts",
                "packages/opencode/test/permission/next.test.ts",
                "packages/opencode/test/project/project-directory.test.ts",
            },
        )
        self.assertIn('"ai4heor.system-context/v1"', text)
        self.assertIn("createHash(\"sha256\")", text)
        self.assertIn("JSON.stringify(system)", text)
        self.assertIn("onPreparedSystem", text)
        self.assertIn("MAX_SYSTEM_CONTEXT_BLOCKS = 1024", text)
        self.assertIn(
            "system.length < 1 || system.length > MAX_SYSTEM_CONTEXT_BLOCKS",
            text,
        )
        self.assertIn("rejects an empty or unbounded system block list", text)
        production_patch = text.split(
            "diff --git a/packages/opencode/test/session/system-context.test.ts",
            maxsplit=1,
        )[0]
        self.assertNotRegex(production_patch, r"https?://")
        self.assertIn('PermissionSaved.Service', text)
        self.assertIn('projectID: ctx.project.id', text)
        self.assertIn('resources: existing.info.patterns', text)
        self.assertIn('HttpApiEndpoint.get("saved"', text)
        self.assertIn('HttpApiEndpoint.delete("removeSaved"', text)
        self.assertIn('"always permission survives instance reload"', text)
        self.assertIn('"saved permission does not override a configured deny rule"', text)
        self.assertIn('"always permission is scoped to the exact resource"', text)
        self.assertIn('"always permission is scoped to one project"', text)
        self.assertIn('"removing saved permission makes the next request ask again"', text)
        self.assertIn('"migrates saved permissions when the project id changes"', text)
        self.assertIn(".update(PermissionTable)", text)
        self.assertIn(
            "context.blockCount <= 1024",
            SDK_CLIENT.read_text(encoding="utf-8"),
        )

    def test_fetch_builds_the_reviewed_source_instead_of_downloading_release_binary(self) -> None:
        fetch = FETCH.read_text(encoding="utf-8")
        self.assertIn("build-opencode.sh", fetch)
        self.assertNotIn("anomalyco/opencode/releases/download", fetch)
        build = BUILD.read_text(encoding="utf-8")
        self.assertIn("sourceArchiveSha256", build)
        self.assertIn("patchSha256", build)
        self.assertIn("apply --check --unidiff-zero", build)
        self.assertIn("bun test", build)
        self.assertIn("build --single", build)
        self.assertIn("OPENCODE_VERSION=1.17.13-ai4heor.2", build)
        self.assertIn("test/permission/next.test.ts", build)
        self.assertIn("test/project/project-directory.test.ts", build)

    def test_source_hash_verification_is_available_on_windows(self) -> None:
        build = BUILD.read_text(encoding="utf-8")
        self.assertNotIn("shasum -a 256", build)
        self.assertIn("command -v python3 || command -v python", build)
        self.assertIn("hashlib.sha256(path.read_bytes()).hexdigest()", build)
        self.assertIn('verify_sha256 "$ARCHIVE" "$sourceArchiveSha256"', build)
        self.assertIn('verify_sha256 "$PATCH" "$patchSha256"', build)

    def test_release_ci_installs_bun_and_runs_patch_contract_before_build(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("oven-sh/setup-bun", workflow)
        self.assertIn("test_patched_opencode.py", workflow)
        self.assertLess(
            workflow.index("test_patched_opencode.py"),
            workflow.index("fetch-opencode.sh"),
        )


if __name__ == "__main__":
    unittest.main()

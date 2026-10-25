"""Image preparation cannot substitute branch-tip code or mismatched versions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import image
import release


class ImageTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repository"
        self.root.mkdir()
        self.context = Path(temporary.name) / "context"
        patched = patch.object(release, "ROOT", self.root)
        patched.start()
        self.addCleanup(patched.stop)
        release.git("init", "-b", "main")
        release.git("config", "user.name", "Test")
        release.git("config", "user.email", "test@example.invalid")
        release.git("config", "commit.gpgsign", "false")
        release.git("config", "tag.gpgsign", "false")
        (self.root / "frontend").mkdir()
        (self.root / "backend/src/core").mkdir(parents=True)
        (self.root / "frontend/package.json").write_text(json.dumps({"version": "1.2.3"}))
        (self.root / "backend/src/core/version.py").write_text('VERSION = "1.2.3"\n')
        (self.root / "LICENSE").write_text("MIT")
        release.git("add", ".")
        release.git("commit", "-m", "Application 1.2.3")
        release.git("tag", "v1.2.3")
        self.revision = release.git("rev-parse", "HEAD").stdout.strip()
        # The recipe is deliberately newer than the tag, as in a backfill.
        (self.root / "docker").mkdir()
        (self.root / "docker/deployment.py").write_text("# Current SPA adapter")
        (self.root / "Dockerfile").write_text("# Current build recipe")
        (self.root / ".dockerignore").write_text("**/.env")

    def test_tag_and_branch_metadata_preserve_version_and_full_commit(self) -> None:
        for tag in ("v1.2.3", None):
            with self.subTest(tag=tag):
                info = image.metadata(tag, "Example/Lychee")
                self.assertEqual(info["version"], "1.2.3")
                self.assertEqual(info["revision"], self.revision)
                self.assertEqual(info["image"], "ghcr.io/example/lychee:v1.2.3")

    def test_non_prefixed_version_tag_keeps_its_exact_image_tag(self) -> None:
        release.git("tag", "1.2.3")
        self.assertEqual(
            image.metadata("1.2.3", "example/lychee")["image"], "ghcr.io/example/lychee:1.2.3"
        )

    def test_missing_or_mismatched_tag_is_not_built(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not exist"):
            image.metadata("v9.9.9", "example/lychee")
        release.git("tag", "v9.9.9")
        with self.assertRaisesRegex(ValueError, "does not match"):
            image.metadata("v9.9.9", "example/lychee")

    def test_non_image_tags_still_allow_a_github_release(self) -> None:
        for tag in ("snapshot/workers", "v1.2.3+build.1"):
            with self.subTest(tag=tag):
                release.git("tag", tag)
                self.assertEqual(image.metadata(tag, "example/lychee"), {"build": "false"})

    def test_backend_and_frontend_must_agree(self) -> None:
        (self.root / "backend/src/core/version.py").write_text('VERSION = "1.2.4"\n')
        release.git("add", ".")
        release.git("commit", "-m", "Mismatched backend")
        with self.assertRaisesRegex(ValueError, "versions disagree"):
            image.metadata(None, "example/lychee")

    def test_context_uses_tagged_app_but_current_recipe_and_excludes_local_files(self) -> None:
        (self.root / "frontend/package.json").write_text('{"version":"99.0.0"}')
        (self.root / "backend/.env").write_text("SECRET=uncommitted")
        (self.root / "frontend/node_modules").mkdir()
        (self.root / "frontend/node_modules/local.js").write_text("Not a source input")
        image.prepare(self.context, self.revision)
        self.assertEqual(
            json.loads((self.context / "frontend/package.json").read_text())["version"], "1.2.3"
        )
        self.assertEqual((self.context / "Dockerfile").read_text(), "# Current build recipe")
        self.assertEqual(
            (self.context / "docker/deployment.py").read_text(), "# Current SPA adapter"
        )
        self.assertFalse((self.context / "backend/.env").exists())
        self.assertFalse((self.context / "frontend/node_modules").exists())
        self.assertFalse((self.context / ".git").exists())

    def test_never_clears_an_existing_nonempty_build_directory(self) -> None:
        self.context.mkdir()
        existing = self.context / "keep.txt"
        existing.write_text("Keep me")
        with self.assertRaisesRegex(ValueError, "must be empty"):
            image.prepare(self.context, self.revision)
        self.assertEqual(existing.read_text(), "Keep me")

    def test_repository_cannot_inject_github_output_rows(self) -> None:
        with self.assertRaisesRegex(ValueError, "owner/name"):
            image.metadata("v1.2.3", "example/lychee\nbuild=false")

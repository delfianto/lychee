"""Exercise real tag histories offline and intercept all release API writes."""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import release


class ReleaseNotesTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        root = patch.object(release, "ROOT", self.root)
        root.start()
        self.addCleanup(root.stop)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Release test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "tag.gpgsign", "false")
        self.commit("feat: initial library")

    def git(self, *args: str) -> str:
        return release.git(*args).stdout.strip()

    def commit(self, subject: str, body: str = "") -> str:
        self.git("commit", "--allow-empty", "-m", subject, "-m", body)
        return self.git("rev-parse", "HEAD")

    def notes(self, tag: str) -> release.Release:
        return release.generate(tag, "example/lychee")

    def test_annotated_first_release_has_full_history(self) -> None:
        self.git("tag", "-a", "v0.1.0-beta.1", "-m", "First functional beta")
        notes = self.notes("v0.1.0-beta.1")
        self.assertTrue(notes.prerelease)
        self.assertTrue(notes.body.startswith("First functional beta\n"))
        self.assertIn("### Features\n\n- initial library", notes.body)
        self.assertIn("/commits/v0.1.0-beta.1", notes.body)
        self.assertEqual(notes.payload()["make_latest"], "false")

    def test_direct_commits_are_categorized_and_newer_work_is_excluded(self) -> None:
        self.git("tag", "v0.1.0-beta.9")
        feature = self.commit("feat(downloads): fetch files in parallel")
        self.commit("fix: preserve favorites")
        self.commit("perf: release database connections")
        self.commit("bench: measure download throughput")
        self.commit("docs: explain worker settings")
        self.commit("release: v0.1.0-beta.10")
        self.git("tag", "-a", "v0.1.0-beta.10", "-m", "Faster downloads")
        self.commit("feat: future untagged feature")
        self.git("tag", "v0.1.0-beta.11")
        body = self.notes("v0.1.0-beta.10").body
        self.assertIn("Faster downloads", body)
        self.assertIn("### Features\n\n- downloads: fetch files in parallel", body)
        self.assertIn(f"/commit/{feature}", body)
        self.assertIn("### Fixes\n\n- preserve favorites", body)
        self.assertIn("### Performance", body)
        self.assertIn("### Documentation", body)
        self.assertIn("### Maintenance", body)
        self.assertIn("v0.1.0-beta.9...v0.1.0-beta.10", body)
        self.assertNotIn("initial library", body)
        self.assertNotIn("future untagged feature", body)
        self.assertNotIn("- v0.1.0-beta.10", body)

    def test_release_only_commit_is_kept_for_existing_squashed_releases(self) -> None:
        self.git("tag", "v0.1.0-beta.8")
        self.commit("release: v0.1.0-beta.9 simplify library settings")
        self.git("tag", "v0.1.0-beta.9")
        self.assertIn("simplify library settings", self.notes("v0.1.0-beta.9").body)

    def test_breaking_changes_include_migration_footer(self) -> None:
        self.git("tag", "v1.0.0")
        self.commit("feat(api)!: rename settings", "BREAKING CHANGE: update /api/config clients")
        self.git("tag", "v2.0.0")
        notes = self.notes("v2.0.0")
        self.assertIn("### Breaking changes", notes.body)
        self.assertIn("update /api/config clients", notes.body)
        self.assertFalse(notes.prerelease)
        self.assertEqual(notes.payload()["make_latest"], "legacy")

    def test_curated_notes_come_from_the_tag_not_the_current_worktree(self) -> None:
        self.git("tag", "v0.1.0-beta.9")
        path = self.root / "notes/releases/v0.1.0-beta.10.md"
        path.parent.mkdir(parents=True)
        path.write_text("## Highlights\n\nTen files fetch together.\n")
        self.git("add", ".")
        self.commit("feat: improve download concurrency")
        self.git("tag", "-a", "v0.1.0-beta.10", "-m", "Generic annotation")
        path.write_text("Uncommitted and incorrect notes")
        notes = self.notes("v0.1.0-beta.10")
        self.assertTrue(notes.body.startswith("## Highlights\n\nTen files fetch together."))
        self.assertIn("improve download concurrency", notes.body)
        self.assertNotIn("Uncommitted", notes.body)
        self.assertNotIn("Generic annotation", notes.body)

    def test_non_version_tags_are_prereleases_and_links_are_encoded(self) -> None:
        self.git("tag", "snapshot/worker-settings")
        notes = self.notes("snapshot/worker-settings")
        self.assertTrue(notes.prerelease)
        self.assertIn("/commits/snapshot%2Fworker-settings", notes.body)

    def test_unknown_commit_types_are_included_and_markup_is_escaped(self) -> None:
        self.git("tag", "v1.0.0")
        self.commit("catalog: fix [title] <script> @someone")
        self.git("tag", "v1.0.1")
        body = self.notes("v1.0.1").body
        self.assertIn("### Changes", body)
        self.assertIn(r"catalog: fix \[title\] \<script\> &#64;someone", body)

    def test_build_metadata_does_not_turn_a_stable_tag_into_prerelease(self) -> None:
        self.git("tag", "v1.0.0+build.123")
        self.assertFalse(self.notes("v1.0.0+build.123").prerelease)

    def test_invalid_or_missing_tag_fails(self) -> None:
        for tag in ("../../outside", "--shell-option", "missing"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                self.notes(tag)

    def test_shallow_clone_fails_instead_of_publishing_incomplete_notes(self) -> None:
        clone = self.root / "shallow"
        subprocess.run(
            ["git", "clone", "--depth=1", self.root.as_uri(), str(clone)],
            check=True,
            capture_output=True,
        )
        with (
            patch.object(release, "ROOT", clone),
            self.assertRaisesRegex(ValueError, "full history"),
        ):
            self.notes("v1.0.0")


class PublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.release = release.Release("v0.1.0-beta.10", "Actual tag changes", True)
        self.endpoint = "https://api.github.com/repos/example/lychee/releases"

    def error(self, code: int) -> HTTPError:
        return HTTPError(self.endpoint, code, "API error", Message(), None)

    def test_new_release_has_exact_generated_notes_and_beta_flags(self) -> None:
        response = io.BytesIO(
            json.dumps(
                {"html_url": "https://github.com/example/lychee/releases/tag/v0.1.0-beta.10"}
            ).encode()
        )
        with patch.object(release, "urlopen", side_effect=[self.error(404), response]) as request:
            url = release.publish(
                self.release, "example/lychee", "test-token", "https://api.github.com"
            )
        self.assertIn("/releases/tag/v0.1.0-beta.10", url)
        post = request.call_args_list[1].args[0]
        self.assertEqual(post.get_method(), "POST")
        self.assertEqual(json.loads(post.data), self.release.payload())
        self.assertEqual(post.get_header("Authorization"), "Bearer test-token")

    def test_rerun_keeps_existing_hand_edited_notes_and_draft_state(self) -> None:
        response = io.BytesIO(
            json.dumps(
                {"html_url": "https://github.com/existing", "draft": True, "body": "Edited notes"}
            ).encode()
        )
        with patch.object(release, "urlopen", return_value=response) as request:
            url = release.publish(
                self.release, "example/lychee", "test-token", "https://api.github.com"
            )
        self.assertEqual(url, "https://github.com/existing")
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0].get_method(), "GET")

    def test_permission_and_server_errors_do_not_attempt_creation(self) -> None:
        for code in (401, 403, 500):
            with (
                self.subTest(code=code),
                patch.object(release, "urlopen", side_effect=self.error(code)) as request,
            ):
                with self.assertRaises(HTTPError):
                    release.publish(
                        self.release, "example/lychee", "test-token", "https://api.github.com"
                    )
                request.assert_called_once()

    def test_publish_requires_token(self) -> None:
        with (
            patch.object(release, "urlopen") as request,
            self.assertRaisesRegex(ValueError, "GITHUB_TOKEN"),
        ):
            release.publish(self.release, "example/lychee", "", "https://api.github.com")
        request.assert_not_called()

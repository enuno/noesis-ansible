"""Offline tests for scope decisions, source scanning, and document identity.

No network access and no writes to the real wiki.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import SyncTestBase, make_scope, write_doc  # noqa: E402

from wiki_hindsight_sync.engine import plan_run  # noqa: E402
from wiki_hindsight_sync.manifest import document_id_for  # noqa: E402
from wiki_hindsight_sync.scope import Scope  # noqa: E402


class TestScopeDecisions(SyncTestBase):
    def test_allowlisted_file_is_eligible(self):
        decision = self.scope.decide(PurePosixPath("docs/a.md"))
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.classification, "test-doc")

    def test_unlisted_file_is_excluded(self):
        decision = self.scope.decide(PurePosixPath("other/a.md"))
        self.assertFalse(decision.eligible)
        self.assertEqual(decision.reason, "not_allowlisted")

    def test_sensitive_tree_is_excluded_even_if_allowlisted(self):
        scope = Scope.from_rules(
            "test-wiki",
            [("legal", "dir", "test-doc", "deliberately bad rule")],
        )
        decision = scope.decide(PurePosixPath("legal/case.md"))
        self.assertFalse(decision.eligible)
        self.assertIn("sensitive_tree", decision.reason)

    def test_non_markdown_is_excluded(self):
        decision = self.scope.decide(PurePosixPath("docs/a.json"))
        self.assertFalse(decision.eligible)
        self.assertEqual(decision.reason, "non_prose_suffix")

    def test_secret_filename_is_excluded(self):
        decision = self.scope.decide(PurePosixPath("docs/api-key.md"))
        self.assertFalse(decision.eligible)
        self.assertEqual(decision.reason, "secret_filename")

    def test_secret_content_is_detected_not_by_filename(self):
        # The filename is innocuous; the content is a live-format credential.
        # An AWS access key id is exactly 20 characters: AKIA + 16.
        hits = Scope.find_secrets("token = AKIAIOSFODNN7EXAMPLE")
        self.assertIn("aws_access_key", hits)

    def test_prose_mentioning_secrets_is_not_flagged(self):
        hits = Scope.find_secrets(
            "The token-standard defines API-key rotation. Secret rotation is "
            "handled by Bitwarden Secrets Manager."
        )
        self.assertEqual(hits, [])

    def test_placeholder_values_are_not_flagged(self):
        hits = Scope.find_secrets('api_key = "YOUR_API_KEY_HERE"')
        self.assertEqual(hits, [])


class TestScan(SyncTestBase):
    def test_empty_document_becomes_review_item(self):
        write_doc(self.root, "docs/empty.md", "   \n")
        report = plan_run(self.make_config())
        self.assertEqual(report.counts.get("create", 0), 0)
        self.assertTrue(
            any("empty document" in item.detail for item in report.review_items)
        )

    def test_secret_bearing_document_becomes_review_item(self):
        write_doc(self.root, "docs/leak.md", "key: AKIAIOSFODNN7EXAMPLE")
        report = plan_run(self.make_config())
        self.assertTrue(
            any("secret-shaped content" in item.detail for item in report.review_items)
        )

    def test_symlink_escape_is_not_followed(self):
        outside = Path(self._tmp.name) / "outside.md"
        outside.write_text("secret outside the wiki", encoding="utf-8")
        docs = self.root / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        os.symlink(outside, docs / "escape.md")
        report = plan_run(self.make_config())
        paths = {rel for rel, _ in report.excluded}
        self.assertTrue(any("escape.md" in p for p in paths))
        self.assertEqual(report.counts.get("create", 0), 0)

    def test_missing_root_is_an_error(self):
        config = self.make_config(wiki_root=Path(self._tmp.name) / "nope")
        with self.assertRaises(FileNotFoundError):
            plan_run(config)

    def test_unreadable_file_is_a_review_item(self):
        write_doc(self.root, "docs/a.md", "# A\n")
        path = self.root / "docs/a.md"
        os.chmod(path, 0o000)
        try:
            report = plan_run(self.make_config())
        finally:
            os.chmod(path, 0o644)
        if report.counts.get("create", 0) == 0:
            self.assertTrue(
                any("unreadable" in item.detail for item in report.review_items)
            )


class TestDocumentIdentity(SyncTestBase):
    def test_identity_is_deterministic(self):
        self.assertEqual(
            document_id_for("ns", "concepts/a.md"),
            document_id_for("ns", "concepts/a.md"),
        )

    def test_identity_depends_on_namespace(self):
        self.assertNotEqual(
            document_id_for("a", "x.md"), document_id_for("b", "x.md")
        )

    def test_identity_depends_on_path(self):
        self.assertNotEqual(
            document_id_for("ns", "x/y.md"), document_id_for("ns", "x/z.md")
        )

    def test_identity_survives_content_change(self):
        write_doc(self.root, "docs/a.md", "one")
        before = document_id_for("test-wiki", "docs/a.md")
        write_doc(self.root, "docs/a.md", "two")
        after = document_id_for("test-wiki", "docs/a.md")
        self.assertEqual(before, after)

    def test_identity_is_url_safe(self):
        doc_id = document_id_for("ns", "docs/a file (v2).md")
        self.assertNotIn(" ", doc_id)
        self.assertNotIn("(", doc_id)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

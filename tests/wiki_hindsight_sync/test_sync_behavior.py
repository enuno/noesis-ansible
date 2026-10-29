"""Offline tests for the sync's plan, apply, manifest, and locking behavior.

No network access and no writes to the real wiki.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import FakeHindsight, SyncTestBase, write_doc  # noqa: E402

from wiki_hindsight_sync.engine import plan_run  # noqa: E402
from wiki_hindsight_sync.manifest import (  # noqa: E402
    LockHeld,
    SyncError,
    _Lock,
    load_manifest,
    save_manifest,
    sha256_bytes,
)
from wiki_hindsight_sync.scope import Scope  # noqa: E402


class TestPlanAndApply(SyncTestBase):
    def test_initial_sync_creates_documents(self):
        write_doc(self.root, "docs/a.md", "# A\n\ncontent a\n")
        write_doc(self.root, "docs/b.md", "# B\n\ncontent b\n")
        fake = FakeHindsight()
        report = self.apply_with(fake)
        self.assertEqual(report.counts.get("create"), 2)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(len(fake.documents), 2)
        manifest = load_manifest(
            self.state / "manifest.json", self.make_config().scope_key()
        )
        self.assertEqual(len(manifest["documents"]), 2)

    def test_noop_rerun_performs_no_ingestion(self):
        write_doc(self.root, "docs/a.md", "# A\n\ncontent a\n")
        self.apply_with(FakeHindsight())
        fake = FakeHindsight()
        report = self.apply_with(fake)
        self.assertEqual(len(fake.calls), 0)
        self.assertEqual(report.counts.get("create", 0), 0)

    def test_changed_document_is_replaced_not_duplicated(self):
        write_doc(self.root, "docs/a.md", "# A\n\nv1\n")
        self.apply_with(FakeHindsight())
        write_doc(self.root, "docs/a.md", "# A\n\nv2\n")
        fake = FakeHindsight()
        report = self.apply_with(fake)
        self.assertEqual(report.counts.get("update"), 1)
        self.assertEqual(report.counts.get("create", 0), 0)
        self.assertEqual(len(fake.documents), 1)
        self.assertIn("v2", list(fake.documents.values())[0]["text"])

    def test_failed_ingestion_does_not_advance_manifest(self):
        write_doc(self.root, "docs/a.md", "# A\n\nv1\n")
        write_doc(self.root, "docs/b.md", "# B\n\nv2\n")
        fake = FakeHindsight(fail_on={"docs/b.md"})
        report = self.apply_with(fake)
        self.assertTrue(report.errors)
        manifest = load_manifest(
            self.state / "manifest.json", self.make_config().scope_key()
        )
        self.assertIn("docs/a.md", manifest["documents"])
        self.assertNotIn("docs/b.md", manifest["documents"])

    def test_deleted_source_is_a_review_item_and_is_not_deleted_remotely(self):
        write_doc(self.root, "docs/a.md", "# A\n\nv1\n")
        fake = FakeHindsight()
        self.apply_with(fake)
        os.remove(self.root / "docs/a.md")
        report = self.apply_with(fake)
        self.assertTrue(
            any("no longer present" in item.detail for item in report.review_items)
        )
        self.assertEqual(fake.deleted, [])
        self.assertEqual(len(fake.documents), 1)

    def test_renamed_source_creates_new_identity_and_keeps_the_old(self):
        write_doc(self.root, "docs/a.md", "# A\n\nv1\n")
        fake = FakeHindsight()
        self.apply_with(fake)
        os.rename(self.root / "docs/a.md", self.root / "docs/b.md")
        report = self.apply_with(fake)
        self.assertEqual(report.counts.get("create"), 1)
        self.assertEqual(report.counts.get("update", 0), 0)
        self.assertEqual(len(fake.documents), 2)
        self.assertEqual(fake.deleted, [])

    def test_runtime_budget_stops_the_run(self):
        for i in range(3):
            write_doc(self.root, f"docs/{i}.md", f"# {i}\n")
        fake = FakeHindsight()
        config = self.make_config(dry_run=False, max_runtime_s=0.0)
        # A budget of 0 means no limit; use a negative-value guard instead:
        # set the budget so small that it is already spent.
        config.max_runtime_s = 0.000001
        report = self.apply_with(fake, config=config)
        self.assertTrue(report.errors)
        self.assertIn("runtime budget exhausted", " ".join(report.errors))

    def test_max_documents_ceiling_is_enforced(self):
        for i in range(3):
            write_doc(self.root, f"docs/{i}.md", f"# {i}\n")
        config = self.make_config(dry_run=False, max_documents=2)
        with self.assertRaises(SyncError):
            self.apply_with(FakeHindsight(), config=config)

    def test_duplicate_include_paths_ingest_once(self):
        scope = Scope.from_rules(
            "test-wiki",
            [
                ("docs", "dir", "test-doc", "directory rule"),
                ("docs/a.md", "file", "test-doc", "explicit file rule"),
            ],
        )
        write_doc(self.root, "docs/a.md", "# A\n")
        fake = FakeHindsight()
        report = self.apply_with(
            fake, config=self.make_config(scope=scope, dry_run=False)
        )
        self.assertEqual(report.counts.get("create"), 1)
        self.assertEqual(len(fake.documents), 1)

    def test_dry_run_does_not_contact_hindsight(self):
        write_doc(self.root, "docs/a.md", "# A\n")
        report = plan_run(self.make_config())
        self.assertEqual(report.counts.get("create"), 1)
        # A dry run writes no manifest either.
        self.assertFalse((self.state / "manifest.json").exists())

    def test_provenance_metadata_is_recorded(self):
        write_doc(
            self.root,
            "docs/a.md",
            "---\ntitle: Page A\nupdated: 2026-10-01\ntype: concept\n---\n\nbody\n",
        )
        fake = FakeHindsight()
        self.apply_with(fake)
        item = fake.calls[0]["items"][0]
        meta = item["metadata"]
        self.assertEqual(meta["source_path"], "docs/a.md")
        self.assertEqual(meta["source_classification"], "test-doc")
        self.assertEqual(meta["doc_updated"], "2026-10-01")
        self.assertEqual(meta["source_title"], "Page A")
        self.assertEqual(len(meta["source_sha256"]), 64)
        self.assertEqual(item["update_mode"], "replace")

    def test_retain_item_carries_the_sync_namespace_tags(self):
        write_doc(self.root, "docs/a.md", "# A\n")
        fake = FakeHindsight()
        self.apply_with(fake)
        tags = fake.calls[0]["items"][0]["tags"]
        self.assertIn("source:noesis-wiki-sync", tags)
        self.assertIn("source:noesis-wiki-sync-doc", tags)

    def test_provenance_follows_the_repo_memory_routing_schema(self):
        write_doc(self.root, "docs/a.md", "# A\n")
        fake = FakeHindsight()
        self.apply_with(fake)
        meta = fake.calls[0]["items"][0]["metadata"]
        for field in (
            "record_id",
            "agent_id",
            "scope",
            "source_reference",
            "recorded_time",
            "verification_status",
            "sensitivity",
            "sharing_status",
            "review_time",
        ):
            self.assertIn(field, meta)
            self.assertTrue(meta[field], f"{field} must not be empty")
        self.assertEqual(meta["verification_status"], "derived")
        self.assertEqual(meta["sharing_status"], "approved-shared")
        self.assertEqual(meta["source_reference"], "llm-wiki:docs/a.md")

    def test_low_confidence_document_is_recorded_as_open(self):
        write_doc(
            self.root,
            "docs/a.md",
            "---\ntitle: A\nconfidence: low\n---\n\nbody\n",
        )
        fake = FakeHindsight()
        self.apply_with(fake)
        meta = fake.calls[0]["items"][0]["metadata"]
        self.assertEqual(meta["verification_status"], "open")

    def test_sync_never_claims_verified(self):
        # A page asserting a verified deployment is still a derived record:
        # the sync ingests a document, it does not confirm the claim.
        write_doc(
            self.root,
            "docs/a.md",
            "---\ntitle: A\nconfidence: high\nstatus: deployed\n---\n\nbody\n",
        )
        fake = FakeHindsight()
        self.apply_with(fake)
        meta = fake.calls[0]["items"][0]["metadata"]
        self.assertNotEqual(meta["verification_status"], "verified")

    def test_timeless_document_sends_an_unset_timestamp(self):
        write_doc(
            self.root,
            "docs/a.md",
            "---\ntitle: A\nupdated: 2026-10-01\n---\n\nbody\n",
        )
        fake = FakeHindsight()
        self.apply_with(fake)
        item = fake.calls[0]["items"][0]
        # The wiki date is a revision date, not an event date.
        self.assertEqual(item["timestamp"], "unset")
        self.assertEqual(item["metadata"]["doc_updated"], "2026-10-01")

    def test_explicit_event_time_is_used_as_the_timestamp(self):
        scope = Scope.from_rules(
            "test-wiki",
            [("docs", "dir", "test-doc", "test scope")],
            event_times={"docs": "2026-08-28"},
        )
        write_doc(self.root, "docs/a.md", "# A\n")
        fake = FakeHindsight()
        self.apply_with(
            fake, config=self.make_config(scope=scope, dry_run=False)
        )
        item = fake.calls[0]["items"][0]
        self.assertEqual(item["timestamp"], "2026-08-28")
        self.assertEqual(item["metadata"]["event_time"], "2026-08-28")

    def test_update_records_what_it_supersedes(self):
        write_doc(self.root, "docs/a.md", "# A\n\nv1\n")
        self.apply_with(FakeHindsight())
        write_doc(self.root, "docs/a.md", "# A\n\nv2\n")
        fake = FakeHindsight()
        self.apply_with(fake)
        meta = fake.calls[0]["items"][0]["metadata"]
        self.assertEqual(len(meta["supersedes"]), 64)


class TestManifestScope(SyncTestBase):
    def _write_manifest(self, scope_overrides: dict) -> None:
        scope = self.make_config().scope_key()
        scope.update(scope_overrides)
        save_manifest(
            self.state / "manifest.json",
            {
                "version": 1,
                "scope": scope,
                "documents": {"docs/a.md": {"sha256": "x", "size": 1}},
            },
        )

    def test_bank_mismatch_is_refused(self):
        self._write_manifest({"bank_id": "other-bank"})
        with self.assertRaises(SyncError) as ctx:
            plan_run(self.make_config())
        self.assertIn("different scope", str(ctx.exception))

    def test_endpoint_mismatch_is_refused(self):
        self._write_manifest({"endpoint": "https://other.invalid"})
        with self.assertRaises(SyncError):
            plan_run(self.make_config())

    def test_root_mismatch_is_refused(self):
        self._write_manifest({"wiki_root": "/somewhere/else"})
        with self.assertRaises(SyncError):
            plan_run(self.make_config())

    def test_namespace_mismatch_is_refused(self):
        self._write_manifest({"namespace": "other"})
        with self.assertRaises(SyncError):
            plan_run(self.make_config())

    def test_matching_scope_is_accepted(self):
        # A manifest written for this exact scope is accepted, and a file
        # whose hash matches the manifest is skipped.
        write_doc(self.root, "docs/a.md", "# A\n")
        digest = sha256_bytes((self.root / "docs/a.md").read_bytes())
        scope = self.make_config().scope_key()
        save_manifest(
            self.state / "manifest.json",
            {
                "version": 1,
                "scope": scope,
                "documents": {
                    "docs/a.md": {
                        "document_id": "test-wiki/docs/a.md",
                        "sha256": digest,
                        "size": 5,
                        "classification": "test-doc",
                    }
                },
            },
        )
        report = plan_run(self.make_config())
        self.assertEqual(report.counts.get("skip"), 1)
        self.assertEqual(report.counts.get("create", 0), 0)
        self.assertEqual(report.counts.get("update", 0), 0)


class TestLocking(SyncTestBase):
    def test_overlapping_runs_are_refused(self):
        config = self.make_config()
        with _Lock(config.lock_path):
            with self.assertRaises(LockHeld):
                plan_run(config)


class TestUnrelatedDocumentsUntouched(SyncTestBase):
    def test_only_namespaced_documents_are_written(self):
        write_doc(self.root, "docs/a.md", "# A\n")
        fake = FakeHindsight()
        # A document that belongs to another writer.
        fake.documents["someone-elses-document"] = {"sha256": "other"}
        self.apply_with(fake)
        self.assertIn("someone-elses-document", fake.documents)
        self.assertEqual(fake.deleted, [])
        synced = [d for d in fake.documents if d.startswith("test-wiki/")]
        self.assertEqual(len(synced), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

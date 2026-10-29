"""Shared fixtures for the offline wiki -> Hindsight sync tests.

No network access and no writes to the real wiki. Every test builds its
own temporary wiki and its own fake Hindsight transport.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "roles/wiki_hindsight_sync/files"))

from wiki_hindsight_sync.engine import Config  # noqa: E402
from wiki_hindsight_sync.scope import Scope  # noqa: E402


class FakeResponse:
    """The minimal context-manager shape urllib returns."""

    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None


class FakeHindsight:
    """A recording stand-in for HindsightClient.

    It models the two behaviours the sync depends on: a retain with a
    document_id replaces that document, and nothing is ever deleted.
    """

    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.calls: list[dict] = []
        self.documents: dict[str, dict] = {}
        self.fail_on = fail_on or set()
        self.deleted: list[str] = []

    def retain(self, bank_id, items, *, use_async=False, operation_id=None):
        from wiki_hindsight_sync.hindsight import HindsightError, RetainOutcome

        self.calls.append(
            {"bank_id": bank_id, "items": items, "async": use_async}
        )
        for item in items:
            doc_id = item["document_id"]
            if any(f in doc_id for f in self.fail_on):
                raise HindsightError(f"simulated failure for {doc_id}")
            self.documents[doc_id] = {
                "sha256": item["metadata"]["source_sha256"],
                "text": item["content"],
                "tags": item.get("tags", []),
                "metadata": item.get("metadata", {}),
            }
        return RetainOutcome(
            success=True,
            bank_id=bank_id,
            items_count=len(items),
            async_=use_async,
            usage={"input_tokens": 10 * len(items), "output_tokens": 3 * len(items)},
        )

    def wait_for_operation(self, bank_id, operation_id, **kwargs):
        return {"operation_id": operation_id, "status": "completed"}

    def list_documents(self, bank_id, **kwargs):
        return list(self.documents.values())

    def delete_document(self, doc_id):
        # Present only to prove the sync never calls it.
        self.deleted.append(doc_id)
        raise AssertionError("the sync must never delete remotely")


def make_scope(rules: list[tuple[str, str, str, str]] | None = None) -> Scope:
    if rules is None:
        rules = [("docs", "dir", "test-doc", "test scope")]
    return Scope.from_rules(
        "test-wiki", rules, reviewed_on="2026-10-27"
    )


def write_doc(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class SyncTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "wiki"
        self.root.mkdir()
        self.state = Path(self._tmp.name) / "state"
        self.state.mkdir()
        self.scope = make_scope()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_config(self, **overrides) -> Config:
        params = dict(
            wiki_root=self.root,
            bank_id="test-bank",
            endpoint="https://hindsight.invalid",
            namespace="test-wiki",
            state_dir=self.state,
            api_key="test-key-not-real",
            scope=self.scope,
            dry_run=True,
        )
        params.update(overrides)
        return Config(**params)

    def apply_with(self, fake: FakeHindsight, config: Config | None = None):
        """Run an apply against a fake transport, restoring the real one after."""
        import wiki_hindsight_sync.engine as engine

        config = config or self.make_config(dry_run=False)
        original = engine.HindsightClient
        engine.HindsightClient = lambda *a, **k: fake  # type: ignore[assignment]
        try:
            report = engine.apply_run(config)
        finally:
            engine.HindsightClient = original  # type: ignore[assignment]
        return report


__all__ = [
    "FakeHindsight",
    "FakeResponse",
    "SyncTestBase",
    "make_scope",
    "os",
    "write_doc",
]

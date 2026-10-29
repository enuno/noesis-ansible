"""The sync engine: plan and apply.

Direction is fixed: wiki -> Hindsight. Nothing in this module writes to the
wiki, and nothing in this module deletes anything remotely.

The engine is split into a plan phase and an apply phase:

  plan_run()  reads the wiki, hashes candidates, compares against the
              manifest, and returns the actions that *would* be taken. It
              never contacts Hindsight and never retains content.

  apply_run() executes the actions from a plan and advances the manifest
              only after the server confirms each ingestion.

Both phases take the same lock, so two runs cannot overlap.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .hindsight import HindsightClient, HindsightError
from .manifest import (
    DOC_TAG,
    SYNC_TAG,
    LockHeld,
    SyncError,
    _Lock,
    document_id_for,
    load_manifest,
    save_manifest,
    scope_of,
    utcnow,
)
from .scope import Scope
from .source import Candidate, scan_wiki

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_SKIP = "skip"
ACTION_REVIEW = "review"


@dataclass
class Config:
    """Everything the sync needs to run."""

    wiki_root: Path
    bank_id: str
    endpoint: str
    namespace: str
    state_dir: Path
    api_key: str
    scope: Scope
    dry_run: bool = True
    timeout_s: float = 120.0
    max_attempts: int = 3
    use_async: bool = False
    #: Maximum documents ingested in one apply run; 0 means no ceiling.
    max_documents: int = 0
    #: Wall-clock budget for the run; 0 means no limit. The run stops
    #: starting new documents once the budget is spent.
    max_runtime_s: float = 0.0

    @property
    def manifest_path(self) -> Path:
        return self.state_dir / "manifest.json"

    @property
    def lock_path(self) -> Path:
        return self.state_dir / "run.lock"

    def scope_key(self) -> dict[str, str]:
        return scope_of(self.endpoint, self.bank_id, self.namespace, self.wiki_root)


@dataclass
class Action:
    """One proposed or completed operation."""

    action: str
    rel: str
    document_id: str
    classification: str
    sha256: str
    size: int
    detail: str = ""
    revision: dict[str, str] = field(default_factory=dict)
    title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Report:
    """The outcome of a plan or apply run."""

    dry_run: bool
    bank_id: str
    endpoint: str
    namespace: str
    wiki_root: str
    started_at: str
    actions: list[Action] = field(default_factory=list)
    review_items: list[Action] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "bank_id": self.bank_id,
            "endpoint": self.endpoint,
            "namespace": self.namespace,
            "wiki_root": self.wiki_root,
            "started_at": self.started_at,
            "counts": self.counts,
            "actions": [a.to_dict() for a in self.actions],
            "review_items": [a.to_dict() for a in self.review_items],
            "excluded": [{"path": p, "reason": r} for p, r in self.excluded],
            "errors": self.errors,
            "usage": self.usage,
        }


def build_plan(
    config: Config,
    manifest: dict[str, Any],
    candidates: list[Candidate],
) -> tuple[list[Action], list[Action]]:
    """Compare candidates against the manifest.

    Returns (actions, review_items). A candidate whose hash matches the
    manifest is skipped; one whose hash differs is an update; one not in
    the manifest is a create.

    Files the manifest knows about that are gone from the wiki become
    review items. They are never deleted remotely.
    """
    known = manifest.get("documents", {})
    actions: list[Action] = []
    review: list[Action] = []

    seen: set[str] = set()
    for cand in candidates:
        seen.add(cand.rel)
        doc_id = document_id_for(config.namespace, cand.rel)
        entry = known.get(cand.rel)
        if entry and entry.get("sha256") == cand.sha256:
            actions.append(
                Action(
                    action=ACTION_SKIP,
                    rel=cand.rel,
                    document_id=doc_id,
                    classification=cand.classification,
                    sha256=cand.sha256,
                    size=cand.size,
                    detail="unchanged",
                    revision=cand.revision,
                    title=cand.title,
                )
            )
            continue
        actions.append(
            Action(
                action=ACTION_UPDATE if entry else ACTION_CREATE,
                rel=cand.rel,
                document_id=doc_id,
                classification=cand.classification,
                sha256=cand.sha256,
                size=cand.size,
                detail="changed" if entry else "new",
                revision=cand.revision,
                title=cand.title,
            )
        )

    for rel, entry in known.items():
        if rel in seen:
            continue
        review.append(
            Action(
                action=ACTION_REVIEW,
                rel=rel,
                document_id=document_id_for(config.namespace, rel),
                classification=entry.get("classification", ""),
                sha256=entry.get("sha256", ""),
                size=int(entry.get("size") or 0),
                detail="source file no longer present; not deleted remotely",
            )
        )
    return actions, review


def _verification_status(cand: Candidate) -> str:
    """Map the wiki's own confidence onto the repo's verification vocabulary.

    The vocabulary is the one fixed by the noesis-memory-routing skill:
    verified | derived | inference | open.

    The sync never emits "verified". It ingests a document; it does not
    independently confirm what the document claims. A page with
    `confidence: high` is a reviewed, cited source, so the record derived
    from it is "derived". A page with `confidence: low`, or one that
    declares itself draft or open, is "open".
    """
    confidence = cand.revision.get("doc_confidence", "").strip().lower()
    status = cand.revision.get("doc_status", "").strip().lower()
    if confidence in ("low", "unverified") or status in ("draft", "open", "proposed"):
        return "open"
    return "derived"


def _retain_item(
    config: Config, cand: Candidate, doc_id: str, text: str, supersedes: str = ""
) -> dict[str, Any]:
    """Build one retain item with its provenance metadata.

    The metadata keys follow the provenance schema fixed by the
    noesis-memory-routing skill, so a record written by this sync is
    legible to the rest of the memory architecture: record_id, agent_id,
    scope, source_reference, event_time, recorded_time,
    verification_status, sensitivity, sharing_status, supersedes,
    review_time.

    `metadata` is the flat string-to-string map the deployed API accepts on
    a retain item; it is stored on the memory unit and returned with every
    recalled memory.
    """
    metadata: dict[str, str] = {
        # -- the repo's provenance schema --
        "record_id": doc_id,
        "agent_id": "noesis-wiki-sync",
        "scope": config.namespace,
        "source_reference": f"llm-wiki:{cand.rel}",
        "recorded_time": utcnow(),
        "verification_status": _verification_status(cand),
        "sensitivity": "internal",
        # The wiki is shared cross-agent context and this bank is shared, so
        # these records are shared on purpose.
        "sharing_status": "approved-shared",
        "review_time": config.scope.reviewed_on,
        # -- the fields this sync is required to record --
        "source_path": cand.rel,
        "source_sha256": cand.sha256,
        "source_classification": cand.classification,
        "sync_namespace": config.namespace,
    }
    if supersedes:
        metadata["supersedes"] = supersedes
    metadata.update(cand.revision)
    if cand.title:
        metadata["source_title"] = cand.title

    # The wiki's dates are revision dates, not the date an event occurred.
    # A retained page is reference material, so the event anchor is "unset"
    # unless the scope rule explicitly opts into the document's own date.
    event_time = cand.revision.get("event_time", "")
    item: dict[str, Any] = {
        "content": text,
        "context": f"noesis-wiki document ({cand.classification})",
        "document_id": doc_id,
        "metadata": metadata,
        "tags": [SYNC_TAG, DOC_TAG],
        "timestamp": event_time or "unset",
        # 'replace' is the documented default and the behavior this sync
        # depends on: re-retaining the same document_id deletes the old
        # document and its memory units before creating new ones.
        "update_mode": "replace",
    }
    return item


def _review_action(detail: str) -> Action:
    return Action(
        action=ACTION_REVIEW,
        rel=detail.split(":", 1)[0],
        document_id="",
        classification="",
        sha256="",
        size=0,
        detail=detail,
    )


def plan_run(config: Config) -> Report:
    """Produce the inventory of what a run would do. No writes to Hindsight."""
    with _Lock(config.lock_path):
        manifest = load_manifest(config.manifest_path, config.scope_key())
        scan = scan_wiki(config.wiki_root, config.scope)
        actions, review_actions = build_plan(config, manifest, scan.candidates)

        report = Report(
            dry_run=True,
            bank_id=config.bank_id,
            endpoint=config.endpoint,
            namespace=config.namespace,
            wiki_root=str(config.wiki_root),
            started_at=utcnow(),
        )
        report.actions = actions
        report.excluded = scan.excluded
        report.review_items = list(review_actions)
        report.review_items.extend(_review_action(item) for item in scan.review)

        counts: dict[str, int] = {}
        for action in actions:
            counts[action.action] = counts.get(action.action, 0) + 1
        counts["excluded"] = len(scan.excluded)
        counts["review"] = len(report.review_items)
        report.counts = counts
        return report


def apply_run(config: Config) -> Report:
    """Run the sync for real, writing to Hindsight."""
    with _Lock(config.lock_path):
        manifest = load_manifest(config.manifest_path, config.scope_key())
        scan = scan_wiki(config.wiki_root, config.scope)
        actions, review_actions = build_plan(config, manifest, scan.candidates)
        by_rel = {c.rel: c for c in scan.candidates}

        client = HindsightClient(
            config.endpoint,
            config.api_key,
            timeout=config.timeout_s,
            max_attempts=config.max_attempts,
        )
        report = _apply_actions(config, client, manifest, actions, by_rel)
        report.excluded = scan.excluded
        report.review_items = list(review_actions)
        report.review_items.extend(_review_action(item) for item in scan.review)
        report.counts.setdefault("review", len(report.review_items))
        return report


def _apply_actions(
    config: Config,
    client: HindsightClient,
    manifest: dict[str, Any],
    actions: list[Action],
    candidates: dict[str, Candidate],
) -> Report:
    """Execute the create/update actions and advance the manifest.

    A manifest entry is written only after the server confirms the
    ingestion. A failure leaves the manifest unchanged for that document,
    so the next run retries it.
    """
    report = Report(
        dry_run=config.dry_run,
        bank_id=config.bank_id,
        endpoint=config.endpoint,
        namespace=config.namespace,
        wiki_root=str(config.wiki_root),
        started_at=utcnow(),
    )
    documents = manifest.setdefault("documents", {})
    totals: dict[str, int] = {}

    # For an update, the previous content hash is the superseded record.
    # The upstream 'replace' semantics delete the old document, so this
    # is the only durable pointer to what it was.
    supersedes = {
        rel: entry.get("sha256", "")
        for rel, entry in documents.items()
        if entry.get("sha256")
    }

    todo = [a for a in actions if a.action in (ACTION_CREATE, ACTION_UPDATE)]
    if config.max_documents and len(todo) > config.max_documents:
        raise SyncError(
            f"apply would ingest {len(todo)} documents, above the "
            f"--max-documents ceiling of {config.max_documents}"
        )

    deadline = (
        time.monotonic() + config.max_runtime_s if config.max_runtime_s else None
    )
    for action in todo:
        if deadline is not None and time.monotonic() >= deadline:
            report.errors.append(
                "runtime budget exhausted; remaining documents were not ingested"
            )
            break
        cand = candidates.get(action.rel)
        if cand is None:
            report.errors.append(f"{action.rel}: candidate vanished before apply")
            continue
        try:
            text = cand.abs_path.read_text(encoding="utf-8")
        except OSError as exc:
            report.errors.append(f"{action.rel}: read failed ({exc.strerror})")
            continue

        item = _retain_item(
            config,
            cand,
            action.document_id,
            text,
            supersedes=supersedes.get(action.rel, ""),
        )
        try:
            outcome = client.retain(config.bank_id, [item], use_async=config.use_async)
            if outcome.async_ and outcome.operation_id:
                client.wait_for_operation(config.bank_id, outcome.operation_id)
        except HindsightError as exc:
            report.errors.append(f"{action.rel}: ingest failed ({exc})")
            totals["failed"] = totals.get("failed", 0) + 1
            continue

        if not outcome.success:
            report.errors.append(f"{action.rel}: server reported failure")
            totals["failed"] = totals.get("failed", 0) + 1
            continue

        # Only now is the document considered ingested.
        documents[action.rel] = {
            "document_id": action.document_id,
            "sha256": action.sha256,
            "size": action.size,
            "classification": action.classification,
            "revision": action.revision,
            "title": action.title,
            "ingested_at": utcnow(),
        }
        save_manifest(config.manifest_path, manifest)

        action.detail = f"{action.detail} -> ingested"
        report.actions.append(action)
        totals[action.action] = totals.get(action.action, 0) + 1
        for key, value in (outcome.usage or {}).items():
            if isinstance(value, (int, float)):
                report.usage[key] = report.usage.get(key, 0) + value

    report.counts = totals
    return report


__all__ = [
    "ACTION_CREATE",
    "ACTION_REVIEW",
    "ACTION_SKIP",
    "ACTION_UPDATE",
    "Action",
    "Config",
    "LockHeld",
    "Report",
    "SyncError",
    "apply_run",
    "build_plan",
    "plan_run",
]

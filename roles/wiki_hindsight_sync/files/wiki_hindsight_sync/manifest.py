"""Manifest handling, locking, and document identity.

The manifest is the sync's memory of what it has already ingested. It is
scoped to (endpoint, bank, namespace, wiki root) so that a hash recorded
against one target is never compared against another.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST_VERSION = 1

# Namespace tag applied to every document this sync owns.
SYNC_TAG = "source:noesis-wiki-sync"

# Per-document tag. The documents endpoint filters with `tags` +
# `tags_match=any_strict`, so this isolates the sync's documents from every
# other document in the bank.
DOC_TAG = "source:noesis-wiki-sync-doc"


class SyncError(RuntimeError):
    """A sync precondition failed."""


class LockHeld(SyncError):
    """Another run holds the lock."""


class _Lock:
    """An exclusive, non-blocking lock file.

    The lock is advisory (flock) and lives outside the wiki. A second run
    fails fast rather than racing the first.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    def __enter__(self) -> "_Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise LockHeld(f"another sync run holds {self.path}") from exc
            raise
        self._fd = fd
        return self

    def __exit__(self, *_: object) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically: temp file in the same dir, fsync, rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def scope_of(
    endpoint: str, bank_id: str, namespace: str, wiki_root: Path
) -> dict[str, str]:
    """The scope key a manifest is bound to."""
    return {
        "endpoint": endpoint,
        "bank_id": bank_id,
        "namespace": namespace,
        "wiki_root": str(wiki_root.resolve()),
    }


def load_manifest(
    manifest_path: Path, scope: dict[str, str]
) -> dict[str, Any]:
    """Load the manifest, or return an empty one.

    A manifest written for a different scope is a hard error: reusing it
    would make the skip logic compare hashes across unrelated targets.
    """
    if not manifest_path.exists():
        return {
            "version": MANIFEST_VERSION,
            "scope": dict(scope),
            "documents": {},
        }
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncError(
            f"manifest at {manifest_path} is not valid JSON: {exc}"
        ) from exc
    if data.get("version") != MANIFEST_VERSION:
        raise SyncError(
            f"manifest at {manifest_path} has version {data.get('version')!r}; "
            f"this sync writes version {MANIFEST_VERSION}"
        )
    actual = data.get("scope") or {}
    mismatches = {
        key: (actual.get(key), value)
        for key, value in scope.items()
        if actual.get(key) != value
    }
    if mismatches:
        detail = ", ".join(
            f"{k}: manifest={a!r} current={b!r}"
            for k, (a, b) in mismatches.items()
        )
        raise SyncError(
            f"manifest at {manifest_path} was written for a different scope "
            f"({detail}). Point --state-dir at a directory for this target, or "
            "move the manifest aside deliberately. Refusing to reuse it."
        )
    data.setdefault("documents", {})
    return data


def save_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utcnow()
    atomic_write_json(manifest_path, manifest)


def document_id_for(namespace: str, rel: str) -> str:
    """Deterministic document identity for a wiki-relative path.

    The identity is a function of the namespace and the normalized path
    only. It does not depend on content, so a changed file keeps its
    identity and is replaced in place rather than duplicated.
    """
    parts = [p for p in PurePosixPath(rel).parts if p not in ("", ".")]
    encoded = "/".join(_encode_segment(p) for p in parts)
    return f"{namespace}/{encoded}"


def _encode_segment(segment: str) -> str:
    return re.sub(
        r"[^A-Za-z0-9._~-]", lambda m: f"%{ord(m.group(0)):02X}", segment
    )


def utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

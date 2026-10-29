"""Reading wiki source documents and their revision metadata.

Nothing here writes to the wiki. Files are opened read-only, and a file
that cannot be read cleanly becomes a review item rather than a silent
omission.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .manifest import sha256_bytes, utcnow
from .scope import Scope, relative_wiki_path, symlink_escapes

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
_FM_FIELDS = {
    "title": re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE),
    "updated": re.compile(r"^updated:\s*['\"]?([0-9]{4}-[0-9]{2}-[0-9]{2})", re.MULTILINE),
    "created": re.compile(r"^created:\s*['\"]?([0-9]{4}-[0-9]{2}-[0-9]{2})", re.MULTILINE),
    "type": re.compile(r"^type:\s*(.+?)\s*$", re.MULTILINE),
    "confidence": re.compile(r"^confidence:\s*(.+?)\s*$", re.MULTILINE),
    "status": re.compile(r"^status:\s*(.+?)\s*$", re.MULTILINE),
    "source": re.compile(r"^sources?:\s*(.+?)\s*$", re.MULTILINE),
}


@dataclass
class Candidate:
    """A wiki file considered for ingestion."""

    rel: str
    abs_path: Path
    size: int
    sha256: str
    classification: str
    reason: str
    #: Revision metadata from the wiki and its git history. These are
    #: document revision dates, never the date an event occurred.
    revision: dict[str, str] = field(default_factory=dict)
    title: str = ""


@dataclass
class ScanResult:
    """Everything one walk of the wiki produced."""

    candidates: list[Candidate] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)
    review: list[str] = field(default_factory=list)


def read_frontmatter(text: str) -> dict[str, str]:
    """Extract a small set of frontmatter fields.

    A deliberately narrow reader: it pulls the fields the sync records as
    provenance and nothing else. It is not a YAML parser and does not
    interpret arbitrary YAML.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    block = match.group(1)
    out: dict[str, str] = {}
    for key, pattern in _FM_FIELDS.items():
        found = pattern.search(block)
        if not found:
            continue
        value = found.group(1).strip().strip("'\"")
        if value and not value.startswith("["):
            out[key] = value
    return out


def git_revision(rel: str, root: Path) -> dict[str, str]:
    """Return the last git commit that touched a wiki-relative path.

    The commit date is the document's revision date. It is recorded as
    revision metadata and is never used as the occurrence time of an event.
    """
    env = dict(os.environ)
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%H%x1f%cI", "--", rel],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0:
        return {}
    line = proc.stdout.strip()
    if not line:
        return {}
    sha, _, date = line.partition("\x1f")
    return {"git_commit": sha, "git_date": date}


def scan_wiki(root: Path, scope: Scope) -> ScanResult:
    """Walk the wiki and collect eligible candidates.

    A candidate is a file that is in the allowlist, passes the content
    secret scan, and is readable. Files that are in scope but unusable
    (empty, unreadable, secret-bearing) become review items rather than
    silently disappearing.
    """
    from .scope import EXCLUDED_DIR_NAMES

    if not root.exists():
        raise FileNotFoundError(f"wiki root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"wiki root is not a directory: {root}")

    result = ScanResult()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = [
            d
            for d in dirnames
            if d not in EXCLUDED_DIR_NAMES
            and not d.startswith(".")
            and not (here / d).is_symlink()
        ]
        for filename in sorted(filenames):
            path = here / filename
            if path.is_symlink():
                if symlink_escapes(root, path):
                    result.excluded.append((str(path), "symlink_escape"))
                continue
            try:
                rel = relative_wiki_path(root, path)
            except ValueError:
                result.excluded.append((str(path), "path_escape"))
                continue

            decision = scope.decide(PurePosixPath(rel))
            if not decision.eligible:
                result.excluded.append((rel, decision.reason))
                continue

            try:
                data = path.read_bytes()
            except OSError as exc:
                result.review.append(f"{rel}: unreadable ({exc.strerror})")
                continue
            if not data.strip():
                result.review.append(f"{rel}: empty document")
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                result.review.append(f"{rel}: not valid UTF-8")
                continue

            hits = scope.find_secrets(text)
            if hits:
                result.review.append(
                    f"{rel}: secret-shaped content ({', '.join(hits)})"
                )
                continue

            front = read_frontmatter(text)
            revision: dict[str, str] = {}
            for key in ("updated", "created", "type", "confidence", "status", "source"):
                if front.get(key):
                    revision[f"doc_{key}"] = front[key]
            revision.update(git_revision(rel, root))

            # The event anchor is set only when a scope rule declares one
            # explicitly. The wiki's own `updated:` field is a revision
            # date, so it is recorded as revision metadata and is never
            # promoted to the event time on its own.
            rule = scope.best_rule(PurePosixPath(rel))
            if rule is not None and rule.event_time:
                revision["event_time"] = rule.event_time

            result.candidates.append(
                Candidate(
                    rel=rel,
                    abs_path=path,
                    size=len(data),
                    sha256=sha256_bytes(data),
                    classification=decision.classification,
                    reason=decision.reason,
                    revision=revision,
                    title=front.get("title", ""),
                )
            )
    return result

"""Ingestion scope rules for the llm-wiki -> Hindsight sync.

Scope is an explicit allowlist of wiki-relative paths, plus exclusions that
apply to everything. The allowlist is the unit of review: a reviewer approves
paths, not a directory that happens to contain them.

Exclusions are applied to the *content* as well as the path. A filename is
not evidence of safety, so every candidate is scanned for secret-shaped
content before it is eligible for retention.

This module is import-safe and has no third-party dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

# ---------------------------------------------------------------------------
# Path-level exclusions
# ---------------------------------------------------------------------------

# Directories that never hold wiki prose. Either machine state, generated
# output, or a checkout of another repository.
EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".github",
        ".obsidian",
        ".agents",
        ".claude",
        ".codex",
        ".opencode",
        ".omh",
        ".serena",
        ".copilot",
        ".gbrain",
        ".moltbot",
        ".history",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cache",
        "dist",
        "build",
        "site-packages",
        "assets",
        "images",
    }
)

# A path component that marks a tree as non-prose.
EXCLUDED_DIR_SUFFIXES = (".history", "_history", ".bak")

# ---------------------------------------------------------------------------
# Filename-level exclusions
# ---------------------------------------------------------------------------

# Exact basenames that are never wiki prose.
EXCLUDED_BASENAMES = frozenset(
    {
        ".env",
        "credentials.json",
        "cookies.txt",
        "cookies.sqlite",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "codeowners",
        "license",
        "dockerfile",
        "makefile",
    }
)

# Any basename containing one of these parts is excluded, unless it carries
# an example/template suffix.
SECRET_NAME_PARTS = (
    "secret",
    "credential",
    "token",
    "cookie",
    "password",
    "passwd",
    "mnemonic",
    "privatekey",
    "private-key",
    "seedphrase",
    "keystore",
    "apikey",
    "api-key",
    "api_key",
)

EXAMPLE_SUFFIXES = (".example", ".sample", ".template", ".tpl", ".dist")

# Binary and non-prose extensions.
NON_PROSE_SUFFIXES = frozenset(
    {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
        ".bmp",
        ".ico",
        ".tiff",
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".webm",
        ".mp3",
        ".wav",
        ".flac",
        ".aac",
        ".ogg",
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".7z",
        ".rar",
        ".dmg",
        ".iso",
        ".docx",
        ".doc",
        ".xlsx",
        ".xls",
        ".pptx",
        ".ppt",
        ".pyc",
        ".so",
        ".dylib",
        ".dll",
        ".exe",
        ".bin",
        ".gguf",
        ".safetensors",
        ".onnx",
        ".pt",
        ".pth",
        ".parquet",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".log",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".py",
        ".js",
        ".mjs",
        ".ts",
        ".tsx",
        ".jsx",
        ".sh",
        ".bash",
        ".zsh",
        ".rb",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".css",
        ".html",
        ".xml",
        ".csv",
        ".tsv",
        ".sql",
        ".ipynb",
        ".patch",
        ".diff",
    }
)

# ---------------------------------------------------------------------------
# Content-level secret detection
# ---------------------------------------------------------------------------

# High-confidence credential shapes. These patterns were validated against the
# whole wiki: they produced 258 raw matches, all of which were either
# placeholders (0x000...000, 0x123456...5678) or English prose that merely
# contained the words "token" or "secret" ("token-standard", "secret
# rotation"). The patterns below are anchored so that a bare noun does not
# match; a value must look like a credential, not like a word.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws_secret_key", re.compile(r"(?i)\baws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{32,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("stripe_key", re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("npm_token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    # agentmail-style API keys seen in the wiki tree
    ("agentmail_key", re.compile(r"\bam_[A-Za-z0-9]{32,}\b")),
    # a 32-byte hex private key (not a 20-byte ethereum address, which is public)
    ("hex_private_key", re.compile(r"\b(?:0x)?[0-9a-fA-F]{64}\b")),
    # credential assignment with an explicit value that is not a placeholder
    (
        "credential_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|api[_-]?secret|secret[_-]?key|access[_-]?token|"
            r"auth[_-]?token|password|passwd)\b\s*[=:]\s*"
            r"['\"]?(?!x{3,}|\*{3,}|\.\.\.|<[^>]*>|\{\{[^}]*\}\}|"
            r"redacted|changeme|placeholder|example|your[_-]?\w*|none|null|todo|"
            r"true|false|yes|no|\d+|env|\$)[A-Za-z0-9_./+=-]{16,}"
        ),
    ),
    # credential embedded in a URL
    ("url_embedded_credential", re.compile(r"https?://[^/\s:@]+:[^@\s/]{8,}@")),
    # bearer header with a real token
    ("bearer_token", re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._-]{20,}\b")),
)

# Files whose *name* marks them as sensitive even though the content is prose.
SENSITIVE_TREE_PARTS = frozenset(
    {
        "legal",
        "misjustice-alliance-firm",
        "missoula-eviction",
        "personal-journal",
        "legal-representation",
        "contract",
        "contracts",
        "private",
        "secret",
        "secrets",
        "wallet",
        "wallets",
        "keyring",
    }
)


@dataclass(frozen=True)
class ScopeRule:
    """One allowlist entry.

    path      wiki-relative path or directory prefix
    kind      'file' or 'dir'
    classif   provenance classification recorded with the retained document
    reason    why this path is in scope (carried into the manifest)
    event_time  optional explicit event anchor for the retained facts.
                Empty means the document is timeless reference material and
                the retain timestamp is sent as "unset". The wiki's
                `updated:` field is a *revision* date and is never used as
                an event anchor on its own.
    """

    path: str
    kind: str
    classif: str
    reason: str
    event_time: str = ""

    def matches(self, rel: PurePosixPath) -> bool:
        if self.kind == "file":
            return str(rel) == self.path
        prefix = self.path.rstrip("/") + "/"
        return str(rel).startswith(prefix)


@dataclass
class ScopeDecision:
    """Why a candidate path is or is not eligible."""

    rel: str
    eligible: bool
    reason: str
    classification: str = ""


@dataclass
class Scope:
    """The approved ingestion scope."""

    namespace: str
    rules: list[ScopeRule] = field(default_factory=list)
    exclude_sensitive_trees: bool = True
    max_bytes: int = 400_000
    #: Date the scope was last reviewed by a human. Recorded as the
    #: `review_time` provenance field on every retained document.
    reviewed_on: str = ""

    # -- construction ------------------------------------------------------

    @classmethod
    def from_rules(
        cls,
        namespace: str,
        entries: list[tuple[str, str, str, str]],
        *,
        exclude_sensitive_trees: bool = True,
        max_bytes: int = 400_000,
        reviewed_on: str = "",
        event_times: dict[str, str] | None = None,
    ) -> "Scope":
        """Build a scope from (path, kind, classification, reason) tuples.

        ``event_times`` maps a rule path to an explicit event anchor.
        """
        anchors = event_times or {}
        rules = [
            ScopeRule(
                path=p,
                kind=k,
                classif=c,
                reason=r,
                event_time=anchors.get(p, ""),
            )
            for p, k, c, r in entries
        ]
        return cls(
            namespace=namespace,
            rules=rules,
            exclude_sensitive_trees=exclude_sensitive_trees,
            max_bytes=max_bytes,
            reviewed_on=reviewed_on,
        )

    # -- classification ----------------------------------------------------

    def classification_for(self, rel: PurePosixPath) -> tuple[str, str]:
        """Return (classification, reason) for a path, or ('', '')."""
        best = self.best_rule(rel)
        if best is None:
            return "", ""
        return best.classif, best.reason

    def best_rule(self, rel: PurePosixPath) -> ScopeRule | None:
        """Return the rule that governs a path, or None.

        Most specific rule wins: an explicit file rule beats a directory rule.
        """
        best: ScopeRule | None = None
        for rule in self.rules:
            if not rule.matches(rel):
                continue
            if best is None:
                best = rule
                continue
            best_len = len(best.path)
            if len(rule.path) > best_len or (rule.kind == "file" and best.kind != "file"):
                best = rule
        return best

    # -- evaluation --------------------------------------------------------

    def decide(self, rel: PurePosixPath, size: int | None = None) -> ScopeDecision:
        """Decide whether a wiki-relative path is eligible for ingestion.

        The order matters. A path that is not allowlisted is excluded
        regardless of its name. An allowlisted path is then subject to the
        structural and filename guards, with one exception: a path named
        explicitly by an individual file rule has been reviewed by a human,
        so a filename that merely *looks* like a secret ("verifiable-
        credentials.md") does not veto it. The content scan still applies
        to every file either way.
        """
        name = rel.name
        lower = name.lower()

        rule = self.best_rule(rel)
        explicitly_listed = rule is not None and rule.kind == "file"

        for part in rel.parts[:-1]:
            if part in EXCLUDED_DIR_NAMES or part.startswith("."):
                return ScopeDecision(str(rel), False, f"excluded_dir:{part}")
            if part.lower().endswith(EXCLUDED_DIR_SUFFIXES):
                return ScopeDecision(str(rel), False, f"excluded_dir_suffix:{part}")

        if lower in EXCLUDED_BASENAMES or lower.startswith(".env"):
            return ScopeDecision(str(rel), False, "excluded_basename")
        if (
            not explicitly_listed
            and any(part in lower for part in SECRET_NAME_PARTS)
            and not lower.endswith(EXAMPLE_SUFFIXES)
        ):
            return ScopeDecision(str(rel), False, "secret_filename")
        if rel.suffix.lower() in NON_PROSE_SUFFIXES:
            return ScopeDecision(str(rel), False, "non_prose_suffix")
        if lower.endswith(".md") is False:
            return ScopeDecision(str(rel), False, "not_markdown")

        if self.exclude_sensitive_trees:
            for part in rel.parts[:-1]:
                if part.lower() in SENSITIVE_TREE_PARTS:
                    return ScopeDecision(str(rel), False, f"sensitive_tree:{part}")

        classif, reason = self.classification_for(rel)
        if not classif:
            return ScopeDecision(str(rel), False, "not_allowlisted")

        if size is not None and size > self.max_bytes:
            return ScopeDecision(str(rel), False, f"too_large:{size}")

        return ScopeDecision(str(rel), True, reason or "allowlisted", classif)

    # -- content check -----------------------------------------------------

    @staticmethod
    def find_secrets(text: str) -> list[str]:
        """Return the names of every secret pattern that matches the text."""
        return [name for name, pattern in SECRET_PATTERNS if pattern.search(text)]


def scan_content_for_secrets(text: str) -> list[str]:
    """Module-level alias for :meth:`Scope.find_secrets`."""
    return Scope.find_secrets(text)


def is_example_name(lower: str) -> bool:
    return lower.endswith(EXAMPLE_SUFFIXES)


def relative_wiki_path(root: Path, path: Path) -> str:
    """Return the POSIX-normalized path of *path* relative to *root*.

    Raises ValueError when the path escapes the root, which is the
    path-traversal guard the sync relies on.
    """
    root_resolved = root.resolve(strict=True)
    resolved = path.resolve(strict=False)
    try:
        rel = resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"path escapes root: {path}") from exc
    return str(PurePosixPath(rel))


def symlink_escapes(root: Path, path: Path) -> bool:
    """True when a symlink's target resolves outside *root*.

    The link is never followed into the scan; an escaping symlink is simply
    not eligible.
    """
    if not path.is_symlink():
        return False
    try:
        target = path.resolve(strict=False)
    except OSError:
        return True
    root_resolved = root.resolve(strict=False)
    try:
        target.relative_to(root_resolved)
    except ValueError:
        return True
    return False

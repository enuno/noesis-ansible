"""Minimal Hindsight client for the wiki sync.

Scope: this client implements only what the sync needs, against the
Hindsight Cloud REST API (api_version 1.1.0 as reported by GET /version).

Verified contract, from the deployed server's own OpenAPI document:

  POST /v1/default/banks/{bank_id}/memories
      Body: {items: [...], async: bool, operation_id: str|null}
      Item fields used here: content, context, document_id, metadata, tags,
      timestamp, update_mode.
      Response: {success, bank_id, items_count, async, operation_id, usage}

  GET  /v1/default/banks/{bank_id}/documents
      Query: q, tags, tags_match, limit, offset
      Response: {items: [{id, content_hash, text_length, memory_unit_count,
      tags, document_metadata, created_at, updated_at}], total, ...}

  GET  /v1/default/banks/{bank_id}/operations/{operation_id}
      Response: {operation_id, status: pending|processing|completed|failed|...}

Document update semantics (verified in the deployed OpenAPI description of
POST /memories): "If a memory item has a document_id that already exists, the
old document and its memory units will be deleted before creating new ones
(upsert behavior)." The default update_mode is "replace"; "append" is the
only alternative and is deliberately not used here, because a wiki file is a
whole-document unit, not an incremental log.

Nothing here deletes anything remotely. There is no delete call.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BASE_URL = "https://api.hindsight.vectorize.io"
DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_ATTEMPTS = 3


class HindsightError(RuntimeError):
    """A Hindsight request failed after the retry budget was exhausted."""


class HindsightConfigError(RuntimeError):
    """The client is missing configuration it cannot proceed without."""


@dataclass
class RetainOutcome:
    """What the server reported for one retain call."""

    success: bool
    bank_id: str
    items_count: int
    async_: bool
    operation_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    attempts: int = 1
    elapsed_s: float = 0.0


@dataclass
class DocumentSummary:
    """A document row from the list endpoint."""

    id: str
    content_hash: str | None = None
    text_length: int = 0
    memory_unit_count: int = 0
    tags: list[str] = field(default_factory=list)
    document_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class HindsightClient:
    """A small, explicit Hindsight REST client.

    The API key is read from a caller-supplied provider and is never
    logged, printed, or included in any error message.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        user_agent: str = "noesis-wiki-hindsight-sync/1.0",
        opener=None,
    ) -> None:
        if not api_key:
            raise HindsightConfigError("Hindsight API key is required")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_attempts = max(1, int(max_attempts))
        self._user_agent = user_agent
        # An opener may be injected so tests can drive the transport without
        # a network.
        self._opener = opener or urllib.request.urlopen

    # -- transport ---------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        query: str | None = None,
    ) -> tuple[int, Any]:
        url = f"{self._base_url}{path}"
        if query:
            url = f"{url}?{query}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with self._opener(req, timeout=self._timeout) as resp:
            raw = resp.read()
            if not raw:
                return resp.status, {}
            try:
                return resp.status, json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return resp.status, {"raw": raw.decode("utf-8", "replace")}

    def _request_with_retry(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        query: str | None = None,
    ) -> Any:
        """Retry transient failures with bounded backoff.

        Retries only on 408/429/5xx and on transport errors. A 4xx that is
        not 408/429 is a client error and is raised immediately: retrying a
        rejected request would not change the outcome.
        """
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                status, payload = self._request(method, path, body, query=query)
            except urllib.error.HTTPError as exc:
                status = exc.code
                if status not in (408, 429) and status < 500:
                    raise HindsightError(
                        f"Hindsight {method} {path} failed with HTTP {status}"
                    ) from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
            else:
                if status < 400:
                    return payload
                if status not in (408, 429) and status < 500:
                    raise HindsightError(
                        f"Hindsight {method} {path} failed with HTTP {status}"
                    )
                last_error = HindsightError(f"HTTP {status}")
            if attempt < self._max_attempts:
                time.sleep(min(2.0 ** (attempt - 1), 8.0))
        raise HindsightError(
            f"Hindsight {method} {path} failed after {self._max_attempts} attempts"
        ) from last_error

    # -- operations --------------------------------------------------------

    def get_version(self) -> dict[str, Any]:
        return self._request_with_retry("GET", "/version")

    def list_documents(
        self,
        bank_id: str,
        *,
        q: str | None = None,
        tags: list[str] | None = None,
        tags_match: str = "any_strict",
        limit: int = 200,
        offset: int = 0,
    ) -> list[DocumentSummary]:
        """List documents in a bank.

        ``tags_match='any_strict'`` is the documented default and excludes
        untagged documents, which is what keeps this listing scoped to the
        sync's own namespace.
        """
        params: list[str] = []
        if q:
            params.append(f"q={urllib.parse.quote(q)}")
        if tags:
            joined = ",".join(urllib.parse.quote(t) for t in tags)
            params.append(f"tags={joined}")
            params.append(f"tags_match={urllib.parse.quote(tags_match)}")
        params.append(f"limit={limit}")
        params.append(f"offset={offset}")
        query = "&".join(params)
        payload = self._request_with_retry(
            "GET", f"/v1/default/banks/{bank_id}/documents", query=query
        )
        rows = payload.get("items", []) if isinstance(payload, dict) else []
        out: list[DocumentSummary] = []
        for row in rows:
            out.append(
                DocumentSummary(
                    id=row.get("id", ""),
                    content_hash=row.get("content_hash"),
                    text_length=int(row.get("text_length") or 0),
                    memory_unit_count=int(row.get("memory_unit_count") or 0),
                    tags=list(row.get("tags") or []),
                    document_metadata=dict(row.get("document_metadata") or {}),
                    created_at=row.get("created_at") or "",
                    updated_at=row.get("updated_at") or "",
                )
            )
        return out

    def retain(
        self,
        bank_id: str,
        items: list[dict[str, Any]],
        *,
        use_async: bool = False,
        operation_id: str | None = None,
    ) -> RetainOutcome:
        """Retain items into a bank.

        ``items`` must each carry a ``document_id``; the upsert behavior
        described in the module docstring is what makes re-retaining a
        changed file replace its previous facts instead of duplicating them.
        """
        if not items:
            raise ValueError("retain requires at least one item")
        body: dict[str, Any] = {"items": items, "async": use_async}
        if operation_id is not None:
            if not use_async:
                raise ValueError("operation_id is only meaningful for async retain")
            body["operation_id"] = operation_id

        started = time.monotonic()
        payload = self._request_with_retry(
            "POST", f"/v1/default/banks/{bank_id}/memories", body
        )
        elapsed = time.monotonic() - started
        if not isinstance(payload, dict):
            raise HindsightError("Hindsight retain returned an unexpected payload")
        return RetainOutcome(
            success=bool(payload.get("success")),
            bank_id=payload.get("bank_id", bank_id),
            items_count=int(payload.get("items_count") or 0),
            async_=bool(payload.get("async", use_async)),
            operation_id=payload.get("operation_id"),
            usage=dict(payload.get("usage") or {}),
            elapsed_s=elapsed,
        )

    def wait_for_operation(
        self,
        bank_id: str,
        operation_id: str,
        *,
        poll_interval_s: float = 3.0,
        timeout_s: float = 900.0,
    ) -> dict[str, Any]:
        """Poll an async operation until it reaches a terminal state.

        Returns the final operation record. Raises on timeout or on a
        terminal 'failed' status.
        """
        deadline = time.monotonic() + timeout_s
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = self._request_with_retry(
                "GET", f"/v1/default/banks/{bank_id}/operations/{operation_id}"
            )
            status = (last or {}).get("status")
            if status == "completed":
                return last
            if status in ("failed", "cancelled", "not_found"):
                raise HindsightError(
                    f"Hindsight operation {operation_id} ended with status {status}"
                )
            time.sleep(poll_interval_s)
        raise HindsightError(
            f"Hindsight operation {operation_id} did not complete within {timeout_s}s"
        )

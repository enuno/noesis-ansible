# Wiki → Hindsight sync — runbook

One-way sync from the llm-wiki (`~/wiki`) into a Hindsight memory bank.
The wiki stays canonical and editable; Hindsight holds a reviewed subset
with provenance.

Nothing in this pipeline writes to the wiki, and nothing deletes anything
remotely.

## What this is

| | |
|---|---|
| Direction | `~/wiki` → Hindsight. One way. Never the reverse. |
| Source of truth | The wiki. A Hindsight record is a copy, not the original. |
| Target | Hindsight Cloud, bank `hermes`, endpoint `https://api.hindsight.vectorize.io` |
| Namespace | `noesis-wiki` — every document id starts with this |
| Tags | `source:noesis-wiki-sync` (all), `source:noesis-wiki-sync-doc` (per document) |
| Code | `roles/wiki_hindsight_sync/files/wiki_hindsight_sync/` |
| Scope | `roles/wiki_hindsight_sync/files/wiki_hindsight_sync/scope.json` |
| State | `~/.local/share/noesis/wiki-hindsight-sync/manifest.json` |
| Tests | `tests/wiki_hindsight_sync/` (43 offline tests) |

## Prerequisites

1. `HINDSIGHT_API_KEY` in the environment. The key is read from the
   environment at run time and is never written to disk, a log, the
   manifest, or a report.
2. A wiki root that exists and is readable. The default is `/home/elvis/wiki`.
3. Python 3 with no third-party packages. The collector uses only the
   standard library.
4. A reviewed `scope.json`. The scope file is the unit of review: it lists
   the exact wiki-relative paths that may be ingested.

## Dry run first

Dry-run is the default and contacts no Hindsight endpoint that changes
anything. It writes no manifest.

```bash
cd ~/projects/noesis-ansible/roles/wiki_hindsight_sync/files

HINDSIGHT_API_KEY="$HINDSIGHT_API_KEY" /usr/bin/python3 -m wiki_hindsight_sync \
  --wiki-root /home/elvis/wiki --bank hermes \
  --state-dir ~/.local/share/noesis/wiki-hindsight-sync \
  --scope-file ./wiki_hindsight_sync/scope.json --json
```

Read the output before applying. The counts section shows how many
documents would be created, updated, skipped, or held for review.

## Apply

Requires an explicit `--apply`. Without it the run is a dry run.

```bash
HINDSIGHT_API_KEY="$HINDSIGHT_API_KEY" /usr/bin/python3 -m wiki_hindsight_sync \
  --apply --wiki-root /home/elvis/wiki --bank hermes \
  --state-dir ~/.local/share/noesis/wiki-hindsight-sync \
  --scope-file ./wiki_hindsight_sync/scope.json
```

`--max-documents N` bounds one run. `--max-runtime-s N` bounds the wall
clock; the run stops starting new documents once the budget is spent.

## How updates work

Document identity is `noesis-wiki/<percent-encoded wiki-relative path>`.
It does not depend on content, so a changed file keeps its identity.

Re-retaining an existing `document_id` uses the upstream `replace`
semantics: the old document and its memory units are deleted, then the
new content is processed. That is what prevents duplicate copies of the
same page accumulating.

The manifest is the skip mechanism. A file whose SHA-256 matches the
manifest is not re-ingested. The manifest is advanced only after the
server confirms each ingestion, so an interrupted run resumes rather than
repeats.

## Validation after a run

1. **Document presence.** The sync's documents are identifiable by tag:

   ```bash
   curl -sS -H "Authorization: Bearer $HINDSIGHT_API_KEY" \
     "https://api.hindsight.vectorize.io/v1/default/banks/hermes/documents?tags=source:noesis-wiki-sync-doc&tags_match=any_strict&limit=200" \
     | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['total'])"
   ```

2. **Provenance.** Recall a known fact and confirm `metadata.source_path`
   points at the expected wiki file:

   ```bash
   curl -sS -H "Authorization: Bearer $HINDSIGHT_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"query":"Noesis fleet supervisor worker split","tags":["source:noesis-wiki-sync"]}' \
     "https://api.hindsight.vectorize.io/v1/default/banks/hermes/memories/recall"
   ```

3. **No-op rerun.** Run the apply a second time. It must report zero
   ingests. A non-zero count means the skip logic is broken.

4. **Source evidence.** Open the wiki file named in `metadata.source_path`
   and confirm the recalled statement matches it. A recalled fact that
   contradicts its source is an extraction problem, not a sync problem.

## Failure handling

| Symptom | Cause | Action |
|---|---|---|
| `manifest at ... was written for a different scope` | Manifest belongs to another endpoint/bank/namespace/root | Use a different `--state-dir`, or move the manifest aside deliberately. Do not edit it in place. |
| `another sync run holds ...` | A run is already in progress | Wait. The lock is released when the first run exits. |
| `Hindsight POST ... failed after 3 attempts` | Server or network failure | Re-run. Failed documents were not written to the manifest, so they are retried. |
| `ingest failed` in the errors list | One document failed; the rest continued | Fix the cause, re-run. Only the failed document is retried. |
| `runtime budget exhausted` | `--max-runtime-s` reached | Re-run to continue. Progress was already saved. |
| `empty document` / `secret-shaped content` in review items | The file was held out | Review it. Either fix the file, or narrow the scope. It is not ingested silently. |
| Exit code 1 with errors | At least one document failed | Not a success. Re-run after addressing the cause. |

The exit code is 1 when any error occurred, 0 otherwise, so a scheduler
notices. A run with only review items and no errors exits 0 — review items
are expected output, not failures.

## Recovery limitations

**What the sync cannot undo.**

- *No remote deletion.* The tool never calls a delete endpoint. A wiki file
  that is deleted or renamed leaves its Hindsight document in place,
  reported as a review item. Pruning is manual and reviewed.
- *A rename is a new document.* The old document survives. The pair is
  reported as review items so a human can decide whether to prune the old
  one.
- *An update replaces, it does not merge.* The prior facts for that
  document are deleted upstream. The previous content hash is recorded in
  `metadata.supersedes` on the replacement, which is the only durable
  pointer to what it was.
- *A failed update can lose the old document.* Upstream `replace` deletes
  before creating. If the new retain then fails, the document is gone
  upstream but the manifest still lists the old hash, so the next run
  retries it. This is upstream behavior, not a sync choice.
- *Observations re-consolidate.* Replacing a document invalidates the
  observations derived from it and they are rebuilt from the new content.

**Manual recovery.**

- Re-ingest one document: delete its entry from `manifest.json` and
  re-run. The file's hash no longer matches, so it is re-created.
- Force a full re-ingest: move `manifest.json` aside. Every in-scope
  document is then treated as new and re-created in place (same identity,
  so no duplicates).
- Reset to a clean state: stop the schedule, delete the manifest, and
  re-run with `--apply`. The upstream documents are replaced in place.

## Reviewed pruning

Pruning is deliberately not automated. When the scope changes and some
documents should no longer exist in Hindsight:

1. Review the scope diff. The removed paths are the pruning list.
2. For each removed path, find its document id:
   `noesis-wiki/<percent-encoded path>`.
3. Confirm the document belongs to this sync before removing it:
   `GET /v1/default/banks/{bank}/documents/{document_id}` and check the
   `tags` contain `source:noesis-wiki-sync-doc`.
4. Delete it explicitly, one at a time, reviewing the response.
5. Remove its manifest entry so the sync does not re-create it.

Never bulk-delete by tag prefix without checking each document. A document
that was written by something else will not carry the tag, but a
mis-scoped filter is still a destructive act.

## Scope and exclusions

`scope.json` lists every eligible path with a classification and a reason.
Paths not listed are not ingested, whatever their content looks like.

Two independent guards apply on top of the allowlist:

1. **Filename and structure guards.** Non-markdown suffixes, secret-shaped
   filenames, machine-state directories, and sensitive trees (`legal`,
   `personal-journal`, `contracts`, `wallet`, …) are excluded.
2. **Content secret scan.** Sixteen credential patterns are matched against
   the file body. A file with a secret-shaped match is held as a review
   item, never ingested. Filenames alone are not sufficient detection.

An explicitly named file rule overrides the filename heuristic only —
the content scan still applies. This is why
`identity/verifiable-credentials.md` is listed by name: its filename looks
like a credential but its content is a concept page.

### Deliberately excluded

| Path | Why |
|---|---|
| `raw/` | 1,657 files / 396 MB. Raw imports, web captures, and the `raw/legal/` archive (200 MB, cell-phone forensics). |
| `sources/` | Immutable source snapshots per wiki `AGENTS.md`. |
| `personal-journal/` | Private journal; the Notion exports have no frontmatter. |
| `ywca-missoula/`, `missoula-eviction/`, `legal-representation/`, `contracts/`, `misjustice-alliance-firm/` | Legal, civic, and contractual material. |
| `bankr/`, `clawbank/`, `catalog/`, `tools/`, `copilot/`, `dc-compare/`, `buildordie/`, `ryno-crypto-research/`, `terrahash-stack/`, `ai-research/` | Third-party API references and unrelated vendor research. |
| `agentmail/` | Contains `agentmail/raw/agentmail_api_key_hermes-agent.txt`, a live-format API key committed to the wiki. Rotate it separately. |
| `logs/`, `queries/`, `reports/`, `telemetry/AFFECT_LOG` history, `evals/` | Generated output and session scratch. |
| `index.md`, `log.md`, `_ingestion-log.md`, `tags/` | Generated catalogs. |

## Provenance

Every retained document carries the metadata schema fixed by the
`noesis-memory-routing` skill, so these records are legible to the rest of
the memory architecture:

`record_id`, `agent_id`, `scope`, `source_reference`, `recorded_time`,
`verification_status`, `sensitivity`, `sharing_status`, `supersedes`,
`review_time`, plus `source_path`, `source_sha256`,
`source_classification`, and the document's own frontmatter and git
revision fields.

`verification_status` uses the repo vocabulary `verified | derived |
inference | open`. **The sync never writes `verified`.** It ingests a
document; it does not independently confirm what the document claims. A
page with `confidence: high` becomes `derived`; a page with
`confidence: low`, or one that declares itself draft, becomes `open`.

`timestamp` is `unset` for reference material. The wiki's `updated:` field
is a *revision* date, not the date an event occurred, so it is recorded as
`doc_updated` and never used as an event anchor. Only three scope rules
declare an explicit `event_time`, and each names a dated session record
rather than a page with an edit date.

## Relationship to the mental model

A Hindsight mental model named `wiki` already exists in the `hermes` bank
and refreshes hourly. It summarizes what is in the bank; it does not
control what gets ingested. Those are separate operations:

- **File ingestion** — this sync. Wiki → Hindsight documents.
- **Mental-model refresh** — the server's own consolidation pass over
  whatever is in the bank.

A source query is not a sync configuration. Do not point a mental model
at the wiki expecting it to pull documents in.

## Scheduled execution

The Ansible role `wiki_hindsight_sync` installs the collector and, only
when `wiki_hindsight_sync_activate=true`, a crontab line. The role is
**not** referenced by `master-stack.yml` and its activation default is
`false`. Nothing is scheduled until separately approved.

```bash
ansible-playbook --syntax-check -i inventory/local/hosts.ini \
  playbooks/wiki-hindsight-sync.yml

ansible-playbook -i inventory/local/hosts.ini \
  playbooks/wiki-hindsight-sync.yml -e wiki_hindsight_sync_activate=true
```

The cron entry runs at 03:25 `America/Denver`. `03:25` exists on both
2026 US DST transition days, so unlike `02:25` it is never skipped.

If the scheduled run needs the API key, provide it through the
environment of the crontab. The role does not create, modify, or read any
credential store.

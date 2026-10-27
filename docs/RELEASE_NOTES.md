# Wayback Atlas release notes

## 3.2.0 — resumable discovery and Common Crawl

October 26, 2026 (America/New_York). Still beta; provider availability and completeness
are not guaranteed.

- Every main-CLI discovery creates a versioned run with immutable query options.
- Per-provider cursors, downloaded page buffers and consumption offsets survive restarts.
  Evidence and checkpoint advancement commit atomically. Previously completed sources
  are skipped; failed pages are retried from saved progress.
- Added `runs`, `runs --json`, `resume RUN_ID`, and menu **12**. Resume accepts additional
  record/page budgets and `--strict`; fresh discovery remains an intentional refresh.
- Repeated-cursor detection survives process restarts. Optimistic revision checks prevent
  a stale worker from overwriting progress; avoid overlapping workers nonetheless.
- Common Crawl CDX JSONL joins default discovery and menu 3. `--cc-latest` (default 1)
  or repeated `--cc-index` selects collections, pinned before pages are read. Source
  evidence retains each crawl ID. This is index discovery, not active target crawling.
- `--page-size` fixes the Wayback request size for a run. Record limits no longer
  discard the unprocessed tail of a downloaded provider page.
- Tests cover mid-page restarts, transactional rollback, interrupted commits, stale
  writers, repeated cursors, multi-index Common Crawl pagination, malformed JSONL and
  query validation. The frozen-EXE smoke now exercises offline staged-page resume.

Compatibility: existing inventories gain three additive checkpoint tables without
rewriting assets/check history. Checkpoint format is version 1; unknown formats are
refused. Pre-3.2 runs cannot be retroactively resumed; start a new discovery. SQLite
backup includes checkpoint buffers. JSON exports/imports are not checkpoint backups.

Budget semantics: `--limit` and `--max-pages` are now per-source/per-invocation processing
budgets, not lifetime caps. Record counts include processed duplicates. Catalog/count
steps consume page budget. Reports still use schema 1; `provider_runs` audit entries
now include page/batch commits with run IDs. Opaque cursors may contain private URLs;
protect databases and backups. No API keys are checkpointed.

Limits: provider snapshots can change; opaque cursors can expire; interrupted HTTP
downloads restart their page. Invalid schemas stop the page without advancing it.
Wayback still collapses URL keys, and Common Crawl covers only the selected indexes.
Host-first budgets, full timelines, report streaming, automated retention and stronger
availability analysis remain follow-ups. Retained `wayback-recon` is not resumable.

See [resumable discovery](RESUMABLE_DISCOVERY.md) for the design and exact recovery contract.

## 3.1.0 — historical reliability release

Reliability release — October 26, 2026 (America/New_York). Still beta; this is not
a claim of exhaustive discovery, zero defects or continuous provider availability.

## Fixed

- RapidDNS no longer discards distinct A/AAAA/type/value evidence at the same host/time.
- Provider JSON is streamed with a 16 MiB decompressed-body ceiling; chunked responses
  are bounded too. Responses close on success and failure. Slow transfers have a
  deadline checked between chunks, in addition to socket timeouts.
- Malformed certificate records and invalid RapidDNS counts return explicit source
  errors with partial evidence retained instead of uncaught type errors.
- Invalid calendar dates, nonfinite watch intervals and empty/closed interactive input
  are handled explicitly. A blank menu entry retries; EOF shuts down cleanly.
- Unexpected per-host failures no longer cancel unrelated hosts. Database-write failures
  still propagate rather than being disguised as successful observations.

## Added

- `--version` and offline `doctor`; credentials are shown only as present/missing.
- Menu 11 for diagnostics and backups; existing menu numbers remain unchanged.
- `backup NEW_FILE.sqlite3` uses SQLite's backup API and checks integrity without
  overwriting an existing file. It preserves all database history, not just exports.
- `CERTSPOTTER_API_KEY` for optional Bearer authentication. Provider limits still apply.
- JSONL/NDJSON imports, `host` field support and preserved imported provenance/DNS fields.
- `discover --strict` exits 1 on provider errors or truncation after saving reports.
- `--host-timeout` (default 45 seconds), per-round IDs, finish times and durations.
- Accepted/rejected/duplicate/omitted record counts and unique-host counts in source metadata.
- An offline packaged-EXE smoke script and Windows EXE CI job.

## Compatibility and remaining work

Existing 3.0 SQLite inventories remain readable; no destructive database migration
is performed. Existing public commands and launcher names remain available.
The report schema stays at version 1 with additive sample and metadata fields.
Import deduplication now preserves distinct evidence, so record counts can increase
without increasing unique-host counts.

At the time of 3.1, pagination checkpoints across restarts, unique-host-first collection budgets,
multi-resolver measurements, Common Crawl integration, full capture timelines,
schema migration management and notifications remain roadmap work. Monitoring is
foreground-only; no tasks or services are automatically installed.

Paid-key integrations are regression-tested with fixtures, not live-account tested.
See [operations](OPERATIONS.md), [development](DEVELOPMENT.md) and the
[remaining roadmap](ASSESSMENT_AND_ROADMAP.md).

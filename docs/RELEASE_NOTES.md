# Wayback Atlas 3.1.0

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

Pagination checkpoints across restarts, unique-host-first collection budgets,
multi-resolver measurements, Common Crawl integration, full capture timelines,
schema migration management and notifications remain roadmap work. Monitoring is
foreground-only; no tasks or services are automatically installed.

Paid-key integrations are regression-tested with fixtures, not live-account tested.
See [operations](OPERATIONS.md), [development](DEVELOPMENT.md) and the
[remaining roadmap](ASSESSMENT_AND_ROADMAP.md).

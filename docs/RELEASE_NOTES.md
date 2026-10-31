# Wayback-Recon release notes

## 4.0.1 — workflow reliability

- Main menu labels explain each action and distinguish discovery, checking and saved data.
- Menu discovery and imports now export reports automatically, matching CLI behavior.
- Every completed check/watch round exports a snapshot and prints its HTML/folder paths.
  Watch accepts `--final-report-only` for disk-conscious long runs.
- `check --only-unchecked` (also menu 4) selects hosts with no saved check of any kind.
  Completed/total progress counts make large checks easier to follow.
- Failed writes/flushes clean up their temporary file without replacing existing results.
- Async host/control timeout handling also recognizes Python 3.10's distinct timeout class.

Remaining larger opportunities: streaming exports for very large inventories, per-request
rate limits, configurable snapshot retention, and dedicated persistent monitoring-job
checkpoints. These are not implemented by this release; unchecked selection is not a
full monitoring checkpoint system.

## 4.0.0 — Wayback-Recon and validated webpage results

October 31, 2026 (America/New_York).

- Renamed package, main command, launcher, executable, CI artifacts and GitHub URLs.
  Main command: `wayback-recon`; legacy parameter collector: `wayback-parameters`.
- Central classification separates HTTP reachability from webpage accessibility.
  `alive.txt` now aliases confirmed webpages, not every responding HTTP/TLS endpoint.
- Bounded HTML inspection, title/error signals, fingerprints, per-scheme evidence,
  internal redirect chains/loops, external redirect labels and HTTP wildcard controls.
- JSON schema 2, categorized lists, HTML/CSV classification fields and CLI filters.
- Existing SQLite checks are reclassified on export without changing raw history.
  Old 200s without content remain candidates until checked again.

## 3.3.0 — offline HTML and public-tree cleanup

October 27, 2026 (America/New_York).

- Each report bundle now includes `report.html`, with summary counts, every host,
  expandable evidence previews, source errors and companion export links. HTML is
  script-free, escapes untrusted text and uses no external resources or target fetches.
  JSON remains the complete exported evidence source; HTML previews 20 evidence
  records and 5 samples per host. JSON is still written last as the completion marker.
- Build outputs move to ignored `dist/`; the launcher and CI use that location.
  Distribute executable/wheel/checksums as release attachments rather than Git source.
- Consolidated overlapping quick-start/install/index/structure/assessment guides into
  the README and focused maintenance docs. Removed duplicate requirements metadata;
  `pyproject.toml` is the dependency authority.
- Added `scripts/check_repo.py` for current-tree artifact/link checks and limited
  credential-signature detection. It does not scan history or ignored research data.

## 3.2.1 — grouped report folders

October 27, 2026 (America/New_York).

- Every inventory export now has its own `reports/DOMAIN/UTC_TIMESTAMP_UNIQUE_ID/`
  directory containing JSON, CSV and hostname lists, instead of loose root-level files.
- Automatic discovery/resume/import/check/watch exports use the same layout as menu 10.
- Filenames inside each bundle are `report.json`, `inventory.csv`, `hosts.txt`,
  `alive.txt`, `down_observed.txt` and `intermittent.txt`. The main JSON is written last
  as a completion marker; interrupted bundles remain distinguishable.
- Windows-reserved and long target names use safe folder names. Separate snapshots
  never overwrite one another. The returned/printed path points to the new JSON report.
- The shared SQLite database, resume checkpoints and existing loose exports are not
  moved or deleted. Scripts consuming old flat filename patterns must use the new layout.

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
[remaining development priorities](../README.md#improvements-to-prioritize-next).

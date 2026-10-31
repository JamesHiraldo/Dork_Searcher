# Operations, data and troubleshooting

Applies to Wayback-Recon 4.0.1. Commands below run in CMD from the repository
root. In PowerShell prefix the launcher with `.\`. Use only authorized targets.

## Keep a consistent workspace

```cmd
wayback_recon.bat --output-dir "D:\Recon\Example" discover example.com --sources wayback crtsh certspotter
wayback_recon.bat --output-dir "D:\Recon\Example" inventory example.com
wayback_recon.bat --output-dir "D:\Recon\Example" check example.com --concurrency 4 --timeout 5
wayback_recon.bat --output-dir "D:\Recon\Example" watch example.com --dns-only --rounds 12 --interval 300
wayback_recon.bat --output-dir "D:\Recon\Example" export example.com
```

Resolution order: `--output-dir`, `WAYBACK_RECON_OUTPUT_DIR`, then `WAYBACK_ATLAS_OUTPUT_DIR`, then the legacy
`DORK_SEARCHER_OUTPUT_DIR`. With none set, try the actual Desktop location plus
`Wayback_Recon_Results`, then `%LOCALAPPDATA%\WaybackRecon\Results` when available,
then `~/Wayback_Recon_Results`. Existing Desktop `Wayback_Atlas_Results` with an
inventory database is reused first. An explicit unwritable path fails without fallback.
The dashboard/report message shows the path actually used. Changing it opens a
different inventory; it does not move or merge the previous database.

Relative paths passed through the Windows batch launcher resolve from the project
folder because the launcher changes directory there. Prefer absolute paths in jobs.

## Resume discovery and select crawl indexes

Discovery creates a run ID and saves each page before processing. `runs` lists the
latest 50 IDs; `resume RUN_ID` continues a saved query. Menu 12 provides the same
workflow. Use the same output folder; budgets are additional per source for this
invocation, and completed sources are skipped. A fresh `discover` starts a new query
without deleting inventory data. API keys are read again from the environment.

Default sources now include Common Crawl's latest one published index. Use
`--sources commoncrawl --cc-latest 3` or repeated `--cc-index CC-MAIN-YYYY-NN`
options for more collections. Selection is pinned in the checkpoint; date filters
do not automatically select older collections. No live page crawling is performed.
See [resumable discovery](RESUMABLE_DISCOVERY.md) for exact budgets, query stability,
crash recovery, concurrency, schema versioning and Common Crawl behavior.

## What gets checked

Discovery queries third-party services; it does not fetch discovered target pages.
`check`/`watch` resolve A and AAAA and make two random-name DNS controls under the
root per round. HTTP mode then tries up to two public addresses per host, preferring
both families, with HTTPS then HTTP as needed. Connections use the resolved address
with the target Host/SNI. They request `/`, inspect up to 64 KiB, and follow bounded
internal redirects after public-address validation at each hop. Two random-name HTTP
controls detect generic wildcard pages. This is not port scanning or a site crawl.
See [classification](WEBPAGE_CLASSIFICATION.md) for exact limits, outputs and migration.

Private-only answers are stored but not HTTP-probed. `--dns-only` never sends HTTP.
HTTP sampling ignores proxy environment settings; provider requests use Requests'
normal environment behavior. There is no CLI proxy or custom-resolver option.

Timeouts apply per operation, so a host/round can take substantially longer than
`--timeout`. Concurrency limits workers, not requests per second. Use conservative
settings that fit the program's limits. `watch` waits after each completed round,
and never refreshes its startup host list. It is not a background service.
`--host-timeout` defaults to 45 seconds (maximum 600) for each host's overall
DNS/HTTP work. It excludes time waiting in the queue and the round's wildcard
controls. Unexpected host errors/deadlines become `unknown`, preserving the batch.
Samples include a shared round ID, finish time and duration; old samples remain readable.

## Import formats and limits

```cmd
wayback_recon.bat --output-dir "D:\Recon\Example" import example.com "D:\Recon\hosts.txt"
```

Files must be UTF-8 (BOM accepted), at most 25 MiB. At most 50,000 distinct
evidence records are retained per import. The current CLI does not expose an
import-limit flag. Duplicates are collapsed; unrelated and malformed rows are skipped.

TXT: one hostname or absolute HTTP(S) URL per line. Leading-whitespace comments are accepted:

```text
# Synthetic format example
api.example.com
https://old.example.com/api?version=1
```

CSV: a header row, for example:

```csv
hostname,url
api.example.com,https://api.example.com/api
old.example.com,
```

JSON: a list of strings/objects, or a wrapper with `assets`, `records`, `data`, or
RapidDNS-style `data.data`. Object hostname lookup uses the first nonempty field
in this order: `hostname`, `host`, `subdomain`, `domain`, `url`, `title`. An accompanying
URL must refer to the same host and must not contain credentials. `observed_at`
or `timestamp` is retained when supplied. `source`, `sources`, `type`, `record_type`
and `value` are retained under `imported_*` evidence fields when strings or lists.
Import does not retain arbitrary fields or promote imported provenance to live provider proof.

```json
[
  "old.example.com",
  {"hostname": "api.example.com", "url": "https://api.example.com/api", "observed_at": "2020-01-01"}
]
```

JSON Lines/NDJSON (`.jsonl`/`.ndjson`) accepts one JSON record per nonempty line,
including Subfinder's `host`/`source` records. Parse errors identify the line without
echoing its contents. An entire `wayback-parameters` JSON report is not supported
directly; use its CSV export instead. An Wayback-Recon JSON
report can seed its host list, but nested evidence, checks, original local discovery
times and provider provenance are not restored: the new source is `import`.
Import is not a database-backup restore.

## Reading reports

`inventory.sqlite3` stores assets, source evidence, provider runs and all completed
availability samples, plus discovery jobs/cursors and pending page buffers.
Exports have `schema_version: 1`. Inspect these sections:

- `assets`: local first/last seen, sources, evidence, latest sample and trends.
- `samples`: latest 100 stored checks per host; full history remains in SQLite.
- `archive_summary`: distinct stored URLs, endpoints and parameter names.
- `provider_runs`: latest 100 audit entries, including source errors and page/batch commits.
- `provider_runs[].payload.metadata`: CompleteDNS events and other provider context.

Wayback-Recon timestamps are UTC; provider timestamps keep their provider-specific format.
crt.sh evidence uses log entry time; Cert Spotter evidence uses certificate
`not_before`, not DNS creation time. Imported URLs can contribute to URL summary
counts; those counts alone do not prove Wayback provenance. Check each evidence source.

Wayback uses `collapse=urlkey`: a representative capture is kept per URL key within
the query. `first_archived_sample`/`last_archived_sample` are extrema of retained
Wayback/Common Crawl samples, not complete first/last captures. Common Crawl evidence
includes `crawl_index`; `runs --json` includes pinned index IDs and query options.
Date-range jobs improve coverage but do
not turn this into an exhaustive lifetime history.

Only `confirmed_webpage` goes into the alive list. HTTP errors, TLS failures,
unvalidated 200 responses and generic wildcard pages are excluded. Down-observed includes NXDOMAIN, no address,
and unreachable. Unknown, unchecked and private-only hosts are not classified as
dead. The availability percentage includes conclusive HTTP-mode observations,
including DNS negatives; DNS-only runs do not contribute. It is not time-weighted.
Two observed HTTP or DNS transitions flag an intermittent candidate. Inspect sample
times and possible local network failures before interpreting that flag.

`discover`, `resume`, `import`, `check`, `watch` and `export` write timestamped reports.
Each export creates `reports/DOMAIN/UTC_TIMESTAMP_UNIQUE_ID/` with `report.json`,
`report.html`, `inventory.csv`, `hosts.txt`, `alive.txt`, `down_observed.txt` and `intermittent.txt`.
Open `report.html` in a browser for the offline summary. All hosts appear; expandable
previews show 20 evidence records and 5 recent samples each. Use JSON for all exported
evidence. No scripts or external resources are loaded; research text is escaped.
The database remains at the output root; existing exports are not automatically moved.
Long or Windows-reserved target names use filesystem-safe folder names. The CLI prints
the actual report path. The JSON report is written last; a snapshot folder without
`report.json` is incomplete and can be regenerated with `export DOMAIN`.
`inventory` displays a maximum of 200 rows. `dorks` replaces `archive_matches.json`.
Ctrl+C retains completed samples but can interrupt the final report export; run
`export` afterwards. Source failure never automatically deletes prior discoveries.

## Backup, restore and privacy

1. Stop every Wayback-Recon process using the output directory, including watch jobs.
2. Copy the entire output directory to a protected backup location. Preserve SQLite
   `-wal`/`-shm` sidecars if present; never discard them to resolve a lock problem.
3. Keep the original untouched. To test a restore, use the copied directory with
   `--output-dir` and run `inventory DOMAIN`; compare expected hosts and samples.
4. Resume only the intended working copy. A later `discover`/`check` will modify it.

For a consistent database-only copy, including while a watcher runs, use:

```cmd
wayback_recon.bat --output-dir "D:\Recon\Example" backup "D:\Recon\Example-backup.sqlite3"
```

This uses SQLite's backup API, checks integrity and refuses to overwrite an existing
path. It has a 30-second progress deadline; retry during a quiet period if busy.
Custom dork templates and exported reports are not part of this database-only copy.
Discovery checkpoints and pending buffers are included, so the restored copy can resume.
To restore, stop the application and place a copy of the backup in a new empty
output directory named `inventory.sqlite3`, then run `inventory` with that directory.
There is no automatic restore, prune or schema-migration command. Never use a raw
copy of just the live main database file as an online backup.
Keep databases on local storage; back up closed files to sync/network storage.

Query-name-based redaction is a heuristic, not a secret detector. Names, paths,
unrecognized parameter values and imported/provider metadata may remain sensitive.
Opaque pagination cursors may also contain unredacted URL information; keep SQLite
files/backups private even when exported URLs have redacted parameters.
Review reports before sharing. Default Git ignore rules do not cover every custom
output path. Run `git status --short` before committing. Do not publish API keys.

## Exit codes and unattended use

| Code | Wayback-Recon meaning |
| --- | --- |
| 0 | Command completed; can include empty results, failed hosts or partial provider coverage |
| 1 | All selected discovery sources failed; or any incomplete/failed with discover/resume `--strict`; or `doctor` found a local error |
| 2 | CLI parsing, input, output-path or handled database/OS error |
| 130 | User interrupted the CLI |

Inspect `provider_runs`, truncation and per-host states rather than treating exit
0 as complete discovery or universal availability. `discover --strict` fails on
any source error or truncation, but cannot establish index completeness. An import
with zero retained rows can still return 0. `runs --json` offers machine-readable
checkpoint summaries; other data commands use saved JSON reports.
Use absolute output paths, prevent overlapping jobs, and preserve logs if you
configure an external scheduler yourself. Wayback-Recon installs no scheduled tasks.

## Troubleshooting

| Symptom | Check / action |
| --- | --- |
| `wayback-recon` not recognized | Use the bundled launcher or install/activate the Python environment. |
| Running source changes shows the old behavior | The batch file prefers the EXE; use `python -m src.cli` or rebuild. |
| Access denied writing results | Choose a writable absolute `--output-dir`; close files held by other apps. Elevation is not normally needed. |
| Inventory is empty | Confirm the exact root and output directory. Discovery/import must run before check/watch. |
| Provider HTTP 403/429 or challenge page | Review provider account/quota and wait. Use another documented source or import; do not loop rapidly. |
| Missing RapidDNS/CompleteDNS key | Set the corresponding environment variable in the same shell; select that source explicitly. |
| Cert Spotter misses older names | Its endpoint covers unexpired issuances even with `CERTSPOTTER_API_KEY`; combine sources. |
| Discovery says paused / resumable | Use menu 12 or `runs` then `resume RUN_ID` in the same output directory. |
| Cursor expired / repeated | Progress is intact; retry later or intentionally start a fresh `discover`. No silent reset occurs. |
| Run changed in another process | Stop duplicate workers, then resume once. Stale revisions cannot overwrite progress. |
| Common Crawl gives no older captures | Select historical crawl IDs; date filters alone do not select old indexes. |
| Many hosts switch down together | Check local connectivity/resolver and compare another permitted vantage point. This is not proof of target outages. |
| Database locked | Stop duplicate writers and wait for normal shutdown. Do not delete SQLite sidecars. |
| SSL or corporate proxy trouble | Check system time/trust policy and distinguish provider access from direct HTTP probes. Do not disable TLS verification. |
| A copied `.venv` cannot start | Create `.venv-recon` using an installed Python; copied environments retain interpreter paths. |
| Provider response exceeds 16 MiB | Use a narrower archive query, a different documented source or a split export import. |
| Old pytest folders deny access | Use the verification script's separate cache paths. Those caches are not needed by the EXE. |

For reproducible issues provide version, source versus EXE, command with keys and
private targets removed, exit code, relevant provider status, and OS/Python details.
Do not post a whole research database. See [development](DEVELOPMENT.md) and
[security reporting](../SECURITY.md).
`doctor` checks local TLS context creation, DNS backend/configuration, dependencies,
database integrity and optional key presence. It does not test network reachability
or validate provider credentials. `--version` identifies the running source/EXE version.

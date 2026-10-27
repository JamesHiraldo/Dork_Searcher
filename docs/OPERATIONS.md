# Operations, data and troubleshooting

Applies to Wayback Atlas 3.0.0. Commands below run in CMD from the repository
root. In PowerShell prefix the launcher with `.\`. Use only authorized targets.

## Keep a consistent workspace

```cmd
wayback_atlas.bat --output-dir "D:\Recon\Example" discover example.com --sources wayback crtsh certspotter
wayback_atlas.bat --output-dir "D:\Recon\Example" inventory example.com
wayback_atlas.bat --output-dir "D:\Recon\Example" check example.com --concurrency 4 --timeout 5
wayback_atlas.bat --output-dir "D:\Recon\Example" watch example.com --dns-only --rounds 12 --interval 300
wayback_atlas.bat --output-dir "D:\Recon\Example" export example.com
```

Resolution order: `--output-dir`, then `WAYBACK_ATLAS_OUTPUT_DIR`, then the legacy
`DORK_SEARCHER_OUTPUT_DIR`. With none set, try the actual Desktop location plus
`Wayback_Atlas_Results`, then `%LOCALAPPDATA%\WaybackAtlas\Results` when available,
then `~/Wayback_Atlas_Results`. An explicit unwritable path fails without fallback.
The dashboard/report message shows the path actually used. Changing it opens a
different inventory; it does not move or merge the previous database.

Relative paths passed through the Windows batch launcher resolve from the project
folder because the launcher changes directory there. Prefer absolute paths in jobs.

## What gets checked

Discovery queries third-party services; it does not fetch discovered target pages.
`check`/`watch` resolve A and AAAA and make two random-name DNS controls under the
root per round. HTTP mode then tries up to two public addresses per host, preferring
both families, with HTTPS then HTTP as needed. Connections use the resolved address
with the target Host/SNI. They request `/`, do not follow redirects, and close the
response stream without collecting the body. This is not port scanning or a crawl.

Private-only answers are stored but not HTTP-probed. `--dns-only` never sends HTTP.
HTTP sampling ignores proxy environment settings; provider requests use Requests'
normal environment behavior. There is no CLI proxy or custom-resolver option.

Timeouts apply per operation, so a host/round can take substantially longer than
`--timeout`. Concurrency limits workers, not requests per second. Use conservative
settings that fit the program's limits. `watch` waits after each completed round,
and never refreshes its startup host list. It is not a background service.

## Import formats and limits

```cmd
wayback_atlas.bat --output-dir "D:\Recon\Example" import example.com "D:\Recon\hosts.txt"
```

Files must be UTF-8 (BOM accepted), at most 25 MiB. At most 50,000 distinct
hostname/URL records are retained per import. The current CLI does not expose an
import-limit flag. Duplicates are collapsed; unrelated and malformed rows are skipped.

TXT: one hostname or absolute HTTP(S) URL per line. Put comment markers in column 1:

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
in this order: `hostname`, `subdomain`, `domain`, `url`, `title`. An accompanying
URL must refer to the same host and must not contain credentials. `observed_at`
or `timestamp` is retained when supplied. Import does not retain arbitrary fields.

```json
[
  "old.example.com",
  {"hostname": "api.example.com", "url": "https://api.example.com/api", "observed_at": "2020-01-01"}
]
```

JSON Lines/NDJSON and an entire `wayback-recon` JSON report are not supported
directly. Use host TXT or the retained command's CSV export instead. An Atlas JSON
report can seed its host list, but nested evidence, checks, original local discovery
times and provider provenance are not restored: the new source is `import`.
Import is not a database-backup restore.

## Reading reports

`inventory.sqlite3` stores assets, source evidence, provider runs and all completed
availability samples. Exports have `schema_version: 1`. Inspect these sections:

- `assets`: local first/last seen, sources, evidence, latest sample and trends.
- `samples`: latest 100 stored checks per host; full history remains in SQLite.
- `archive_summary`: distinct stored URLs, endpoints and parameter names.
- `provider_runs`: latest 100 runs, including source errors, new-host lists and truncation.
- `provider_runs[].payload.metadata`: CompleteDNS events and other provider context.

Atlas timestamps are UTC; provider timestamps keep their provider-specific format.
crt.sh evidence uses log entry time; Cert Spotter evidence uses certificate
`not_before`, not DNS creation time. Imported URLs can contribute to URL summary
counts; those counts alone do not prove Wayback provenance. Check each evidence source.

Wayback uses `collapse=urlkey`: a representative capture is kept per URL key within
the query. `first_archived_sample`/`last_archived_sample` are extrema of retained
samples, not complete first/last captures. Date-range jobs improve coverage but do
not turn this into an exhaustive lifetime history.

`online` and `tls_error` go into the alive list; the latter does not prove a
successful HTTP application response. Down-observed includes NXDOMAIN, no address,
and unreachable. Unknown, unchecked and private-only hosts are not classified as
dead. The availability percentage includes conclusive HTTP-mode observations,
including DNS negatives; DNS-only runs do not contribute. It is not time-weighted.
Two observed HTTP or DNS transitions flag an intermittent candidate. Inspect sample
times and possible local network failures before interpreting that flag.

`discover`, `import`, `check`, `watch` and `export` write timestamped reports.
`inventory` displays a maximum of 200 rows. `dorks` replaces `archive_matches.json`.
Ctrl+C retains completed samples but can interrupt the final report export; run
`export` afterwards. Source failure never automatically deletes prior discoveries.

## Backup, restore and privacy

1. Stop every Atlas process using the output directory, including watch jobs.
2. Copy the entire output directory to a protected backup location. Preserve SQLite
   `-wal`/`-shm` sidecars if present; never discard them to resolve a lock problem.
3. Keep the original untouched. To test a restore, use the copied directory with
   `--output-dir` and run `inventory DOMAIN`; compare expected hosts and samples.
4. Resume only the intended working copy. A later `discover`/`check` will modify it.

There is no built-in online backup, restore, prune or schema-migration command.
For backup while processes are running, use SQLite's supported backup facilities
with an appropriate database tool, not a raw copy of the main database file alone.
Keep databases on local storage; back up closed files to sync/network storage.

Query-name-based redaction is a heuristic, not a secret detector. Names, paths,
unrecognized parameter values and imported/provider metadata may remain sensitive.
Review reports before sharing. Default Git ignore rules do not cover every custom
output path. Run `git status --short` before committing. Do not publish API keys.

## Exit codes and unattended use

| Code | Atlas meaning |
| --- | --- |
| 0 | Command completed; can include empty results, failed hosts or partial provider coverage |
| 1 | Every selected discovery provider returned an error status |
| 2 | CLI parsing, input, output-path or handled database/OS error |
| 130 | User interrupted the CLI |

Inspect `provider_runs`, truncation and per-host states rather than treating exit
0 as complete discovery or universal availability. An import with zero retained
rows can also return 0. No strict-completeness or machine-readable stdout flag exists.
Use absolute output paths, prevent overlapping jobs, and preserve logs if you
configure an external scheduler yourself. Atlas installs no scheduled tasks.

## Troubleshooting

| Symptom | Check / action |
| --- | --- |
| `wayback-atlas` not recognized | Use the bundled launcher or install/activate the Python environment. |
| Running source changes shows the old behavior | The batch file prefers the EXE; use `python -m src.cli` or rebuild. |
| Access denied writing results | Choose a writable absolute `--output-dir`; close files held by other apps. Elevation is not normally needed. |
| Inventory is empty | Confirm the exact root and output directory. Discovery/import must run before check/watch. |
| Provider HTTP 403/429 or challenge page | Review provider account/quota and wait. Use another documented source or import; do not loop rapidly. |
| Missing RapidDNS/CompleteDNS key | Set the corresponding environment variable in the same shell; select that source explicitly. |
| Cert Spotter misses older names | Its endpoint covers unexpired issuances and Atlas currently has no key setting; combine sources. |
| Discovery says limit reached | Coverage is partial; try a suitable budget or year-sliced Wayback jobs. Existing runs cannot resume across restarts. |
| Many hosts switch down together | Check local connectivity/resolver and compare another permitted vantage point. This is not proof of target outages. |
| Database locked | Stop duplicate writers and wait for normal shutdown. Do not delete SQLite sidecars. |
| SSL or corporate proxy trouble | Check system time/trust policy and distinguish provider access from direct HTTP probes. Do not disable TLS verification. |
| A copied `.venv` cannot start | Create `.venv-atlas` using an installed Python; copied environments retain interpreter paths. |
| Old pytest folders deny access | Use the verification script's separate cache paths. Those caches are not needed by the EXE. |

For reproducible issues provide version, source versus EXE, command with keys and
private targets removed, exit code, relevant provider status, and OS/Python details.
Do not post a whole research database. See [development](DEVELOPMENT.md) and
[security reporting](../SECURITY.md).

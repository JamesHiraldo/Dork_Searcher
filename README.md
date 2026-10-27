# Wayback Atlas 3.2

A terminal workspace for finding historical URLs, collecting subdomains, and tracking
how their DNS and web availability change over time. Formerly Dork Searcher.

Use only on assets you own or have permission to assess.

[Quick start](QUICKSTART.md) · [Installation](docs/INSTALL.md) ·
[Operations and troubleshooting](docs/OPERATIONS.md) ·
[Assessment and roadmap](docs/ASSESSMENT_AND_ROADMAP.md) ·
[Development](docs/DEVELOPMENT.md)

## What changed

- A spider ASCII banner, grouped color menus, progress indicators and scriptable commands.
- Wayback CDX, Common Crawl, crt.sh and Cert Spotter discovery in a persistent SQLite inventory.
- Resumable discovery: durable per-source cursors, mid-page buffers and atomic evidence commits.
- RapidDNS API integration and TXT/CSV/JSON imports; CompleteDNS nameserver history.
- Repeated DNS and HTTP sampling, wildcard indicators, IP changes and intermittent candidates.
- Offline archive dorks, custom templates and optional DuckDuckGo browser links.
- Google and Dogpile backends removed. No Playwright or browser installation is needed.
- JSON, spreadsheet-safe CSV and separate alive, down-observed and intermittent host lists.
- Local `doctor` diagnostics, full SQLite backups and `--version` identification.
- JSONL/NDJSON imports with original-source evidence, optional Cert Spotter authentication,
  strict discovery exit codes and per-host deadlines. See [release notes](docs/RELEASE_NOTES.md).

## Start on Windows

From the project folder in CMD:

```cmd
wayback_atlas.bat
```

In PowerShell use `.\wayback_atlas.bat`. Examples below using `wayback-atlas`
assume a source/wheel installation with its environment activated. EXE-only users
can substitute `wayback_atlas.bat` in CMD or `.\wayback_atlas.bat` in PowerShell.
No Python installation is required for the supplied Windows executable.

Or launch the packaged application directly:

```cmd
cd /d "C:\path\to\dork_searcher\Wayback_Atlas_App"
wayback_atlas.exe
```

The old `dork_searcher.bat` forwards to the new launcher. The launcher selects the
Atlas executable first, then a project Python environment. Obsolete 2.0 binaries
have been removed; previous tracked releases remain available in Git history.

Unlike the old EXE, the new EXE accepts the same subcommands and flags as the Python CLI.

## Install from source

Python 3.10+:

```cmd
python -m venv .venv-atlas
.venv-atlas\Scripts\activate.bat
python -m pip install -e "."
python -m src.cli
```

On Linux/macOS use `python3 -m venv .venv-atlas`, then
`source .venv-atlas/bin/activate`. The installed command is `wayback-atlas`.
Legacy `dork_searcher` and `dork-search` command names invoke the new interface.

## Menu

| Key | Workflow |
| --- | --- |
| 1 | Discover and merge Wayback + certificate sources + Common Crawl |
| 2 | Wayback archive, with date range |
| 3 | Select CT, RapidDNS, CompleteDNS or Common Crawl |
| 4 | Sample current DNS/HTTP availability |
| 5 | Watch availability across repeated samples |
| 6 | Inspect the inventory |
| 7 | Import discoveries |
| 8 | Archive dork workbench and saved templates |
| 9 | Open research resources |
| 10 | Export the inventory and history |
| 11 | Local diagnostics and full inventory backup |
| 12 | List saved discovery runs and resume one |
| 0 | Exit |

Type a menu number and press Enter; the prompt no longer repeats the entire choice
list. Blank input on the main menu does not exit. Source, check-mode and dork menus
also use numbered choices, explain any Enter default, and offer `0` to go back.
Wide terminals show two menu columns; narrow windows stack them. The spider uses
plain ASCII characters for compatibility with older Windows CMD encodings.

Discovery is passive with respect to the target: it queries third-party providers.
Check/watch sends DNS queries and, unless `--dns-only` is selected, root-page GETs
to the stored hosts. It reads response headers, closes the stream without collecting
page bodies, and does not follow redirects. No administrator privileges are needed.

## Recommended workflow

```cmd
wayback-atlas discover example.com
wayback-atlas check example.com
wayback-atlas watch example.com --rounds 12 --interval 300
wayback-atlas inventory example.com
wayback-atlas export example.com
```

Repeat discovery later against the same output folder to find newly observed names.
Each `discover` creates a fresh run. To continue an interrupted/limited run instead,
use `runs` to find its full ID and `resume RUN_ID`, or choose menu **12**.
Completed sources are skipped; unfinished sources continue from saved progress.
Watch resamples the inventory present at startup; it does not rediscover names
mid-run. Use separate discover runs when you want the list refreshed.

`watch` runs in the foreground. Keep the terminal open. Ctrl+C stops it; each
completed sample is saved immediately. The interval is a delay after a completed
round, not an exact wall-clock schedule. Nothing is silently scheduled or installed.

## Commands and flags

```text
wayback-atlas [--output-dir PATH] COMMAND
```

Place the global `--output-dir` option before the command. Run without a command
for the dashboard. Every command supports `--help`.

| Command | Arguments and options |
| --- | --- |
| discover DOMAIN | `--sources wayback crtsh certspotter rapiddns completedns commoncrawl`; defaults to Wayback, both CT sources and Common Crawl |
| | `--limit 5000`: record-processing budget per source for this invocation |
| | `--max-pages 20`: page/metadata steps per source for this invocation |
| | `--page-size 1000`: Wayback request size (1–10000), fixed for the run |
| | `--from-date YYYY`, `--to-date YYYY`: Wayback/Common Crawl date filters, up to YYYYMMDDhhmmss |
| | `--cc-latest 1`: select latest N Common Crawl indexes (1–100); pinned when catalog is saved |
| | `--cc-index CC-MAIN-YYYY-NN`: explicitly select an index; repeat for more (overrides `--cc-latest`) |
| | `--strict`: exit 1 if any provider errors or coverage is truncated |
| runs | Latest 50 saved run IDs, states, counts and errors; `--json` for machine-readable summaries |
| resume RUN_ID | `--limit 5000`, `--max-pages 20`, `--strict`; budgets are additional, query cannot change |
| check DOMAIN | `--dns-only`, `--concurrency 8`, `--timeout 5`, `--host-timeout 45` |
| watch DOMAIN | Same check flags; `--rounds 5`, `--interval 60` seconds |
| inventory DOMAIN | Display stored hosts and latest state |
| import DOMAIN FILE | TXT, CSV, JSON, JSONL or NDJSON, up to 25 MiB |
| export DOMAIN | Timestamped JSON, CSV and host lists |
| dorks DOMAIN QUERY | Filter locally stored archived URLs |
| resources | Print all four requested resource links |
| doctor | Local runtime/TLS/DNS/database checks; no network requests or key disclosure |
| backup DESTINATION | Consistent full SQLite backup to a new file; never overwrites |

`wayback-atlas --version` prints the running application's version.

Concurrency is 1–50, timeout is greater than zero and at most 60 seconds,
watch rounds are 1–10000 and the interval is 10–86400 seconds. `--host-timeout`
is an overall per-host deadline greater than zero and at most 600 seconds.
Timeouts and unexpected host errors become unknown samples; other hosts continue.
A batch probes up to two public addresses per host, trying both IP families when possible.
Date and page ceilings intentionally mean partial archive coverage on large domains.
`--limit` counts processed evidence records, not unique hosts (duplicates can consume budget).
Unprocessed records in a downloaded page are saved for the next resume; they are not discarded.
Limits accept 1–1000000 records and 1–10000 page steps per invocation. Each provider response
is separately limited to 16 MiB of decompressed JSON. Oversized replies produce an
explicit source error; narrow the query or use a suitable alternative source.
Common Crawl catalog/page-count steps also consume `--max-pages`; crt.sh/CompleteDNS
are single-response sources with a durable local buffer, not remotely paginated APIs.
`--timeout` applies to individual
DNS/HTTP operations, not the entire job. There is no Atlas requests-per-second flag.
Date strings accept 4, 6, 8, 10, 12 or 14 digits and are calendar-validated.

Examples:

```cmd
wayback-atlas --output-dir "D:\Recon\Example" discover example.com --sources wayback --from-date 2005 --to-date 2015 --limit 20000 --max-pages 50
wayback-atlas --output-dir "D:\Recon\Example" discover example.com --sources crtsh certspotter
wayback-atlas --output-dir "D:\Recon\Example" discover example.com --sources commoncrawl --cc-latest 3 --limit 5000
wayback-atlas --output-dir "D:\Recon\Example" runs
wayback-atlas --output-dir "D:\Recon\Example" resume RUN_ID --limit 20000 --max-pages 50
wayback-atlas --output-dir "D:\Recon\Example" import example.com hosts.csv
wayback-atlas --output-dir "D:\Recon\Example" watch example.com --dns-only --rounds 10 --interval 60
```

Unrelated domains from provider data and imports are excluded structurally; a result
for `notexample.com` is not treated as a child of `example.com`. Enter any desired
root domain—there is no hard-coded target allowlist or authorization ticket workflow.

Common Crawl uses its public CDX JSONL index, preserving the crawl collection ID on
each record. It does not download WARC files, execute archived content, or actively
crawl the target. The default covers the latest **one** published index, not the full
archive. Select more indexes for broader history; date filters do not automatically
select older indexes. See the [official index](https://index.commoncrawl.org/) and
[resumable discovery guide](docs/RESUMABLE_DISCOVERY.md) for coverage and recovery limits.

## Your requested services

| Service | Integration | Requirements / meaning |
| --- | --- | --- |
| [CompleteDNS](https://completedns.com/dns-history/) | Nameserver event history via v2 API; menu link | `COMPLETEDNS_API_KEY`; nameserver changes are not proof of host uptime |
| [RapidDNS](https://rapiddns.io/) | Paginated API records; export import; menu link | `RAPIDDNS_API_KEY`; official docs specify Pro/Max API access |
| [Secret Finder](https://serene-agnesi-57a014.netlify.app/) | Explicit browser launch | Reachable JavaScript helper; no verified collector API |
| [Pentest.bd / ReconNexus](https://pentest.bd/dorks/) | Explicit browser launch | External research/dork helper; no verified collector API |

Credentials are read from environment variables and are not saved to reports:

```cmd
set RAPIDDNS_API_KEY=your-key
set COMPLETEDNS_API_KEY=your-key
wayback-atlas discover example.com --sources rapiddns completedns
```

Keys may consume your provider quota when you explicitly select that source.
CompleteDNS data is attached to the root domain; external nameserver hostnames are
not imported as target subdomains. Missing keys, rate limits and challenge pages
produce source errors, not fake empty successes. Other sources continue.

Reference contracts: [RapidDNS API](https://rapiddns.io/help/api),
[CompleteDNS v2](https://completedns.com/api/documentation/v2),
[Internet Archive CDX](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server).

Set optional `CERTSPOTTER_API_KEY` to send Bearer authentication to Cert Spotter.
Without it, the adapter uses limited unauthenticated access. Its endpoint lists
unexpired issuances, not a complete historical certificate archive; a key does not
change that meaning. See [SSLMate's contract](https://sslmate.com/help/reference/ct_search_api_v1).

## Dorks without scraper failures

Recommendation: use **local archive filtering** as the reliable automated path.
It has no search-engine CAPTCHA or API quota once URLs are collected:

```cmd
wayback-atlas dorks example.com "ext:js"
wayback-atlas dorks example.com "path:/api/ -ext:png"
wayback-atlas dorks example.com "param:redirect OR param:url"
wayback-atlas dorks example.com "host:dev.example.com"
```

Terms separated by spaces are ANDed; `OR` joins groups; `-term` excludes matches.
Quoted phrases are supported. Fields are `host:`, `path:`, `ext:` and `param:`.
These inspect URL strings and parameter names, not archived page bodies. They are
not a full Google query-language implementation.

Menu 8 can save custom templates in `custom_dorks.txt` or create a target-scoped
DuckDuckGo URL and open it at your request. Public search engines retain their own
rate limits, operator behavior and bot checks. There is no honest promise of
unrestricted automated dork scraping. Google/Dogpile scraping is not included.
Use local fields such as `path:` only in the local filter. Browser mode forwards
your query unchanged after adding `site:DOMAIN`; it does not translate local fields
into DuckDuckGo operators. Use plain keywords in browser mode when uncertain.

## Understanding historical, alive, dead and intermittent results

| Label | What the observation actually establishes |
| --- | --- |
| First/last seen | When this inventory first/last collected the name, not when it was created/deleted |
| Archived evidence | A URL was present in the selected CDX sample; historical status is not current status |
| unchecked | Discovered, but no availability sample yet |
| online | An HTTP response arrived; 401, 403, 404 and 500 still prove a responding service |
| tls_error | A TLS certificate validation failure indicates a responding TLS endpoint |
| dns_only | DNS resolves, but HTTP was not requested |
| nxdomain | The resolver returned NXDOMAIN at sampling time |
| no_address | No A/AAAA answer in this observation |
| unreachable | Selected addresses did not yield HTTP responses; this is not proof of permanent death |
| unknown | DNS timeout, SERVFAIL or resolver error; excluded from transition inference |
| private_address | Resolved only to non-public addresses; HTTP sampling skipped |
| intermittent candidate | At least two observed HTTP or DNS state transitions in the latest 100 samples |
| wildcard_possible | The address overlapped a random-name DNS control; shared hosting can also do this |

DNS-only sampling records DNS transitions separately. Unknown samples interrupt
transition inference. Address changes are reported separately: IP rotation alone
does not prove an outage. Sampling from one machine cannot establish randomness,
global uptime, or why a service is unreachable. Exported availability percentages
describe the usable observations in the sample window, not an SLA.

A wildcard certificate is evidence for a DNS suffix, not proof that every possible
name exists. Likewise, old CT/Wayback evidence does not establish current ownership,
DNS resolution or a takeover vulnerability.

## Output and recovery

Default: `Desktop\Wayback_Atlas_Results`, using the real Windows Desktop location.
Automatic fallback: `%LOCALAPPDATA%\WaybackAtlas\Results`, then the home directory.

Set `WAYBACK_ATLAS_OUTPUT_DIR` or pass `--output-dir` to use a fixed project folder.
The previous `DORK_SEARCHER_OUTPUT_DIR` variable remains recognized. An explicit
unwritable path gives an error rather than silently selecting a different database.

Files include:

- `inventory.sqlite3`: hosts, evidence, check history, discovery jobs and resumable page buffers.
- `DOMAIN_TIMESTAMP.json`: source evidence, recent samples, errors, archive summary and trends.
- `DOMAIN_TIMESTAMP.csv`: flat host inventory with spreadsheet formula protection.
- `*_hosts.txt`, `*_alive.txt`, `*_down_observed.txt`, `*_intermittent.txt`.
- `archive_matches.json`: latest local query results (replaced by the next local query).
- `custom_dorks.txt`: saved templates.

JSON reports include the latest 100 checks per host and latest 100 provider runs;
the database retains the full history. Back up the database only after closing
the application, or use SQLite's backup facility. Source query failures never
delete previously discovered hosts. Interrupted checks retain completed samples.
Discovery saves each fetched page before processing and commits evidence with its
checkpoint. On an interruption, only an uncommitted/in-flight request may need repeating.

Potentially sensitive query parameter values are redacted in archived URLs.
Reports can still contain private research context: keep output folders out of Git.
Opaque provider cursors can contain unredacted URL information; protect the database
and backups even when exported evidence URLs are redacted. API keys are not checkpointed.
Existing Dork Searcher results can be imported; nothing is automatically deleted.
Importing an Atlas JSON report imports host records, not the complete database
history. It is not a backup restore. See [import formats and backup procedure](docs/OPERATIONS.md).
Use `backup NEW_FILE.sqlite3` (or menu 11) for a consistent database snapshot,
including full evidence and check history. Copy custom templates separately.
Custom output directories are not automatically covered by this repository's
`.gitignore`; check before committing any research files.

## Improvements to prioritize next

1. Repeat discovery daily and watch confirmed assets over several days; a few samples
   are insufficient to establish intermittent behavior.
2. Compare observations from a second permitted network/resolver to separate local
   connectivity problems from target failures.
3. Split large archive jobs into year ranges to reduce bias from URL-sorted limits.
4. Import independent discovery exports to increase coverage; no single index is complete.
5. Manually investigate long-lived CNAMEs and ownership changes. Do not equate an old
   hostname, DNS failure or cloud-provider CNAME with a confirmed takeover.
6. Add scheduled report comparisons and notifications only after baselining expected
   maintenance, wildcard behavior and rate limits.

This is a tested 3.2 beta, not a claim of exhaustive discovery or guaranteed provider uptime.
The [code-based assessment](docs/ASSESSMENT_AND_ROADMAP.md) separates existing
capabilities from proposed changes and provides an implementation order and test criteria.

## Development and packaging

```powershell
.\.venv-atlas\Scripts\python.exe -m pip install -e ".[dev,build]"
.\scripts\verify.ps1 -PythonCommand ".\.venv-atlas\Scripts\python.exe"
.\scripts\build_windows.ps1 -PythonCommand ".\.venv-atlas\Scripts\python.exe"
```

The build emits `Wayback_Atlas_App\wayback_atlas.exe` and a versioned Python wheel.
It also writes `SHA256SUMS.txt`. The launcher prefers the EXE even after source edits;
run `python -m src.cli` to test source changes, then rebuild for distribution.
No browser engine or packet-injection driver is bundled.
Tests mock DNS/providers and use synthetic availability sequences.

The older parameter-analysis command `wayback-recon` and HTTP-header command
`http-metadata-probe` remain available for compatibility; see their `--help`.
They are no longer the main menu.
Their separate flags and output paths are documented in [retained commands](docs/README_RECON.md).

MIT license. See [LICENSE](LICENSE).

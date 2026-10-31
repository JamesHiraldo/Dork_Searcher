# Resumable discovery and Common Crawl (3.2)

## Use it

From CMD in the project folder (prefix the launcher with `.\` in PowerShell):

```cmd
wayback_recon.bat --output-dir "D:\Recon\Example" discover example.com --sources wayback commoncrawl --cc-latest 3 --limit 5000
wayback_recon.bat --output-dir "D:\Recon\Example" runs
wayback_recon.bat --output-dir "D:\Recon\Example" resume RUN_ID --limit 20000 --max-pages 50
wayback_recon.bat --output-dir "D:\Recon\Example" runs --json
```

Replace `RUN_ID` with the full ID printed when discovery starts or listed by `runs`.
Keep the same output folder. Menu **12** lists the latest 50 runs and lets you resume
one using numbered choices. The CLI can resume an older run by its full saved ID.

- **Continue:** `resume RUN_ID` retries errors and consumes saved buffers/cursors.
- **Refresh:** `discover DOMAIN ...` starts a new run, retaining all existing inventory evidence.
- **Change query:** start a new discovery with the desired source/date/index options.
  Resume cannot change them. Budgets are allowed to change because they only control
  how much more work is performed, not which records a provider page contains.
- **Finish:** repeat resume as needed until all sources say `complete`. This means
  the selected provider query was exhausted, not that all possible subdomains exist in it.
- **Interrupt:** Ctrl+C leaves saved pages/evidence intact. `export DOMAIN` regenerates
  reports if interruption prevented the automatic export. The checkpoint is in SQLite,
  not the JSON report.

`--limit` defaults to 5000 processed records **per source, per invocation**; duplicates
may count. `--max-pages` defaults to 20 newly fetched page/metadata steps per source.
Reading a saved buffer consumes the record budget but no new page budget. Common Crawl
catalog and page-count steps count as steps even when they contain no evidence.
Remaining records in a downloaded page stay in SQLite. No rows are intentionally
discarded because an invocation reaches its limit. Response size and parse failures
stop that source rather than silently advancing it.

`--strict` on discover/resume exits 1 if any source is incomplete or failed, after
saving progress and exporting. Without it, partial coverage can return 0; inspect
statuses and errors. Bad IDs/database conflicts return 2; CLI Ctrl+C returns 130.

## Common Crawl selection

`commoncrawl` is included in default discovery. Menu 3 also offers it individually.
The default chooses the latest one published `CC-MAIN-YYYY-NN` collection from the
[official catalog](https://index.commoncrawl.org/collinfo.json).

Use `--cc-latest 3` to select the latest three, or repeat `--cc-index` to choose exact
IDs from that catalog. Explicit IDs override the latest count. Up to 100 indexes can
be selected; begin with a small number to respect the shared service.

Resolved IDs and their order are persisted before any index pages are read. Resume
does not look up a new catalog or silently switch to newer collections. Each stored
URL has `source=commoncrawl`, `crawl_index`, capture timestamp, archive status and MIME
type. Archived sample date summaries and local archive dorks include this evidence.

The adapter uses `matchType=domain`, then structurally validates hostnames so unrelated
domains are excluded. It uses page counts and zero-based pages with `pageSize=1` for
both requests. That size is **one compressed index block**, not one URL. A server-side
record limit is deliberately not added: that would drop the rest of a page. JSONL
responses use the same 16 MiB decompressed-body cap and bounded retries as other sources.
404/no-capture responses on a validated index are treated as empty results; other HTTP
failures remain errors. Catalog IDs are validated; remote endpoint URLs are not trusted.

`--from-date`/`--to-date` filter captures in the selected Wayback/Common Crawl indexes.
They do **not** cause older Common Crawl collections to be selected automatically.
An old date range against the latest collection may legitimately return no captures.
Choose historical collection IDs deliberately for historical research.

This is archive-index discovery, **not an active web crawler**. It does not download
WARC files or page bodies, follow target links, execute JavaScript, bypass provider
access controls, or claim complete coverage. Requests run sequentially with a delay
between newly fetched steps and bounded retry/backoff. For bulk analytics, Common Crawl
recommends its columnar index rather than heavy queries to the shared CDX service.
See the [official index](https://index.commoncrawl.org/) and
[pagination contract](https://github.com/webrecorder/pywb/wiki/CDX-Server-API#pagination-api).

## Persistence design

Three additive tables leave existing 3.0/3.1 inventory/check history intact:

| Table | Saved state |
| --- | --- |
| `discovery_jobs` | Full run ID, checkpoint format version, root domain, creation time, immutable query options |
| `discovery_checkpoints` | Per-source revision, status, next cursor, staged page with consumption offset, counts and last error |
| `discovery_cursors` | Hashes of visited continuation states to detect cycles across restarts |

Checkpoint format is version 1. Unknown versions are rejected, not guessed. There
is no destructive migration, checkpoint pruning, or automatic conversion of pre-3.2
provider runs: start a new discovery to create checkpoints for an older inventory.

```text
fetch bounded page -> stage page in SQLite -> commit evidence + offset/next cursor
                              |                         |
                       interruption safe       record limit -> paused
                                                next page -> repeat
                                                exhausted -> complete
```

Staging and evidence consumption are two transactions. Once staged, a page survives
even if consumption never starts. Evidence insertion, host updates, provider-run
audit entry and consumed offset/cursor update share **one** transaction. A failure
rolls all of them back. Completed sources are skipped on subsequent resumes.

Every checkpoint update compares a revision counter. Two processes may make redundant
network requests, but a stale writer cannot overwrite committed progress/evidence.
Avoid overlapping workers; this is not a distributed queue or lease scheduler. A
conflict is explicit and requires resuming after duplicate workers stop.

Full-record fingerprinting deduplicates inventory evidence across pages and fresh
runs. The displayed record counter measures processed records, not unique evidence
or hosts. `new_hosts` means names newly inserted in this local target inventory.
Provider-run audit rows now represent page/batch commits and source errors; their
metadata contains `job_id`, page number, offset and checkpoint status. The report
retains only the latest 100 audit rows; the database retains the full history.

## Recovery boundaries and privacy

- A crash before staging may repeat the in-flight page. A crash after staging resumes
  its local buffer. No promise is made to resume partway through an HTTP download.
- Wayback uses opaque resume keys; Cert Spotter uses issuance IDs; RapidDNS uses page
  numbers. crt.sh and CompleteDNS expose one response, so their downloaded response
  is locally buffered but cannot resume a partially downloaded HTTP body.
- Provider datasets can change. RapidDNS offset pages in particular are not a stable
  snapshot; names can shift between requests. Resume cannot guarantee provider-side
  consistency. Fresh discovery complements an older resumed run.
- Invalid/expired/repeated cursors stop with saved progress intact. Retry later or
  intentionally start a fresh run; the tool never silently resets a cursor. Invalid
  schema/JSON rows leave that page uncommitted for retry (prior pages remain saved).
- Keys are read from environment variables at execution time and are not stored in
  query configuration. Opaque cursors may embed **unredacted URL information** and
  pending pages contain research context. Protect the database and backup files.
- `backup NEW_FILE.sqlite3` includes jobs, buffers and cursors. Export/import is not
  a checkpoint backup. Restore a backup into a new output folder as described in
  [operations](OPERATIONS.md); resume only the intended working copy.
- These guarantees apply to the main Wayback-Recon discover/resume workflow. The retained
  `wayback-parameters` command and direct `collect()` library function remain non-resumable.
- Large inventories still require memory for report generation. This release does
  not introduce streaming reports, retention policies, automatic scheduling or leases.

Use only on assets you own or have permission to assess.

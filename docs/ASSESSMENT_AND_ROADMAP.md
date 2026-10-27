# Engineering assessment and improvement roadmap

Reviewed against the current 3.0.0 source and CLI contracts on 2026-10-27 (UTC).
This is a functionality/reliability review, not an exhaustive security audit or a
benchmark. Proposed commands and capabilities below are **not implemented**.
No runtime features, accounts, schedules or external tools were changed in this review.

## Overall assessment

Atlas is a useful single-operator beta: passive collection is separated from active
sampling, provenance and failures are retained, and SQLite supports repeated research.
It is not yet a dependable unattended monitoring service or exhaustive historical
inventory. The largest gains come from better collection coverage, resumability
and measurement quality, rather than more search-engine scraping.

Existing strengths include structural hostname matching, explicit truncation,
per-sample persistence, separate unknown states, pinned-address Atlas HTTP checks,
no target redirects in the main checker, CSV formula protection, and a reusable
Windows release. These are code observations, not proof of complete robustness.

## Recommended implementation order

### 1. Provider contracts, coverage accounting and fault isolation — high priority

Evidence: [discovery.py](../src/discovery.py) deduplicates on hostname, URL and
timestamp. Certificate renewals consume multiple retained records for one host;
different RapidDNS record types/values with the same host/time can collapse into
one record. `limit` caps retained records, not downloaded response size. Responses
are loaded as JSON without a byte ceiling. Some wrong-type values can raise
exceptions outside the current ValueError/Requests error handlers.

Offline reproduction during this review: a synthetic successful RapidDNS response
containing A and AAAA records for `api.example.com` at the same timestamp produced
one retained record. This confirms the deduplication edge case without querying a
provider or target. The remaining robustness observations are source-reviewed, not
claims that every failure mode was reproduced.

Recommendation: validate provider schemas, fingerprint complete relevant evidence,
separate unique-host and evidence budgets, cap response bytes, and report downloaded,
accepted, rejected and retained counts. Isolate malformed-provider failures so the
next source still runs. Add per-provider rate budgets, jitter and persisted cooldowns.

Cert Spotter currently sends no authentication. Add an optional key and preserve
provider error codes; do not advertise unlimited or full historical coverage.
The official API is for unexpired issuances, supports authenticated access, and
limits unauthenticated evaluation queries. [SSLMate reference](https://sslmate.com/help/reference/ct_search_api_v1).

Acceptance: repeated certificates do not starve unique names; A/AAAA/CNAME evidence
at one timestamp survives; malformed bodies, huge bodies, 401/403/429 and timeouts
give bounded, credential-free source errors without cancelling other sources.

### 2. Incremental discovery and persistent checkpoints — high priority

Evidence: [wayback.py](../src/wayback.py) and [discovery.py](../src/discovery.py)
keep pagination cursors only in memory. Every run starts again. A limited query
can repeatedly retrieve the same initial records, missing later/new names.
[cli.py](../src/cli.py) merges a source only after its collection returns, so an
interruption mid-provider can lose that source's in-flight results.

Recommendation: store a run ID, source/query/date/budget fingerprint, page cursor
and page-level evidence atomically. Support resume, intentional refresh and a
coverage summary. Track incomplete versus completed runs separately. Handle
expired/invalid cursors by a visible, idempotent restart rather than silent omission.

Acceptance: interrupt after page N, resume without duplicate evidence or lost pages;
changing the query/date range does not reuse an incompatible checkpoint. New-name
counts are based on inventory differences, not certificate timestamps.

### 3. More trustworthy intermittent-availability analysis — high priority

Evidence: [availability.py](../src/availability.py) uses one system resolver/network,
root-level wildcard controls and per-operation timeouts. [inventory.py](../src/inventory.py)
flags two state transitions in the latest 100 samples regardless of elapsed time.
There is no persisted round ID, resolver identity or network-health control. Samples
are saved incrementally, but an unexpected worker exception can terminate the batch.

Recommendation: add sample/run IDs, start/end times, resolver/vantage identity,
per-host overall deadlines and network-health context. Isolate unexpected host
failures. Add configurable minimum sample/time windows and consecutive confirmations
before alerts. Test nested wildcard suffixes when relevant; preserve observations
rather than deleting likely wildcard hosts. Keep TLS reachability distinct from
successful HTTP service availability in summaries.

Acceptance: injected local network failures do not generate a flood of target-outage
alerts; DNS-only, unknown, TLS-only and mixed-family samples retain distinct meanings;
clock gaps and interrupted rounds are visible. False-positive rates are measured
on synthetic transition sequences and an operator-controlled test service.

### 4. Historical capture investigation — medium priority

Evidence: [wayback.py](../src/wayback.py) uses `collapse=urlkey`, retaining representative
captures rather than a complete timeline. The documented CDX behavior suppresses
later captures of a URL key. [Internet Archive CDX documentation](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server).

Recommendation: keep fast discovery as default, then offer an explicit bounded
timeline for selected hosts/URLs: earliest/latest observed capture, status/MIME
changes, year coverage and archive-view links. A future JS endpoint extractor
should be opt-in, byte-limited and treat content as data; never execute archived JS.

Acceptance: fixture timelines preserve repeated captures and clearly distinguish
archive status from live state. Large jobs retain date/budget limits and checkpointing.

### 5. Database lifecycle and report performance — medium priority

Evidence: [inventory.py](../src/inventory.py) has `CREATE TABLE IF NOT EXISTS` but no
schema migration manager, backup API or retention policy. `report()` performs per-host
queries and materializes evidence and samples for all assets, including when the UI
only shows 200 rows. [artifacts.py](../src/artifacts.py) builds entire exports in memory.
JSON import is lossy and cannot restore historical samples.

Recommendation: explicit DB versions/migrations, transactional backup/restore with
integrity checks, paginated inventory queries, batched sample retrieval, and streaming
exports. Add opt-in retention with a dry-run count and backup requirement; never
silently delete research evidence. Preserve full-fidelity provenance when importing
a future versioned backup format.

Acceptance: round-trip a representative database without losing provenance/history;
rollback a failed migration; benchmark 10k and 100k-host synthetic inventories with
documented memory/time targets before claiming scalability.

### 6. Repeatable Windows release and operational diagnostics — medium priority

Evidence: [.github/workflows/ci.yml](../.github/workflows/ci.yml) tests Windows Python
versions and builds Python distributions, but does not build/smoke-test the EXE.
The local build needed SSL runtime-data handling; source tests alone did not catch
that packaging failure. Dependencies use ranges, and the launcher prefers a possibly
older EXE over edited source. There is no `doctor` or `--version` command.

Recommendation: frozen-EXE CI tests, clean-machine smoke tests, build identity and
dependency manifest, reproducible dependency constraints, and explicit diagnostics
for output permissions, CA data, DNS backend and provider credentials. Consider
release signing if distributing widely. Keep live provider tests opt-in and small.

Acceptance: EXE help, import/export, local dorks, mocked DNS/HTTP and non-UTF CMD
rendering pass without a developer environment. Verify artifact hashes and source
revision. Test Python/Linux/macOS separately before claiming platform validation.

### 7. Broader passive coverage through supported interfaces — medium priority

Recommended add-ons, after reliable checkpoints and budgets:

- **Common Crawl CDX:** a complementary archive index. Store collection identifiers
  and query budgets; do not bulk-hammer the shared URL index. Its operator recommends
  the columnar index for bulk filtering. [Official index](https://index.commoncrawl.org/).
- **Subfinder import adapter:** retain JSONL source attribution and source timestamps
  rather than spawning opaque commands. Today, its plain host TXT output can already
  be imported; JSONL is not supported by Atlas. Subfinder's documented `-oJ` and `-cs`
  provide a useful future interchange format. [Official usage](https://docs.projectdiscovery.io/opensource/subfinder/usage).
- **RapidDNS richer history:** preserve record type/value and assess documented export
  jobs for large authorized datasets. Account access and quotas still apply.
  [RapidDNS API](https://rapiddns.io/help/api).

Keep provider provenance and distinguish certificate names, observed DNS records,
and archived URLs. CompleteDNS is nameserver-event history, not a complete passive
DNS database for every child hostname. [CompleteDNS v2](https://completedns.com/api/documentation/v2).

### 8. Triage UI, comparison reports and opt-in notifications — later

Build filtered views for newly found, recovered, changed-IP and stale observations;
show last-check age and provider completeness. Add per-host timelines, saved searches
and an HTML report that escapes all provider/imported content. Prioritize evidence
links and confidence explanations over an opaque risk score.

Only after run-state handling is reliable, add explicit scheduling and alert delivery
with overlap protection, deduplication, retry/backoff, maintenance windows and a
quiet mode. A failed provider or local network outage should not look like assets
were deleted. Keep payloads minimal so notifications do not leak query values.

## Best next development milestone

Implement items 1–3 first: evidence correctness, resumable discovery and dependable
samples. Follow with database backup/migrations and EXE CI before unattended use.
Add Common Crawl and a historical timeline after those foundations are measured.
Keep local archive dorks; there is no reliable promise of unrestricted search scraping.

## Validation boundaries

The previous runtime implementation passed 46 local automated tests and bounded
live example.com tests for Wayback, crt.sh, Cert Spotter and HTTPS. This documentation
review checked source behavior, current CLI help and official API references; it
did not rerun arbitrary-target scans, validate paid-account credentials, benchmark
large inventories or establish round-the-clock provider availability. The Windows
CI matrix is configured, not evidence that a remote CI run passed in this review.
Documentation checks resolved 43 local links across 11 Markdown files and parsed
representative Atlas command examples. No executable or wheel was rebuilt; their
release hashes remain unchanged.

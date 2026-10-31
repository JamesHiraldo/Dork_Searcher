# Webpage classification and 4.0 upgrade

Wayback-Recon distinguishes network reachability from webpage accessibility. All
outputs use `src/classification.py`, including the console, JSON, CSV, HTML and TXT.
`state=online` is retained only as a legacy transport signal for availability trends.
Use `classification`, `network_reachable`, `webpage_accessible` and `confidence` instead.

## What enters alive.txt

Only `confirmed_webpage`: a final 2xx response with HTML content type, recognizable
structure, meaningful text/form content, at least 200 downloaded bytes, and no detected
error-page signals or matching HTTP wildcard response. This is a conservative heuristic,
not a browser execution test or a guarantee that a JavaScript application works.
Small pages, API/JSON responses, encoded bodies and incomplete legacy evidence remain
`alive_candidate`. They may still be useful; they are not declared dead.

401 is `authentication_required`; 403 `forbidden`; 400 `bad_request`; 404 `not_found`;
5xx `server_error`. A denial/error title or a short denial message can turn a 200 into
`error_page`. Keywords in longer normal content alone do not reject a page. These
heuristics can still misclassify unusual pages; review the title, signals and sample.

`alive.txt` and `confirmed_webpages.txt` contain identical hostnames. Separate lists:
`alive_candidates.txt`, `redirects.txt`, `external_redirects.txt`, `protected.txt`
(401 and 403), `forbidden.txt`, `not_found.txt`, `bad_request.txt`, `server_errors.txt`,
`timeouts.txt`, `connection_failed.txt`, `tls_errors.txt`, `dns_only.txt`,
`unreachable.txt`, `error_pages.txt`, and `wildcard_candidates.txt`.

## Request and redirect limits

HTTPS is tried first; HTTP is tried on connection/read/TLS failure. Each attempt remains
separate in `http`. HTTP error statuses do not trigger bypass attempts. Requests start
at `/`, use a transparent Wayback-Recon User-Agent, validate TLS, ignore environment
proxies, and pin connections to resolved public IPs while retaining Host and SNI.

Defaults: connect/DNS timeout 5 seconds, read timeout 10 seconds, total host deadline
45 seconds, maximum 10 redirects. Configure `check`/`watch` with `--timeout`,
`--read-timeout`, `--host-timeout`, and `--max-redirects` (0–10).
Redirect loops, timeouts and TLS failures cannot become confirmed webpages.

Only HTTP(S), default-port destinations inside the requested target DNS subtree are
followed. Each hop gets fresh DNS resolution and an exclusively public address check.
This is a conservative **target boundary**, not a Public Suffix List ownership assertion.
If you specify a subdomain target, sibling destinations are external to that target.
External redirects are recorded but never contacted automatically. `final_url` and
`final_status` describe the last fetched response; `redirect_destination` identifies
an unvisited external destination. Chains retain URL, status and Location per hop.

At most 64 KiB of an uncompressed response is inspected, and only a 2 KiB sample is
persisted. Encoded responses are not decompressed (they remain candidates). Full body
length beyond that cap is unknown; `body_truncated` is explicit. Metadata includes title,
content type, advertised length, downloaded size, server, elapsed time, TLS state,
fingerprint and classification signals. No browser/JavaScript runs.

Two random-name controls per HTTP sampling round test generic wildcard behavior.
A matching public IP + final status + normalized-body fingerprint marks
`http_wildcard_possible`. Matching confirmed pages become low-confidence
`wildcard_candidate`; a matching 403 stays forbidden. Dynamic/host-specific responses
may evade this heuristic; shared responses are not proof a hostname is nonexistent.
Duplicate fingerprints across latest host samples are grouped in JSON/HTML.

## Filters and audit logging

```cmd
wayback_recon.bat inventory example.com --only-webpages
wayback_recon.bat export example.com --only-webpages --include-protected --include-redirects
wayback_recon.bat export example.com --status 200
wayback_recon.bat inventory example.com --classification forbidden
wayback_recon.bat --debug check example.com --read-timeout 10 --max-redirects 5
```

Filters apply to `inventory` and `export`, not discovery or the stored database.
Include flags expand `--only-webpages`; without that filter all categories already
appear. Status/classification filters additionally narrow the selection. Filtered
exports retain target-wide archive/provider summaries. `--debug` logs classification
and whether the host qualifies for alive output; it does not enable HTTP wire logging.

## Upgrade and privacy

Install the updated project, or run `dist/wayback_recon.exe` / `wayback_recon.bat`.
`wayback-atlas` and `wayback_atlas.bat` remain compatibility aliases. The old standalone
`wayback-recon` parameter collector has moved to `wayback-parameters` to free the main name.
Update scripts that previously used `wayback-recon --targets ...` accordingly.

New workspaces use `Desktop/Wayback_Recon_Results`. Existing Desktop inventory in
`Wayback_Atlas_Results` is reused without moving or deleting it. For another existing
location pass `--output-dir`. Environment precedence: explicit option, then
`WAYBACK_RECON_OUTPUT_DIR`, `WAYBACK_ATLAS_OUTPUT_DIR`, `DORK_SEARCHER_OUTPUT_DIR`.

Old database samples are reclassified in memory on report/export; raw SQLite rows stay
unchanged. A historical 200 without body evidence cannot become confirmed without a
new authorized check. Old exports are not rewritten: run menu 10 or `export` again.

JSON report schema is now 2. Reports contain titles, raw body snippets and redirect URLs
that may expose sensitive information. Keep them and database backups out of public Git.
The original attachment supplied status counts, not a complete dataset. Tests recreate
that distribution using synthetic `example.com` hosts; no requests to its named domain
are required or made by the tests.

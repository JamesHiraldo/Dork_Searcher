# Retained parameter-analysis and HTTP/CORS commands

These are separate Python entry points retained for compatibility. They are not
subcommands of `wayback_atlas.exe` and are not part of the Atlas dashboard.
Install from source or wheel and activate that Python environment first; see
[installation](INSTALL.md). They write the explicit paths supplied by the user,
not the Atlas Desktop inventory, and do not update `inventory.sqlite3`.

Use only targets you own or have permission to assess. The command-specific scope
acknowledgement below applies to the retained HTTP probe, not Atlas discovery.

## Wayback parameter analysis

`wayback-recon` uses the shared HTTPS CDX client. It retries transient failures,
honors `Retry-After`, paginates with resumption keys, validates that every archived
URL belongs to the requested scope, and reports truncation and errors explicitly.
Retry delays are bounded; both seconds and HTTP-date Retry-After values are parsed.
Pagination state is not saved across process restarts. No target pages are fetched.

```powershell
wayback-recon --targets example.com api.example.com `
  --max-urls 100000 --rate 0.5 `
  --output Result\recon.json --csv Result\recon.csv
```

Add `--include-subdomains` when the program scope authorizes child hosts.

| Flag | Meaning / default |
| --- | --- |
| `--targets DOMAIN ...` | Required; one or more domains |
| `--output PATH` | Required JSON path |
| `--csv PATH` | Optional CSV path; must differ from JSON |
| `--rate 0.5` | Delay in seconds between CDX pages/targets; nonnegative |
| `--max-urls 50000` | Positive retained-URL limit per target |
| `--include-subdomains` | Include child hosts; off by default in this command |
| `--include-sensitive-values` | Disable query-value redaction; off by default |
| `--help` | Print usage |

The shared client currently has a 100-page ceiling for this entry point. It does
not expose the Atlas `--from-date`, `--to-date` or `--max-pages` options.

The JSON report contains:

- retrieval status, page count, error, and truncation status;
- archived URL and unique endpoint counts;
- a deterministic endpoint sample;
- parameter occurrence and unique-value counts;
- token-like parameter classification and redaction;
- scoped, validated archived URLs.

Parameter values are decoded exactly once. Sensitive values are redacted in both
the URL list and parameter examples unless `--include-sensitive-values` is set.
Redaction is heuristic; paths and unrecognized parameter names can remain sensitive.

## Active HTTP metadata / CORS probe

Despite the historical module filename `passive_probe.py`, this command sends
active GET requests. Domain input generates HTTPS URLs for `/`, `/robots.txt`,
`/.well-known/security.txt` and `/favicon.ico`; URL-file input uses the supplied URLs.
It collects selected headers and query parameters, not response bodies. Redirects
are followed only within its validated hostname rules and redirect budget.

Example from an activated environment in CMD:

```cmd
http-metadata-probe --targets example.com --allowed-target example.com --acknowledge-scope --output Result\headers.json --csv Result\headers.csv
```

| Flag | Meaning / default |
| --- | --- |
| `--targets DOMAIN ...` | Domain input; choose this or `--urls-file` |
| `--urls-file PATH` | One absolute HTTP(S) URL per line; blank/comment lines ignored |
| `--output PATH`, `--csv PATH` | Required JSON and optional distinct CSV path |
| `--concurrency 8` | 1–50 concurrent workers |
| `--timeout 15` | Per-operation timeout, greater than 0 and at most 120 seconds |
| `--max-redirects 5` | Redirect ceiling, 0–10 |
| `--test-cors` | Include an Origin header and classify returned CORS headers |
| `--origin https://example.com` | Origin value used by `--test-cors` |
| `--allowed-target DOMAIN` | Repeatable destination domain; defaults to each input URL's host |
| `--allow-subdomains` | Permit child hosts of allowed targets |
| `--allow-private` | Permit private/local destinations for explicitly selected lab use |
| `--acknowledge-scope` | Required for this retained active command |
| `--help` | Print usage |

The command reports header patterns, not verified browser exploitation. An allowed
origin or wildcard can be intentional; a credentialed wildcard is not automatically
an exploitable browser policy. Assess actual data sensitivity and browser behavior
before reporting a finding. This retained command can store raw query parameters;
do not assume Atlas's archive redaction applies to its output.

The two entry points also run as `python -m src.recon_pipeline` and
`python -m src.passive_probe`. Existing output paths are replaced when reused.
For both, 0 means processing completed (possibly partial), 1 indicates all targets
failed by their respective result checks, and 2 indicates handled input errors.
Inspect the individual records, not just the exit status.

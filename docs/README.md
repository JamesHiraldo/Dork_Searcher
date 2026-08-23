# Dork Searcher 2.0

Dork Searcher is a scope-aware reconnaissance toolkit for authorized bug bounty,
penetration-testing, and asset-inventory work. It combines search-engine queries,
Internet Archive CDX collection, Certificate Transparency discovery, DNSDumpster,
structural hostname cross-referencing, and a bounded HTTP metadata probe.

> Use this software only on systems you own or have explicit permission to test.
> Program scope, rate limits, and platform rules always take precedence.

## Trust model

Results explicitly distinguish evidence types:

- `observed`: reported by a search index, archive, CT log, or DNS data source. This
  does not assert that the asset is currently live.
- `candidate`: generated from a wordlist and requires DNS verification. Candidate
  generation is not mixed into discovery results.
- `error`: a failed backend request retained in the artifact for auditability.

Cross-referencing parses DNS hostnames. It never uses substring matching.

## Capabilities

- Google Programmable Search with site restriction and pagination (maximum 100)
- DuckDuckGo-first search with rendered-page recovery, Dogpile fallback, and a
  browser-rendered Brave last resort
- Direct Dogpile diagnostics across both known result routes
- Wayback CDX HTTPS collection with retries and resumption-key pagination
- Parameter and endpoint inventory with sensitive-value redaction by default
- Passive subdomain enumeration that merges `crt.sh` and Cert Spotter observations
- DNSDumpster API discovery
- Active, bodyless GET metadata probing with redirect and private-IP safeguards
- CSP/security-header inventory and evidence-based CORS classification
- Atomic JSON/CSV artifacts with spreadsheet formula-injection protection

## Install

Python 3.10 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Playwright is a core dependency. Search rendering prefers an installed Microsoft Edge
or Google Chrome. If neither is available, install Playwright Chromium once:

```powershell
python -m playwright install chromium
```

The Windows executable uses the installed Edge browser and does not require a separate
Chromium download.

The interactive menu uses terminal-safe ANSI colors when supported. Set `NO_COLOR=1`
to disable them; redirected output is always left uncolored.

Menu option 10 displays the built-in dork templates and lets users add or remove
persistent custom templates. Custom entries are automatically target-scoped with
`site:{t}` and included in Google, DuckDuckGo, and Dogpile runs.

## Entry points

```powershell
dork_searcher
dork-search --help
wayback-recon --help
http-metadata-probe --help
```

Run from a source checkout with `python -m src.cli` if the package is not installed.

### Wayback collection

```powershell
dork-search --backend wayback --targets example.com `
  --include-subdomains --max-results 50000 `
  --output Result\wayback.json --csv Result\wayback.csv
```

### Certificate Transparency discovery

```powershell
dork-search --backend crtsh --targets example.com `
  --output Result\ct.json --csv Result\ct.csv
```

`c99subdomain` remains a compatibility alias for CT discovery. It no longer emits
guessed subdomains or claims that candidates were discovered.

### Wayback parameter inventory

```powershell
wayback-recon --targets example.com --include-subdomains --max-urls 50000 `
  --output Result\recon.json --csv Result\recon.csv
```

Token-like query values are redacted. `--include-sensitive-values` disables this
protection and should be used only with controlled artifact storage.

### Active HTTP metadata probe

```powershell
http-metadata-probe --targets example.com --acknowledge-scope `
  --test-cors --output Result\probe.json --csv Result\probe.csv
```

This command is active: it sends GET requests but streams only headers and never
downloads response bodies. It blocks private, loopback, link-local, and reserved
addresses by default. Each redirect is DNS-checked and must remain within the
authorized hostname scope. Use `--allow-private` only in an owned lab.

## API keys

Google and DNSDumpster accept `--api-key`. To keep secrets out of shell history and
process listings, prefer `DORK_SEARCHER_API_KEY`. Google CSE IDs can be supplied with
`GOOGLE_CSE_ID`. Interactive prompts hide API keys.

## Artifacts and operational safety

Interactive results default to `Desktop\Dork_Searcher_Results` so the files are easy
to find. JSON is the canonical evidence format. CSV is sanitized for safe opening in
spreadsheet applications. Writes are atomic, so an interrupted run does not partially
overwrite a prior report.

The application resolves the actual Windows Desktop location, including redirected
or localized folders, and verifies that it is writable. If unavailable, output moves
to `%LOCALAPPDATA%\Dork_Searcher\Results`. Set `DORK_SEARCHER_OUTPUT_DIR` to select a
different default location.

Backends that depend on third-party HTML can change or rate-limit requests. Their
failures are reported explicitly; an empty successful result is not silently
substituted for a transport error.

## Development

```powershell
python -m pytest
python -m ruff check src tests
python -m mypy src
```

On Windows, `scripts\verify.ps1` runs all validation gates. The GitHub Actions
workflow tests Python 3.10, 3.12, and 3.13 and builds distribution artifacts.

The test suite uses mocked backend responses and does not contact third-party or
target systems.

# Dork Searcher 2.0

[![CI](https://github.com/JamesHiraldo/Dork_Searcher/actions/workflows/ci.yml/badge.svg)](https://github.com/JamesHiraldo/Dork_Searcher/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Dork Searcher is a scope-aware reconnaissance toolkit for authorized bug bounty,
penetration-testing, and asset-inventory work. It combines search-engine dorks,
Wayback Machine collection and parsing, Certificate Transparency discovery,
DNSDumpster, structural hostname correlation, and bounded HTTP header/CORS checks in
one interactive Windows application and a set of scriptable Python commands.

> [!WARNING]
> Use Dork Searcher only on assets you own or are explicitly authorized to assess.
> Bug bounty scope, rate limits, and platform rules always take precedence.

## Contents

- [Highlights](#highlights)
- [Interactive menu](#interactive-menu)
- [Run the Windows executable](#run-the-windows-executable)
- [Install from source](#install-from-source)
- [Output files](#output-files)
- [Custom dorks](#custom-dorks)
- [Command-line tools and flags](#command-line-tools-and-flags)
- [Usage examples](#usage-examples)
- [API keys](#api-keys)
- [How results are represented](#how-results-are-represented)
- [Troubleshooting](#troubleshooting)
- [Development and packaging](#development-and-packaging)
- [Security and license](#security-and-license)

## Highlights

- Google Programmable Search with API-side site restriction and pagination
- DuckDuckGo-first HTML search with Dogpile and optional Brave fallbacks
- Direct Dogpile mode for backend diagnostics
- Persistent custom dorks that remain tied to the selected target
- Wayback CDX collection with retry handling and resumption-key pagination
- Archived endpoint and parameter inventory with sensitive-value redaction
- Passive subdomain enumeration combining `crt.sh` and Cert Spotter observations
- DNSDumpster discovery using its API
- Structural hostname cross-referencing instead of unsafe substring matching
- Active HTTP security-header and CORS analysis with redirect and private-IP controls
- Atomic JSON/CSV writes and spreadsheet formula-injection protection
- Colorized interactive UI with automatic plain-text output when redirected
- Standalone Windows executable plus installable Python entry points

## Interactive menu

The executable and the `dork_searcher` command open this menu:

```text
Dork_Search
----------------------------------------
1. Google (API Req)
2. DuckDuckGo Search
3. Dogpile Direct Search

Wayback / Parser
----------------------------------------
4. Wayback CDX URL Collection
5. Wayback Recon + Parameter Inventory

Sub-Domain Search
----------------------------------------
6. Certificate Transparency Discovery
7. DNSDumpster Discovery (API Req)

CORS Check
----------------------------------------
8. Active HTTP Header/CORS Probe

Other
----------------------------------------
9. Cross-Reference Existing Results
10. View Dork Templates
0. Exit
```

Google and DNSDumpster require API credentials. DuckDuckGo, Dogpile, Wayback, and
Certificate Transparency do not require an API key.

## Run the Windows executable

The standalone executable is interactive. It does not accept the command-line flags
described later in this README; those flags belong to the installed Python commands.

### Command Prompt (CMD)

Open Command Prompt, change to the directory containing the executable, and run it:

```cmd
cd /d "C:\path\to\Dork_Searcher"
dork_searcher-2.0.0.exe
```

For example, if it is on your Desktop:

```cmd
cd /d "%USERPROFILE%\Desktop"
dork_searcher-2.0.0.exe
```

### PowerShell

```powershell
Set-Location "C:\path\to\Dork_Searcher"
.\dork_searcher-2.0.0.exe
```

### Verify the download

Compare the executable hash with the value published for the release:

```powershell
Get-FileHash .\dork_searcher-2.0.0.exe -Algorithm SHA256
```

The restored 2.0.0 executable currently has this SHA-256 value:

```text
5DEF0AB48F29A8D63F5A75B24E44F18229A8590E3E50F8825618F35147217385
```

## Install from source

Python 3.10 through 3.13 is supported.

### Windows PowerShell

```powershell
git clone https://github.com/JamesHiraldo/Dork_Searcher.git
Set-Location Dork_Searcher
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
dork_searcher
```

### Windows Command Prompt

```cmd
git clone https://github.com/JamesHiraldo/Dork_Searcher.git
cd /d Dork_Searcher
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e "."
dork_searcher
```

### Linux or macOS

```bash
git clone https://github.com/JamesHiraldo/Dork_Searcher.git
cd Dork_Searcher
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "."
dork_searcher
```

To install development tools, use `python -m pip install -e ".[dev]"`.

### Optional Brave browser fallback

DuckDuckGo falls back to Dogpile automatically. A final browser-rendered Brave
fallback can be enabled in a source installation:

```powershell
python -m pip install -e ".[browser]"
python -m playwright install chromium
```

Playwright and Chromium are intentionally not bundled in the base Windows executable.

## Output files

Interactive reports default to:

```text
Desktop\Dork_Searcher_Results
```

The program resolves the real Windows Desktop path, including localized or OneDrive-
redirected folders. If the Desktop is not writable, it falls back to:

```text
%LOCALAPPDATA%\Dork_Searcher\Results
```

Set a different default directory before launching if desired:

```cmd
set DORK_SEARCHER_OUTPUT_DIR=D:\BugBounty\Reports
dork_searcher-2.0.0.exe
```

JSON is the canonical evidence format. CSV is optional and sanitized for safer use in
spreadsheet applications. Artifact writes are atomic, so an interrupted operation
does not leave a partially written report.

> [!IMPORTANT]
> Reconnaissance output can contain sensitive URLs, parameters, hostnames, and program
> data. The repository ignores local result folders, but you are still responsible
> for storing and sharing reports according to the applicable program rules.

## Custom dorks

Select **10. View Dork Templates**, then:

- press `A` to add one or more custom dorks;
- press `R` to remove a custom dork;
- press `0` to return to the main menu.

Use `{t}` wherever the selected target should appear:

```text
site:{t} inurl:graphql
site:{t} (ext:env OR ext:ini) "DB_PASSWORD"
site:{t} intitle:"index of" (backup OR archive)
```

If a custom dork has no site restriction, Dork Searcher automatically wraps it with
`site:{t}`. Custom templates are de-duplicated, persisted in
`custom_dorks.txt` inside the results directory, and included in interactive Google,
DuckDuckGo, and Dogpile searches.

## Command-line tools and flags

Installing the Python package provides four entry points:

| Command | Purpose |
|---|---|
| `dork_searcher` | Open the interactive menu; no command-line flags |
| `dork-search` | Run search, archive, CT, or DNS discovery non-interactively |
| `wayback-recon` | Build a Wayback endpoint and parameter inventory |
| `http-metadata-probe` | Run bounded active header and CORS checks |

Use `<command> --help` to view the parser-generated reference for the installed
version.

### `dork-search`

```text
dork-search --backend BACKEND --targets DOMAIN [DOMAIN ...] --output FILE [options]
```

| Flag | Required | Description |
|---|---:|---|
| `--backend` | Yes | `google`, `wayback`, `duckduckgo`, `dogpile`, `dnsdumpster`, `crtsh`, or the legacy `c99subdomain` alias |
| `--targets` | Yes | One or more authorized domain names |
| `--output` | Yes | JSON output path |
| `--csv` | No | Optional CSV output path |
| `--api-key` | Backend-specific | Google or DNSDumpster API key; environment variable preferred |
| `--cse-id` | Google only | Google Programmable Search Engine ID |
| `--rate` | No | Seconds between requests; default `1.0` |
| `--max-results` | No | Per-query result ceiling |
| `--include-subdomains` | No | Include child hosts in Wayback collection |
| `--cross-ref` | No | Discovery JSON file to structurally cross-reference |
| `-h`, `--help` | No | Display command help |

### `wayback-recon`

```text
wayback-recon --targets DOMAIN [DOMAIN ...] --output FILE [options]
```

| Flag | Required | Description |
|---|---:|---|
| `--targets` | Yes | One or more authorized domain names |
| `--output` | Yes | JSON report path |
| `--csv` | No | Optional CSV report path |
| `--rate` | No | Seconds between CDX requests; default `0.5` |
| `--max-urls` | No | Maximum archived URLs per target; default `50000` |
| `--include-subdomains` | No | Include child hosts in CDX collection |
| `--include-sensitive-values` | No | Preserve token-like archived values instead of redacting them |
| `-h`, `--help` | No | Display command help |

### `http-metadata-probe`

This command is active: it sends GET requests but streams headers without consuming
response bodies. Either `--targets` or `--urls-file` is required.

```text
http-metadata-probe (--targets DOMAIN [...] | --urls-file FILE) \
  --output FILE --acknowledge-scope [options]
```

| Flag | Required | Description |
|---|---:|---|
| `--targets` | One input mode | Build common URLs for one or more domains |
| `--urls-file` | One input mode | Read one authorized absolute URL per line |
| `--output` | Yes | JSON report path |
| `--csv` | No | Optional CSV report path |
| `--concurrency` | No | Concurrent workers; default `8`, maximum `50` |
| `--timeout` | No | Per-request timeout in seconds; default `15` |
| `--max-redirects` | No | Redirect ceiling; default `5`, maximum `10` |
| `--test-cors` | No | Send an `Origin` header and classify the response |
| `--origin` | No | Origin value used by the CORS test; default `https://example.com` |
| `--allowed-target` | No | Override the hostname allowlist; repeat for every permitted initial and redirect host |
| `--allow-subdomains` | No | Permit redirects to child hosts of authorized targets |
| `--allow-private` | No | Permit private/local destinations for an owned lab |
| `--acknowledge-scope` | Yes | Confirm that all active targets are authorized |
| `-h`, `--help` | No | Display command help |

## Usage examples

### DuckDuckGo search

DuckDuckGo is the primary provider for this backend. Empty or blocked results fall
back to Dogpile and then to Brave when the optional browser dependencies are present.

```cmd
dork-search --backend duckduckgo --targets example.com --max-results 30 ^
  --output Result\duckduckgo.json --csv Result\duckduckgo.csv
```

### Google Programmable Search

Prefer environment variables so secrets are not placed directly in shell history:

```cmd
set DORK_SEARCHER_API_KEY=your-google-api-key
set GOOGLE_CSE_ID=your-search-engine-id
dork-search --backend google --targets example.com ^
  --output Result\google.json
```

### Wayback URL collection

```cmd
dork-search --backend wayback --targets example.com --include-subdomains ^
  --max-results 50000 --output Result\wayback.json --csv Result\wayback.csv
```

### Wayback parameter inventory

```cmd
wayback-recon --targets example.com --include-subdomains --max-urls 50000 ^
  --output Result\recon.json --csv Result\recon.csv
```

Potential token, credential, session, and key values are redacted by default. Only
use `--include-sensitive-values` when the artifact will be stored securely.

### Certificate Transparency subdomain discovery

```cmd
dork-search --backend crtsh --targets example.com --max-results 5000 ^
  --output Result\certificate-transparency.json
```

This workflow combines names observed by `crt.sh` and Cert Spotter. The apex domain
is excluded from subdomain results. `verified: false` means an item was observed in a
third-party source but was not actively DNS-verified; it does not mean the request
failed. A populated `error` field represents an actual backend failure.

### DNSDumpster discovery

```cmd
set DORK_SEARCHER_API_KEY=your-dnsdumpster-api-key
dork-search --backend dnsdumpster --targets example.com ^
  --output Result\dnsdumpster.json
```

### HTTP header and CORS probe

```cmd
http-metadata-probe --targets example.com --acknowledge-scope --test-cors ^
  --origin https://researcher.example --output Result\probe.json ^
  --csv Result\probe.csv
```

The active probe rejects private, loopback, link-local, and reserved destinations by
default. Redirects are checked before each request and must remain within the supplied
hostname scope. Use `--allowed-target` for a separate authorized redirect host,
`--allow-subdomains` for child hosts, and `--allow-private` only in an owned lab.

## API keys

### Google Programmable Search

Google mode requires both an API key and a Programmable Search Engine ID. Supply them
through interactive hidden input, flags, or these environment variables:

```cmd
set DORK_SEARCHER_API_KEY=your-google-api-key
set GOOGLE_CSE_ID=your-search-engine-id
```

### DNSDumpster

DNSDumpster mode requires an API key. The application sends it through the documented
`X-API-Key` request header. Use hidden interactive input or
`DORK_SEARCHER_API_KEY`.

Avoid committing credentials, embedding them in custom dorks, or publishing result
files containing private program data.

## How results are represented

Search artifacts use a consistent evidence model:

| Field | Meaning |
|---|---|
| `query` | Query or target that produced the row |
| `title` | Result title or observed hostname |
| `url` | Result URL |
| `snippet` | Provider context or evidence note |
| `source` | Backend that supplied the result |
| `result_type` | `observed`, `candidate`, or `error` |
| `verified` | Whether the tool actively verified the item; search observations normally remain `false` |
| `error` | Backend error message, otherwise empty |

- **Observed** means a third-party search index, archive, CT log, or DNS source
  reported the item. It does not prove that the asset is currently live.
- **Candidate** means a generated name that still requires separate validation.
- **Error** preserves a backend failure in the artifact for auditability. It is not
  equivalent to a successful search with zero findings.

## Troubleshooting

### The executable opens and immediately closes

Launch it from CMD so the window and any error message remain visible:

```cmd
cd /d "C:\path\to\Dork_Searcher"
dork_searcher-2.0.0.exe
```

### `Destination hostname is outside the authorized scope`

The active probe encountered a redirect to a different hostname. If that destination
is also authorized, use repeatable `--allowed-target` flags for both the original and
redirect hostnames in command-line mode, or enable the appropriate child-subdomain
redirect option in the interactive workflow.

### `Result` or output path access is denied

Interactive output normally goes to `Desktop\Dork_Searcher_Results`. If Windows
blocks that location, the application uses `%LOCALAPPDATA%\Dork_Searcher\Results`.
You can also set `DORK_SEARCHER_OUTPUT_DIR` to a directory you control.

### A search backend returns an error row

HTML-based providers can change markup, rate-limit automated requests, or return a
challenge page. Increase the delay, retry later, and inspect the row's `source` and
`error` fields. DuckDuckGo mode automatically attempts its fallback chain.

### Certificate Transparency returns few results

CT logs only contain names present on public certificates. A small or empty result is
not proof that no subdomains exist. DNSDumpster, Wayback, search dorks, and authorized
asset data can provide complementary coverage.

### Disable terminal colors

Set the standard `NO_COLOR` variable before launching:

```cmd
set NO_COLOR=1
dork_searcher-2.0.0.exe
```

## Development and packaging

Install the development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run the complete validation suite:

```powershell
python -m pytest -q
python -m ruff check src tests
python -m mypy src
```

On Windows, the repository also provides:

```powershell
.\scripts\verify.ps1
```

Build Python distributions:

```powershell
python -m pip install build
python -m build
```

Build the standalone Windows executable:

```powershell
python -m pip install -e ".[build]"
python -m PyInstaller --clean --noconfirm config\dork_searcher.spec
```

CI validates Python 3.10, 3.12, and 3.13 on Windows and publishes build artifacts for
each workflow run.

## Security and license

Report security issues through GitHub's private Security Advisory flow. Do not place
API keys, authentication material, private bug bounty findings, or sensitive target
URLs in a public issue. See [SECURITY.md](SECURITY.md) for the full policy.

Dork Searcher is available under the [MIT License](LICENSE).

Additional documentation:

- [Complete technical guide](docs/README.md)
- [Windows executable guide](docs/WINDOWS_EXE_GUIDE.md)
- [Installation guide](docs/INSTALL.md)
- [Wayback recon notes](docs/README_RECON.md)

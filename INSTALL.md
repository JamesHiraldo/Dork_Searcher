# Installation & Usage Guide

This guide is updated for the current menu and workflow.

## Prerequisites

- Python 3.8+
- Internet access for external APIs (Google CSE, Wayback, DuckDuckGo, etc.)

## Recommended Install (Virtual Environment)

### Windows (PowerShell)

```powershell
cd "path\to\dork_searcher"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Run:

```powershell
dork_searcher
```

### Linux / macOS

```bash
cd /path/to/dork_searcher
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Run:

```bash
dork_searcher
```

## Quick Run Without Install

From the project folder:

```bash
python dork_searcher.py
```

## Current Menu Options

1. Google CSE Search
2. Wayback Machine (CDX) Search
3. DuckDuckGo Search
4. C99.nl Subdomain Finder
5. Cross-Reference Results
6. Recon Pipeline (Wayback + Params)
7. Passive Probe (Headers/CSP/CORS)
8. View Dork Templates
0. Exit

## API Keys

### Google CSE

Required only for option 1 and Google-based cross-reference mode in option 5.

- Create engine: https://programmablesearchengine.google.com/
- Create API key in Google Cloud
- Provide API Key and CSE ID when prompted

### Key Handling

- In the interactive menu, API key input is hidden.
- The app redacts secrets from error messages.
- Avoid passing `--api-key` directly in shell history if you want maximum key privacy.

## Output Files

- JSON output is always supported.
- CSV output is optional for most menu options.
- Files are written to the current working directory unless you provide an absolute path.

## Troubleshooting

### `ModuleNotFoundError` (for example: `requests` or `httpx`)

```bash
pip install -r requirements.txt
```

If using a virtual environment, make sure it is activated first.

### `dork_searcher` command not found

Install entry point in current environment:

```bash
pip install -e .
```

Or run directly with:

```bash
python dork_searcher.py
```

### API / network errors

- Check internet connectivity
- Increase rate delay in menu prompts
- Verify Google API key and CSE ID for Google mode

## Optional Windows Batch Wrapper

If needed, use the included `dork_searcher.bat` from this project, or create your own wrapper in a folder on PATH.

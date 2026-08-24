# Quick start

From a downloaded or cloned Windows project folder, use the launcher. It prefers the
packaged executable and does not depend on a global Python installation:

```cmd
dork_searcher.bat
```

For source development:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
dork_searcher
```

Useful non-interactive commands:

```powershell
dork-search --backend crtsh --targets example.com --output Result\ct.json
dork-search --backend wayback --targets example.com --max-results 50000 --output Result\urls.json
wayback-recon --targets example.com --output Result\recon.json
http-metadata-probe --targets example.com --acknowledge-scope --output Result\probe.json
```

Only assess explicitly authorized assets. The HTTP metadata probe is active even
though it does not download response bodies.

See [docs/README.md](docs/README.md) for the trust model and full command reference.

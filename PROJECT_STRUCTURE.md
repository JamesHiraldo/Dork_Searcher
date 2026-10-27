# Project structure

- `src/cli.py`: Rich dashboard and CLI subcommands
- `src/discovery.py`: Wayback, CT, RapidDNS, CompleteDNS, and import adapters
- `src/wayback.py`: bounded CDX pagination and capture metadata
- `src/inventory.py`: SQLite evidence/history, trends and exports
- `src/availability.py`: bounded asynchronous DNS and HTTP sampling
- `src/workbench.py`: offline URL query language and external research links
- `src/workspace.py`: writable output directory selection
- `src/http_transport.py`: streamed JSON size limits and bounded retry delays
- `src/diagnostics.py`: local runtime, TLS, DNS, database and credential-presence checks
- `src/artifacts.py`: atomic JSON/text and spreadsheet-safe CSV
- `src/recon_pipeline.py`: retained parameter inventory command
- `src/passive_probe.py`: retained HTTP-header/CORS command
- `src/scope.py`: hostname and URL parsing helpers
- `src/searcher.py`: legacy command alias and hostname correlation helper
- `src/app_entry.py`: Windows executable entry point
- `Wayback_Atlas_App/`: current EXE, wheel and checksums
- `scripts/`: verification and packaging
- `tests/`: mocked provider, parser, history, probe and CLI tests

## Supporting files

- `wayback_atlas.bat`: Windows launcher; prefers the bundled EXE.
- `dork_searcher.bat`, `src/dork_searcher.py`: retained compatibility entry points.
- `config/dork_searcher.spec`: current Atlas PyInstaller build specification; historical filename retained.
- `pyproject.toml`: dependencies, installed commands, tool configuration and package metadata.
- `.github/workflows/ci.yml`: Windows Python test matrix and wheel/source-distribution packaging.
- `scripts/demo.py`: synthetic, offline dashboard preview and sample exports.
- `scripts/provider_smoke.py`: explicit live example.com provider/DNS/HTTP checks.
- `scripts/release_smoke.py`: offline EXE checks with disposable synthetic data.
- `docs/`: installation, operations, retained commands, development and roadmap.

## Generated files versus research data

`.venv-atlas/` is the active local development environment. `*.egg-info/`, `build/`,
`dist/`, test/type/lint caches and `__pycache__/` are generated and can return after
installation, testing or packaging. Do not remove an environment used by a running
process. The obsolete `.venv/` and archived 2.0 release folders were removed.

`Result/` is retained for compatibility and existing research. Normal Atlas runs
use the selected output directory, usually Desktop/Wayback_Atlas_Results, not
the repository. Preserve research data separately from disposable test fixtures.
See [operations](docs/OPERATIONS.md) before backing up or moving an inventory.

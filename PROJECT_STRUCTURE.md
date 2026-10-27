# Project structure

- `src/cli.py`: Rich dashboard and CLI subcommands
- `src/discovery.py`: Wayback, CT, RapidDNS, CompleteDNS, and import adapters
- `src/wayback.py`: bounded CDX pagination and capture metadata
- `src/inventory.py`: SQLite evidence/history, trends and exports
- `src/availability.py`: bounded asynchronous DNS and HTTP sampling
- `src/workbench.py`: offline URL query language and external research links
- `src/workspace.py`: writable output directory selection
- `src/artifacts.py`: atomic JSON/text and spreadsheet-safe CSV
- `src/recon_pipeline.py`: retained parameter inventory command
- `src/passive_probe.py`: retained HTTP-header/CORS command
- `src/scope.py`: hostname and URL parsing helpers
- `src/searcher.py`: legacy command alias and hostname correlation helper
- `src/app_entry.py`: Windows executable entry point
- `Wayback_Atlas_App/`: current EXE, wheel and checksums
- `legacy/Dork_Searcher_App/`: recoverable previous binary release
- `scripts/`: verification and packaging
- `tests/`: mocked provider, parser, history, probe and CLI tests

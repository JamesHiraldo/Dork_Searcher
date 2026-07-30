# Project structure

```text
dork_searcher/
|-- src/
|   |-- artifacts.py       # Atomic and spreadsheet-safe artifact writers
|   |-- scope.py           # DNS/URL normalization and scope enforcement
|   |-- wayback.py         # Shared retrying, paginated CDX client
|   |-- searcher.py        # Search, CT, DNS, and cross-reference backends
|   |-- recon_pipeline.py  # Wayback endpoint and parameter reporting
|   |-- passive_probe.py   # Bounded active HTTP metadata probe
|   `-- cli.py             # Interactive interface
|-- tests/                 # Mocked, network-free automated tests
|-- scripts/               # Reproducible validation and Windows build scripts
|-- .github/workflows/     # Multi-version CI and package build
|-- config/
|   |-- requirements.txt
|   `-- dork_searcher.spec
|-- docs/
|-- Result/                # Ignored local evidence artifacts
|-- pyproject.toml         # Canonical packaging and tool configuration
`-- LICENSE
```

There is one canonical package configuration at the repository root. Build output,
virtual environments, IDE state, bytecode, and reconnaissance artifacts are ignored.

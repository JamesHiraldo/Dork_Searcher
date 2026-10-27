# Development and release verification

Run commands from the repository root. Python 3.10+ is declared; the current local
EXE was built with Python 3.12 on Windows. The configured CI matrix is Windows
3.10/3.12/3.13. Configuration is not a guarantee that every environment was tested.

## Install and test the source

```powershell
python -m venv .venv-atlas
.\.venv-atlas\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv-atlas\Scripts\python.exe -m src.cli --help
.\scripts\verify.ps1 -PythonCommand ".\.venv-atlas\Scripts\python.exe"
```

The verification script runs dependency consistency, mocked pytest tests, Ruff and
MyPy. It uses `.pytest-atlas-verify` and `.pytest-atlas-cache` rather than older
potentially locked pytest folders. MyPy/Ruff caches and Python bytecode may reappear.
No live target requests are required by this test suite. Tests are not a complete
security audit or a substitute for release/runtime checks.

For source debugging use `python -m src.cli`. The `.bat` launcher prefers the EXE
and therefore will not reflect unbuilt source edits. A wheel installation is also
separate from the source checkout unless installed in editable mode.

## Offline UI demonstration

```powershell
.\.venv-atlas\Scripts\python.exe scripts/demo.py --output .pytest-atlas-demo
```

This writes a synthetic example.com SQLite inventory, reports and
`terminal-preview.svg` in the demo directory. It performs no network requests.
Rerunning against the same directory adds samples; use a fresh dedicated demo
directory for a clean sequence. Do not use a real investigation directory.

## Optional live provider smoke test

```powershell
.\.venv-atlas\Scripts\python.exe scripts/provider_smoke.py
```

This makes small Wayback/crt.sh/Cert Spotter requests for example.com and performs
DNS/HTTP checks of example.com. It is not offline and does not test paid providers.
Inspect the printed JSON `status`, `error`, counts and HTTP/DNS state: the script
prints provider failures but does not currently fail its process merely because a
provider returned an error. It is diagnostic output, not a strict release gate.

## Build Windows artifacts

```powershell
.\scripts\build_windows.ps1 -PythonCommand ".\.venv-atlas\Scripts\python.exe"
```

The script installs build requirements, builds the EXE with
`config/dork_searcher.spec`, builds the wheel, and writes SHA-256 sums. It replaces
same-named current artifacts in `Wayback_Atlas_App/`; preserve a needed release
before rebuilding. Normal build caches return under `build/`. The spec includes
the asynchronous DNS backend and applicable SSL runtime policy data without
disabling certificate validation. Dependency ranges mean builds are not guaranteed
byte-for-byte reproducible. There is currently no release-signing step.

## Release checklist

1. Run source verification and record Python/dependency versions and source revision.
2. Build the EXE/wheel and verify `SHA256SUMS.txt` against both output files.
3. Run the actual EXE's help, dashboard, import, inventory, dorks and export commands
   using a separate synthetic-data directory; check both CMD and PowerShell.
4. Test DNS/HTTPS with a small operator-approved target; verify packaged certificate
   data and DNS backend. Inspect nonzero exits and output even when source tests pass.
5. Install the wheel in a clean environment and check all installed entry points.
6. Test interruption, writable-path fallback and provider failures; preserve completed
   observations and do not turn failure into a false empty-success result.
7. Publish source, release notes and checksums together. Do not include test databases,
   provider keys or research results. Claim only the platforms actually tested.

Current CI builds wheel/source distributions but not the frozen EXE; adding that
gate is a [roadmap priority](ASSESSMENT_AND_ROADMAP.md). Documentation-only changes
do not require rebuilding executable code. The wheel's embedded README metadata
remains a build-time snapshot until the next wheel rebuild.

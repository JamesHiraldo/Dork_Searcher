# Installation

## Supported environment

- Python 3.10 through 3.13
- Windows, Linux, or macOS
- Internet access to the selected third-party APIs

## Source installation

```powershell
git clone https://github.com/Maydayx2/dork-searcher.git
cd dork-searcher
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
dork_searcher
```

For development, install `.[dev]`. For the optional browser fallback, install
`.[browser]` and then run `python -m playwright install chromium`.

## Build a Windows executable

```powershell
python -m pip install -e ".[build]"
python -m PyInstaller --clean --noconfirm config\dork_searcher.spec
```

Rebuild the executable for every release and publish a SHA-256 checksum. Playwright
browser binaries are intentionally not bundled by the base specification; the
DuckDuckGo-first path still has its built-in Dogpile fallback without them.

## Troubleshooting

- If `python` is not found, install Python 3.10+ and enable “Add Python to PATH.”
- Virtual environments are machine-specific. Delete and recreate a broken local
  environment rather than copying `.venv` between systems.
- A backend error row means the service failed or rate-limited the request; it is
  not equivalent to zero findings.
- Active probing requires `--acknowledge-scope` outside the interactive menu.

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

When using the repository on Windows, `dork_searcher.bat` prefers the packaged EXE.
If that artifact is absent, it checks `.venv` before global Python and refuses to run
source mode until the required packages are installed.

For development, install `.[dev]`. Playwright is installed as a core dependency and
prefers Microsoft Edge or Google Chrome. Run `python -m playwright install chromium`
only when neither browser is installed.

## Build a Windows executable

```powershell
python -m pip install -e ".[build]"
python -m PyInstaller --clean --noconfirm config\dork_searcher.spec
```

Rebuild the executable for every release and publish a SHA-256 checksum. The build
bundles Playwright's control runtime, uses the system-installed Edge browser for
rendered DuckDuckGo recovery, and retains Dogpile as the secondary provider.

## Troubleshooting

- If `python` is not found, install Python 3.10+ and enable “Add Python to PATH.”
- Virtual environments are machine-specific. Delete and recreate a broken local
  environment rather than copying `.venv` between systems.
- A backend error row means the service failed or rate-limited the request; it is
  not equivalent to zero findings.
- Dogpile can return HTTP 403 from its own CloudFront distribution. The tool checks
  both known result routes and reports that provider outage explicitly.
- Active probing requires `--acknowledge-scope` outside the interactive menu.

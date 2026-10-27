# Install Wayback Atlas

Windows users can run `wayback_atlas.bat` from the project root. It selects
`Wayback_Atlas_App/wayback_atlas.exe` before looking for Python.
Use `.\wayback_atlas.bat` in PowerShell. This path needs no Python installation.

Source installation (Python 3.10+, CMD, from the repository root):

```cmd
python -m venv .venv-atlas
.venv-atlas\Scripts\activate.bat
python -m pip install -e "."
wayback-atlas
```

PowerShell without activating an environment:

```powershell
python -m venv .venv-atlas
.\.venv-atlas\Scripts\python.exe -m pip install -e "."
.\.venv-atlas\Scripts\python.exe -m src.cli
```

Linux/macOS:

```sh
python3 -m venv .venv-atlas
. .venv-atlas/bin/activate
python -m pip install -e "."
wayback-atlas --help
```

Alternatively, install the supplied wheel in your chosen Python environment:

```cmd
python -m pip install Wayback_Atlas_App\wayback_atlas-3.0.0-py3-none-any.whl
wayback-atlas --help
```

Pip needs access to the declared dependencies unless they are already installed
or supplied by your package mirror. The wheel does not embed those dependencies.
When using a non-editable wheel, repository edits do not update the installed copy.

A copied virtual environment is not portable. Create a new one if its original
Python path is missing. Atlas requires requests, httpx, rich and dnspython,
installed automatically from pyproject.toml. It does not require Playwright.

For development use `.[dev]`; for packaging use `.[build]`.
The supported build script is `scripts/build_windows.ps1`.
The active local environment is `.venv-atlas`; the obsolete copied `.venv` was
removed during cleanup. Generated caches/build folders may reappear when testing.

API keys are optional and source-specific. In PowerShell use
`$env:RAPIDDNS_API_KEY = 'your-key'` or `$env:COMPLETEDNS_API_KEY = 'your-key'`;
in CMD use `set RAPIDDNS_API_KEY=your-key`. These examples affect the current
shell session. Do not put real keys in tracked files or screenshots.

Keep one output directory per investigation. See [operations](OPERATIONS.md) for
path precedence and why switching directories produces a separate inventory.

Full instructions: [README](../README.md).

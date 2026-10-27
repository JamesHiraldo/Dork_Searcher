# Install Wayback Atlas

Windows users can run `wayback_atlas.bat` from the project root. It selects
`Wayback_Atlas_App/wayback_atlas.exe` before looking for Python.

Source installation:

```cmd
python -m venv .venv-atlas
.venv-atlas\Scripts\activate.bat
python -m pip install -e "."
wayback-atlas
```

A copied virtual environment is not portable. Create a new one if its original
Python path is missing. Atlas requires requests, httpx, rich and dnspython,
installed automatically from pyproject.toml. It does not require Playwright.

For development use `.[dev]`; for packaging use `.[build]`.
The supported build script is `scripts/build_windows.ps1`.

Full instructions: [README](../README.md).

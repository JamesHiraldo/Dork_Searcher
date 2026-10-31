"""Persistent output paths, shared by the CLI and terminal dashboard."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def desktop_directory() -> Path:
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "Desktop")
            return Path(os.path.expandvars(str(value)))
        except OSError:
            pass
    return Path.home() / "Desktop"


def result_directory(explicit: str | None = None) -> Path:
    configured = (
        explicit
        or os.getenv("WAYBACK_RECON_OUTPUT_DIR")
        or os.getenv("WAYBACK_ATLAS_OUTPUT_DIR")
        or os.getenv("DORK_SEARCHER_OUTPUT_DIR")
    )
    if configured:
        candidates = [Path(configured).expanduser()]
    else:
        legacy = desktop_directory() / "Wayback_Atlas_Results"
        candidates = [legacy] if (legacy / "inventory.sqlite3").is_file() else []
        candidates.append(desktop_directory() / "Wayback_Recon_Results")
        local = os.getenv("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "WaybackRecon" / "Results")
        candidates.append(Path.home() / "Wayback_Recon_Results")
    errors = []
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path, prefix=".write-test-"):
                pass
            return path.resolve()
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    raise OSError("No writable output directory: " + "; ".join(errors))

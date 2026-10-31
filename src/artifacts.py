"""Safe, atomic artifact writers used by every command."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any


def atomic_write_text(path: str, content: str) -> None:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=str(destination.parent),
            prefix=destination.name + ".",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
            temporary.flush()
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def save_json(path: str, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _safe_csv_cell(value: Any) -> Any:
    """Prevent spreadsheet formula execution without altering JSON evidence."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def save_csv(path: str, fieldnames: Sequence[str], rows: Iterable[dict[str, Any]]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _safe_csv_cell(row.get(field, "")) for field in fieldnames})
    atomic_write_text(path, stream.getvalue())


def derived_csv_path(json_path: str) -> str:
    source = Path(json_path)
    candidate = source.with_suffix(".csv") if source.suffix else Path(str(source) + ".csv")
    if candidate.resolve() == source.resolve():
        candidate = Path(str(source) + ".csv")
    return str(candidate)


def ensure_distinct_paths(*paths: str | None) -> None:
    """Reject artifact configurations that would overwrite another format."""
    resolved: dict[Path, str] = {}
    for raw_path in paths:
        if not raw_path:
            continue
        path = Path(raw_path).expanduser().resolve()
        if path in resolved:
            raise ValueError(
                f"Artifact paths must be distinct: {raw_path!r} collides with {resolved[path]!r}"
            )
        resolved[path] = raw_path

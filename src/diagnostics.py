"""Local diagnostics only: never contact providers or print credential values."""

from __future__ import annotations

import importlib.metadata
import os
import platform
import sqlite3
import ssl
import sys
from pathlib import Path
from typing import Any

import dns.asyncbackend
import dns.resolver

from . import __version__


def diagnose(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {"check": "Atlas", "status": "ok", "detail": __version__},
        {
            "check": "Runtime",
            "status": "ok",
            "detail": f"Python {platform.python_version()} / "
            + ("packaged EXE" if getattr(sys, "frozen", False) else "source / installed Python"),
        },
        {"check": "Output folder", "status": "ok", "detail": str(directory)},
    ]
    for dependency in ("requests", "httpx", "rich", "dnspython"):
        try:
            version = importlib.metadata.version(dependency)
        except importlib.metadata.PackageNotFoundError:
            version = "loaded; package version metadata unavailable"
        rows.append({"check": dependency, "status": "ok", "detail": version})
    try:
        ssl.create_default_context()
        rows.append({"check": "TLS", "status": "ok", "detail": "Certificate context created"})
    except (OSError, ValueError) as exc:
        rows.append({"check": "TLS", "status": "error", "detail": type(exc).__name__})
    try:
        dns.asyncbackend.get_backend("asyncio")
        resolver = dns.resolver.Resolver()
        rows.append(
            {
                "check": "DNS",
                "status": "ok",
                "detail": f"Async backend ready; {len(resolver.nameservers)} resolver(s)",
            }
        )
    except Exception as exc:
        rows.append({"check": "DNS", "status": "error", "detail": type(exc).__name__})
    database = directory / "inventory.sqlite3"
    if database.exists():
        try:
            connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                valid = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            finally:
                connection.close()
            rows.append(
                {
                    "check": "Inventory",
                    "status": "ok" if valid else "error",
                    "detail": "Integrity check passed" if valid else "Integrity check failed",
                }
            )
        except sqlite3.Error as exc:
            rows.append({"check": "Inventory", "status": "error", "detail": type(exc).__name__})
    else:
        rows.append({"check": "Inventory", "status": "info", "detail": "Not created yet"})
    for key in ("RAPIDDNS_API_KEY", "COMPLETEDNS_API_KEY", "CERTSPOTTER_API_KEY"):
        rows.append(
            {
                "check": key,
                "status": "info",
                "detail": "configured (not tested)"
                if os.getenv(key)
                else "not configured (optional)",
            }
        )
    return rows

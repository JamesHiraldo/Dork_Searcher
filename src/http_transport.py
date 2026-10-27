"""Bounded JSON decoding shared by passive discovery providers."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests

MAX_RESPONSE_BYTES = 16 * 1024 * 1024


def read_json(response: requests.Response, max_bytes: int = MAX_RESPONSE_BYTES) -> Any:
    """Count decompressed bytes, including chunked replies; never buffer an unlimited body."""
    length = response.headers.get("Content-Length", "")
    if length.isdigit() and int(length) > max_bytes:
        raise ValueError("Provider response exceeds the 16 MiB limit; narrow the query")
    body = bytearray()
    deadline = time.monotonic() + 60
    for chunk in response.iter_content(chunk_size=65536):
        if time.monotonic() > deadline:
            raise ValueError("Provider response exceeded the download time budget")
        if len(body) + len(chunk) > max_bytes:
            raise ValueError("Provider response exceeds the 16 MiB limit; narrow the query")
        body.extend(chunk)
    try:
        return json.loads(body)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("Provider returned invalid JSON (possibly a challenge page)") from None


def retry_delay(value: str, fallback: float, maximum: float = 30) -> float:
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            seconds = fallback
    return max(0, min(seconds, maximum))

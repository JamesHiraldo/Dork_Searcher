"""Passive providers with explicit partial results and source provenance."""

from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import requests

from .recon_pipeline import redact_sensitive_url
from .scope import ScopeError, host_in_scope, normalize_hostname, parse_http_url
from .wayback import WaybackClient


@dataclass
class DiscoveryResult:
    source: str
    records: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "partial" if self.error and self.records else "error" if self.error else "ok"


def request_json(
    session: requests.Session, url: str, *, secrets: tuple[str, ...] = (), **kwargs: Any
) -> Any:
    """Bound transient retries and never expose credential-bearing request URLs."""
    for attempt in range(3):
        try:
            response = session.get(url, timeout=(10, 25), allow_redirects=False, **kwargs)
        except requests.RequestException as exc:
            if attempt < 2:
                time.sleep(0.5 * 2**attempt)
                continue
            raise ValueError(f"Provider transport failure: {type(exc).__name__}") from None
        if (response.status_code == 429 or response.status_code >= 500) and attempt < 2:
            delay = response.headers.get("Retry-After", "")
            time.sleep(min(float(delay), 30) if delay.isdigit() else 0.5 * 2**attempt)
            continue
        if not 200 <= response.status_code < 300:
            raise ValueError(f"Provider returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise ValueError("Provider returned a non-JSON page (possibly a challenge)") from None
        if isinstance(payload, dict) and (payload.get("error_type") or payload.get("error")):
            message = str(payload.get("error_type") or "provider_error")
            for secret in secrets:
                message = message.replace(secret, "[REDACTED]") if secret else message
            raise ValueError(f"Provider error: {message[:160]}")
        return payload
    raise ValueError("Provider retry budget exhausted")


def record(target: str, host: str, **extra: Any) -> dict[str, Any] | None:
    try:
        normalized = normalize_hostname(host.removeprefix("*."))
    except (ScopeError, ValueError):
        return None
    if not host_in_scope(normalized, target):
        return None
    return {"hostname": normalized, **extra}


def collect(
    target: str,
    source: str,
    *,
    limit: int = 5000,
    api_key: str = "",
    session: requests.Session | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    max_pages: int = 20,
) -> DiscoveryResult:
    target = normalize_hostname(target)
    if limit < 1 or max_pages < 1:
        raise ValueError("Limits must be positive")
    result = DiscoveryResult(source)
    client = session or requests.Session()
    seen: set[tuple[str, str, str]] = set()

    def add(host: str, **extra: Any) -> None:
        item = record(target, host, **extra)
        if item:
            key = (item["hostname"], str(item.get("url", "")), str(item.get("observed_at", "")))
            if key not in seen:
                seen.add(key)
                if len(result.records) < limit:
                    result.records.append(item)
                else:
                    result.truncated = True

    try:
        if source == "wayback":
            fetched = WaybackClient(session=client, timeout=25, retries=2).fetch(
                target,
                max_urls=limit,
                include_subdomains=True,
                from_date=from_date,
                to_date=to_date,
                max_pages=max_pages,
            )
            for capture in fetched.captures:
                url = capture.get("original", "")
                add(
                    urlsplit(url).hostname or "",
                    url=redact_sensitive_url(url),
                    observed_at=capture.get("timestamp", ""),
                    archive_status=capture.get("statuscode", ""),
                    mimetype=capture.get("mimetype", ""),
                )
            result.error, result.truncated = fetched.error, fetched.truncated
            result.metadata = {"pages": fetched.pages, "dates_are": "sampled_capture_dates"}
        elif source == "crtsh":
            data = request_json(
                client, "https://crt.sh/", params={"q": f"%.{target}", "output": "json"}
            )
            if not isinstance(data, list):
                raise ValueError("Unexpected crt.sh response schema")
            for cert in data:
                if isinstance(cert, dict):
                    for name in str(cert.get("name_value", "")).splitlines():
                        add(name, observed_at=str(cert.get("entry_timestamp", "")))
        elif source == "certspotter":
            after = None
            cursors: set[str] = set()
            for page in range(max_pages):
                params = {"domain": target, "include_subdomains": "true", "expand": "dns_names"}
                if after:
                    params["after"] = after
                data = request_json(
                    client, "https://api.certspotter.com/v1/issuances", params=params
                )
                if not isinstance(data, list):
                    raise ValueError("Unexpected Cert Spotter response schema")
                if not data:
                    break
                for cert in data:
                    if isinstance(cert, dict) and isinstance(cert.get("dns_names"), list):
                        for name in cert["dns_names"]:
                            if isinstance(name, str):
                                add(name, observed_at=str(cert.get("not_before", "")))
                after = str(data[-1].get("id", "")) if isinstance(data[-1], dict) else ""
                if not after or after in cursors:
                    raise ValueError("Cert Spotter pagination stalled; results are partial")
                cursors.add(after)
                if len(result.records) >= limit or page + 1 == max_pages:
                    result.truncated = True
                    break
                time.sleep(0.25)
        elif source == "rapiddns":
            if not api_key:
                raise ValueError("Set RAPIDDNS_API_KEY (Pro/Max API) or import a saved export")
            for page in range(1, max_pages + 1):
                payload = request_json(
                    client,
                    f"https://rapiddns.io/api/search/{quote(target, safe='')}",
                    headers={"X-API-KEY": api_key},
                    secrets=(api_key,),
                    params={"page": page, "pagesize": 100, "search_type": "subdomain"},
                )
                body = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(payload, dict) and payload.get("status", 200) not in (200, "ok"):
                    raise ValueError("RapidDNS reported an unsuccessful query")
                if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                    raise ValueError("Unexpected RapidDNS response schema")
                for row in body["data"]:
                    if isinstance(row, dict):
                        add(
                            str(row.get("subdomain", "")),
                            observed_at=str(row.get("timestamp") or row.get("date") or ""),
                            record_type=str(row.get("type", "")),
                            value=str(row.get("value", "")),
                        )
                if page * 100 >= int(body.get("total", 0)) or not body["data"]:
                    break
                if len(result.records) >= limit or page == max_pages:
                    result.truncated = True
                    break
                time.sleep(0.25)
        elif source == "completedns":
            if not api_key:
                raise ValueError("Set COMPLETEDNS_API_KEY for nameserver history")
            payload = request_json(
                client,
                f"https://api.completedns.com/v2/dns-history/{quote(target, safe='')}",
                params={"key": api_key},
                secrets=(api_key,),
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
                raise ValueError("Unexpected CompleteDNS response schema")
            # NS names belong to infrastructure providers, not automatically to the target.
            result.metadata = {
                key: payload.get(key)
                for key in ("domain", "drops", "changes", "years", "was_parked", "events")
            }
            add(target, evidence="nameserver_history")
        else:
            raise ValueError(f"Unknown source: {source}")
    except (ValueError, requests.RequestException) as exc:
        result.error = str(exc).replace(api_key, "[REDACTED]") if api_key else str(exc)
    finally:
        if session is None:
            client.close()
    return result


def import_records(path: str, target: str, limit: int = 50000) -> DiscoveryResult:
    """Accept text, CSV, JSON, RapidDNS JSON, or an Atlas export without executing content."""
    source = Path(path).expanduser()
    if source.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("Import exceeds 25 MiB; split it into smaller files")
    text = source.read_text(encoding="utf-8-sig")
    rows: Any
    if source.suffix.lower() == ".json":
        rows = json.loads(text)
        if isinstance(rows, dict):
            rows = rows.get("assets", rows.get("records", rows.get("data", [])))
        if isinstance(rows, dict):
            rows = rows.get("data", [])
        if not isinstance(rows, list):
            raise ValueError("JSON import must contain a list of hosts or records")
    elif source.suffix.lower() == ".csv":
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        rows = [
            line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")
        ]
    result = DiscoveryResult("import", metadata={"filename": source.name, "rejected": 0})
    seen = set()
    for row in rows:
        raw = (
            row
            if isinstance(row, str)
            else next(
                (
                    str(row[key])
                    for key in ("hostname", "subdomain", "domain", "url", "title")
                    if isinstance(row, dict) and row.get(key)
                ),
                "",
            )
        )
        extra: dict[str, Any] = {}
        url = (
            raw
            if isinstance(raw, str) and raw.startswith(("http://", "https://"))
            else (str(row.get("url", "")) if isinstance(row, dict) else "")
        )
        if url:
            try:
                validated, url_host = parse_http_url(url)
                if url_host != normalize_hostname(raw.removeprefix("*.")):
                    raise ValueError("URL and hostname refer to different hosts")
            except ValueError:
                result.metadata["rejected"] += 1
                continue
            extra["url"] = redact_sensitive_url(validated)
        if isinstance(row, dict):
            extra["observed_at"] = str(row.get("observed_at") or row.get("timestamp") or "")
        item = record(target, raw, **extra)
        if not item:
            result.metadata["rejected"] += 1
        elif (item["hostname"], item.get("url", "")) not in seen:
            seen.add((item["hostname"], item.get("url", "")))
            if len(result.records) < limit:
                result.records.append(item)
            else:
                result.truncated = True
    return result

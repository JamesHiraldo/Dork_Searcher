#!/usr/bin/env python3
# mypy: disable-error-code="no-redef"
"""Wayback reconnaissance pipeline with deterministic parameter analysis."""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

if __package__:
    from .artifacts import ensure_distinct_paths
    from .artifacts import save_csv as save_csv_artifact
    from .artifacts import save_json as save_json_artifact
    from .scope import ScopeError, normalize_targets
    from .wayback import WaybackClient, WaybackError
else:  # pragma: no cover
    from artifacts import ensure_distinct_paths  # type: ignore
    from artifacts import save_csv as save_csv_artifact  # type: ignore
    from artifacts import save_json as save_json_artifact
    from scope import ScopeError, normalize_targets  # type: ignore
    from wayback import WaybackClient, WaybackError  # type: ignore


RATE = 0.5
DEFAULT_MAX_URLS = 50000
SENSITIVE_PARAMETER_RE = re.compile(
    r"(?:^|[_-])(auth|authorization|access|refresh|id)?token(?:$|[_-])|"
    r"(?:api|private|secret)[_-]?key|password|passwd|pwd|session|jwt|bearer|"
    r"signature|credential|oauth|sso|csrf|xsrf|code",
    re.IGNORECASE,
)


def fetch_wayback_urls(target: str, limit: int = DEFAULT_MAX_URLS) -> list[str]:
    """Compatibility wrapper that raises when CDX is unavailable."""
    result = WaybackClient().fetch(target, max_urls=limit)
    if result.error:
        raise WaybackError(result.error)
    return result.urls


def extract_params_from_url(url: str) -> dict[str, list[str]]:
    """Parse query parameters exactly once, retaining blanks and duplicates."""
    parsed = urlsplit(url)
    params: dict[str, list[str]] = {}
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        params.setdefault(key, []).append(value)
    return params


def _is_sensitive_parameter(name: str) -> bool:
    return bool(SENSITIVE_PARAMETER_RE.search(name))


def redact_sensitive_url(url: str, include_sensitive_values: bool = False) -> str:
    if include_sensitive_values:
        return url
    parsed = urlsplit(url)
    redacted_pairs = [
        (key, "[REDACTED]" if _is_sensitive_parameter(key) else value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(redacted_pairs, doseq=True), "")
    )


def summarize_targets(
    targets: list[str],
    rate: float = RATE,
    max_urls: int = DEFAULT_MAX_URLS,
    include_subdomains: bool = False,
    include_sensitive_values: bool = False,
    client: WaybackClient | None = None,
) -> dict[str, dict[str, Any]]:
    if rate < 0:
        raise ValueError("rate cannot be negative")
    if max_urls < 1:
        raise ValueError("max_urls must be greater than zero")

    normalized_targets = normalize_targets(targets)
    wayback = client or WaybackClient()
    report: dict[str, dict[str, Any]] = {}

    for target_index, target in enumerate(normalized_targets):
        print(f"[+] Fetching Wayback URLs for: {target}")
        fetched = wayback.fetch(
            target,
            max_urls=max_urls,
            include_subdomains=include_subdomains,
            rate=rate,
        )
        unique_urls = list(dict.fromkeys(fetched.urls))

        parameter_values: dict[str, set[str]] = {}
        parameter_occurrences: dict[str, int] = {}
        endpoints: set[str] = set()
        safe_urls: list[str] = []

        for url in unique_urls:
            parsed = urlsplit(url)
            endpoints.add(parsed.path or "/")
            safe_urls.append(redact_sensitive_url(url, include_sensitive_values))
            for key, url_values in extract_params_from_url(url).items():
                parameter_occurrences[key] = parameter_occurrences.get(key, 0) + len(url_values)
                parameter_values.setdefault(key, set()).update(url_values)

        parameters: dict[str, dict[str, Any]] = {}
        for key in sorted(parameter_values):
            unique_values = parameter_values[key]
            sensitive = _is_sensitive_parameter(key)
            examples = (
                ["[REDACTED]"]
                if sensitive and not include_sensitive_values
                else sorted(unique_values)[:10]
            )
            parameters[key] = {
                "occurrences": parameter_occurrences[key],
                "unique_value_count": len(unique_values),
                "sensitive": sensitive,
                "examples": examples,
            }

        report[target] = {
            "target": target,
            "status": "error" if fetched.error else "ok",
            "error": fetched.error,
            "pages_fetched": fetched.pages,
            "truncated": fetched.truncated,
            "includes_subdomains": include_subdomains,
            "sensitive_values_included": include_sensitive_values,
            "total_historical_urls": len(unique_urls),
            "unique_endpoints": len(endpoints),
            "endpoints_sample": sorted(endpoints)[:50],
            "parameters": parameters,
            "urls": safe_urls,
        }
        print(
            "  -> {} URL(s), {} endpoint(s), status={}".format(
                len(unique_urls), len(endpoints), report[target]["status"]
            )
        )
        if target_index + 1 < len(normalized_targets) and rate:
            time.sleep(rate)

    return report


def save_json(path: str, data: dict[str, dict[str, Any]]) -> None:
    save_json_artifact(path, data)


def save_csv(path: str, report: dict[str, dict[str, Any]]) -> None:
    fields = ["target", "url", "path", "params", "status", "error"]
    rows: list[dict[str, Any]] = []
    for target, data in report.items():
        urls = data.get("urls", [])
        if not urls and data.get("error"):
            rows.append(
                {
                    "target": target,
                    "url": "",
                    "path": "",
                    "params": "",
                    "status": data.get("status", "error"),
                    "error": data.get("error", ""),
                }
            )
        for url in urls:
            parsed = urlsplit(url)
            rows.append(
                {
                    "target": target,
                    "url": url,
                    "path": parsed.path or "/",
                    "params": parsed.query,
                    "status": data.get("status", "ok"),
                    "error": data.get("error", ""),
                }
            )
    save_csv_artifact(path, fields, rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Authorized Wayback reconnaissance pipeline")
    parser.add_argument("--targets", nargs="+", required=True)
    parser.add_argument("--output", required=True, help="JSON output path")
    parser.add_argument("--csv", help="Optional CSV path")
    parser.add_argument("--rate", type=float, default=RATE, help="Seconds between CDX requests")
    parser.add_argument("--max-urls", type=int, default=DEFAULT_MAX_URLS)
    parser.add_argument("--include-subdomains", action="store_true")
    parser.add_argument(
        "--include-sensitive-values",
        action="store_true",
        help="Write potential tokens/secrets from archived query strings (unsafe by default)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ensure_distinct_paths(args.output, args.csv)
        report = summarize_targets(
            args.targets,
            rate=args.rate,
            max_urls=args.max_urls,
            include_subdomains=args.include_subdomains,
            include_sensitive_values=args.include_sensitive_values,
        )
    except (ScopeError, ValueError) as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2

    save_json(args.output, report)
    print(f"Saved JSON report to: {args.output}")
    if args.csv:
        save_csv(args.csv, report)
        print(f"Saved CSV to: {args.csv}")
    return 1 if report and all(row.get("status") == "error" for row in report.values()) else 0


if __name__ == "__main__":
    sys.exit(main())

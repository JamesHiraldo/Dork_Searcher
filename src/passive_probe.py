#!/usr/bin/env python3
# mypy: disable-error-code="no-redef"
"""Bounded active HTTP metadata probe for explicitly authorized targets.

The probe issues GET requests but never consumes response bodies. Redirects are
handled manually and cannot leave the configured hostname scope.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx

if __package__:
    from .artifacts import ensure_distinct_paths
    from .artifacts import save_csv as save_csv_artifact
    from .artifacts import save_json as save_json_artifact
    from .scope import (
        ScopeError,
        ensure_public_url,
        host_in_scope,
        normalize_targets,
        parse_http_url,
    )
else:  # pragma: no cover
    from artifacts import ensure_distinct_paths  # type: ignore
    from artifacts import save_csv as save_csv_artifact  # type: ignore
    from artifacts import save_json as save_json_artifact
    from scope import (  # type: ignore
        ScopeError,
        ensure_public_url,
        host_in_scope,
        normalize_targets,
        parse_http_url,
    )


DEFAULT_CONCURRENCY = 8
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_REDIRECTS = 5
MAX_CONCURRENCY = 50
SEC_HEADERS = [
    "content-security-policy",
    "content-security-policy-report-only",
    "access-control-allow-origin",
    "access-control-allow-credentials",
    "access-control-allow-methods",
    "access-control-allow-headers",
    "vary",
    "x-frame-options",
    "x-content-type-options",
    "strict-transport-security",
    "referrer-policy",
    "permissions-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
    "cross-origin-embedder-policy",
]
COMMON_PATHS = ["/", "/robots.txt", "/.well-known/security.txt", "/favicon.ico"]
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def extract_params(url: str) -> dict[str, list[str]]:
    params: dict[str, list[str]] = {}
    for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        params.setdefault(key, []).append(value)
    return params


def analyze_cors(headers: dict[str, str], origin: str) -> dict[str, Any] | None:
    acao = headers.get("access-control-allow-origin")
    if acao is None:
        return None
    acao = acao.strip()
    credentials = headers.get("access-control-allow-credentials", "").strip().lower() == "true"
    varies_on_origin = "origin" in {
        value.strip().lower() for value in headers.get("vary", "").split(",") if value.strip()
    }

    reflected = acao == origin
    wildcard = acao == "*"
    if reflected and credentials:
        risk = "high"
        finding = "origin_reflection_with_credentials"
    elif reflected:
        risk = "medium"
        finding = "origin_reflection"
    elif wildcard and credentials:
        risk = "low"
        finding = "invalid_wildcard_credentials_combination"
    elif wildcard:
        risk = "informational"
        finding = "public_wildcard_policy"
    else:
        risk = "informational"
        finding = "fixed_allowed_origin"

    return {
        "access_control_allow_origin": acao,
        "access_control_allow_credentials": credentials,
        "varies_on_origin": varies_on_origin,
        "origin_reflected": reflected,
        "wildcard": wildcard,
        "risk": risk,
        "finding": finding,
        # Compatibility key, now true only for actual reflection.
        "vulnerable_reflection": reflected,
    }


def _host_allowed(host: str, allowed_targets: Iterable[str], allow_subdomains: bool) -> bool:
    return any(
        host_in_scope(host, target, include_subdomains=allow_subdomains)
        for target in allowed_targets
    )


async def _validated_destination(
    url: str,
    allowed_targets: Iterable[str],
    allow_subdomains: bool,
    allow_private: bool,
) -> tuple[str, str]:
    normalized, host = await asyncio.to_thread(
        ensure_public_url,
        url,
        allow_private,
        True,
    )
    if not _host_allowed(host, allowed_targets, allow_subdomains):
        raise ScopeError("Destination hostname is outside the authorized scope")
    return normalized, host


async def probe_url(
    client: httpx.AsyncClient,
    url: str,
    test_cors: bool = False,
    origin: str = "https://example.com",
    allowed_targets: Iterable[str] | None = None,
    allow_subdomains: bool = False,
    allow_private: bool = False,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "url": url,
        "final_url": None,
        "status": None,
        "headers": {},
        "params": extract_params(url),
        "final_params": {},
        "redirect_chain": [],
        "redirect_blocked": None,
        "cors_test": None,
        "active_request": True,
        "error": None,
    }
    try:
        normalized_input, input_host = parse_http_url(url)
        scope_targets = normalize_targets(allowed_targets or [input_host])
        current_url, _ = await _validated_destination(
            normalized_input,
            scope_targets,
            allow_subdomains,
            allow_private,
        )
        request_headers = {"Origin": origin} if test_cors else {}

        for redirect_index in range(max_redirects + 1):
            async with client.stream(
                "GET",
                current_url,
                headers=request_headers,
                follow_redirects=False,
            ) as response:
                result["status"] = response.status_code
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                result["headers"] = {
                    key: response_headers[key] for key in SEC_HEADERS if key in response_headers
                }
                result["final_url"] = str(response.url)
                result["final_params"] = extract_params(str(response.url))

                location = response_headers.get("location")
                if response.status_code not in REDIRECT_STATUSES or not location:
                    if test_cors:
                        result["cors_test"] = analyze_cors(response_headers, origin)
                    return result

                next_url = urljoin(str(response.url), location)
                if redirect_index >= max_redirects:
                    result["error"] = "Maximum redirect count exceeded"
                    return result
                try:
                    next_url, _ = await _validated_destination(
                        next_url,
                        scope_targets,
                        allow_subdomains,
                        allow_private,
                    )
                except ScopeError as exc:
                    result["redirect_blocked"] = {"url": next_url, "reason": str(exc)}
                    return result
                result["redirect_chain"].append(next_url)
                current_url = next_url
    except (httpx.RequestError, ScopeError, ValueError) as exc:
        result["error"] = str(exc)
    except Exception as exc:  # keeps one failed target from cancelling the batch
        result["error"] = f"Unexpected probe error: {exc}"
    return result


async def _worker(
    queue: asyncio.Queue,
    client: httpx.AsyncClient,
    results: list[dict[str, Any] | None],
    test_cors: bool,
    origin: str,
    allowed_targets: Iterable[str] | None,
    allow_subdomains: bool,
    allow_private: bool,
    max_redirects: int,
) -> None:
    while True:
        item = await queue.get()
        try:
            if item is None:
                return
            index, url = item
            results[index] = await probe_url(
                client,
                url,
                test_cors=test_cors,
                origin=origin,
                allowed_targets=allowed_targets,
                allow_subdomains=allow_subdomains,
                allow_private=allow_private,
                max_redirects=max_redirects,
            )
        finally:
            queue.task_done()


async def run_probes(
    urls: list[str],
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout: float = DEFAULT_TIMEOUT,
    test_cors: bool = False,
    origin: str = "https://example.com",
    allowed_targets: Iterable[str] | None = None,
    allow_subdomains: bool = False,
    allow_private: bool = False,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> list[dict[str, Any]]:
    if concurrency < 1 or concurrency > MAX_CONCURRENCY:
        raise ValueError(f"concurrency must be between 1 and {MAX_CONCURRENCY}")
    if timeout <= 0 or timeout > 120:
        raise ValueError("timeout must be greater than zero and at most 120 seconds")
    if max_redirects < 0 or max_redirects > 10:
        raise ValueError("max_redirects must be between 0 and 10")
    if not urls:
        return []

    worker_count = min(concurrency, len(urls))
    queue: asyncio.Queue = asyncio.Queue()
    for index, url in enumerate(urls):
        await queue.put((index, url))
    for _ in range(worker_count):
        await queue.put(None)

    results: list[dict[str, Any] | None] = [None] * len(urls)
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        limits=limits,
        follow_redirects=False,
        verify=True,
        headers={"User-Agent": "dork-searcher/2.0"},
    ) as client:
        tasks = [
            asyncio.create_task(
                _worker(
                    queue,
                    client,
                    results,
                    test_cors,
                    origin,
                    allowed_targets,
                    allow_subdomains,
                    allow_private,
                    max_redirects,
                )
            )
            for _ in range(worker_count)
        ]
        await queue.join()
        await asyncio.gather(*tasks)
    return [result for result in results if result is not None]


def build_target_urls_from_domains(domains: list[str]) -> list[str]:
    urls: list[str] = []
    for host in normalize_targets(domains):
        base = "https://" + host
        urls.extend(urljoin(base, path) for path in COMMON_PATHS)
    return urls


def save_json(path: str, data: list[dict[str, Any]]) -> None:
    save_json_artifact(path, data)


def save_csv(path: str, data: list[dict[str, Any]]) -> None:
    fields = [
        "url",
        "final_url",
        "status",
        "headers",
        "params",
        "final_params",
        "redirect_chain",
        "redirect_blocked",
        "cors_risk",
        "cors_finding",
        "error",
    ]
    rows: list[dict[str, Any]] = []
    for result in data:
        cors = result.get("cors_test") or {}
        rows.append(
            {
                "url": result.get("url"),
                "final_url": result.get("final_url"),
                "status": result.get("status"),
                "headers": json.dumps(result.get("headers", {}), sort_keys=True),
                "params": json.dumps(result.get("params", {}), sort_keys=True),
                "final_params": json.dumps(result.get("final_params", {}), sort_keys=True),
                "redirect_chain": json.dumps(result.get("redirect_chain", [])),
                "redirect_blocked": json.dumps(result.get("redirect_blocked")),
                "cors_risk": cors.get("risk", ""),
                "cors_finding": cors.get("finding", ""),
                "error": result.get("error", ""),
            }
        )
    save_csv_artifact(path, fields, rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Authorized active HTTP metadata probe")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--urls-file", help="File with one authorized URL per line")
    group.add_argument("--targets", nargs="+", help="Authorized domains to probe")
    parser.add_argument("--output", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--max-redirects", type=int, default=DEFAULT_MAX_REDIRECTS)
    parser.add_argument("--test-cors", action="store_true")
    parser.add_argument("--origin", default="https://example.com")
    parser.add_argument("--allowed-target", action="append", dest="allowed_targets")
    parser.add_argument("--allow-subdomains", action="store_true")
    parser.add_argument(
        "--allow-private",
        action="store_true",
        help="Permit private/local destinations (disabled by default; use only in owned labs)",
    )
    parser.add_argument(
        "--acknowledge-scope",
        action="store_true",
        help="Confirm that every target is explicitly authorized",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.acknowledge_scope:
        print("Refusing active requests without --acknowledge-scope", file=sys.stderr)
        return 2

    try:
        ensure_distinct_paths(args.output, args.csv)
        if args.urls_file:
            with open(args.urls_file, encoding="utf-8") as source:
                urls = [
                    line.strip()
                    for line in source
                    if line.strip() and not line.lstrip().startswith("#")
                ]
        else:
            urls = build_target_urls_from_domains(args.targets)
        if not urls:
            raise ValueError("No URLs to probe")
        allowed_targets = normalize_targets(args.allowed_targets) if args.allowed_targets else None
        results = asyncio.run(
            run_probes(
                urls,
                concurrency=args.concurrency,
                timeout=args.timeout,
                test_cors=args.test_cors,
                origin=args.origin,
                allowed_targets=allowed_targets,
                allow_subdomains=args.allow_subdomains,
                allow_private=args.allow_private,
                max_redirects=args.max_redirects,
            )
        )
    except (OSError, ScopeError, ValueError) as exc:
        print(f"Probe input error: {exc}", file=sys.stderr)
        return 2

    save_json(args.output, results)
    print(f"JSON saved to: {args.output}")
    if args.csv:
        save_csv(args.csv, results)
        print(f"CSV saved to: {args.csv}")
    return 1 if results and all(result.get("error") for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())

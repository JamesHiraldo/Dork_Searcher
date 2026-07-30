#!/usr/bin/env python3
# mypy: disable-error-code="no-redef"
"""Search and passive-discovery backends for authorized reconnaissance.

Every returned row identifies its source and result type.  ``observed`` means a
third-party data source reported the item; it does not claim the host is live.
``candidate`` means a name was generated and still requires DNS verification.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import re
import sys
import time
import urllib.parse
from collections.abc import Iterable
from html.parser import HTMLParser
from typing import Any

import requests

if __package__:
    from .artifacts import ensure_distinct_paths
    from .artifacts import save_csv as save_csv_artifact
    from .artifacts import save_json as save_json_artifact
    from .scope import (
        ScopeError,
        host_in_scope,
        match_url_to_scoped_hosts,
        normalize_hostname,
        normalize_targets,
        parse_http_url,
    )
    from .wayback import WaybackClient, WaybackError
else:  # pragma: no cover - supports ``python src/searcher.py``
    from artifacts import ensure_distinct_paths  # type: ignore
    from artifacts import save_csv as save_csv_artifact  # type: ignore
    from artifacts import save_json as save_json_artifact
    from scope import (  # type: ignore
        ScopeError,
        host_in_scope,
        match_url_to_scoped_hosts,
        normalize_hostname,
        normalize_targets,
        parse_http_url,
    )
    from wayback import WaybackClient, WaybackError  # type: ignore


DORK_TEMPLATES = [
    'site:{t} intitle:"index of"',
    "site:{t} inurl:admin",
    "site:{t} (inurl:login OR inurl:signin)",
    "site:{t} (inurl:api OR inurl:/api/)",
    "site:{t} (filetype:pdf OR filetype:doc OR filetype:docx OR filetype:xls)",
    'site:{t} ("password" OR "credentials" OR "private key")',
    "site:{t} (ext:env OR filetype:env OR filetype:ini)",
    'site:{t} ("flag.txt" OR "secret")',
    "site:{t} (inurl:upload OR inurl:files)",
    'site:{t} intitle:"index of" (backup OR old OR archive)',
    "site:{t} (inurl:staging OR inurl:dev OR inurl:test)",
]

RATE_LIMIT = 1.0
DEFAULT_SEARCH_RESULTS = 30
DEFAULT_WAYBACK_RESULTS = 50000
RESULT_FIELDS = [
    "query",
    "title",
    "url",
    "snippet",
    "source",
    "result_type",
    "verified",
    "error",
]


class SearchBackendError(RuntimeError):
    """Raised when a backend fails instead of returning a legitimate empty set."""


def redact_secrets(text: str, secrets: Iterable[str | None]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def safe_error_message(err: Exception, secrets: Iterable[str | None]) -> str:
    message = str(err).strip() or err.__class__.__name__
    return redact_secrets(message, secrets)


def _get_with_retries(
    session: requests.Session,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 0.5,
    **kwargs: Any,
) -> requests.Response:
    """Issue a GET with bounded retries for transport errors, 429, and 5xx."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(url, **kwargs)
            if response.status_code == 429 or 500 <= response.status_code < 600:
                retry_after = response.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else backoff * (2**attempt)
                if attempt + 1 < retries:
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(backoff * (2**attempt))
    raise SearchBackendError(f"GET {url} failed after {retries} attempts: {last_error}")


def _result(
    url: str | None,
    title: str | None,
    snippet: str | None,
    source: str,
    result_type: str = "observed",
    verified: bool = False,
) -> dict[str, Any]:
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "source": source,
        "result_type": result_type,
        "verified": verified,
    }


def _query_target(query: str) -> str | None:
    match = re.search(r"(?:^|\s)site:([^\s()]+)", query, re.IGNORECASE)
    if not match:
        return None
    try:
        return normalize_hostname(match.group(1))
    except ScopeError:
        return None


def build_queries(targets: list[str]) -> list[str]:
    queries: list[str] = []
    for target in normalize_targets(targets):
        queries.extend(template.format(t=target) for template in DORK_TEMPLATES)
    return queries


def _dedupe_results(items: Iterable[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or "").strip()
        key = url or "{}\0{}".format(item.get("title", ""), item.get("snippet", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output


def search_google_cse(
    query: str,
    api_key: str,
    cse_id: str,
    num: int = DEFAULT_SEARCH_RESULTS,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Search Google CSE with supported pagination (up to Google's 100-result cap)."""
    if num < 1:
        return []
    max_results = min(num, 100)
    client = session or requests.Session()
    endpoint = "https://www.googleapis.com/customsearch/v1"
    target = _query_target(query)
    collected: list[dict[str, Any]] = []

    for start in range(1, max_results + 1, 10):
        page_size = min(10, max_results - len(collected))
        params: dict[str, Any] = {
            "key": api_key,
            "cx": cse_id,
            "q": query,
            "num": page_size,
            "start": start,
        }
        if target:
            params.update({"siteSearch": target, "siteSearchFilter": "i"})
        response = _get_with_retries(client, endpoint, params=params, timeout=20)
        payload = response.json()
        page_items = payload.get("items", [])
        if not isinstance(page_items, list):
            raise SearchBackendError("Google returned an unexpected items document")
        for item in page_items:
            if not isinstance(item, dict):
                continue
            url = item.get("link")
            if target and url:
                try:
                    _, host = parse_http_url(url)
                except ScopeError:
                    continue
                if not host_in_scope(host, target, include_subdomains=True):
                    continue
            collected.append(_result(url, item.get("title"), item.get("snippet"), "google_cse"))
        if len(page_items) < page_size or len(collected) >= max_results:
            break
    return _dedupe_results(collected, max_results)


def search_wayback(
    target: str,
    max_results: int = DEFAULT_WAYBACK_RESULTS,
    include_subdomains: bool = False,
    client: WaybackClient | None = None,
) -> list[dict[str, Any]]:
    result = (client or WaybackClient()).fetch(
        target,
        max_urls=max_results,
        include_subdomains=include_subdomains,
    )
    if result.error:
        raise WaybackError(result.error)
    suffix = "; result limit reached" if result.truncated else ""
    return [
        _result(url, None, f"Internet Archive CDX{suffix}", "wayback_cdx") for url in result.urls
    ]


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[Any]) -> None:
        if tag.lower() != "a":
            return
        attributes = dict(attrs)
        classes = str(attributes.get("class", "")).split()
        if "result__a" in classes and attributes.get("href"):
            self._href = str(attributes["href"])
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.items.append({"href": self._href, "title": " ".join(self._text).strip()})
            self._href = None
            self._text = []


def _unwrap_duckduckgo_url(href: str) -> str:
    absolute = urllib.parse.urljoin("https://html.duckduckgo.com/", html.unescape(href))
    parsed = urllib.parse.urlsplit(absolute)
    redirect_target = urllib.parse.parse_qs(parsed.query).get("uddg")
    return redirect_target[0] if redirect_target else absolute


def _search_duckduckgo_html(
    query: str,
    num: int = DEFAULT_SEARCH_RESULTS,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Query and parse DuckDuckGo's accessible HTML result page directly."""
    if num < 1:
        return []
    client = session or requests.Session()
    response = _get_with_retries(
        client,
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0 (compatible; dork-searcher/2.0)"},
    )
    parser = _DuckDuckGoParser()
    parser.feed(response.text)
    target = _query_target(query)
    results: list[dict[str, Any]] = []
    for item in parser.items:
        url = _unwrap_duckduckgo_url(item["href"])
        try:
            _, host = parse_http_url(url)
        except ScopeError:
            continue
        if target and not host_in_scope(host, target, include_subdomains=True):
            continue
        results.append(_result(url, item["title"] or host, "", "duckduckgo_html"))
    if not parser.items and "no results" not in response.text.lower():
        raise SearchBackendError("DuckDuckGo returned an unrecognized or blocked HTML page")
    return _dedupe_results(results, num)


def search_brave_web(query: str, num: int = 10) -> list[dict[str, Any]]:
    """Render Brave Search in a headless browser as an optional fallback."""
    try:
        from playwright.async_api import async_playwright  # type: ignore[import-not-found]
    except ImportError:
        return []

    target = _query_target(query)

    async def _fetch_results() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent="Mozilla/5.0")
                search_url = "https://search.brave.com/search?source=web&q=" + urllib.parse.quote(
                    query
                )
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                page_text = await page.locator("body").inner_text()
                if "captcha" in page_text.lower() or "temporarily unavailable" in page_text.lower():
                    return []
                anchors = await page.locator("main a").evaluate_all(
                    "(elements) => elements.map((a) => ({href: a.href || '', "
                    "text: (a.textContent || '').replace(/\\s+/g, ' ').trim()}))"
                )
                for anchor in anchors:
                    url = str(anchor.get("href", "")).strip()
                    try:
                        _, host = parse_http_url(url)
                    except ScopeError:
                        continue
                    if "brave.com" in host:
                        continue
                    if target and not host_in_scope(host, target, include_subdomains=True):
                        continue
                    results.append(_result(url, anchor.get("text") or host, "", "brave_html"))
                return _dedupe_results(results, num)
            finally:
                await browser.close()

    try:
        return asyncio.run(_fetch_results())
    except Exception:
        return []


def search_dogpile(
    query: str,
    num: int = DEFAULT_SEARCH_RESULTS,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Query Dogpile directly as the secondary HTML search provider."""
    if num < 1:
        return []
    client = session or requests.Session()
    response = _get_with_retries(
        client,
        "https://www.dogpile.com/search",
        params={"q": query},
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0 (compatible; dork-searcher/2.0)"},
    )
    target = _query_target(query)
    results: list[dict[str, Any]] = []
    for match in re.finditer(
        r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
        response.text,
        re.IGNORECASE | re.DOTALL,
    ):
        url = html.unescape(match.group(1)).strip()
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(match.group(2)))).strip()
        try:
            _, host = parse_http_url(url)
        except ScopeError:
            continue
        if "dogpile.com" in host:
            continue
        if target and not host_in_scope(host, target, include_subdomains=True):
            continue
        results.append(_result(url, title or host, "", "dogpile_html"))
    return _dedupe_results(results, num)


def search_duckduckgo(
    query: str,
    num: int = DEFAULT_SEARCH_RESULTS,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Search DuckDuckGo first, then Dogpile, then optional browser-rendered Brave."""
    if num < 1:
        return []
    client = session or requests.Session()
    provider_errors: list[str] = []

    try:
        results = _search_duckduckgo_html(query, num=num, session=client)
        if results:
            return results
    except (requests.RequestException, SearchBackendError, ValueError) as exc:
        provider_errors.append(f"DuckDuckGo={exc}")

    try:
        results = search_dogpile(query, num=num, session=client)
        if results:
            return results
    except (requests.RequestException, SearchBackendError, ValueError) as exc:
        provider_errors.append(f"Dogpile={exc}")

    brave_results = search_brave_web(query, num=num)
    if brave_results:
        return brave_results
    if provider_errors:
        raise SearchBackendError("Search provider chain failed: " + "; ".join(provider_errors))
    return []


def search_dnsdumpster(
    target: str,
    api_key: str,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    normalized_target = normalize_hostname(target)
    client = session or requests.Session()
    response = _get_with_retries(
        client,
        f"https://api.dnsdumpster.com/domain/{normalized_target}",
        headers={"X-API-Key": api_key, "User-Agent": "dork-searcher/2.0"},
        timeout=30,
    )
    payload = response.json()
    if not isinstance(payload, dict):
        raise SearchBackendError("DNSDumpster returned an unexpected document")

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record_type in ("a", "cname", "mx", "ns"):
        entries = payload.get(record_type, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            raw_host = entry.get("host", "")
            try:
                host = normalize_hostname(raw_host)
            except ScopeError:
                continue
            if host in seen or not host_in_scope(host, normalized_target, include_subdomains=True):
                continue
            seen.add(host)
            ips = [
                str(ip["ip"])
                for ip in entry.get("ips", [])
                if isinstance(ip, dict) and ip.get("ip")
            ]
            snippet = f"DNSDumpster {record_type.upper()} record"
            if ips:
                snippet += " | IPs: {}".format(", ".join(ips[:3]))
            results.append(_result("https://" + host, host, snippet, "dnsdumpster"))
    return results


def search_certificate_transparency(
    target: str,
    session: requests.Session | None = None,
    max_results: int = 10000,
) -> list[dict[str, Any]]:
    """Discover CT names through crt.sh with a bounded Cert Spotter fallback."""
    normalized_target = normalize_hostname(target)
    client = session or requests.Session()
    if max_results < 1:
        return []
    hosts: set[str] = set()
    deadline = time.monotonic() + 60.0

    def add_names(names: Iterable[Any]) -> None:
        for raw_name in names:
            name = raw_name.strip().lower()
            if name.startswith("*."):
                name = name[2:]
            try:
                host = normalize_hostname(name)
            except ScopeError:
                continue
            if host_in_scope(host, normalized_target, include_subdomains=True):
                hosts.add(host)

    source = "crt.sh"
    crt_error: Exception | None = None
    try:
        response = _get_with_retries(
            client,
            "https://crt.sh/",
            retries=1,
            params={"q": f"%.{normalized_target}", "output": "json"},
            timeout=15,
            headers={"User-Agent": "dork-searcher/2.0"},
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise SearchBackendError("crt.sh returned an unexpected document")
        for certificate in payload:
            if isinstance(certificate, dict):
                add_names(str(certificate.get("name_value", "")).splitlines())
    except (requests.RequestException, SearchBackendError, ValueError) as exc:
        crt_error = exc

    if not hosts:
        source = "certspotter"
        after: str | None = None
        certspotter_error: Exception | None = None
        try:
            for _ in range(20):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SearchBackendError("Certificate Transparency request budget exceeded")
                params: dict[str, Any] = {
                    "domain": normalized_target,
                    "include_subdomains": "true",
                    "expand": "dns_names",
                }
                if after:
                    params["after"] = after
                response = _get_with_retries(
                    client,
                    "https://api.certspotter.com/v1/issuances",
                    retries=1,
                    params=params,
                    timeout=max(1.0, min(15.0, remaining)),
                    headers={"User-Agent": "dork-searcher/2.0"},
                )
                issuances = response.json()
                if not isinstance(issuances, list):
                    raise SearchBackendError("Cert Spotter returned an unexpected document")
                if not issuances:
                    break
                for issuance in issuances:
                    if not isinstance(issuance, dict):
                        continue
                    dns_names = issuance.get("dns_names", [])
                    if isinstance(dns_names, list):
                        add_names(dns_names)
                    if len(hosts) >= max_results:
                        break
                last = issuances[-1] if issuances else None
                next_after = (
                    str(last.get("id")) if isinstance(last, dict) and last.get("id") else None
                )
                if len(hosts) >= max_results or not next_after or next_after == after:
                    break
                after = next_after
        except (requests.RequestException, SearchBackendError, ValueError) as exc:
            certspotter_error = exc
        if not hosts and certspotter_error:
            raise SearchBackendError(
                f"Certificate Transparency sources failed: crt.sh={crt_error}; "
                f"Cert Spotter={certspotter_error}"
            ) from certspotter_error

    return [
        _result(
            "https://" + host,
            host,
            "Observed in a public Certificate Transparency log; DNS not yet verified",
            source,
        )
        for host in sorted(hosts)[:max_results]
    ]


def generate_subdomain_candidates(target: str, words: Iterable[str]) -> list[dict[str, Any]]:
    """Generate explicitly-labelled candidates without presenting them as discoveries."""
    normalized_target = normalize_hostname(target)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for word in words:
        label = word.strip().lower()
        try:
            host = normalize_hostname(f"{label}.{normalized_target}")
        except ScopeError:
            continue
        if host in seen:
            continue
        seen.add(host)
        candidates.append(
            _result(
                "https://" + host,
                host,
                "Generated candidate; requires DNS and authorization verification",
                "wordlist",
                result_type="candidate",
            )
        )
    return candidates


def search_c99_subdomains(target: str) -> list[dict[str, Any]]:
    """Compatibility alias: legacy C99 mode now performs honest CT discovery."""
    return search_certificate_transparency(target)


def cross_reference_with_subdomains(urls: list[str], subdomains: list[str]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen = set()
    for url in urls:
        for subdomain in match_url_to_scoped_hosts(url, subdomains):
            key = (url, subdomain)
            if key in seen:
                continue
            seen.add(key)
            matches.append({"url": url, "subdomain": subdomain, "match_type": "hostname_match"})
    return matches


def save_json(out_path: str, data: list[dict[str, Any]]) -> None:
    save_json_artifact(out_path, data)


def save_csv(out_path: str, data: list[dict[str, Any]]) -> None:
    save_csv_artifact(out_path, RESULT_FIELDS, data)


def _target_from_query(query: str) -> str:
    target = _query_target(query)
    if target:
        return target
    return normalize_hostname(query.split()[0])


def run_queries(
    queries: list[str],
    backend: str,
    api_key: str | None = None,
    cse_id: str | None = None,
    rate_limit: float = RATE_LIMIT,
    max_results: int | None = None,
    include_subdomains: bool = False,
) -> list[dict[str, Any]]:
    """Execute queries and retain explicit error rows for auditability."""
    if rate_limit < 0:
        raise ValueError("rate_limit cannot be negative")
    search_limit = max_results or (
        DEFAULT_WAYBACK_RESULTS if backend == "wayback" else DEFAULT_SEARCH_RESULTS
    )
    if search_limit < 1:
        raise ValueError("max_results must be greater than zero")

    results: list[dict[str, Any]] = []
    for index, query in enumerate(queries, 1):
        print(f"[{index}/{len(queries)}] Querying: {query}")
        try:
            if backend == "google":
                if not api_key or not cse_id:
                    raise ValueError("Google CSE requires an API key and CSE ID")
                items = search_google_cse(query, api_key, cse_id, num=search_limit)
            elif backend == "wayback":
                items = search_wayback(
                    _target_from_query(query),
                    max_results=search_limit,
                    include_subdomains=include_subdomains,
                )
            elif backend == "duckduckgo":
                items = search_duckduckgo(query, num=search_limit)
            elif backend == "dogpile":
                items = search_dogpile(query, num=search_limit)
            elif backend == "dnsdumpster":
                if not api_key:
                    raise ValueError("DNSDumpster requires an API key")
                items = search_dnsdumpster(_target_from_query(query), api_key)
            elif backend in ("c99subdomain", "crtsh"):
                items = search_certificate_transparency(
                    _target_from_query(query), max_results=search_limit
                )
            else:
                raise ValueError(f"Unsupported backend: {backend}")

            for item in items:
                row = {field: item.get(field, "") for field in RESULT_FIELDS}
                row["query"] = query
                results.append(row)
            print(f"  [+] {len(items)} result(s)")
        except Exception as exc:
            message = safe_error_message(exc, [api_key])
            print(f"  ! {message}", file=sys.stderr)
            results.append(
                {
                    "query": query,
                    "title": "",
                    "url": "",
                    "snippet": "",
                    "source": backend,
                    "result_type": "error",
                    "verified": False,
                    "error": message,
                }
            )
        if index < len(queries) and rate_limit:
            time.sleep(rate_limit)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Authorized passive reconnaissance searcher")
    parser.add_argument(
        "--backend",
        choices=[
            "google",
            "wayback",
            "duckduckgo",
            "dogpile",
            "dnsdumpster",
            "crtsh",
            "c99subdomain",
        ],
        required=True,
    )
    parser.add_argument("--api-key", help="Backend API key (prefer DORK_SEARCHER_API_KEY)")
    parser.add_argument("--cse-id", help="Google CSE ID (or GOOGLE_CSE_ID)")
    parser.add_argument("--targets", nargs="+", required=True, help="Authorized target domains")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--csv", help="Optional CSV path")
    parser.add_argument("--rate", type=float, default=RATE_LIMIT, help="Seconds between requests")
    parser.add_argument("--max-results", type=int, help="Per-query result ceiling")
    parser.add_argument(
        "--include-subdomains", action="store_true", help="Include child hosts in Wayback queries"
    )
    parser.add_argument("--cross-ref", help="JSON discovery file to structurally cross-reference")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ensure_distinct_paths(args.output, args.csv)
        targets = normalize_targets(args.targets)
    except (ScopeError, ValueError) as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2

    if args.backend in ("wayback", "dnsdumpster", "crtsh", "c99subdomain"):
        queries = [f"site:{target}" for target in targets]
    else:
        queries = build_queries(targets)

    api_key = args.api_key or os.environ.get("DORK_SEARCHER_API_KEY")
    cse_id = args.cse_id or os.environ.get("GOOGLE_CSE_ID")
    results = run_queries(
        queries,
        args.backend,
        api_key=api_key,
        cse_id=cse_id,
        rate_limit=args.rate,
        max_results=args.max_results,
        include_subdomains=args.include_subdomains,
    )

    if args.cross_ref:
        try:
            with open(args.cross_ref, encoding="utf-8") as source:
                discovery_rows = json.load(source)
            if not isinstance(discovery_rows, list):
                raise ValueError("Cross-reference JSON must contain a list")
            observed_hosts = [
                row.get("title") or row.get("url", "")
                for row in discovery_rows
                if isinstance(row, dict) and row.get("result_type") != "candidate"
            ]
            host_values: list[str] = []
            for value in observed_hosts:
                try:
                    if str(value).startswith(("http://", "https://")):
                        _, host = parse_http_url(str(value))
                    else:
                        host = normalize_hostname(str(value))
                    host_values.append(host)
                except ScopeError:
                    continue
            matches = cross_reference_with_subdomains(
                [str(row.get("url")) for row in results if row.get("url")],
                host_values,
            )
            results.extend(
                {
                    "query": "cross_reference",
                    "title": match["subdomain"],
                    "url": match["url"],
                    "snippet": match["match_type"],
                    "source": "cross_reference",
                    "result_type": "observed",
                    "verified": False,
                    "error": "",
                }
                for match in matches
            )
        except Exception as exc:
            print(f"Cross-reference failed: {exc}", file=sys.stderr)

    save_json(args.output, results)
    print(f"JSON results saved to: {args.output}")
    if args.csv:
        save_csv(args.csv, results)
        print(f"CSV results saved to: {args.csv}")

    return 1 if results and all(row.get("result_type") == "error" for row in results) else 0


if __name__ == "__main__":
    sys.exit(main())

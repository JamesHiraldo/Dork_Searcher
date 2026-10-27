"""Bounded DNS and root-page availability sampling; no page-body collection."""

from __future__ import annotations

import asyncio
import ipaddress
import ssl
import uuid
from collections.abc import Callable
from typing import Any

import dns.asyncresolver
import dns.exception
import dns.resolver
import httpx

from .inventory import utc_now


async def resolve_host(host: str, timeout: float = 5) -> dict[str, Any]:
    try:
        resolver = dns.asyncresolver.Resolver()
    except dns.exception.DNSException as exc:
        return {
            "dns_state": "unknown",
            "addresses": [],
            "cnames": [],
            "dns_errors": [type(exc).__name__],
        }
    resolver.lifetime = timeout
    addresses: set[str] = set()
    aliases: set[str] = set()
    errors = []
    nxdomain = False
    for kind in ("A", "AAAA"):
        try:
            answer = await resolver.resolve(host, kind, search=False, lifetime=timeout)
            addresses.update(str(value) for value in answer)
            canonical = str(answer.canonical_name).rstrip(".")
            if canonical != host:
                aliases.add(canonical)
        except dns.resolver.NXDOMAIN:
            nxdomain = True
        except dns.resolver.NoAnswer:
            pass
        except (dns.exception.DNSException, OSError) as exc:
            errors.append(type(exc).__name__)
    state = (
        "resolved"
        if addresses
        else "unknown"
        if errors
        else ("nxdomain" if nxdomain else "no_address")
    )
    return {
        "dns_state": state,
        "addresses": sorted(addresses),
        "cnames": sorted(aliases),
        "dns_errors": errors,
    }


async def probe_address(host: str, address: str, timeout: float) -> dict[str, Any]:
    """Pin the connection to the resolved address, retain Host/SNI, do not follow redirects."""
    endpoint = f"[{address}]" if ":" in address else address
    responses = []
    for scheme in ("https", "http"):
        item: dict[str, Any] = {"scheme": scheme, "address": address}
        try:
            async with (
                httpx.AsyncClient(timeout=timeout, trust_env=False) as client,
                client.stream(
                    "GET",
                    f"{scheme}://{endpoint}/",
                    headers={"Host": host, "User-Agent": "WaybackAtlas/3.0"},
                    extensions={"sni_hostname": host},
                    follow_redirects=False,
                ) as response,
            ):
                item["status"] = response.status_code
                # All HTTP responses, including 401/403/404/500, prove a responding service.
                try:
                    item["location_host"] = httpx.URL(response.headers.get("location", "")).host
                except httpx.InvalidURL:
                    item["location_host"] = "invalid Location header"
                responses.append(item)
                return {"state": "online", "http": responses}
        except (httpx.RequestError, ValueError, ssl.SSLError) as exc:
            item["error"] = type(exc).__name__
            if "CERTIFICATE_VERIFY_FAILED" in str(exc) or isinstance(exc, ssl.SSLError):
                item["tls_error"] = True
            responses.append(item)
    state = "tls_error" if any(r.get("tls_error") for r in responses) else "unreachable"
    return {"state": state, "http": responses}


async def check_host(
    host: str,
    *,
    http: bool = True,
    timeout: float = 5,
    wildcard_addresses: set[str] | None = None,
) -> dict[str, Any]:
    result = {"hostname": host, "checked_at": utc_now(), **await resolve_host(host, timeout)}
    result["wildcard_possible"] = bool(set(result["addresses"]) & (wildcard_addresses or set()))
    result["http"] = []
    result["http_requested"] = http
    result["state"] = result["dns_state"]
    if result["dns_state"] != "resolved":
        return result
    if not http:
        result["state"] = "dns_only"
        return result
    public = [a for a in result["addresses"] if ipaddress.ip_address(a).is_global]
    if not public:
        result["state"] = "private_address"
        return result
    # Try up to two addresses, covering both IP families when present.
    selected = [public[0]]
    other = next((a for a in public if (":" in a) != (":" in public[0])), None)
    if other:
        selected.append(other)
    elif len(public) > 1:
        selected.append(public[1])
    states = []
    for address in selected:
        probe = await probe_address(host, address, timeout)
        result["http"].extend(probe["http"])
        states.append(probe["state"])
        if probe["state"] == "online":
            break
    result["state"] = (
        "online"
        if "online" in states
        else ("tls_error" if "tls_error" in states else "unreachable")
    )
    return result


async def sample_hosts(
    target: str,
    hosts: list[str],
    *,
    concurrency: int = 8,
    timeout: float = 5,
    http: bool = True,
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    if not 1 <= concurrency <= 50 or not 0 < timeout <= 60:
        raise ValueError("Concurrency must be 1-50; timeout must be >0 and <=60 seconds")
    wildcard_addresses: set[str] = set()
    for _ in range(2):
        check = await resolve_host(f"atlas-{uuid.uuid4().hex}.{target}", timeout)
        wildcard_addresses.update(check["addresses"])
    queue: asyncio.Queue[str] = asyncio.Queue()
    for host in dict.fromkeys(hosts):
        queue.put_nowait(host)
    results = []

    async def worker() -> None:
        while not queue.empty():
            host = queue.get_nowait()
            try:
                row = await check_host(
                    host, http=http, timeout=timeout, wildcard_addresses=wildcard_addresses
                )
                results.append(row)
                if on_result:
                    on_result(row)
            finally:
                queue.task_done()

    await asyncio.gather(*(worker() for _ in range(min(concurrency, len(hosts)))))
    return sorted(results, key=lambda row: row["hostname"])

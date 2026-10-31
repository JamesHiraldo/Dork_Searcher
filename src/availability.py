"""Bounded, IP-pinned webpage sampling with auditable content classification."""

from __future__ import annotations

import asyncio
import ipaddress
import math
import ssl
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import dns.asyncresolver
import dns.exception
import dns.resolver
import httpx

from .classification import body_evidence, classify_sample
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


async def probe_address(
    host: str,
    address: str,
    timeout: float,
    *,
    target: str | None = None,
    max_redirects: int = 10,
    read_timeout: float = 10,
) -> dict[str, Any]:
    """Follow bounded internal redirects; validate and pin every destination anew."""
    responses = []
    boundary = target or host
    for scheme in ("https", "http"):
        original = f"{scheme}://{host}/"
        item: dict[str, Any] = {
            "scheme": scheme,
            "address": address,
            "original_url": original,
            "redirect_chain": [],
            "redirect_count": 0,
        }
        current, current_address = original, address
        visited: set[str] = set()
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout, read=read_timeout), trust_env=False
            ) as client:
                for hop in range(max_redirects + 1):
                    if current in visited:
                        item["outcome"] = "redirect_loop"
                        break
                    visited.add(current)
                    parts = urlsplit(current)
                    name = parts.hostname or ""
                    endpoint = f"[{current_address}]" if ":" in current_address else current_address
                    pinned = urlunsplit(
                        (parts.scheme, endpoint, parts.path or "/", parts.query, "")
                    )
                    item.update(final_url=current, final_hostname=name)
                    async with client.stream(
                        "GET",
                        pinned,
                        headers={
                            "Host": name,
                            "User-Agent": "Wayback-Recon/4.0",
                            "Accept": "text/html,application/xhtml+xml,application/json;q=0.8",
                            "Accept-Language": "en-US,en;q=0.9",
                            "Accept-Encoding": "identity",
                        },
                        extensions={"sni_hostname": name},
                        follow_redirects=False,
                    ) as response:
                        status = response.status_code
                        item.setdefault("status", status)
                        item["final_status"] = status
                        item.update(
                            content_type=response.headers.get("content-type", ""),
                            content_length=response.headers.get("content-length"),
                            server=response.headers.get("server", ""),
                            tls_state="verified" if parts.scheme == "https" else "not_used",
                        )
                        location = response.headers.get("location", "")
                        item.setdefault("location", location)
                        if status in (301, 302, 303, 307, 308) and location:
                            next_url = urljoin(current, location)
                            next_parts = urlsplit(next_url)
                            next_url = urlunsplit(next_parts._replace(fragment=""))
                            item["redirect_chain"].append(
                                {
                                    "url": current,
                                    "status": status,
                                    "location": location,
                                    "next_url": next_url,
                                }
                            )
                            item["redirect_count"] = len(item["redirect_chain"])
                            next_host = next_parts.hostname or ""
                            if (
                                next_parts.scheme not in ("https", "http")
                                or next_parts.username
                                or next_parts.password
                                or next_parts.port
                                not in (None, 443 if next_parts.scheme == "https" else 80)
                            ):
                                item["outcome"] = "redirect"
                                item["redirect_stop_reason"] = "Unsupported redirect URL"
                                break
                            if not (next_host == boundary or next_host.endswith("." + boundary)):
                                item.update(
                                    outcome="external_redirect",
                                    external_redirect=True,
                                    redirect_destination=next_url,
                                )
                                break
                            if next_url in visited:
                                item["outcome"] = "redirect_loop"
                                break
                            if hop == max_redirects:
                                item["outcome"] = "redirect_limit"
                                break
                            resolved = await resolve_host(next_host, timeout)
                            addresses = resolved["addresses"]
                            if not addresses or any(
                                not ipaddress.ip_address(a).is_global for a in addresses
                            ):
                                item["outcome"] = "redirect"
                                item["redirect_stop_reason"] = (
                                    "Destination has no exclusively public DNS addresses"
                                )
                                break
                            current, current_address = next_url, addresses[0]
                            continue
                        # Read only uncompressed, bounded bytes. Encoded bodies are candidates,
                        # avoiding decompression bombs even if a server ignores identity.
                        if response.headers.get("content-encoding", "identity").lower() in (
                            "identity",
                            "",
                        ):
                            body = bytearray()
                            truncated = False
                            async for chunk in response.aiter_raw(chunk_size=8192):
                                remaining = 65536 - len(body)
                                body.extend(chunk[:remaining])
                                if len(chunk) >= remaining:
                                    truncated = True
                                    break
                            item.update(body_evidence(bytes(body), item["content_type"], truncated))
                        else:
                            item["content_skip_reason"] = "Encoded body not inspected"
                        break
            item["response_seconds"] = round(time.monotonic() - started, 3)
            responses.append(item)
            # HTTP errors still count as transport reachability, not webpage availability.
            return classify_sample({"state": "online", "http": responses})
        except (httpx.RequestError, ValueError, ssl.SSLError) as exc:
            item["error"] = type(exc).__name__
            item["outcome"] = (
                "timeout" if isinstance(exc, httpx.TimeoutException) else "connection_failed"
            )
            if "CERTIFICATE_VERIFY_FAILED" in str(exc) or isinstance(exc, ssl.SSLError):
                item["tls_error"] = True
                item["outcome"] = "tls_error"
            responses.append(item)
    state = "tls_error" if any(r.get("tls_error") for r in responses) else "unreachable"
    return classify_sample({"state": state, "http": responses})


async def check_host(
    host: str,
    *,
    http: bool = True,
    timeout: float = 5,
    wildcard_addresses: set[str] | None = None,
    target: str | None = None,
    max_redirects: int = 10,
    read_timeout: float = 10,
) -> dict[str, Any]:
    result = {"hostname": host, "checked_at": utc_now(), **await resolve_host(host, timeout)}
    result["wildcard_possible"] = bool(set(result["addresses"]) & (wildcard_addresses or set()))
    result["http"] = []
    result["http_requested"] = http
    result["state"] = result["dns_state"]
    if result["dns_state"] != "resolved":
        return classify_sample(result)
    if not http:
        result["state"] = "dns_only"
        return classify_sample(result)
    public = [a for a in result["addresses"] if ipaddress.ip_address(a).is_global]
    if not public:
        result["state"] = "private_address"
        return classify_sample(result)
    # Try up to two addresses, covering both IP families when present.
    selected = [public[0]]
    other = next((a for a in public if (":" in a) != (":" in public[0])), None)
    if other:
        selected.append(other)
    elif len(public) > 1:
        selected.append(public[1])
    states = []
    for address in selected:
        probe = await probe_address(
            host,
            address,
            timeout,
            target=target,
            max_redirects=max_redirects,
            read_timeout=read_timeout,
        )
        result["http"].extend(probe["http"])
        states.append(probe["state"])
        if probe["state"] == "online":
            break
    result["state"] = (
        "online"
        if "online" in states
        else ("tls_error" if "tls_error" in states else "unreachable")
    )
    return classify_sample(result)


async def sample_hosts(
    target: str,
    hosts: list[str],
    *,
    concurrency: int = 8,
    timeout: float = 5,
    http: bool = True,
    host_timeout: float = 45,
    max_redirects: int = 10,
    read_timeout: float = 10,
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    if not 1 <= concurrency <= 50 or not 0 < timeout <= 60:
        raise ValueError("Concurrency must be 1-50; timeout must be >0 and <=60 seconds")
    if not math.isfinite(host_timeout) or not 0 < host_timeout <= 600:
        raise ValueError("Host timeout must be >0 and <=600 seconds")
    if (
        not 0 <= max_redirects <= 10
        or not math.isfinite(read_timeout)
        or not 0 < read_timeout <= 60
    ):
        raise ValueError("Redirect limit must be 0-10; read timeout must be >0 and <=60 seconds")
    if not hosts:
        return []
    round_id = uuid.uuid4().hex
    wildcard_addresses: set[str] = set()
    wildcard_signatures: set[tuple[Any, ...]] = set()
    for _ in range(2):
        random_host = f"recon-{uuid.uuid4().hex}.{target}"
        check = await resolve_host(random_host, timeout)
        wildcard_addresses.update(check["addresses"])
        if http and any(ipaddress.ip_address(a).is_global for a in check["addresses"]):
            try:
                control = await asyncio.wait_for(
                    check_host(
                        random_host,
                        timeout=timeout,
                        target=target,
                        max_redirects=max_redirects,
                        read_timeout=read_timeout,
                    ),
                    timeout=host_timeout,
                )
                for attempt in control.get("http", []):
                    if attempt.get("body_fingerprint"):
                        wildcard_signatures.add(
                            (
                                attempt.get("address"),
                                attempt.get("final_status"),
                                attempt["body_fingerprint"],
                            )
                        )
            except (asyncio.TimeoutError, TimeoutError, httpx.RequestError, OSError):
                pass
    queue: asyncio.Queue[str] = asyncio.Queue()
    for host in dict.fromkeys(hosts):
        queue.put_nowait(host)
    results = []

    async def worker() -> None:
        while not queue.empty():
            host = queue.get_nowait()
            started = time.monotonic()
            checked_at = utc_now()
            try:
                try:
                    row = await asyncio.wait_for(
                        check_host(
                            host,
                            http=http,
                            timeout=timeout,
                            wildcard_addresses=wildcard_addresses,
                            target=target,
                            max_redirects=max_redirects,
                            read_timeout=read_timeout,
                        ),
                        timeout=host_timeout,
                    )
                except Exception as exc:
                    # A failed host must not cancel other samples. Cancellation still propagates.
                    row = {
                        "hostname": host,
                        "checked_at": checked_at,
                        "state": "unknown",
                        "dns_state": "unknown",
                        "addresses": [],
                        "cnames": [],
                        "http": [],
                        "http_requested": http,
                        "error": type(exc).__name__,
                        "dns_errors": [],
                        "wildcard_possible": False,
                    }
                    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
                        row["state"] = "timeout"
                row["http_wildcard_possible"] = any(
                    (a.get("address"), a.get("final_status"), a.get("body_fingerprint"))
                    in wildcard_signatures
                    for a in row.get("http", [])
                )
                row = classify_sample(row)
                row["round_id"] = round_id
                row["finished_at"] = utc_now()
                row["duration_seconds"] = round(time.monotonic() - started, 3)
                results.append(row)
                if on_result:
                    on_result(row)
            finally:
                queue.task_done()

    await asyncio.gather(*(worker() for _ in range(min(concurrency, len(hosts)))))
    return sorted(results, key=lambda row: row["hostname"])

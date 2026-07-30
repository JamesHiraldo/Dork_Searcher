"""Target normalization and scope enforcement helpers.

The project accepts targets from interactive users and from result files.  These
helpers keep hostname comparisons structural; security tooling must never use
substring matching to decide whether a URL is in scope.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit


class ScopeError(ValueError):
    """Raised when a target or URL is malformed or outside the allowed scope."""


_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def normalize_hostname(value: str) -> str:
    """Return a lowercase ASCII hostname, accepting a hostname or HTTP(S) URL."""
    raw = (value or "").strip()
    if not raw:
        raise ScopeError("Target cannot be empty")

    candidate = raw if "://" in raw else "//" + raw
    parsed = urlsplit(candidate)
    if parsed.scheme and parsed.scheme.lower() not in ("http", "https"):
        raise ScopeError("Only HTTP and HTTPS targets are supported")
    if parsed.username or parsed.password:
        raise ScopeError("Credentials are not allowed in target URLs")
    if not parsed.hostname:
        raise ScopeError("Target must contain a hostname")
    if "://" not in raw and (parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ScopeError("Enter a hostname, not a path or query string")

    host = parsed.hostname.rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ScopeError("Target contains an invalid internationalized hostname") from exc

    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass

    if len(host) > 253 or not host:
        raise ScopeError("Hostname is too long")
    labels = host.split(".")
    if any(not _LABEL_RE.fullmatch(label) for label in labels):
        raise ScopeError("Hostname contains an invalid DNS label")
    return host


def normalize_targets(values: Iterable[str]) -> list[str]:
    """Normalize and de-duplicate targets while preserving input order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        host = normalize_hostname(value)
        if host not in seen:
            seen.add(host)
            normalized.append(host)
    return normalized


def host_in_scope(host: str, target: str, include_subdomains: bool = True) -> bool:
    """Return whether *host* is exactly target or a DNS child of target."""
    try:
        normalized_host = normalize_hostname(host)
        normalized_target = normalize_hostname(target)
    except ScopeError:
        return False
    return normalized_host == normalized_target or (
        include_subdomains and normalized_host.endswith("." + normalized_target)
    )


def parse_http_url(url: str) -> tuple[str, str]:
    """Validate an HTTP(S) URL and return ``(normalized_url, hostname)``."""
    raw = (url or "").strip()
    if not raw or _CONTROL_RE.search(raw):
        raise ScopeError("URL is empty or contains control characters")
    if len(raw) > 16384:
        raise ScopeError("URL exceeds the 16 KiB safety limit")

    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ScopeError("Only absolute HTTP and HTTPS URLs are supported")
    if parsed.username or parsed.password:
        raise ScopeError("Credentials are not allowed in URLs")

    host = normalize_hostname(parsed.hostname)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ScopeError("URL contains an invalid port") from exc

    host_for_netloc = f"[{host}]" if ":" in host else host
    netloc = host_for_netloc + (f":{port}" if port is not None else "")
    path = parsed.path or "/"
    normalized = urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))
    return normalized, host


def url_in_scope(url: str, targets: Iterable[str], include_subdomains: bool = True) -> bool:
    try:
        _, host = parse_http_url(url)
    except ScopeError:
        return False
    return any(host_in_scope(host, target, include_subdomains) for target in targets)


def match_url_to_scoped_hosts(url: str, hosts: Iterable[str]) -> list[str]:
    """Return observed hosts that structurally contain the URL hostname."""
    try:
        _, url_host = parse_http_url(url)
    except ScopeError:
        return []

    matches: list[str] = []
    seen: set[str] = set()
    for candidate in hosts:
        try:
            scoped_host = normalize_hostname(candidate)
        except ScopeError:
            continue
        if (
            url_host == scoped_host or url_host.endswith("." + scoped_host)
        ) and scoped_host not in seen:
            seen.add(scoped_host)
            matches.append(scoped_host)
    return matches


def _is_globally_routable(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


def ensure_public_url(
    url: str, allow_private: bool = False, resolve: bool = True
) -> tuple[str, str]:
    """Validate a URL and reject local/private destinations by default.

    DNS is checked before the request as a defense-in-depth guard.  Callers must
    repeat this check for every redirect because redirects can change hosts.
    """
    normalized, host = parse_http_url(url)
    if allow_private:
        return normalized, host

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ScopeError("Private, loopback, link-local, and reserved IPs are blocked")

    if resolve and literal is None:
        try:
            records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ScopeError("Hostname could not be resolved") from exc
        addresses = {str(record[4][0]) for record in records if record[4]}
        if not addresses:
            raise ScopeError("Hostname did not resolve to an address")
        blocked = sorted(address for address in addresses if not _is_globally_routable(address))
        if blocked:
            raise ScopeError("Hostname resolves to a non-public address")

    return normalized, host

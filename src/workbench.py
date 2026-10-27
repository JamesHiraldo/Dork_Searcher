"""Offline archive queries and explicit, user-opened research links."""

from __future__ import annotations

import shlex
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlsplit

from .scope import normalize_hostname

TEMPLATES = ["path:/api/", "param:redirect", "ext:js", "ext:json", "backup", "staging", "admin"]
RESOURCES = [
    (
        "CompleteDNS",
        "https://completedns.com/dns-history/",
        "Nameserver history; keyed API supported",
    ),
    ("RapidDNS", "https://rapiddns.io/", "DNS records; keyed Pro/Max API or CSV/JSON import"),
    (
        "Secret Finder",
        "https://serene-agnesi-57a014.netlify.app/",
        "External JavaScript research helper",
    ),
    ("Pentest.bd / ReconNexus", "https://pentest.bd/dorks/", "External dork/recon helper"),
]


def duckduckgo_link(target: str, query: str) -> str:
    return "https://duckduckgo.com/?q=" + quote_plus(f"site:{normalize_hostname(target)} {query}")


def filter_archive(records: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """AND terms, OR groups, quoted phrases, -exclusions, host/path/ext/param fields."""
    if len(query) > 2000:
        raise ValueError("Query must not exceed 2000 characters")
    groups: list[list[str]] = [[]]
    for term in shlex.split(query):
        if term == "OR":
            if not groups[-1]:
                raise ValueError("OR must separate nonempty query groups")
            groups.append([])
        else:
            groups[-1].append(term)
    if not groups[-1]:
        raise ValueError("Enter an archive query")
    allowed = {"host", "path", "ext", "param"}
    for group in groups:
        for term in group:
            token = term.removeprefix("-")
            if ":" in token and token.split(":", 1)[0] not in allowed:
                raise ValueError("Local query fields: host:, path:, ext:, param:")

    def matches(url: str, term: str) -> bool:
        negative = term.startswith("-")
        token = term.removeprefix("-").lower()
        parsed = urlsplit(url)
        field, separator, value = token.partition(":")
        if not separator:
            found = token in url.lower()
        elif field == "host":
            host = parsed.hostname or ""
            found = host == value or host.endswith("." + value)
        elif field == "path":
            found = value in parsed.path.lower()
        elif field == "ext":
            found = parsed.path.lower().endswith("." + value.lstrip("."))
        else:
            found = value in {key.lower() for key in parse_qs(parsed.query, keep_blank_values=True)}
        return not found if negative else found

    output = []
    seen = set()
    for row in records:
        url = str(row.get("url", ""))
        if url and url not in seen and any(all(matches(url, t) for t in group) for group in groups):
            output.append(row)
            seen.add(url)
    return output

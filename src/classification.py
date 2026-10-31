"""Canonical, conservative webpage classification shared by every output."""

from __future__ import annotations

import hashlib
import logging
import re
from html.parser import HTMLParser
from typing import Any

LOG = logging.getLogger(__name__)
ERRORS = (
    "access denied",
    "forbidden",
    "request blocked",
    "permission denied",
    "unauthorized",
    "not found",
    "page not found",
    "invalid host",
    "unknown host",
    "bad request",
    "application error",
    "service unavailable",
    "temporarily unavailable",
    "backend unavailable",
    "the request could not be satisfied",
)
EXPORT_STATES = {
    "confirmed_webpages": {"confirmed_webpage"},
    "alive_candidates": {"alive_candidate"},
    "redirects": {"redirect", "external_redirect", "redirect_loop", "redirect_limit"},
    "external_redirects": {"external_redirect"},
    "protected": {"authentication_required", "forbidden"},
    "forbidden": {"forbidden"},
    "not_found": {"not_found"},
    "bad_request": {"bad_request"},
    "server_errors": {"server_error"},
    "timeouts": {"timeout"},
    "connection_failed": {"connection_failed"},
    "tls_errors": {"tls_error"},
    "dns_only": {"dns_only"},
    "unreachable": {"connection_failed", "timeout", "nxdomain", "no_address"},
    "error_pages": {"error_page"},
    "wildcard_candidates": {"wildcard_candidate"},
}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()
        self.title_parts: list[str] = []
        self.parts: list[str] = []
        self.in_title = False
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)
        if tag == "title":
            self.in_title = True
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if not self.hidden:
            self.parts.append(data)


def body_evidence(body: bytes, content_type: str, truncated: bool = False) -> dict[str, Any]:
    page = PageParser()
    page.feed(body.decode("utf-8", errors="replace"))
    title = " ".join(" ".join(page.title_parts).split())[:300]
    visible = " ".join(" ".join(page.parts).split())
    title_lower, text_lower = title.lower(), visible.lower()
    signals = [term for term in ERRORS if term in text_lower]
    # A keyword in a normal article is not enough. Error titles or short denial
    # responses are stronger signals; retain the reasons for manual review.
    error = (
        title_lower in ("error", "403", "404", "500")
        or any(term in title_lower for term in ERRORS)
        or bool(signals and len(visible) < 600)
    )
    html = any(t in content_type.lower() for t in ("text/html", "application/xhtml+xml"))
    structure = bool(page.tags & {"html", "body", "main", "form", "title"})
    meaningful = len(visible) >= 40 or bool(title and page.tags & {"form", "input", "main"})
    return {
        "title": title,
        "body_length": len(body),
        "body_truncated": truncated,
        "body_fingerprint": hashlib.sha256(re.sub(rb"\s+", b" ", body).strip()).hexdigest(),
        "body_sample": body[:2048].decode("utf-8", errors="replace"),
        "error_signals": signals,
        "known_error_page": error,
        "meaningful_html": html and structure and meaningful and len(body) >= 200,
        "content_checked": True,
    }


def classify_http(item: dict[str, Any]) -> dict[str, Any]:
    status = item.get("final_status", item.get("status"))
    state = item.get("outcome")
    confidence = "low"
    if not state:
        if isinstance(status, int) and 200 <= status < 300:
            if item.get("known_error_page"):
                state = "error_page"
            elif item.get("meaningful_html") and item.get("content_checked"):
                state = "confirmed_webpage"
                confidence = "high" if item.get("title") else "medium"
            else:
                state = "alive_candidate"
        elif isinstance(status, int) and 300 <= status < 400:
            state = "redirect"
        elif status in (400, 401, 403, 404):
            state = {
                400: "bad_request",
                401: "authentication_required",
                403: "forbidden",
                404: "not_found",
            }[status]
        elif isinstance(status, int) and 500 <= status < 600:
            state = "server_error"
        else:
            state = "http_response" if status else "unknown"
    reachable = bool(item.get("status") or status)
    return {
        "classification": state,
        "network_reachable": reachable,
        "webpage_accessible": state == "confirmed_webpage",
        "confidence": confidence,
    }


def classify_sample(sample: dict[str, Any]) -> dict[str, Any]:
    """Reclassify legacy samples without inventing missing content evidence."""
    result = dict(sample)
    attempts = [{**item, **classify_http(item)} for item in sample.get("http", [])]
    result["http"] = attempts
    chosen = next((a for a in attempts if a["webpage_accessible"]), None)
    if chosen is None:
        chosen = next((a for a in reversed(attempts) if a["network_reachable"]), None)
    if chosen is None and attempts:
        chosen = attempts[-1]
    if chosen:
        for key in (
            "classification",
            "webpage_accessible",
            "confidence",
            "title",
            "final_url",
            "final_status",
        ):
            result[key] = chosen.get(key)
        result["final_status"] = chosen.get("final_status", chosen.get("status"))
        result["network_reachable"] = any(a["network_reachable"] for a in attempts)
    else:
        state = sample.get("state", "unknown")
        result.update(
            classification={"online": "http_response", "unreachable": "connection_failed"}.get(
                state, state
            ),
            network_reachable=state == "online",
            webpage_accessible=False,
            confidence="low",
        )
    if sample.get("http_wildcard_possible"):
        result["confidence"] = "low"
        if result["webpage_accessible"]:
            result.update(classification="wildcard_candidate", webpage_accessible=False)
    result["classification_version"] = 1
    LOG.debug(
        "%s: %s; alive=%s",
        result.get("hostname"),
        result["classification"],
        result["webpage_accessible"],
    )
    return result

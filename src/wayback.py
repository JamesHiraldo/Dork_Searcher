"""Hardened Internet Archive CDX client shared by all Wayback workflows."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import requests

if __package__:
    from .scope import normalize_hostname, url_in_scope
else:  # pragma: no cover
    from scope import normalize_hostname, url_in_scope  # type: ignore


CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
DEFAULT_USER_AGENT = "dork-searcher/2.0 (+https://github.com/Maydayx2/dork-searcher)"


class WaybackError(RuntimeError):
    """Raised when CDX data cannot be retrieved or parsed reliably."""


@dataclass
class WaybackResult:
    target: str
    urls: list[str] = field(default_factory=list)
    pages: int = 0
    truncated: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _parse_cdx_payload(payload: Any) -> tuple[list[str], str | None]:
    """Parse CDX JSON rows and the optional resumption-key trailer."""
    if not isinstance(payload, list) or not payload:
        raise WaybackError("CDX returned an unexpected JSON document")

    header = payload[0]
    if not isinstance(header, list) or "original" not in header:
        raise WaybackError("CDX response is missing the original URL column")
    original_index = header.index("original")

    urls: list[str] = []
    resume_key: str | None = None
    rows: Sequence[Any] = payload[1:]
    for index, row in enumerate(rows):
        if row == []:
            if index + 1 < len(rows):
                trailer = rows[index + 1]
                if isinstance(trailer, list) and len(trailer) == 1 and isinstance(trailer[0], str):
                    resume_key = trailer[0]
            break
        if not isinstance(row, list) or original_index >= len(row):
            continue
        original = row[original_index]
        if isinstance(original, str) and original:
            urls.append(original)
    return urls, resume_key


class WaybackClient:
    """Retrieve unique archived URLs with retries and resumption-key pagination."""

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 45.0,
        retries: int = 3,
        backoff: float = 1.0,
        page_size: int = 1000,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if retries < 1:
            raise ValueError("retries must be at least one")
        if page_size < 1 or page_size > 10000:
            raise ValueError("page_size must be between 1 and 10000")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.retries = retries
        self.backoff = max(0.0, backoff)
        self.page_size = page_size
        self.user_agent = user_agent

    def _get_page(self, params: dict[str, Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self.session.get(
                    CDX_ENDPOINT,
                    params=params,
                    timeout=self.timeout,
                    headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                )
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    retry_after = response.headers.get("Retry-After", "")
                    delay = (
                        float(retry_after) if retry_after.isdigit() else self.backoff * (2**attempt)
                    )
                    if attempt + 1 < self.retries:
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                try:
                    return response.json()
                except (ValueError, json.JSONDecodeError) as exc:
                    raise WaybackError("CDX returned invalid JSON") from exc
            except (requests.RequestException, WaybackError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(self.backoff * (2**attempt))
        raise WaybackError(f"CDX request failed after {self.retries} attempts: {last_error}")

    def fetch(
        self,
        target: str,
        max_urls: int = 50000,
        include_subdomains: bool = False,
        rate: float = 0.25,
    ) -> WaybackResult:
        if max_urls < 1:
            raise ValueError("max_urls must be greater than zero")
        if rate < 0:
            raise ValueError("rate cannot be negative")

        normalized_target = normalize_hostname(target)
        query_target = (
            f"*.{normalized_target}/*" if include_subdomains else f"{normalized_target}/*"
        )
        params: dict[str, Any] = {
            "url": query_target,
            "output": "json",
            "fl": "original",
            "collapse": "urlkey",
            "limit": min(self.page_size, max_urls),
            "showResumeKey": "true",
        }

        result = WaybackResult(target=normalized_target)
        seen = set()
        resume_key: str | None = None

        try:
            while len(result.urls) < max_urls:
                if resume_key:
                    params["resumeKey"] = resume_key
                payload = self._get_page(params)
                page_urls, next_resume_key = _parse_cdx_payload(payload)
                result.pages += 1

                for url in page_urls:
                    if url in seen:
                        continue
                    if not url_in_scope(
                        url, [normalized_target], include_subdomains=include_subdomains
                    ):
                        continue
                    seen.add(url)
                    result.urls.append(url)
                    if len(result.urls) >= max_urls:
                        break

                if len(result.urls) >= max_urls:
                    result.truncated = bool(next_resume_key) or len(page_urls) >= int(
                        params["limit"]
                    )
                    break
                if not next_resume_key or next_resume_key == resume_key:
                    break
                resume_key = next_resume_key
                if rate:
                    time.sleep(rate)
        except (WaybackError, requests.RequestException, ValueError) as exc:
            result.error = str(exc)

        return result


def fetch_wayback_urls(
    target: str,
    max_urls: int = 50000,
    include_subdomains: bool = False,
    rate: float = 0.25,
    client: WaybackClient | None = None,
) -> WaybackResult:
    return (client or WaybackClient()).fetch(
        target,
        max_urls=max_urls,
        include_subdomains=include_subdomains,
        rate=rate,
    )

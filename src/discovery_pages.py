"""One bounded provider page at a time; network code never advances durable cursors."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests

from .discovery import NOT_FOUND, DiscoveryResult, collect, record, request_json
from .recon_pipeline import redact_sensitive_url
from .scope import parse_http_url
from .wayback import WaybackClient, WaybackError, _parse_cdx_payload

SOURCES = ("wayback", "crtsh", "certspotter", "rapiddns", "completedns", "commoncrawl")
CC_ROOT = "https://index.commoncrawl.org/"
CC_INDEX = re.compile(r"CC-MAIN-\d{4}-\d{2}\Z")


@dataclass
class Page:
    result: DiscoveryResult
    cursor: dict[str, Any]
    done: bool = False


def validate_dates(start: str | None, end: str | None) -> None:
    for value in (start, end):
        if value:
            if not re.fullmatch(r"\d{4}(?:\d{2}){0,5}", value):
                raise ValueError("Archive dates must be YYYY through YYYYMMDDhhmmss")
            try:
                datetime.strptime(value + "20000101000000"[len(value) :], "%Y%m%d%H%M%S")
            except ValueError:
                raise ValueError("Archive dates must be valid calendar dates") from None
    if start and end and start.ljust(14, "0") > end.ljust(14, "9"):
        raise ValueError("Archive start must not exceed archive end")


def archive_record(target: str, row: dict[str, Any], **extra: Any) -> dict[str, Any] | None:
    url = row.get("url", row.get("original"))
    if not isinstance(url, str):
        raise ValueError("Archive row is missing a URL")
    try:
        validated, host = parse_http_url(url)
    except ValueError:
        return None
    return record(
        target,
        host,
        url=redact_sensitive_url(validated),
        observed_at=str(row.get("timestamp", "")),
        archive_status=str(row.get("status", row.get("statuscode", ""))),
        mimetype=str(row.get("mime", row.get("mimetype", ""))),
        **extra,
    )


def fetch_page(
    target: str,
    source: str,
    config: dict[str, Any],
    cursor: dict[str, Any],
    session: requests.Session,
    api_key: str = "",
) -> Page:
    result = DiscoveryResult(source)
    next_cursor = dict(cursor)

    def add(item: dict[str, Any] | None) -> None:
        if item:
            result.records.append(item)
        else:
            result.metadata["rejected"] = result.metadata.get("rejected", 0) + 1

    dates = {k: config[v] for k, v in (("from", "from_date"), ("to", "to_date")) if config.get(v)}
    if source == "wayback":
        params = {
            "url": f"*.{target}/*",
            "output": "json",
            "fl": "original,timestamp,statuscode,mimetype",
            "collapse": "urlkey",
            "limit": config["page_size"],
            "showResumeKey": "true",
            **dates,
        }
        if cursor.get("resume_key"):
            params["resumeKey"] = cursor["resume_key"]
        try:
            payload = WaybackClient(session=session, timeout=25, retries=2)._get_page(params)
            _, key = _parse_cdx_payload(payload)
        except WaybackError as exc:
            # Request exceptions can include raw archive cursors/URLs. Keep them out of logs.
            raise ValueError(
                "Wayback page failed; retry this checkpoint or start a narrower run"
            ) from exc
        if payload:
            header = payload[0]
            if not all(isinstance(column, str) for column in header) or len(set(header)) != len(
                header
            ):
                raise ValueError("Malformed Wayback columns; checkpoint not advanced")
            for position, row in enumerate(payload[1:], 1):
                if row == []:
                    if position != len(payload) - 2 or not key:
                        raise ValueError(
                            "Malformed Wayback cursor trailer; checkpoint not advanced"
                        )
                    break
                if not isinstance(row, list) or len(row) != len(header):
                    raise ValueError("Malformed Wayback row; checkpoint not advanced")
                add(archive_record(target, dict(zip(header, row, strict=True))))
        next_cursor["resume_key"] = key
        result.metadata["dates_are"] = "sampled_capture_dates"
        return Page(result, next_cursor, not key)

    if source == "certspotter":
        params = {"domain": target, "include_subdomains": "true", "expand": "dns_names"}
        if cursor.get("after"):
            params["after"] = cursor["after"]
        data = request_json(
            session,
            "https://api.certspotter.com/v1/issuances",
            params=params,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            secrets=(api_key,),
        )
        if not isinstance(data, list):
            raise ValueError("Unexpected Cert Spotter response schema")
        for cert in data:
            if not isinstance(cert, dict) or not isinstance(cert.get("dns_names"), list):
                raise ValueError("Unexpected Cert Spotter certificate schema")
            for name in cert["dns_names"]:
                add(record(target, name, observed_at=str(cert.get("not_before", ""))))
        if data:
            after = data[-1].get("id")
            if not isinstance(after, (str, int)) or isinstance(after, bool) or not str(after):
                raise ValueError("Cert Spotter omitted its continuation ID")
            next_cursor["after"] = str(after)
        return Page(result, next_cursor, not data)

    if source == "rapiddns":
        if not api_key:
            raise ValueError("Set RAPIDDNS_API_KEY (Pro/Max API) or import a saved export")
        number = cursor.get("page", 1)
        payload = request_json(
            session,
            f"https://rapiddns.io/api/search/{quote(target, safe='')}",
            headers={"X-API-KEY": api_key},
            secrets=(api_key,),
            params={"page": number, "pagesize": 100, "search_type": "subdomain"},
        )
        body = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise ValueError("Unexpected RapidDNS response schema")
        if payload.get("status", 200) not in (200, "ok"):
            raise ValueError("RapidDNS reported an unsuccessful query")
        total = body.get("total")
        if isinstance(total, bool) or not isinstance(total, (int, str)) or not str(total).isdigit():
            raise ValueError("RapidDNS returned an invalid total count")
        for row in body["data"]:
            if not isinstance(row, dict):
                raise ValueError("Unexpected RapidDNS record schema")
            add(
                record(
                    target,
                    row.get("subdomain", ""),
                    observed_at=str(row.get("timestamp") or row.get("date") or ""),
                    record_type=str(row.get("type", "")),
                    value=str(row.get("value", "")),
                )
            )
        if not body["data"] and (number - 1) * 100 < int(total):
            raise ValueError("RapidDNS returned an empty page before its reported total")
        next_cursor["page"] = number + 1
        return Page(result, next_cursor, number * 100 >= int(total))

    if source == "commoncrawl":
        # Never use endpoints supplied by the remote catalog: only validated IDs on this host.
        if "indexes" not in cursor:
            ids = config.get("cc_indexes", [])
            catalog = request_json(session, CC_ROOT + "collinfo.json")
            if not isinstance(catalog, list):
                raise ValueError("Unexpected Common Crawl catalog schema")
            available = {
                row["id"]
                for row in catalog
                if isinstance(row, dict)
                and isinstance(row.get("id"), str)
                and CC_INDEX.fullmatch(row["id"])
            }
            if ids and any(index not in available for index in ids):
                raise ValueError("Requested Common Crawl index is not in the published catalog")
            ids = ids or sorted(available, reverse=True)[: config["cc_latest"]]
            if not ids:
                raise ValueError("Common Crawl catalog contains no supported crawl indexes")
            return Page(result, {"indexes": ids, "index": 0, "page": 0})
        ids = cursor["indexes"]
        index = ids[cursor["index"]]
        endpoint = CC_ROOT + index + "-index"
        params = {"url": target, "matchType": "domain", "output": "json", "pageSize": 1, **dates}
        if "pages" not in cursor:
            count = request_json(
                session, endpoint, params={**params, "showNumPages": "true"}, empty_on_404=True
            )
            if count is NOT_FOUND:
                pages = 0
            elif (
                isinstance(count, dict)
                and type(count.get("pages")) is int
                and count["pages"] >= 0
                and count.get("pageSize") == 1
            ):
                pages = count["pages"]
            else:
                raise ValueError("Unexpected Common Crawl pagination schema")
            if pages:
                return Page(result, {**cursor, "pages": pages})
        else:
            # No API limit: it would silently discard the rest of this block/page.
            rows = request_json(
                session,
                endpoint,
                params={**params, "page": cursor["page"]},
                json_lines=True,
                empty_on_404=True,
            )
            if rows is NOT_FOUND:
                rows = []
            if not isinstance(rows, list):
                raise ValueError("Unexpected Common Crawl JSONL schema")
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("Unexpected Common Crawl index row")
                add(archive_record(target, row, crawl_index=index))
            result.metadata["crawl_index"] = index
            if cursor["page"] + 1 < cursor["pages"]:
                return Page(result, {**cursor, "page": cursor["page"] + 1})
        next_index = cursor["index"] + 1
        return Page(
            result, {"indexes": ids, "index": next_index, "page": 0}, next_index == len(ids)
        )

    if source in ("crtsh", "completedns"):
        # These APIs expose a single response, not a page cursor. Stage the whole bounded response.
        result = collect(target, source, session=session, api_key=api_key, limit=2**63 - 1)
        if result.error or result.truncated:
            raise ValueError(result.error or "Provider unexpectedly truncated a single response")
        return Page(result, {}, True)
    raise ValueError(f"Unknown source: {source}")

"""Offline regressions: no requests to the domain mentioned in the supplied report."""

import csv
import json
from collections import Counter

import httpx
import pytest

from src import availability
from src.classification import body_evidence, classify_http, classify_sample
from src.discovery import DiscoveryResult
from src.inventory import Inventory, filter_assets

HTML = (
    b"<html><head><title>Dashboard</title></head><body><main>"
    + b"Welcome to your project dashboard. " * 10
    + b"</main></body></html>"
)


@pytest.mark.parametrize(
    ("status", "body", "mime", "expected"),
    [
        (200, HTML, "text/html", "confirmed_webpage"),
        (200, b"", "text/html", "alive_candidate"),
        (200, b"Access Denied", "text/html", "error_page"),
        (
            200,
            b"<html><title>Access Denied</title><body>No permission</body></html>",
            "text/html",
            "error_page",
        ),
        (200, b'{"ok": true}', "application/json", "alive_candidate"),
        (301, b"", "text/html", "redirect"),
        (400, HTML, "text/html", "bad_request"),
        (401, HTML, "text/html", "authentication_required"),
        (403, HTML, "text/html", "forbidden"),
        (404, HTML, "text/html", "not_found"),
        (500, HTML, "text/html", "server_error"),
    ],
)
def test_status_and_content(status, body, mime, expected):
    row = classify_http({"status": status, **body_evidence(body, mime)})
    assert row["classification"] == expected
    assert row["network_reachable"]
    assert row["webpage_accessible"] == (expected == "confirmed_webpage")


def test_article_keyword_does_not_make_error_page():
    body = (
        HTML.replace(b"Dashboard", b"HTTP tutorial") + b" How to handle Forbidden responses. " * 30
    )
    assert classify_http({"status": 200, **body_evidence(body, "text/html")})["webpage_accessible"]


def test_report_status_distribution_regression(tmp_path):
    """Synthetic reproduction of attachment counts, not the original private dataset."""
    statuses = [403] * 119 + [400] * 10 + [404] * 5 + [401] * 3 + [200, 302]
    with Inventory(tmp_path / "i.sqlite3") as store:
        for index, status in enumerate(statuses):
            host = f"host{index}.example.com"
            store.merge("example.com", DiscoveryResult("import", [{"hostname": host}]))
            store.save_check(
                "example.com",
                {
                    "hostname": host,
                    "checked_at": "2026-10-31",
                    "dns_state": "resolved",
                    "state": "online",
                    "http": [{"status": status}],
                },
            )
        path = store.export("example.com", tmp_path)
        report = json.loads(path.read_text())
        counts = Counter(a["latest"]["classification"] for a in report["assets"])
        assert counts == {
            "forbidden": 119,
            "bad_request": 10,
            "not_found": 5,
            "authentication_required": 3,
            "alive_candidate": 1,
            "redirect": 1,
        }
        assert (path.parent / "alive.txt").read_text() == ""
        assert len((path.parent / "forbidden.txt").read_text().splitlines()) == 119
        csv_rows = list(csv.DictReader((path.parent / "inventory.csv").open(encoding="utf-8-sig")))
        assert Counter(r["classification"] for r in csv_rows) == counts
        html = path.with_suffix(".html").read_text(encoding="utf-8")
        assert "Confirmed webpages" in html and "HTTP responding" not in html
        assert not filter_assets(report["assets"], {"only_webpages": True})
        assert (
            len(filter_assets(report["assets"], {"only_webpages": True, "include_protected": True}))
            == 122
        )
        assert len(filter_assets(report["assets"], {"status": 200})) == 1


def test_validated_export_and_wildcard_downgrade(tmp_path):
    sample = {
        "hostname": "app.example.com",
        "checked_at": "2026-10-31",
        "state": "online",
        "dns_state": "resolved",
        "http": [{"status": 200, **body_evidence(HTML, "text/html")}],
    }
    with Inventory(tmp_path / "i.sqlite3") as store:
        store.merge("example.com", DiscoveryResult("import", [{"hostname": sample["hostname"]}]))
        store.save_check("example.com", sample)
        path = store.export("example.com", tmp_path)
        assert (path.parent / "alive.txt").read_text() == "app.example.com\n"
        assert (path.parent / "alive.txt").read_bytes() == (
            path.parent / "confirmed_webpages.txt"
        ).read_bytes()
    sample["http_wildcard_possible"] = True
    result = classify_sample(sample)
    assert result["classification"] == "wildcard_candidate" and not result["webpage_accessible"]


def fake_network(monkeypatch, replies, addresses=None):
    calls = []

    class Response:
        def __init__(self, status, headers, body):
            self.status_code, self.headers, self.body = status, headers, body

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aiter_raw(self, **kwargs):
            if isinstance(self.body, Exception):
                raise self.body
            for offset in range(0, len(self.body), 8192):
                yield self.body[offset : offset + 8192]

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def stream(self, method, url, **kwargs):
            calls.append((url, kwargs))
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return Response(*reply)

    async def resolve(*args):
        return {"dns_state": "resolved", "addresses": addresses or ["93.184.216.34"], "cnames": []}

    monkeypatch.setattr(availability.httpx, "AsyncClient", Client)
    monkeypatch.setattr(availability, "resolve_host", resolve)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("location", "expected", "count"),
    [
        ("https://elsewhere.example/", "external_redirect", 1),
        ("/", "redirect_loop", 1),
        ("/dashboard", "confirmed_webpage", 2),
    ],
)
async def test_redirects(monkeypatch, location, expected, count):
    calls = fake_network(
        monkeypatch,
        [(302, {"location": location}, b""), (200, {"content-type": "text/html"}, HTML)],
    )
    row = await availability.probe_address(
        "app.example.com", "93.184.216.34", 2, target="example.com"
    )
    assert row["classification"] == expected
    assert len(calls) == count
    assert row["http"][0]["redirect_count"] == 1
    assert all(c[1]["follow_redirects"] is False for c in calls)
    if count == 2:
        assert row["final_url"] == "https://app.example.com/dashboard"
        assert row["title"] == "Dashboard"


@pytest.mark.asyncio
async def test_private_redirect_never_contacted(monkeypatch):
    calls = fake_network(monkeypatch, [(301, {"location": "/next"}, b"")], ["127.0.0.1"])
    row = await availability.probe_address("app.example.com", "93.184.216.34", 2)
    assert len(calls) == 1 and not row["webpage_accessible"]
    assert "public" in row["http"][0]["redirect_stop_reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.ConnectTimeout("slow"), "timeout"),
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectError("refused"), "connection_failed"),
        (httpx.ConnectError("CERTIFICATE_VERIFY_FAILED"), "tls_error"),
    ],
)
async def test_transport_failures(monkeypatch, error, expected):
    calls = fake_network(monkeypatch, [error, error])
    row = await availability.probe_address("app.example.com", "93.184.216.34", 2)
    assert row["classification"] == expected and not row["webpage_accessible"]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_body_bound_and_compression(monkeypatch):
    fake_network(monkeypatch, [(200, {"content-type": "text/html"}, HTML * 1000)])
    row = await availability.probe_address("app.example.com", "93.184.216.34", 2)
    assert row["http"][0]["body_length"] == 65536
    assert row["http"][0]["body_truncated"]
    fake_network(monkeypatch, [(200, {"content-encoding": "gzip"}, b"not inspected")])
    row = await availability.probe_address("app.example.com", "93.184.216.34", 2)
    assert row["classification"] == "alive_candidate"


@pytest.mark.asyncio
async def test_http_wildcard_403(monkeypatch):
    async def resolve(*args):
        return {"addresses": ["93.184.216.34"]}

    async def host(name, **kwargs):
        return {
            "hostname": name,
            "checked_at": "2026-10-31",
            "state": "online",
            "http": [
                {
                    "address": "93.184.216.34",
                    "status": 403,
                    "final_status": 403,
                    **body_evidence(b"Forbidden", "text/html"),
                }
            ],
        }

    monkeypatch.setattr(availability, "resolve_host", resolve)
    monkeypatch.setattr(availability, "check_host", host)
    rows = await availability.sample_hosts("example.com", ["app.example.com"])
    assert rows[0]["http_wildcard_possible"] and rows[0]["classification"] == "forbidden"
    assert not rows[0]["webpage_accessible"]


@pytest.mark.asyncio
async def test_redirect_limit_and_multi_hop_loop(monkeypatch):
    calls = fake_network(monkeypatch, [(301, {"location": "/one"}, b"")])
    result = await availability.probe_address(
        "app.example.com", "93.184.216.34", 2, max_redirects=0
    )
    assert result["classification"] == "redirect_limit" and len(calls) == 1
    calls = fake_network(
        monkeypatch, [(301, {"location": "/one"}, b""), (302, {"location": "/"}, b"")]
    )
    result = await availability.probe_address("app.example.com", "93.184.216.34", 2)
    assert result["classification"] == "redirect_loop" and len(calls) == 2


@pytest.mark.asyncio
async def test_sibling_redirect_retains_host_sni_and_pins_new_dns(monkeypatch):
    calls = fake_network(
        monkeypatch,
        [
            (301, {"location": "https://www.example.com/"}, b""),
            (200, {"content-type": "text/html"}, HTML),
        ],
        ["1.1.1.1"],
    )
    result = await availability.probe_address(
        "app.example.com", "93.184.216.34", 2, target="example.com"
    )
    assert result["webpage_accessible"]
    assert calls[1][0] == "https://1.1.1.1/"
    assert calls[1][1]["headers"]["Host"] == "www.example.com"
    assert calls[1][1]["extensions"]["sni_hostname"] == "www.example.com"


@pytest.mark.asyncio
async def test_read_timeout_retains_response_evidence(monkeypatch):
    fake_network(
        monkeypatch,
        [
            (200, {"content-type": "text/html"}, httpx.ReadTimeout("slow")),
            httpx.ConnectError("refused"),
        ],
    )
    result = await availability.probe_address("app.example.com", "93.184.216.34", 2)
    assert result["network_reachable"] and not result["webpage_accessible"]
    assert result["classification"] == "timeout"
    assert result["http"][0]["status"] == 200
    assert result["http"][1]["classification"] == "connection_failed"


def test_duplicate_fingerprints_and_filtered_export(tmp_path):
    with Inventory(tmp_path / "i.sqlite3") as store:
        for host in ("one.example.com", "two.example.com"):
            store.merge("example.com", DiscoveryResult("import", [{"hostname": host}]))
            store.save_check(
                "example.com",
                {
                    "hostname": host,
                    "checked_at": "2026-10-31",
                    "state": "online",
                    "http": [{"status": 403, **body_evidence(b"Forbidden", "text/html")}],
                },
            )
        assert store.report("example.com")["response_groups"][0]["host_count"] == 2
        path = store.export("example.com", tmp_path, filters={"only_webpages": True})
        assert json.loads(path.read_text())["response_groups"] == []


def test_legacy_output_folder_and_environment_precedence(monkeypatch, tmp_path):
    from src import workspace

    for key in ("WAYBACK_RECON_OUTPUT_DIR", "WAYBACK_ATLAS_OUTPUT_DIR", "DORK_SEARCHER_OUTPUT_DIR"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(workspace, "desktop_directory", lambda: tmp_path)
    legacy = tmp_path / "Wayback_Atlas_Results"
    legacy.mkdir()
    (legacy / "inventory.sqlite3").touch()
    assert workspace.result_directory() == legacy
    monkeypatch.setenv("WAYBACK_RECON_OUTPUT_DIR", str(tmp_path / "new"))
    monkeypatch.setenv("WAYBACK_ATLAS_OUTPUT_DIR", str(legacy))
    assert workspace.result_directory() == tmp_path / "new"
    assert workspace.result_directory(str(tmp_path / "explicit")) == tmp_path / "explicit"

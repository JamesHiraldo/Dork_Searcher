import json

import pytest
import requests

from src.discovery import collect, import_records
from src.searcher import cross_reference_with_subdomains
from src.workbench import duckduckgo_link, filter_archive


class Response:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class Session:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        value = next(self.payloads)
        if isinstance(value, Exception):
            raise value
        return Response(value)


def test_cross_reference_does_not_match_parent_string():
    assert cross_reference_with_subdomains(["https://notexample.com/"], ["example.com"]) == []


def test_ct_normalizes_wildcards_and_excludes_unrelated_names():
    session = Session(
        [
            [
                {
                    "name_value": "api.example.com\n*.dev.example.com\nnotexample.com",
                    "entry_timestamp": "2020-01-02",
                }
            ]
        ]
    )
    result = collect("example.com", "crtsh", session=session)
    assert [r["hostname"] for r in result.records] == ["api.example.com", "dev.example.com"]
    assert result.records[0]["observed_at"] == "2020-01-02"
    assert result.status == "ok"


def test_certspotter_retains_partial_results_when_pagination_stalls():
    page = [{"id": "same", "dns_names": ["dev.example.com"]}]
    result = collect("example.com", "certspotter", session=Session([page, page]))
    assert result.status == "partial"
    assert len(result.records) == 1
    assert "pagination stalled" in result.error


def test_rapiddns_paginates_and_preserves_record_dates():
    session = Session(
        [
            {
                "data": {
                    "total": 101,
                    "data": [{"subdomain": "old.example.com", "type": "A", "date": "2020-03-02"}],
                }
            },
            {"data": {"total": 101, "data": [{"subdomain": "new.example.com", "type": "CNAME"}]}},
        ]
    )
    result = collect("example.com", "rapiddns", api_key="test-key", session=session)
    assert len(result.records) == 2
    assert session.calls[1][1]["params"]["page"] == 2
    assert session.calls[0][1]["headers"] == {"X-API-KEY": "test-key"}
    assert result.records[0]["observed_at"] == "2020-03-02"


def test_completedns_does_not_enumerate_unrelated_nameservers():
    session = Session([{"domain": "example.com", "events": [{"nameservers": ["ns.other.net"]}]}])
    result = collect("example.com", "completedns", api_key="test-key", session=session)
    assert [r["hostname"] for r in result.records] == ["example.com"]
    assert result.metadata["events"][0]["nameservers"] == ["ns.other.net"]


def test_key_is_not_leaked_on_transport_error(monkeypatch):
    monkeypatch.setattr("src.discovery.time.sleep", lambda _: None)
    session = Session([requests.ConnectionError("https://api/?key=secret")] * 3)
    result = collect("example.com", "completedns", api_key="secret", session=session)
    assert result.status == "error"
    assert "secret" not in result.error


def test_missing_credentials_is_error_not_empty_success():
    result = collect("example.com", "rapiddns", session=Session([]))
    assert result.status == "error"
    assert "RAPIDDNS_API_KEY" in result.error


def test_import_csv_deduplicates_and_rejects_scope_confusion(tmp_path):
    path = tmp_path / "hosts.csv"
    path.write_text("subdomain,type\napi.example.com,A\napi.example.com,AAAA\nnotexample.com,A\n")
    result = import_records(str(path), "example.com")
    assert [r["hostname"] for r in result.records] == ["api.example.com"]
    assert result.metadata["rejected"] == 1


def test_local_dorks_fields_or_exclusions_and_duplicates():
    rows = [
        {"url": u}
        for u in [
            "https://api.example.com/api/app.js?redirect=",
            "https://api.example.com/api/app.js?redirect=",
            "https://api.example.com/admin",
            "https://dev.example.com/api/app.js",
        ]
    ]
    result = filter_archive(rows, "ext:js -host:dev.example.com OR path:/admin")
    assert [r["url"] for r in result] == [rows[0]["url"], rows[2]["url"]]
    assert len(filter_archive(rows, "param:redirect")) == 1
    with pytest.raises(ValueError):
        filter_archive(rows, "ext:js OR")


def test_import_rejects_mismatched_or_credential_bearing_urls(tmp_path):
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps(
            [
                {"hostname": "api.example.com", "url": "https://other.example.org/api"},
                {"hostname": "api.example.com", "url": "https://user:secret@api.example.com/"},
                {"hostname": "api.example.com", "url": "https://api.example.com/api?token=secret"},
            ]
        )
    )
    result = import_records(str(path), "example.com")
    assert len(result.records) == 1
    assert result.metadata["rejected"] == 2
    assert "secret" not in result.records[0]["url"]


def test_browser_link_encodes_query():
    assert "site%3Aexample.com" in duckduckgo_link("example.com", "inurl:api &x=1")
    assert "%26x%3D1" in duckduckgo_link("example.com", "inurl:api &x=1")

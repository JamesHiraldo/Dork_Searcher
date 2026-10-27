import asyncio
import io
import json

import pytest
from rich.console import Console

import src.availability as availability
import src.cli as cli
from src.diagnostics import diagnose
from src.discovery import DiscoveryResult, collect, import_records, request_json
from src.http_transport import read_json, retry_delay
from src.inventory import Inventory
from src.wayback import WaybackClient


class Response:
    def __init__(self, data, status=200, headers=None):
        self.data = data
        self.status_code = status
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, chunk_size):
        yield json.dumps(self.data).encode()

    def close(self):
        self.closed = True


class Session:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


def test_dns_evidence_keeps_distinct_types_and_addresses():
    records = [
        {"subdomain": "api.example.com", "timestamp": "2020-01-01", "type": kind, "value": value}
        for kind, value in [("A", "1.1.1.1"), ("A", "8.8.8.8"), ("AAAA", "2606:4700:4700::1111")]
    ]
    reply = Response({"data": {"total": 4, "data": [*records, records[0]]}})
    result = collect("example.com", "rapiddns", api_key="synthetic", session=Session(reply))
    assert len(result.records) == 3
    assert result.metadata["unique_hosts"] == 1
    assert result.metadata["duplicates"] == 1
    assert reply.closed


@pytest.mark.parametrize("bad_total", [None, [], {}, True, -1, "garbage"])
def test_bad_provider_total_is_partial_not_uncaught(bad_total):
    reply = Response({"data": {"total": bad_total, "data": [{"subdomain": "api.example.com"}]}})
    result = collect("example.com", "rapiddns", api_key="synthetic", session=Session(reply))
    assert result.status == "partial"
    assert "invalid total" in result.error


def test_ct_malformed_rows_preserve_previous_records():
    reply = Response([{"name_value": "api.example.com"}, None])
    result = collect("example.com", "crtsh", session=Session(reply))
    assert result.status == "partial"
    assert len(result.records) == 1


def test_certspotter_optional_bearer_key_not_saved():
    session = Session(Response([]))
    result = collect("example.com", "certspotter", api_key="private-test-key", session=session)
    assert session.calls[0]["headers"] == {"Authorization": "Bearer private-test-key"}
    assert "private-test-key" not in json.dumps(result.__dict__)
    assert session.calls[0]["stream"] is True


def test_download_limit_applies_without_content_length():
    with pytest.raises(ValueError, match="limit"):
        read_json(Response({"data": "too long"}), max_bytes=4)


def test_download_limit_applies_with_content_length():
    with pytest.raises(ValueError, match="limit"):
        read_json(Response({}, headers={"Content-Length": "999999999"}))


def test_response_closed_on_bad_status():
    reply = Response({}, status=403)
    with pytest.raises(ValueError, match="403"):
        request_json(Session(reply), "https://provider.invalid/")
    assert reply.closed


def test_backoff_is_bounded_and_understands_http_dates():
    assert retry_delay("99999999", 1) == 30
    assert retry_delay("-100", 1) == 0
    assert retry_delay("Wed, 21 Oct 2015 07:28:00 GMT", 1) == 0
    assert retry_delay("invalid", 2) == 2


@pytest.mark.parametrize("date", ["20260230", "202613", "0000", "20250101240000"])
def test_invalid_calendar_dates_rejected_without_requests(date):
    with pytest.raises(ValueError, match="calendar"):
        WaybackClient(session=Session()).fetch("example.com", from_date=date)


def test_jsonl_import_preserves_provenance_and_dns_evidence(tmp_path):
    path = tmp_path / "subfinder.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"host": "api.example.com", "source": "crtsh"},
                {"host": "api.example.com", "source": "wayback"},
                {"host": "api.other.example", "source": "crtsh"},
            ]
        )
    )
    result = import_records(str(path), "example.com")
    assert len(result.records) == 2
    assert {r["imported_source"] for r in result.records} == {"crtsh", "wayback"}
    assert result.metadata["rejected"] == 1


def test_bad_jsonl_reports_line_not_private_content(tmp_path):
    path = tmp_path / "broken.ndjson"
    path.write_text('"api.example.com"\nprivate-secret-invalid-json')
    with pytest.raises(ValueError, match="line 2") as error:
        import_records(str(path), "example.com")
    assert "secret" not in str(error.value)


def test_backup_preserves_evidence_runs_checks_and_refuses_overwrite(tmp_path):
    with Inventory(tmp_path / "inventory.sqlite3") as store:
        store.merge("example.com", DiscoveryResult("crtsh", [{"hostname": "api.example.com"}]))
        store.save_check(
            "example.com",
            {"hostname": "api.example.com", "checked_at": "2020-01-01", "state": "online"},
        )
        backup = store.backup(tmp_path / "backup.sqlite3")
        original = backup.read_bytes()
        with pytest.raises(FileExistsError):
            store.backup(backup)
        with pytest.raises(FileExistsError):
            store.backup(store.path)
        assert backup.read_bytes() == original
    with Inventory(backup) as restored:
        report = restored.report("example.com")
        assert report["assets"][0]["sources"] == ["crtsh"]
        assert report["assets"][0]["latest"]["state"] == "online"
        assert len(report["provider_runs"]) == 1


def test_doctor_never_prints_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTSPOTTER_API_KEY", "do-not-display-this")
    rows = diagnose(tmp_path)
    assert "do-not-display-this" not in json.dumps(rows)
    assert next(r for r in rows if r["check"] == "CERTSPOTTER_API_KEY")["detail"].startswith(
        "configured"
    )
    assert not (tmp_path / "inventory.sqlite3").exists()


def test_strict_discovery_rejects_partial_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "console", Console(file=io.StringIO()))
    monkeypatch.setattr(
        cli,
        "run_discovery",
        lambda *a, **kw: [
            DiscoveryResult(
                "crtsh",
                truncated=True,
                metadata={"processed": 1, "new_hosts": 1, "total_records": 1, "status": "paused"},
            )
        ],
    )
    base = ["--output-dir", str(tmp_path), "discover", "example.com", "--sources", "crtsh"]
    assert cli.main(base) == 0
    assert cli.main([*base, "--strict"]) == 1


def test_menu_eof_is_clean_shutdown(monkeypatch, tmp_path):
    def eof(*args):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    monkeypatch.setattr(cli, "console", Console(file=io.StringIO()))
    assert cli.main(["--output-dir", str(tmp_path)]) == 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 86401])
def test_invalid_watch_interval_rejected_before_network(tmp_path, value):
    with (
        Inventory(tmp_path / "inventory.sqlite3") as store,
        pytest.raises(ValueError, match="interval"),
    ):
        cli.monitor(store, "example.com", interval=value)


@pytest.mark.asyncio
async def test_one_host_failure_and_deadline_do_not_cancel_batch(monkeypatch):
    async def resolve(*args):
        return {"addresses": []}

    async def host(name, **kwargs):
        if name.startswith("slow"):
            await asyncio.sleep(1)
        if name.startswith("broken"):
            raise OSError("local configuration failure")
        return {"hostname": name, "checked_at": "2020-01-01", "state": "online"}

    monkeypatch.setattr(availability, "resolve_host", resolve)
    monkeypatch.setattr(availability, "check_host", host)
    saved = []
    result = await availability.sample_hosts(
        "example.com",
        ["slow.example.com", "broken.example.com", "api.example.com"],
        host_timeout=0.01,
        on_result=saved.append,
    )
    assert len(saved) == 3
    assert len({r["round_id"] for r in result}) == 1
    assert result[0]["state"] == "online"
    assert all(r["state"] == "unknown" for r in result[1:])
    assert all("duration_seconds" in r for r in result)

import json

from src.discovery import DiscoveryResult
from src.inventory import Inventory, availability_trend


def test_unknown_observations_do_not_invent_transitions():
    rows = [{"state": state} for state in ["online", "unknown", "unreachable", "dns_only"]]
    trend = availability_trend(rows)
    assert trend["transitions"] == 0
    assert trend["conclusive_samples"] == 2
    assert not trend["intermittent_candidate"]


def test_roundtrip_retains_history_and_source_errors(tmp_path):
    path = tmp_path / "inventory.sqlite3"
    discovery = DiscoveryResult("crtsh", [{"hostname": "api.example.com"}])
    with Inventory(path) as store:
        assert store.merge("example.com", discovery) == ["api.example.com"]
        assert store.merge("example.com", discovery) == []
        store.merge("example.com", DiscoveryResult("wayback", error="rate limited"))
        for state in ("online", "unreachable", "online"):
            store.save_check(
                "example.com",
                {"hostname": "api.example.com", "checked_at": "2026-01-01", "state": state},
            )
    with Inventory(path) as store:
        report = store.report("example.com")
        asset = report["assets"][0]
        assert asset["transitions"] == 2
        assert asset["intermittent_candidate"]
        assert len(asset["evidence"]) == 1
        assert report["provider_runs"][0]["status"] == "error"
        exported = store.export("example.com", tmp_path)
        assert json.loads(exported.read_text())["assets"][0]["latest"]["state"] == "online"
        assert list(tmp_path.glob("*_intermittent.txt"))[0].read_text().strip() == "api.example.com"


def test_dns_only_is_not_reported_as_http_alive():
    result = availability_trend([{"state": "dns_only"}])
    assert result["observed_availability_percent"] is None


def test_dns_only_monitor_detects_resolve_disappear_return():
    samples = [
        {"state": "dns_only", "dns_state": "resolved", "addresses": ["93.184.216.34"]},
        {"state": "nxdomain", "dns_state": "nxdomain", "addresses": []},
        {"state": "dns_only", "dns_state": "resolved", "addresses": ["93.184.216.34"]},
    ]
    for sample in samples:
        sample["http_requested"] = False
    result = availability_trend(samples)
    assert result["dns_transitions"] == 2
    assert result["intermittent_candidate"]
    assert result["observed_availability_percent"] is None
    assert result["conclusive_samples"] == 0


def test_exports_do_not_overwrite_previous_snapshot(tmp_path):
    with Inventory(tmp_path / "test.sqlite3") as store:
        first = store.export("example.com", tmp_path)
        second = store.export("example.com", tmp_path)
        assert first != second
        assert first.name.startswith("example.com_")
        assert first.exists() and second.exists()

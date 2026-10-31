import io
import json

import pytest
from rich.console import Console

from src import artifacts, cli
from src.discovery import DiscoveryResult
from src.inventory import Inventory


@pytest.mark.parametrize("failure", ["write", "flush", "replace"])
def test_failed_atomic_write_preserves_existing_file_and_cleans_temp(
    monkeypatch, tmp_path, failure
):
    destination = tmp_path / "report.json"
    destination.write_text("original")
    original_factory = artifacts.tempfile.NamedTemporaryFile

    class BrokenWriter:
        def __enter__(self):
            self.file = original_factory("w", dir=tmp_path, delete=False)
            self.name = self.file.name
            return self

        def write(self, text):
            self.file.write(text[:2])
            if failure == "write":
                raise OSError("disk full")

        def flush(self):
            if failure == "flush":
                raise OSError("flush failed")

        def __exit__(self, *args):
            self.file.close()

    def fail_replace(*args):
        raise OSError("replace failed")

    monkeypatch.setattr(artifacts.tempfile, "NamedTemporaryFile", lambda *a, **kw: BrokenWriter())
    if failure == "replace":
        monkeypatch.setattr(artifacts.os, "replace", fail_replace)
    with pytest.raises(OSError):
        artifacts.atomic_write_text(str(destination), "new report")
    assert destination.read_text() == "original"
    assert list(tmp_path.iterdir()) == [destination]


def seed(store):
    store.merge(
        "example.com",
        DiscoveryResult("import", [{"hostname": "a.example.com"}, {"hostname": "b.example.com"}]),
    )


def fake_checks(monkeypatch):
    calls = []

    async def sample(target, hosts, on_result, **kwargs):
        calls.append(hosts)
        for host in hosts:
            on_result(
                {
                    "hostname": host,
                    "checked_at": "2026-10-31",
                    "state": "dns_only",
                    "dns_state": "resolved",
                    "http_requested": False,
                }
            )
        return []

    monkeypatch.setattr(cli, "sample_hosts", sample)
    monkeypatch.setattr(cli, "console", Console(file=io.StringIO()))
    return calls


def test_only_unchecked_is_target_scoped_and_survives_reopen(tmp_path):
    with Inventory(tmp_path / "i.sqlite3") as store:
        seed(store)
        store.save_check(
            "example.com",
            {"hostname": "a.example.com", "checked_at": "2026-10-31", "state": "unknown"},
        )
    with Inventory(tmp_path / "i.sqlite3") as store:
        assert store.hosts("example.com", only_unchecked=True) == ["b.example.com"]
        assert store.hosts("other.example", only_unchecked=True) == []


def test_unchecked_check_has_no_duplicate_export_or_repeat_requests(monkeypatch, tmp_path):
    calls = fake_checks(monkeypatch)
    with Inventory(tmp_path / "inventory.sqlite3") as store:
        seed(store)
    args = ["--output-dir", str(tmp_path), "check", "example.com", "--only-unchecked"]
    assert cli.main(args) == 0
    assert cli.main(args) == 0
    assert len(calls) == 1
    assert len(list(tmp_path.rglob("report.html"))) == 1


@pytest.mark.parametrize("final_only,expected", [(False, 2), (True, 1)])
def test_watch_exports_each_round_or_final_only(monkeypatch, tmp_path, final_only, expected):
    calls = fake_checks(monkeypatch)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    with Inventory(tmp_path / "inventory.sqlite3") as store:
        seed(store)
        cli.monitor(store, "example.com", rounds=2, export_each_round=not final_only)
    assert len(calls) == 2
    assert len(list(tmp_path.rglob("report.html"))) == expected


def test_interrupt_between_rounds_keeps_completed_report(monkeypatch, tmp_path):
    fake_checks(monkeypatch)

    def interrupt(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", interrupt)
    with Inventory(tmp_path / "inventory.sqlite3") as store:
        seed(store)
        with pytest.raises(KeyboardInterrupt):
            cli.monitor(store, "example.com", rounds=2)
    reports = list(tmp_path.rglob("report.json"))
    assert len(reports) == 1
    assert len(json.loads(reports[0].read_text())["assets"]) == 2


def test_menu_import_automatically_exports(monkeypatch, tmp_path):
    hosts = tmp_path / "input.txt"
    hosts.write_text("a.example.com\n")
    answers = iter(["7", "example.com", str(hosts), "", "0"])
    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    monkeypatch.setattr(cli, "console", Console(file=io.StringIO()))
    cli.main_menu(tmp_path)
    assert len(list(tmp_path.rglob("report.html"))) == 1

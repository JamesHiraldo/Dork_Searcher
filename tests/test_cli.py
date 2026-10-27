import io
import json

import pytest
from rich.console import Console

import src.cli as cli
from src.workspace import result_directory


def test_output_directory_is_explicit_and_does_not_silently_fall_back(tmp_path):
    path = tmp_path / "output"
    assert result_directory(str(path)) == path
    assert path.is_dir()


def test_default_output_uses_desktop(monkeypatch, tmp_path):
    monkeypatch.setattr("src.workspace.desktop_directory", lambda: tmp_path)
    monkeypatch.delenv("WAYBACK_ATLAS_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("DORK_SEARCHER_OUTPUT_DIR", raising=False)
    assert result_directory() == tmp_path / "Wayback_Atlas_Results"


def test_dashboard_has_new_workflows_without_retired_providers(monkeypatch, tmp_path):
    stream = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=stream, width=100, color_system=None))
    cli.dashboard(tmp_path)
    output = stream.getvalue()
    assert "WAYBACK ATLAS" in output
    assert "Watch changes" in output
    assert "Archive dork workbench" in output
    assert "Google" not in output and "Dogpile" not in output


def test_import_and_export_work_end_to_end(tmp_path):
    hosts = tmp_path / "hosts.txt"
    hosts.write_text("dev.example.com\nold.example.com\n")
    output = tmp_path / "output"
    assert cli.main(["--output-dir", str(output), "import", "example.com", str(hosts)]) == 0
    assert cli.main(["--output-dir", str(output), "export", "example.com"]) == 0
    reports = list(output.glob("*.json"))
    assert reports
    data = json.loads(reports[0].read_text())
    assert len(data["assets"]) == 2
    assert all(a["latest"]["state"] == "unchecked" for a in data["assets"])


def test_watch_without_inventory_gives_actionable_error(tmp_path):
    assert cli.main(["--output-dir", str(tmp_path), "watch", "example.com"]) == 2


@pytest.mark.parametrize("width", [40, 80, 120])
def test_spider_dashboard_fits_terminal_width(monkeypatch, width):
    stream = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=stream, width=width, color_system=None))
    cli.dashboard(cli.Path("results"))
    output = stream.getvalue()
    assert "(o)" in output and "(___)" in output
    assert "DISCOVER & CHECK" in output
    assert "YOUR WORKSPACE" in output
    assert "Enter" in output
    assert all(len(line) <= width for line in output.splitlines())


def test_ascii_banner_and_legacy_cmd_rendering(monkeypatch):
    cli.SPIDER.encode("ascii")
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(
        cli, "console", Console(file=stream, width=80, color_system=None, legacy_windows=True)
    )
    cli.dashboard(cli.Path("results"))
    stream.flush()
    assert b"WAYBACK ATLAS" in buffer.getvalue()


def test_choice_retries_blank_and_invalid_without_long_choice_list(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=stream, width=80))
    answers = iter(["", "bad", "13", " 10 "])
    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    assert cli.ask_choice(cli.MENU_LABELS, "Enter a number (0 to exit)") == "10"
    output = stream.getvalue()
    assert output.count("Please type one") == 3
    assert "0/1/2/3" not in output


def test_numbered_menu_default_is_explained(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=stream, width=80))
    monkeypatch.setattr("builtins.input", lambda *args: "")
    assert cli.numbered_menu("CHECKS", {"1": "DNS + HTTP", "2": "DNS only"}, "1") == "1"
    assert "Enter = 1: DNS + HTTP" in stream.getvalue()


@pytest.mark.parametrize(
    "selection,source",
    [
        ("1", "crtsh"),
        ("2", "certspotter"),
        ("3", "rapiddns"),
        ("4", "completedns"),
        ("5", "commoncrawl"),
    ],
)
def test_source_menu_routes_numbers_without_network(monkeypatch, tmp_path, selection, source):
    monkeypatch.setattr(cli, "console", Console(file=io.StringIO(), width=80))
    answers = iter(["3", "example.com", selection, "", "", "0"])
    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    calls = []
    monkeypatch.setattr(cli, "discover", lambda store, target, sources, **kw: calls.append(sources))
    cli.main_menu(tmp_path)
    assert calls == [[source]]


def test_numbered_check_mode_and_back_do_not_trigger_unselected_work(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "console", Console(file=io.StringIO(), width=80))
    answers = iter(["4", "example.com", "0", "4", "example.com", "2", "", "0"])
    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    calls = []
    monkeypatch.setattr(cli, "monitor", lambda store, target, **kw: calls.append(kw))
    cli.main_menu(tmp_path)
    assert len(calls) == 1 and calls[0]["http"] is False


def test_numbered_dork_save_and_back(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "console", Console(file=io.StringIO(), width=80))
    answers = iter(["2", "ext:js", "0"])
    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    with cli.Inventory(tmp_path / "inventory.sqlite3") as store:
        cli.workbench(store, "example.com", tmp_path)
        cli.workbench(store, "example.com", tmp_path)
    assert (tmp_path / "custom_dorks.txt").read_text().strip() == "ext:js"

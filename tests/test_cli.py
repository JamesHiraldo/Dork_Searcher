import io
import json

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

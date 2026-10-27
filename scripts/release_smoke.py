"""Offline smoke test of the actual packaged executable, with disposable synthetic data."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default="dist/wayback_atlas.exe")
    parser.add_argument("--expected-version", default="3.3.0")
    args = parser.parse_args()
    executable = Path(args.exe).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="atlas-release-smoke-") as temporary:
        directory = Path(temporary)

        def run(*arguments: str, input_text: str | None = None) -> str:
            print(f"Checking packaged {arguments[0] if arguments else 'menu'}...", flush=True)
            result = subprocess.run(
                [str(executable), "--output-dir", str(directory), *arguments],
                input=input_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(
                    f"EXE smoke failed: {arguments}\n{result.stdout}\n{result.stderr}"
                )
            return result.stdout

        assert args.expected_version in run("--version")
        assert "doctor" in run("--help")
        assert "--cc-index" in run("discover", "--help")
        assert "--max-pages" in run("resume", "--help")
        assert json.loads(run("runs", "--json")) == []
        assert "TLS" in run("doctor")
        hosts = directory / "hosts.txt"
        hosts.write_text(
            "api.example.com\nhttps://old.example.com/api?version=1\n", encoding="utf-8"
        )
        run("import", "example.com", str(hosts))
        assert "api.example.com" in run("inventory", "example.com")
        run("dorks", "example.com", "path:/api")
        assert len(json.loads((directory / "archive_matches.json").read_text())) == 1
        backup = directory / "copy.sqlite3"
        run("backup", str(backup))
        with closing(sqlite3.connect(backup)) as database:
            assert database.execute("SELECT count(*) FROM assets").fetchone()[0] == 2
        run("export", "example.com")
        reports = list((directory / "reports" / "example.com").glob("*/report.json"))
        assert len(reports) == 2  # Import auto-export and explicit export, separate bundles.
        assert all((path.parent / "inventory.csv").is_file() for path in reports)
        assert all(
            "WAYBACK ATLAS" in (path.parent / "report.html").read_text(encoding="utf-8")
            for path in reports
        )
        assert not list(directory.glob("*.csv"))
        # Seed a durable mid-page fixture, then exercise the frozen resume code with no network.
        job = "offline-smoke-checkpoint"
        with (
            closing(sqlite3.connect(directory / "inventory.sqlite3")) as database,
            database,
        ):
            database.execute(
                "INSERT INTO discovery_jobs VALUES (?,?,?,?,?)",
                (
                    job,
                    1,
                    "example.com",
                    "2026-10-26",
                    json.dumps({"sources": ["commoncrawl"]}),
                ),
            )
            pending = {
                "records": [{"hostname": "staged.example.com", "crawl_index": "CC-MAIN-2026-10"}],
                "offset": 0,
                "metadata": {},
                "cursor": {},
                "done": True,
            }
            state = {
                "status": "paused",
                "cursor": {},
                "pending": pending,
                "pages": 1,
                "records": 0,
                "error": None,
            }
            database.execute(
                "INSERT INTO discovery_checkpoints VALUES (?,?,?,?,?)",
                (
                    job,
                    "commoncrawl",
                    0,
                    "2026-10-26",
                    json.dumps(state),
                ),
            )
        assert "complete" in run("resume", job, "--strict")
        assert "staged.example.com" in run("inventory", "example.com")
        assert (
            json.loads(run("runs", "--json"))[0]["sources"]["commoncrawl"]["status"] == "complete"
        )
        output = run(input_text="\ninvalid\n11\n1\n\n0\n")
        assert "(o)" in output and "Please type one" in output and "TLS" in output
        assert "0/1/2/3" not in output
        assert "Input closed" in run(input_text="")
    print(
        "Packaged release smoke passed: version, TLS/DNS doctor, import, inventory, "
        "dorks, backup, export, checkpoint resume, Common Crawl flags, UI and EOF."
    )


if __name__ == "__main__":
    main()

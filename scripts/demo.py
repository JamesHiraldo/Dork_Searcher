"""Offline release smoke test and terminal preview using clearly synthetic example.com data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cli import dashboard, show_inventory  # noqa: E402
from src.discovery import DiscoveryResult  # noqa: E402
from src.inventory import Inventory, utc_now  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Separate demo output folder")
    args = parser.parse_args()
    directory = Path(args.output).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    import src.cli as cli

    display = Console(record=True, width=112, force_terminal=True, color_system="truecolor")
    cli.console = display
    with Inventory(directory / "demo.sqlite3") as store:
        store.merge(
            "example.com",
            DiscoveryResult(
                "wayback",
                [
                    {
                        "hostname": "old.example.com",
                        "url": "https://old.example.com/api?id=1",
                        "observed_at": "20100101000000",
                        "archive_status": "200",
                    },
                    {"hostname": "api.example.com", "url": "https://api.example.com/app.js"},
                ],
            ),
        )
        store.merge(
            "example.com",
            DiscoveryResult(
                "crtsh",
                [
                    {"hostname": "staging.example.com"},
                    {"hostname": "api.example.com"},
                ],
            ),
        )
        for host, sequence in {
            "api.example.com": ["online"],
            "old.example.com": ["nxdomain"],
            "staging.example.com": ["online", "unreachable", "online"],
        }.items():
            for state in sequence:
                store.save_check(
                    "example.com", {"hostname": host, "state": state, "checked_at": utc_now()}
                )
        dashboard(directory)
        display.print("SYNTHETIC DEMO DATA / no network requests")
        show_inventory(store, "example.com")
        store.export("example.com", directory)
    display.save_svg(
        str(directory / "terminal-preview.svg"), title="Wayback-Recon / synthetic demo"
    )


if __name__ == "__main__":
    main()

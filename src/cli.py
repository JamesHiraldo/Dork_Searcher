"""Wayback Atlas terminal dashboard and scriptable workflows."""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from .artifacts import atomic_write_text, save_json
from .availability import sample_hosts
from .discovery import collect, import_records
from .inventory import Inventory
from .scope import normalize_hostname
from .workbench import RESOURCES, TEMPLATES, duckduckgo_link, filter_archive
from .workspace import result_directory

console = Console(highlight=False, markup=False)
SOURCES = ("wayback", "crtsh", "certspotter", "rapiddns", "completedns")
NOTICE = "Use only on assets you own or have permission to assess."


def dashboard(directory: Path) -> None:
    title = Text("WAYBACK ATLAS", style="bold cyan")
    title.append("  /  3.0\n", style="dim")
    title.append("Archive discovery  /  Subdomains  /  Availability history", style="white")
    console.print(Panel(title, border_style="cyan", padding=(1, 2)))
    table = Table(box=box.SIMPLE, expand=True, show_header=True)
    table.add_column("KEY", style="bold cyan", width=4)
    table.add_column("WORKFLOW", style="bold white")
    table.add_column("WHAT YOU GET", style="dim")
    for row in [
        ("1", "Discover & merge", "Wayback + CT; persistent source evidence"),
        ("2", "Wayback archive", "Historical URLs, dates, status and MIME types"),
        ("3", "Subdomain sources", "CT, RapidDNS, CompleteDNS history"),
        ("4", "Check availability", "DNS + HTTP; responses, failures and unknowns"),
        ("5", "Watch changes", "Repeated checks; intermittent candidates"),
        ("6", "Inventory & history", "First/last discovery and latest state"),
        ("7", "Import discoveries", "TXT / CSV / JSON, including RapidDNS exports"),
        ("8", "Archive dork workbench", "Local queries, custom templates, DDG links"),
        ("9", "Research resources", "Your four requested sites"),
        ("10", "Export reports", "JSON + CSV + alive/intermittent host lists"),
        ("0", "Exit", "Everything already saved stays in the inventory"),
    ]:
        table.add_row(*row)
    console.print(table)
    console.print(Text(f"OUTPUT  {directory}", style="dim"))
    console.print(Text(NOTICE, style="yellow"))


def show_inventory(store: Inventory, target: str) -> None:
    report = store.report(target)
    table = Table(title=f"{target} / {len(report['assets'])} hosts", box=box.ROUNDED)
    table.add_column("Hostname", overflow="fold", min_width=20)
    for column in ("Sources", "Latest state", "Changes\nHTTP/DNS", "Found"):
        table.add_column(column, overflow="fold")
    for asset in report["assets"][:200]:
        state = asset["latest"]["state"]
        color = "green" if state == "online" else "yellow" if state == "unchecked" else "white"
        if asset["intermittent_candidate"]:
            state += " / intermittent?"
        table.add_row(
            asset["hostname"],
            ", ".join(asset["sources"]),
            Text(state, style=color),
            f"{asset['transitions']}/{asset['dns_transitions']}",
            asset["first_seen"][:10],
        )
    console.print(table)
    if len(report["assets"]) > 200:
        console.print("Preview limited to 200 hosts; export contains all records.")
    console.print(
        "'New' means newly found here. No response does not prove a permanently dead host."
    )


def discover(store: Inventory, target: str, sources: list[str], **options: Any) -> list[str]:
    statuses = []
    for source in sources:
        key_name = {"rapiddns": "RAPIDDNS_API_KEY", "completedns": "COMPLETEDNS_API_KEY"}.get(
            source
        )
        key = os.getenv(key_name, "") if key_name else ""
        with console.status(f"Collecting {source} for {target}...", spinner="line"):
            result = collect(target, source, api_key=key, **options)
            new = store.merge(target, result)
        message = (
            f"{source}: {len(result.records)} records / {len(new)} new hosts / {result.status}"
        )
        if result.truncated:
            message += " / limit reached (partial coverage)"
        console.print(Text(message, style="cyan"))
        if result.error:
            console.print(Text(result.error, style="yellow"))
        statuses.append(result.status)
    return statuses


def monitor(
    store: Inventory,
    target: str,
    *,
    rounds: int = 1,
    interval: float = 60,
    http: bool = True,
    concurrency: int = 8,
    timeout: float = 5,
) -> None:
    if rounds < 1 or rounds > 10000 or interval < 10:
        raise ValueError("Use 1-10000 rounds with an interval of at least 10 seconds")
    if not 1 <= concurrency <= 50 or not 0 < timeout <= 60:
        raise ValueError("Concurrency must be 1-50; timeout must be >0 and <=60 seconds")
    hosts = store.hosts(target)
    if not hosts:
        raise ValueError("No hosts stored for this target. Discover or import first.")
    for number in range(rounds):
        console.print(f"Sample {number + 1}/{rounds}: {len(hosts)} hosts; Ctrl+C stops safely")
        with Progress(
            SpinnerColumn("line"), TextColumn("{task.description}"), console=console
        ) as progress:
            task = progress.add_task(
                "Checking DNS and HTTP" if http else "Checking DNS", total=len(hosts)
            )

            def completed(sample: dict[str, Any], current_task: TaskID = task) -> None:
                store.save_check(target, sample)
                progress.update(
                    current_task, advance=1, description=f"Checked {sample['hostname']}"
                )

            asyncio.run(
                sample_hosts(
                    target,
                    hosts,
                    concurrency=concurrency,
                    timeout=timeout,
                    http=http,
                    on_result=completed,
                )
            )
        show_inventory(store, target)
        if number + 1 < rounds:
            console.print(f"Next round in {interval:g}s. Each sample is already saved.")
            time.sleep(interval)


def query_archive(store: Inventory, target: str, query: str) -> list[dict[str, Any]]:
    rows = [e for a in store.report(target)["assets"] for e in a["evidence"] if e.get("url")]
    return filter_archive(rows, query)


def ask_target(store: Inventory) -> str:
    targets = store.targets()
    if targets:
        console.print("Stored targets: " + ", ".join(targets))
    return normalize_hostname(Prompt.ask("Target domain", console=console))


def ask_int(label: str, default: int, minimum: int, maximum: int) -> int:
    while True:
        try:
            value = int(Prompt.ask(label, default=str(default), console=console))
            if minimum <= value <= maximum:
                return value
        except ValueError:
            pass
        console.print(f"Enter a whole number from {minimum} through {maximum}.")


def resource_menu() -> None:
    for index, (name, url, detail) in enumerate(RESOURCES, 1):
        console.print(f"{index}. {name}\n   {url}\n   {detail}")
    choice = Prompt.ask("Open resource (0 returns)", choices=["0", "1", "2", "3", "4"], default="0")
    if choice != "0":
        webbrowser.open(RESOURCES[int(choice) - 1][1])


def workbench(store: Inventory, target: str, directory: Path) -> None:
    path = directory / "custom_dorks.txt"
    custom = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    console.print("Local syntax: path:/api/  ext:js  param:redirect  host:dev.example.com")
    console.print('Combine terms with AND (spaces), OR, "quoted phrases", or -exclusions.')
    console.print("Templates: " + " | ".join([*TEMPLATES, *custom]))
    action = Prompt.ask("Mode", choices=["filter", "add", "browser"], default="filter")
    query = Prompt.ask("Query / template", console=console).strip()
    if not query or len(query) > 2000:
        raise ValueError("Query must contain 1-2000 characters")
    if action == "add":
        atomic_write_text(str(path), "\n".join(dict.fromkeys([*custom, query])) + "\n")
        console.print(f"Saved to {path}")
    elif action == "browser":
        url = duckduckgo_link(target, query)
        console.print(url)
        if Prompt.ask("Open in browser?", choices=["y", "n"], default="n") == "y":
            webbrowser.open(url)
    else:
        rows = query_archive(store, target, query)
        save_json(str(directory / "archive_matches.json"), rows)
        for row in rows[:30]:
            console.print(row["url"])
        console.print(f"{len(rows)} matches saved to {directory / 'archive_matches.json'}")


def main_menu(directory: Path) -> None:
    with Inventory(directory / "inventory.sqlite3") as store:
        while True:
            dashboard(directory)
            choice = Prompt.ask("Select", choices=[str(n) for n in range(11)], default="0")
            if choice == "0":
                return
            try:
                if choice == "9":
                    resource_menu()
                    continue
                target = ask_target(store)
                if choice in ("1", "2", "3"):
                    sources = ["wayback", "crtsh", "certspotter"] if choice == "1" else ["wayback"]
                    if choice == "3":
                        source = Prompt.ask("Source", choices=list(SOURCES[1:]), default="crtsh")
                        sources = [source]
                    limit = ask_int("Maximum records per source", 5000, 1, 100000)
                    start = end = None
                    if choice == "2":
                        start = Prompt.ask("From year/date (blank = all)", default="") or None
                        end = Prompt.ask("To year/date (blank = all)", default="") or None
                    discover(store, target, sources, limit=limit, from_date=start, to_date=end)
                    show_inventory(store, target)
                elif choice in ("4", "5"):
                    rounds = ask_int("Number of samples", 5, 1, 10000) if choice == "5" else 1
                    interval = (
                        ask_int("Seconds between samples", 60, 10, 86400) if rounds > 1 else 60
                    )
                    mode = Prompt.ask("Checks", choices=["dns-http", "dns"], default="dns-http")
                    monitor(
                        store, target, rounds=rounds, interval=interval, http=mode == "dns-http"
                    )
                elif choice == "6":
                    show_inventory(store, target)
                elif choice == "7":
                    path = Prompt.ask("Import file path", console=console).strip('"')
                    result = import_records(path, target)
                    new = store.merge(target, result)
                    console.print(
                        f"Imported {len(result.records)} hosts; {len(new)} new; "
                        f"{result.metadata['rejected']} unrelated/invalid rows skipped"
                    )
                elif choice == "8":
                    workbench(store, target, directory)
                elif choice == "10":
                    console.print(f"Exported: {store.export(target, directory)}")
            except KeyboardInterrupt:
                console.print("Cancelled. Completed observations remain saved.")
            except (ValueError, OSError, sqlite3.Error) as exc:
                console.print(Text(str(exc), style="red"))
            Prompt.ask("Press Enter to return", default="", console=console)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wayback Atlas: archives, subdomains and availability"
    )
    parser.add_argument("--output-dir", help="Output and database folder; defaults to Desktop")
    sub = parser.add_subparsers(dest="command")
    for name in ("discover", "check", "watch", "inventory", "export", "import", "dorks"):
        p = sub.add_parser(name)
        p.add_argument("target", help="Root domain; all its discovered child hosts are included")
        if name == "discover":
            p.add_argument("--sources", nargs="+", choices=SOURCES, default=list(SOURCES[:3]))
            p.add_argument("--limit", type=int, default=5000)
            p.add_argument("--max-pages", type=int, default=20)
            p.add_argument("--from-date")
            p.add_argument("--to-date")
        elif name in ("check", "watch"):
            p.add_argument("--dns-only", action="store_true")
            p.add_argument("--concurrency", type=int, default=8)
            p.add_argument("--timeout", type=float, default=5)
            if name == "watch":
                p.add_argument("--rounds", type=int, default=5)
                p.add_argument("--interval", type=float, default=60)
        elif name == "import":
            p.add_argument("file")
        elif name == "dorks":
            p.add_argument("query")
    sub.add_parser("resources")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        directory = result_directory(args.output_dir)
        if not args.command:
            main_menu(directory)
            return 0
        if args.command == "resources":
            for name, url, detail in RESOURCES:
                console.print(f"{name}: {url}\n  {detail}")
            return 0
        target = normalize_hostname(args.target)
        console.print(NOTICE)
        statuses = []
        with Inventory(directory / "inventory.sqlite3") as store:
            if args.command == "discover":
                statuses = discover(
                    store,
                    target,
                    args.sources,
                    limit=args.limit,
                    max_pages=args.max_pages,
                    from_date=args.from_date,
                    to_date=args.to_date,
                )
            elif args.command in ("check", "watch"):
                monitor(
                    store,
                    target,
                    http=not args.dns_only,
                    concurrency=args.concurrency,
                    timeout=args.timeout,
                    rounds=getattr(args, "rounds", 1),
                    interval=getattr(args, "interval", 60),
                )
            elif args.command == "import":
                result = import_records(args.file, target)
                new = store.merge(target, result)
                console.print(f"Imported {len(result.records)} records; {len(new)} new hosts")
            elif args.command == "inventory":
                show_inventory(store, target)
            elif args.command == "dorks":
                rows = query_archive(store, target, args.query)
                save_json(str(directory / "archive_matches.json"), rows)
                console.print(f"{len(rows)} matches saved to {directory / 'archive_matches.json'}")
            if args.command in ("discover", "export", "check", "watch", "import"):
                console.print(f"Report: {store.export(target, directory)}")
        return 1 if statuses and all(s == "error" for s in statuses) else 0
    except KeyboardInterrupt:
        console.print("Stopped. Completed observations remain in the database.")
        return 130
    except (ValueError, OSError, sqlite3.Error) as exc:
        console.print(Text(str(exc), style="red"))
        return 2


if __name__ == "__main__":
    sys.exit(main())

"""Wayback Atlas terminal dashboard and scriptable workflows."""

from __future__ import annotations

import argparse
import asyncio
import math
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

from . import __version__
from .artifacts import atomic_write_text, save_json
from .availability import sample_hosts
from .diagnostics import diagnose
from .discovery import collect, import_records
from .inventory import Inventory
from .scope import normalize_hostname
from .workbench import RESOURCES, TEMPLATES, duckduckgo_link, filter_archive
from .workspace import result_directory

console = Console(highlight=False, markup=False)
SOURCES = ("wayback", "crtsh", "certspotter", "rapiddns", "completedns")
NOTICE = "Use only on assets you own or have permission to assess."
SPIDER = r"""        |
    \   |   /
     \ (o) /
  ----(   )----
     /(___)\
    / /   \ \
   / /     \ \
""".rstrip()
MENU_LABELS = {
    "1": "Discover & merge",
    "2": "Wayback archive",
    "3": "Subdomain sources",
    "4": "Check availability",
    "5": "Watch changes",
    "6": "Inventory & history",
    "7": "Import discoveries",
    "8": "Archive dork workbench",
    "9": "Research resources",
    "10": "Export reports",
    "11": "Diagnostics & backup",
    "0": "Exit",
}


def menu_panel(title: str, options: dict[str, str]) -> Panel:
    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(style="bold cyan", width=3, no_wrap=True)
    table.add_column(style="white", ratio=1)
    for key, label in options.items():
        table.add_row(f"{key:>2}", label)
    return Panel(table, title=Text(title, style="bold cyan"), border_style="dim cyan")


def ask_choice(options: dict[str, str], label: str, default: str | None = None) -> str:
    """A short numbered prompt, without Rich's long slash-separated choice list."""
    if default is not None and default not in options:
        raise ValueError("Menu default must be an available option")
    hint = f" (Enter = {default}: {options[default]})" if default else ""
    while True:
        choice = Prompt.ask(
            Text(label + hint, style="bold cyan"),
            default=default if default is not None else "",
            show_default=False,
            console=console,
        ).strip()
        if choice in options:
            return choice
        console.print(
            Text("Please type one of the menu numbers, then press Enter.", style="yellow")
        )


def numbered_menu(title: str, options: dict[str, str], default: str | None = None) -> str:
    console.print(menu_panel(title, options))
    return ask_choice(options, "Enter a number", default)


def dashboard(directory: Path) -> None:
    title = Text("WAYBACK ATLAS\n", style="bold cyan")
    title.append(f"THE RECON WEB  /  {__version__}\n\n", style="bold magenta")
    title.append("Find the past. Track the present.\n", style="white")
    title.append("Archives / Subdomains / Availability", style="dim")
    header = Table.grid(padding=(0, 2), expand=True)
    if console.width >= 76:
        header.add_column(width=19, no_wrap=True)
        header.add_column(ratio=1)
        header.add_row(Text(SPIDER, style="bold magenta"), title)
    else:
        header.add_column(ratio=1)
        header.add_row(Text(SPIDER, style="bold magenta"))
        header.add_row(title)
    console.print(Panel(header, border_style="cyan", padding=(0, 1)))
    console.print(Text("START HERE   1 Discover  ->  4 Check  ->  5 Watch", style="dim"))
    left = menu_panel("DISCOVER & CHECK", {str(n): MENU_LABELS[str(n)] for n in range(1, 6)})
    right = menu_panel("YOUR WORKSPACE", {str(n): MENU_LABELS[str(n)] for n in range(6, 12)})
    if console.width >= 76:
        columns = Table.grid(padding=(0, 1), expand=True)
        columns.add_column(ratio=1)
        columns.add_column(ratio=1)
        columns.add_row(left, right)
        console.print(columns)
    else:
        console.print(left, right)
    console.print(Text(" 0  Exit    |    Choose a number, then press Enter.", style="bold white"))
    console.print(Text(f"Results: {directory}", style="dim"), overflow="fold")
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


def discover(
    store: Inventory, target: str, sources: list[str], *, strict: bool = False, **options: Any
) -> list[str]:
    statuses = []
    for source in sources:
        key_name = {
            "rapiddns": "RAPIDDNS_API_KEY",
            "completedns": "COMPLETEDNS_API_KEY",
            "certspotter": "CERTSPOTTER_API_KEY",
        }.get(source)
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
        statuses.append(
            "incomplete" if strict and (result.error or result.truncated) else result.status
        )
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
    host_timeout: float = 45,
) -> None:
    if rounds < 1 or rounds > 10000 or not math.isfinite(interval) or not 10 <= interval <= 86400:
        raise ValueError("Use 1-10000 rounds with an interval of 10-86400 seconds")
    if not 1 <= concurrency <= 50 or not 0 < timeout <= 60:
        raise ValueError("Concurrency must be 1-50; timeout must be >0 and <=60 seconds")
    if not math.isfinite(host_timeout) or not 0 < host_timeout <= 600:
        raise ValueError("Host timeout must be >0 and <=600 seconds")
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
                    host_timeout=host_timeout,
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
    return normalize_hostname(
        Prompt.ask("Target domain (for example, example.com)", console=console)
    )


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
    options = {str(index): name for index, (name, _, _) in enumerate(RESOURCES, 1)}
    options["0"] = "Back to main menu"
    console.print("0. Back to main menu")
    choice = ask_choice(options, "Open which resource?", default="0")
    if choice != "0":
        webbrowser.open(RESOURCES[int(choice) - 1][1])


def workbench(store: Inventory, target: str, directory: Path) -> bool:
    path = directory / "custom_dorks.txt"
    custom = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    console.print("Local syntax: path:/api/  ext:js  param:redirect  host:dev.example.com")
    console.print('Combine terms with AND (spaces), OR, "quoted phrases", or -exclusions.')
    console.print("Templates: " + " | ".join([*TEMPLATES, *custom]))
    selected = numbered_menu(
        "DORK WORKBENCH",
        {
            "1": "Filter collected URLs",
            "2": "Save a custom template",
            "3": "DuckDuckGo browser link",
            "0": "Back to main menu",
        },
        default="1",
    )
    if selected == "0":
        return False
    action = {"1": "filter", "2": "add", "3": "browser"}[selected]
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
    return True


def main_menu(directory: Path) -> None:
    with Inventory(directory / "inventory.sqlite3") as store:
        while True:
            dashboard(directory)
            choice = ask_choice(MENU_LABELS, "Enter a number (0 to exit)")
            if choice == "0":
                return
            console.rule(Text(f"{choice}. {MENU_LABELS[choice]}", style="bold cyan"))
            try:
                if choice == "9":
                    resource_menu()
                    continue
                if choice == "11":
                    action = numbered_menu(
                        "SYSTEM TOOLS",
                        {
                            "1": "Local diagnostics (no network)",
                            "2": "Back up the complete inventory",
                            "0": "Back to main menu",
                        },
                    )
                    if action == "1":
                        show_diagnostics(directory)
                    elif action == "2":
                        destination = Prompt.ask(
                            "New backup file path (must not already exist)", console=console
                        ).strip('"')
                        if not destination:
                            raise ValueError("Enter a new backup file path")
                        console.print(f"Backup saved: {store.backup(destination)}")
                    else:
                        continue
                    Prompt.ask(
                        "Press Enter to return to the main menu",
                        default="",
                        show_default=False,
                        console=console,
                    )
                    continue
                target = ask_target(store)
                if choice in ("1", "2", "3"):
                    sources = ["wayback", "crtsh", "certspotter"] if choice == "1" else ["wayback"]
                    if choice == "3":
                        selection = numbered_menu(
                            "CHOOSE A SOURCE",
                            {
                                "1": "crt.sh - certificate names",
                                "2": "Cert Spotter - certificate names",
                                "3": "RapidDNS - API key required",
                                "4": "CompleteDNS - nameserver history (API key)",
                                "0": "Back to main menu",
                            },
                            default="1",
                        )
                        if selection == "0":
                            continue
                        source = SOURCES[int(selection)]
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
                    mode = numbered_menu(
                        "WHAT SHOULD WE CHECK?",
                        {
                            "1": "DNS + HTTP - check web availability",
                            "2": "DNS only - no HTTP requests",
                            "0": "Back to main menu",
                        },
                        default="1",
                    )
                    if mode == "0":
                        continue
                    monitor(store, target, rounds=rounds, interval=interval, http=mode == "1")
                elif choice == "6":
                    show_inventory(store, target)
                elif choice == "7":
                    path = Prompt.ask("Import file path", console=console).strip('"')
                    result = import_records(path, target)
                    new = store.merge(target, result)
                    console.print(
                        f"Imported {len(result.records)} records; {len(new)} new hosts; "
                        f"{result.metadata['rejected']} unrelated/invalid rows skipped"
                    )
                    if result.truncated:
                        console.print("Import limit reached; some evidence was omitted.")
                elif choice == "8":
                    if not workbench(store, target, directory):
                        continue
                elif choice == "10":
                    console.print(f"Exported: {store.export(target, directory)}")
            except KeyboardInterrupt:
                console.print("Cancelled. Completed observations remain saved.")
            except (ValueError, OSError, sqlite3.Error) as exc:
                console.print(Text(str(exc), style="red"))
            Prompt.ask(
                "Press Enter to return to the main menu",
                default="",
                show_default=False,
                console=console,
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wayback Atlas: archives, subdomains and availability"
    )
    parser.add_argument("--output-dir", help="Output and database folder; defaults to Desktop")
    parser.add_argument("--version", action="version", version=f"Wayback Atlas {__version__}")
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
            p.add_argument(
                "--strict", action="store_true", help="Exit 1 on any provider error or truncation"
            )
        elif name in ("check", "watch"):
            p.add_argument("--dns-only", action="store_true")
            p.add_argument("--concurrency", type=int, default=8)
            p.add_argument("--timeout", type=float, default=5)
            p.add_argument(
                "--host-timeout",
                type=float,
                default=45,
                help="Overall per-host deadline in seconds (max 600)",
            )
            if name == "watch":
                p.add_argument("--rounds", type=int, default=5)
                p.add_argument("--interval", type=float, default=60)
        elif name == "import":
            p.add_argument("file")
        elif name == "dorks":
            p.add_argument("query")
    sub.add_parser("resources")
    sub.add_parser("doctor", help="Local runtime, TLS, DNS and database checks; no network")
    backup = sub.add_parser("backup", help="Consistent full inventory backup; never overwrite")
    backup.add_argument("destination", help="New SQLite backup file path")
    return parser


def show_diagnostics(directory: Path) -> int:
    rows = diagnose(directory)
    table = Table(title="Local diagnostics / no network requests", box=box.ROUNDED)
    for label in ("Check", "Status", "Detail"):
        table.add_column(label, overflow="fold")
    for row in rows:
        color = "red" if row["status"] == "error" else "green" if row["status"] == "ok" else "cyan"
        table.add_row(row["check"], Text(row["status"], style=color), row["detail"])
    console.print(table)
    return int(any(row["status"] == "error" for row in rows))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        directory = result_directory(args.output_dir)
        if not args.command:
            main_menu(directory)
            return 0
        if args.command == "doctor":
            return show_diagnostics(directory)
        if args.command == "backup":
            if not (directory / "inventory.sqlite3").is_file():
                raise ValueError("No inventory database to back up; discover or import first")
            with Inventory(directory / "inventory.sqlite3") as store:
                console.print(f"Backup saved: {store.backup(args.destination)}")
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
                    strict=args.strict,
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
                    host_timeout=args.host_timeout,
                    rounds=getattr(args, "rounds", 1),
                    interval=getattr(args, "interval", 60),
                )
            elif args.command == "import":
                result = import_records(args.file, target)
                new = store.merge(target, result)
                console.print(f"Imported {len(result.records)} records; {len(new)} new hosts")
                console.print(f"Skipped {result.metadata['rejected']} invalid/unrelated records")
                if result.truncated:
                    console.print("Import limit reached; some evidence was omitted.")
            elif args.command == "inventory":
                show_inventory(store, target)
            elif args.command == "dorks":
                rows = query_archive(store, target, args.query)
                save_json(str(directory / "archive_matches.json"), rows)
                console.print(f"{len(rows)} matches saved to {directory / 'archive_matches.json'}")
            if args.command in ("discover", "export", "check", "watch", "import"):
                console.print(f"Report: {store.export(target, directory)}")
        return (
            1
            if "incomplete" in statuses or (statuses and all(s == "error" for s in statuses))
            else 0
        )
    except EOFError:
        console.print("Input closed. Completed observations remain saved.")
        return 0
    except KeyboardInterrupt:
        console.print("Stopped. Completed observations remain in the database.")
        return 130
    except (ValueError, OSError, sqlite3.Error) as exc:
        console.print(Text(str(exc), style="red"))
        return 2


if __name__ == "__main__":
    sys.exit(main())

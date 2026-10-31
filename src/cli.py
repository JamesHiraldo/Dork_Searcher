"""Wayback-Recon terminal dashboard and scriptable workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import sqlite3
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TaskID, TextColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from . import __version__
from .artifacts import atomic_write_text, save_json
from .availability import sample_hosts
from .checkpoints import Checkpoints, run_discovery
from .diagnostics import diagnose
from .discovery import import_records
from .discovery_pages import SOURCES
from .inventory import Inventory, filter_assets
from .scope import normalize_hostname
from .workbench import RESOURCES, TEMPLATES, duckduckgo_link, filter_archive
from .workspace import result_directory

console = Console(highlight=False, markup=False)
DEFAULT_SOURCES = ["wayback", "crtsh", "certspotter", "commoncrawl"]
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
    "1": "Find hosts + archived URLs",
    "2": "Search Wayback by date",
    "3": "Search one data source",
    "4": "Check saved hosts once",
    "5": "Monitor saved hosts repeatedly",
    "6": "View saved hosts + status",
    "7": "Import hosts from a file",
    "8": "Search saved URLs / dorks",
    "9": "Open research websites",
    "10": "Save HTML, CSV + TXT reports",
    "11": "Check setup / back up database",
    "12": "Continue a saved discovery",
    "0": "Exit",
}
MENU_DETAILS = {
    "1": "Query Wayback, Common Crawl and certificate logs; save discoveries. No live host checks.",
    "2": "Collect archived URLs from Wayback within optional start/end dates.",
    "3": "Choose one provider: certificate logs, RapidDNS, CompleteDNS or Common Crawl.",
    "4": "Test hosts already saved for a domain. Choose DNS only or DNS + webpage checks.",
    "5": "Repeat checks at an interval to observe hosts going up or down. No new discovery.",
    "6": "Read the stored inventory and latest classifications. Does not run new checks.",
    "7": "Add hosts/URLs from TXT, CSV, JSON or JSONL. Does not check whether they are alive.",
    "8": "Filter saved archive URLs, save a dork template, or open a DuckDuckGo browser search.",
    "9": "Open an external research site in your browser. Results are not imported automatically.",
    "10": "Create a new report folder from saved data. Does not discover or check hosts.",
    "11": "Diagnose the local setup without network requests, or copy the full SQLite database.",
    "12": "Resume a previous discovery from its checkpoint. This does not resume monitoring.",
}


def menu_panel(title: str, options: dict[str, str], details: dict[str, str] | None = None) -> Panel:
    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(style="bold cyan", width=3, no_wrap=True)
    table.add_column(style="white", ratio=1)
    for key, label in options.items():
        description = Text(label, style="bold white")
        if details and key in details:
            description.append("\n" + details[key], style="dim")
        table.add_row(f"{key:>2}", description)
        if details and key != next(reversed(options)):
            table.add_row("", "")
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
    title = Text("WAYBACK-RECON\n", style="bold cyan")
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
    console.print(Text("FIRST RUN: 1 Find hosts -> 4 Check hosts -> 10 Save reports", style="bold"))
    console.print(
        Text("Already collected data? Use 6 to view it, or 12 to continue discovery.", style="dim")
    )
    groups = [
        ("FIND HOSTS & ARCHIVES", ("1", "2", "3", "12")),
        ("CHECK LIVE AVAILABILITY", ("4", "5")),
        ("SAVED DATA & REPORTS", ("6", "7", "8", "10")),
        ("LINKS & MAINTENANCE", ("9", "11")),
    ]
    panels = [
        menu_panel(title, {key: MENU_LABELS[key] for key in keys}, MENU_DETAILS)
        for title, keys in groups
    ]
    if console.width >= 110:
        columns = Table.grid(padding=(0, 1), expand=True)
        columns.add_column(ratio=1)
        columns.add_column(ratio=1)
        columns.add_row(panels[0], panels[2])
        columns.add_row(panels[1], panels[3])
        console.print(columns)
    else:
        console.print(*panels)
    console.print(Text(" 0  Exit    |    Choose a number, then press Enter.", style="bold white"))
    console.print(Text(f"Results: {directory}", style="dim"), overflow="fold")
    console.print(Text(NOTICE, style="yellow"))


def show_inventory(store: Inventory, target: str, filters: dict[str, Any] | None = None) -> None:
    report = store.report(target)
    report["assets"] = filter_assets(report["assets"], filters or {})
    table = Table(title=f"{target} / {len(report['assets'])} hosts", box=box.ROUNDED)
    table.add_column("Hostname", overflow="fold", min_width=20)
    for column in ("Sources", "Latest state", "Changes\nHTTP/DNS", "Found"):
        table.add_column(column, overflow="fold")
    for asset in report["assets"][:200]:
        state = asset["latest"]["classification"]
        color = (
            "green"
            if state == "confirmed_webpage"
            else "yellow"
            if state in ("alive_candidate", "redirect", "authentication_required")
            else "white"
        )
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
    limit = options.pop("limit", 5000)
    max_pages = options.pop("max_pages", 20)
    checkpoints = Checkpoints(store)
    job_id = checkpoints.create(target, sources, **options)
    return continue_discovery(checkpoints, job_id, limit=limit, max_pages=max_pages, strict=strict)


def continue_discovery(
    checkpoints: Checkpoints,
    job_id: str,
    *,
    limit: int = 5000,
    max_pages: int = 20,
    strict: bool = False,
) -> list[str]:
    console.print(f"Discovery run: {job_id}")
    console.print("Progress is saved automatically. Use 'resume RUN_ID' in this output folder.")
    with console.status("Loading discovery checkpoint...", spinner="line") as progress:
        results = run_discovery(
            checkpoints, job_id, limit=limit, max_pages=max_pages, on_progress=progress.update
        )
    statuses = []
    for result in results:
        meta = result.metadata
        message = (
            f"{result.source}: {meta['processed']} records this invocation / "
            f"{meta['new_hosts']} new hosts / {meta['status']} / {meta['total_records']} total"
        )
        if result.truncated:
            message += " / resumable (partial coverage)"
        console.print(Text(message, style="cyan"))
        if result.error:
            console.print(Text(result.error, style="yellow"))
        statuses.append(
            "incomplete" if strict and (result.error or result.truncated) else result.status
        )
    return statuses


def show_runs(checkpoints: Checkpoints) -> list[dict[str, Any]]:
    runs = checkpoints.runs()
    for run in runs:
        console.print(f"{run['id']}  {run['target']}  {run['created_at'][:19]}")
        if run["crawl_indexes"]:
            console.print("  Crawl indexes: " + ", ".join(run["crawl_indexes"]))
        for source, state in run["sources"].items():
            console.print(
                f"  {source}: {state['status']} / {state['records']} records / "
                f"{state['pages']} pages"
            )
            if state["error"]:
                console.print(Text(f"  {state['error']}", style="yellow"))
    if not runs:
        console.print("No saved discovery runs. Start with option 1 or the discover command.")
    return runs


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
    max_redirects: int = 10,
    read_timeout: float = 10,
    only_unchecked: bool = False,
    export_each_round: bool = True,
) -> None:
    if rounds < 1 or rounds > 10000 or not math.isfinite(interval) or not 10 <= interval <= 86400:
        raise ValueError("Use 1-10000 rounds with an interval of 10-86400 seconds")
    if not 1 <= concurrency <= 50 or not 0 < timeout <= 60:
        raise ValueError("Concurrency must be 1-50; timeout must be >0 and <=60 seconds")
    if not math.isfinite(host_timeout) or not 0 < host_timeout <= 600:
        raise ValueError("Host timeout must be >0 and <=600 seconds")
    if only_unchecked and rounds != 1:
        raise ValueError("Unchecked-only selection is for one check, not repeated monitoring")
    if (
        not 0 <= max_redirects <= 10
        or not math.isfinite(read_timeout)
        or not 0 < read_timeout <= 60
    ):
        raise ValueError("Redirect limit must be 0-10; read timeout must be >0 and <=60 seconds")
    hosts = store.hosts(target, only_unchecked=only_unchecked)
    if not hosts:
        if only_unchecked and store.hosts(target):
            console.print("All saved hosts already have a check. Nothing to do; no requests sent.")
            return
        raise ValueError("No hosts stored for this target. Discover or import first.")
    for number in range(rounds):
        console.print(f"Sample {number + 1}/{rounds}: {len(hosts)} hosts; Ctrl+C stops safely")
        with Progress(
            SpinnerColumn("line"),
            TextColumn("{task.description}"),
            BarColumn(bar_width=16),
            MofNCompleteColumn(),
            console=console,
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
                    max_redirects=max_redirects,
                    read_timeout=read_timeout,
                    on_result=completed,
                )
            )
        show_inventory(store, target)
        if export_each_round or number + 1 == rounds:
            report_path = store.export(target, store.path.parent)
            console.print(f"HTML report: {report_path.with_suffix('.html')}")
            console.print(f"All result files: {report_path.parent}")
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
            console.print(Text(MENU_DETAILS[choice], style="dim"))
            try:
                if choice == "9":
                    resource_menu()
                    continue
                if choice == "12":
                    checkpoints = Checkpoints(store)
                    runs = show_runs(checkpoints)
                    if not runs:
                        continue
                    selected = numbered_menu(
                        "RESUME A SAVED RUN",
                        {
                            **{
                                str(i): f"{r['target']} / {r['id'][:8]}"
                                for i, r in enumerate(runs, 1)
                            },
                            "0": "Back to main menu",
                        },
                        default="0",
                    )
                    if selected == "0":
                        continue
                    run = runs[int(selected) - 1]
                    limit = ask_int("Additional records per source", 5000, 1, 100000)
                    continue_discovery(checkpoints, run["id"], limit=limit)
                    console.print(f"Report: {store.export(run['target'], directory)}")
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
                    sources = DEFAULT_SOURCES if choice == "1" else ["wayback"]
                    if choice == "3":
                        selection = numbered_menu(
                            "CHOOSE A SOURCE",
                            {
                                "1": "crt.sh - certificate names",
                                "2": "Cert Spotter - certificate names",
                                "3": "RapidDNS - API key required",
                                "4": "CompleteDNS - nameserver history (API key)",
                                "5": "Common Crawl - archived URLs and hostnames",
                                "0": "Back to main menu",
                            },
                            default="1",
                        )
                        if selection == "0":
                            continue
                        source = SOURCES[int(selection)]
                        sources = [source]
                    limit = ask_int(
                        "Records per source this run (remaining results resumable)", 5000, 1, 100000
                    )
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
                            "1": "DNS + webpages - classify pages, redirects and HTTP errors",
                            "2": "DNS only - check name resolution; do not contact websites",
                            **(
                                {"3": "DNS + webpages - only hosts with no saved check yet"}
                                if choice == "4"
                                else {}
                            ),
                            "0": "Back to main menu",
                        },
                        default="1",
                    )
                    if mode == "0":
                        continue
                    if mode == "3":
                        console.print(
                            "Skips previously checked hosts, including DNS-only or failed checks."
                        )
                    monitor(
                        store,
                        target,
                        rounds=rounds,
                        interval=interval,
                        http=mode != "2",
                        only_unchecked=mode == "3",
                    )
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
                if choice in ("1", "2", "3", "7"):
                    report_path = store.export(target, directory)
                    console.print(f"HTML report: {report_path.with_suffix('.html')}")
                    console.print(f"All result files: {report_path.parent}")
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
        description="Wayback-Recon: archives, subdomains and availability"
    )
    parser.add_argument("--output-dir", help="Output and database folder; defaults to Desktop")
    parser.add_argument("--debug", action="store_true", help="Explain classification decisions")
    parser.add_argument("--version", action="version", version=f"Wayback-Recon {__version__}")
    sub = parser.add_subparsers(dest="command")
    for name in ("discover", "check", "watch", "inventory", "export", "import", "dorks"):
        p = sub.add_parser(name)
        p.add_argument("target", help="Root domain; all its discovered child hosts are included")
        if name in ("inventory", "export"):
            p.add_argument("--only-webpages", action="store_true")
            p.add_argument(
                "--include-protected",
                action="store_true",
                help="Include protected hosts with --only-webpages",
            )
            p.add_argument(
                "--include-redirects",
                action="store_true",
                help="Include redirects with --only-webpages",
            )
            p.add_argument("--status", type=int)
            p.add_argument("--classification")
        if name == "discover":
            p.add_argument("--sources", nargs="+", choices=SOURCES, default=DEFAULT_SOURCES)
            p.add_argument(
                "--limit", type=int, default=5000, help="Records per source this invocation"
            )
            p.add_argument(
                "--max-pages",
                type=int,
                default=20,
                help="Page/metadata steps per source this invocation",
            )
            p.add_argument(
                "--page-size", type=int, default=1000, help="Wayback request size (fixed for a run)"
            )
            p.add_argument(
                "--cc-index",
                action="append",
                dest="cc_indexes",
                help="Common Crawl ID; repeat for multiple indexes",
            )
            p.add_argument(
                "--cc-latest",
                type=int,
                default=1,
                help="Latest N indexes if --cc-index is omitted (1-100)",
            )
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
                "--read-timeout", type=float, default=10, help="Per-read timeout, 0-60 seconds"
            )
            p.add_argument("--max-redirects", type=int, default=10, help="Internal redirects, 0-10")
            p.add_argument(
                "--host-timeout",
                type=float,
                default=45,
                help="Overall per-host deadline in seconds (max 600)",
            )
            if name == "watch":
                p.add_argument("--rounds", type=int, default=5)
                p.add_argument("--interval", type=float, default=60)
                p.add_argument(
                    "--final-report-only",
                    action="store_true",
                    help="Export only after the last round to reduce disk usage",
                )
            else:
                p.add_argument(
                    "--only-unchecked",
                    action="store_true",
                    help="Skip hosts with any previous check, including DNS-only/errors",
                )
        elif name == "import":
            p.add_argument("file")
        elif name == "dorks":
            p.add_argument("query")
    sub.add_parser("resources")
    sub.add_parser("doctor", help="Local runtime, TLS, DNS and database checks; no network")
    backup = sub.add_parser("backup", help="Consistent full inventory backup; never overwrite")
    backup.add_argument("destination", help="New SQLite backup file path")
    runs = sub.add_parser("runs", help="List the latest 50 saved discovery runs")
    runs.add_argument("--json", action="store_true", help="Machine-readable run summaries")
    resume = sub.add_parser(
        "resume", help="Continue a saved discovery run without changing its query"
    )
    resume.add_argument("run_id")
    resume.add_argument(
        "--limit", type=int, default=5000, help="Additional record budget per source"
    )
    resume.add_argument(
        "--max-pages", type=int, default=20, help="Additional page/metadata steps per source"
    )
    resume.add_argument("--strict", action="store_true")
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
    if args.debug:
        logging.basicConfig(level=logging.WARNING)
        logging.getLogger("src.classification").setLevel(logging.DEBUG)
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
        if args.command in ("runs", "resume"):
            with Inventory(directory / "inventory.sqlite3") as store:
                checkpoints = Checkpoints(store)
                if args.command == "runs":
                    if args.json:
                        console.print(json.dumps(checkpoints.runs(), indent=2), soft_wrap=True)
                    else:
                        show_runs(checkpoints)
                    return 0
                console.print(NOTICE)
                statuses = continue_discovery(
                    checkpoints,
                    args.run_id,
                    limit=args.limit,
                    max_pages=args.max_pages,
                    strict=args.strict,
                )
                console.print(
                    f"Report: {store.export(checkpoints.job(args.run_id)['target'], directory)}"
                )
                return int("incomplete" in statuses or all(s == "error" for s in statuses))
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
                    cc_indexes=args.cc_indexes,
                    cc_latest=args.cc_latest,
                    page_size=args.page_size,
                )
            elif args.command in ("check", "watch"):
                monitor(
                    store,
                    target,
                    http=not args.dns_only,
                    concurrency=args.concurrency,
                    timeout=args.timeout,
                    host_timeout=args.host_timeout,
                    read_timeout=args.read_timeout,
                    max_redirects=args.max_redirects,
                    rounds=getattr(args, "rounds", 1),
                    interval=getattr(args, "interval", 60),
                    only_unchecked=getattr(args, "only_unchecked", False),
                    export_each_round=not getattr(args, "final_report_only", False),
                )
            elif args.command == "import":
                result = import_records(args.file, target)
                new = store.merge(target, result)
                console.print(f"Imported {len(result.records)} records; {len(new)} new hosts")
                console.print(f"Skipped {result.metadata['rejected']} invalid/unrelated records")
                if result.truncated:
                    console.print("Import limit reached; some evidence was omitted.")
            elif args.command == "inventory":
                show_inventory(store, target, vars(args))
            elif args.command == "dorks":
                rows = query_archive(store, target, args.query)
                save_json(str(directory / "archive_matches.json"), rows)
                console.print(f"{len(rows)} matches saved to {directory / 'archive_matches.json'}")
            if args.command in ("discover", "export", "import"):
                filters = vars(args) if args.command == "export" else None
                console.print(f"Report: {store.export(target, directory, filters=filters)}")
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

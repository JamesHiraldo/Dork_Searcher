#!/usr/bin/env python3
# mypy: disable-error-code="no-redef"
"""Interactive interface for authorized reconnaissance workflows."""

from __future__ import annotations

import asyncio
import getpass
import json
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

if __package__:
    from .artifacts import atomic_write_text, derived_csv_path, ensure_distinct_paths
    from .passive_probe import (
        DEFAULT_CONCURRENCY,
        DEFAULT_MAX_REDIRECTS,
        DEFAULT_TIMEOUT,
        MAX_CONCURRENCY,
        build_target_urls_from_domains,
        run_probes,
    )
    from .passive_probe import (
        save_csv as save_probe_csv,
    )
    from .passive_probe import (
        save_json as save_probe_json,
    )
    from .recon_pipeline import (
        DEFAULT_MAX_URLS,
        summarize_targets,
    )
    from .recon_pipeline import (
        RATE as RECON_RATE,
    )
    from .recon_pipeline import (
        save_csv as save_recon_csv,
    )
    from .recon_pipeline import (
        save_json as save_recon_json,
    )
    from .scope import ScopeError, normalize_hostname, normalize_targets, parse_http_url
    from .searcher import (
        DEFAULT_SEARCH_RESULTS,
        DEFAULT_WAYBACK_RESULTS,
        DORK_TEMPLATES,
        RATE_LIMIT,
        build_queries,
        cross_reference_with_subdomains,
        run_queries,
        save_csv,
        save_json,
    )
else:  # pragma: no cover
    from artifacts import atomic_write_text, derived_csv_path, ensure_distinct_paths  # type: ignore
    from passive_probe import (  # type: ignore
        DEFAULT_CONCURRENCY,
        DEFAULT_MAX_REDIRECTS,
        DEFAULT_TIMEOUT,
        MAX_CONCURRENCY,
        build_target_urls_from_domains,
        run_probes,
    )
    from passive_probe import (
        save_csv as save_probe_csv,
    )
    from passive_probe import (
        save_json as save_probe_json,
    )
    from recon_pipeline import (  # type: ignore
        DEFAULT_MAX_URLS,
        summarize_targets,
    )
    from recon_pipeline import (
        RATE as RECON_RATE,
    )
    from recon_pipeline import (
        save_csv as save_recon_csv,
    )
    from recon_pipeline import (
        save_json as save_recon_json,
    )
    from scope import (  # type: ignore
        ScopeError,
        normalize_hostname,
        normalize_targets,
        parse_http_url,
    )
    from searcher import (  # type: ignore
        DEFAULT_SEARCH_RESULTS,
        DEFAULT_WAYBACK_RESULTS,
        DORK_TEMPLATES,
        RATE_LIMIT,
        build_queries,
        cross_reference_with_subdomains,
        run_queries,
        save_csv,
        save_json,
    )


class _Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"


_COLOR_ENABLED = (
    sys.stdout.isatty()
    and "NO_COLOR" not in os.environ
    and os.environ.get("TERM", "").lower() != "dumb"
)
_RESULT_DIRECTORY: Path | None = None
if os.name == "nt" and _COLOR_ENABLED:  # enable ANSI processing in modern Windows consoles
    os.system("")


def _paint(text: str, *styles: str) -> str:
    if not _COLOR_ENABLED:
        return text
    return "".join(styles) + text + _Ansi.RESET


def _menu_item(number: str, label: str) -> None:
    marker = _paint(f"[{number}]", _Ansi.BOLD, _Ansi.CYAN)
    print(f"{marker} {label}")


def _menu_section(title: str) -> None:
    print()
    print(_paint(title, _Ansi.BOLD, _Ansi.YELLOW))
    print(_paint("-" * 40, _Ansi.CYAN))


def _success(message: str) -> None:
    print(_paint(f"[+] {message}", _Ansi.GREEN))


def _warning(message: str) -> None:
    print(_paint(message, _Ansi.YELLOW))


def _error(message: str) -> None:
    print(_paint(message, _Ansi.RED), file=sys.stderr)


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def print_header() -> None:
    divider = _paint("=" * 68, _Ansi.CYAN)
    print(divider)
    print(_paint(" DORK SEARCHER 2.0 - Authorized Reconnaissance by Maydayx2", _Ansi.BOLD))
    print(divider)


def print_authorization_notice() -> None:
    print(
        _paint(
            "Authorization notice: continue only with explicitly permitted targets.\n",
            _Ansi.YELLOW,
        )
    )


def _desktop_directory() -> Path:
    """Resolve the user's real Desktop, including Windows folder redirection."""
    if os.name == "nt":
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                raw_value, _ = winreg.QueryValueEx(key, "Desktop")
            return Path(os.path.expandvars(str(raw_value))).expanduser()
        except OSError:
            pass
    return Path.home() / "Desktop"


def ensure_result_folder() -> Path:
    """Return a verified writable, easily discoverable result directory."""
    global _RESULT_DIRECTORY
    if _RESULT_DIRECTORY is not None:
        return _RESULT_DIRECTORY

    candidates: list[Path] = []
    configured = os.environ.get("DORK_SEARCHER_OUTPUT_DIR")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(_desktop_directory() / "Dork_Searcher_Results")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Dork_Searcher" / "Results")
    candidates.append(Path.home() / "Dork_Searcher_Results")

    attempted: list[str] = []
    for candidate in dict.fromkeys(candidates):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix=".write-check-", dir=candidate):
                pass
            _RESULT_DIRECTORY = candidate.resolve()
            if candidate != candidates[0]:
                _warning(f"Preferred output unavailable; using: {_RESULT_DIRECTORY}")
            return _RESULT_DIRECTORY
        except OSError as exc:
            attempted.append(f"{candidate}: {exc}")

    raise PermissionError("No writable result directory was found. " + " | ".join(attempted))


def default_result_path(filename: str) -> str:
    return str(ensure_result_folder() / filename)


def custom_dork_path() -> Path:
    return ensure_result_folder() / "custom_dorks.txt"


def normalize_custom_dork_template(value: str) -> str:
    template = " ".join(value.strip().split())
    if not template:
        raise ValueError("The dork cannot be empty")
    if len(template) > 500:
        raise ValueError("The dork cannot exceed 500 characters")
    lowered = template.lower()
    if "site:" in lowered and "site:{t}" not in lowered:
        raise ValueError("Use site:{t} instead of a hard-coded site restriction")
    if "site:{t}" not in lowered:
        template = f"site:{{t}} ({template})"
    return template


def load_custom_dork_templates() -> list[str]:
    path = custom_dork_path()
    if not path.exists():
        return []
    templates: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            templates.append(normalize_custom_dork_template(line))
        except ValueError as exc:
            _warning(f"Skipping invalid custom dork: {exc}")
    return list(dict.fromkeys(templates))


def save_custom_dork_templates(templates: list[str]) -> None:
    normalized = list(dict.fromkeys(normalize_custom_dork_template(item) for item in templates))
    content = "# One target-scoped dork per line; {t} is replaced at run time.\n"
    if normalized:
        content += "\n".join(normalized) + "\n"
    atomic_write_text(str(custom_dork_path()), content)


def get_input(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]: " if default is not None else ": "
    value = input(prompt + suffix).strip()
    return value if value else (default or "")


def get_multiple_inputs(prompt: str) -> list[str]:
    value = input(f"{prompt} (comma or space separated): ").strip()
    return [item for item in value.replace(",", " ").split() if item]


def get_targets() -> list[str]:
    values = get_multiple_inputs("Enter authorized target domain(s)")
    try:
        return normalize_targets(values)
    except ScopeError as exc:
        _error(f"Error: {exc}")
        return []


def get_float(prompt: str, default: float, minimum: float = 0.0, maximum: float = 60.0) -> float:
    while True:
        raw = get_input(prompt, str(default))
        try:
            value = float(raw)
            if value < minimum or value > maximum:
                raise ValueError
            return value
        except ValueError:
            _warning(f"Enter a number between {minimum} and {maximum}.")


def get_int(prompt: str, default: int, minimum: int, maximum: int) -> int:
    while True:
        raw = get_input(prompt, str(default))
        try:
            value = int(raw)
            if value < minimum or value > maximum:
                raise ValueError
            return value
        except ValueError:
            _warning(f"Enter a whole number between {minimum} and {maximum}.")


def confirm(prompt: str, default: bool = False) -> bool:
    label = "Y/n" if default else "y/N"
    answer = input(f"{prompt} [{label}]: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def pause() -> None:
    input("\nPress Enter to continue...")


def _write_search_outputs(output_file: str, results: list[dict[str, Any]]) -> None:
    save_json(output_file, results)
    _success(f"JSON saved to: {output_file}")
    if confirm("Also save as CSV?"):
        csv_file = derived_csv_path(output_file)
        save_csv(csv_file, results)
        _success(f"CSV saved to: {csv_file}")


def _menu_search(
    backend: str,
    title: str,
    api_key: str | None = None,
    cse_id: str | None = None,
) -> None:
    clear_screen()
    print_header()
    print("[*] {}\n{}".format(title, "-" * 68))
    targets = get_targets()
    if not targets:
        pause()
        return
    output_file = get_input("Output JSON path", default_result_path(f"{backend}_results.json"))
    rate = get_float("Delay between requests (seconds)", RATE_LIMIT)
    max_results = get_int("Maximum results per query", DEFAULT_SEARCH_RESULTS, 1, 100)
    custom_templates = load_custom_dork_templates()
    templates = [*DORK_TEMPLATES, *custom_templates]
    queries = build_queries(targets, templates=templates)
    print(
        f"Using {len(DORK_TEMPLATES)} built-in and {len(custom_templates)} custom "
        f"dork(s); {len(queries)} scoped queries queued."
    )
    results = run_queries(
        queries,
        backend,
        api_key=api_key,
        cse_id=cse_id,
        rate_limit=rate,
        max_results=max_results,
    )
    _write_search_outputs(output_file, results)
    pause()


def menu_google_search() -> None:
    clear_screen()
    print_header()
    api_key = getpass.getpass("Google API key (hidden): ").strip()
    cse_id = get_input("Google CSE ID")
    if not api_key or not cse_id:
        print("Error: API key and CSE ID are required.")
        pause()
        return
    _menu_search("google", "Google Programmable Search", api_key=api_key, cse_id=cse_id)


def menu_wayback_search() -> None:
    clear_screen()
    print_header()
    print("[*] Wayback CDX URL Collection\n{}".format("-" * 68))
    targets = get_targets()
    if not targets:
        pause()
        return
    output_file = get_input("Output JSON path", default_result_path("wayback_results.json"))
    rate = get_float("Delay between CDX pages (seconds)", 0.25)
    max_results = get_int("Maximum archived URLs per target", DEFAULT_WAYBACK_RESULTS, 1, 1000000)
    include_subdomains = confirm("Include subdomains of each target?")
    results = run_queries(
        [f"site:{target}" for target in targets],
        "wayback",
        rate_limit=rate,
        max_results=max_results,
        include_subdomains=include_subdomains,
    )
    _write_search_outputs(output_file, results)
    pause()


def menu_duckduckgo_search() -> None:
    _menu_search("duckduckgo", "DuckDuckGo Search (Primary; Dogpile fallback)")


def menu_dogpile_search() -> None:
    _menu_search("dogpile", "Dogpile Direct Search (diagnostics)")


def menu_dnsdumpster_search() -> None:
    clear_screen()
    print_header()
    api_key = getpass.getpass("DNSDumpster API key (hidden): ").strip()
    if not api_key:
        print("Error: API key is required.")
        pause()
        return
    targets = get_targets()
    if not targets:
        pause()
        return
    output_file = get_input("Output JSON path", default_result_path("dnsdumpster_results.json"))
    rate = get_float("Delay between targets (seconds)", RATE_LIMIT)
    results = run_queries(
        [f"site:{target}" for target in targets],
        "dnsdumpster",
        api_key=api_key,
        rate_limit=rate,
    )
    _write_search_outputs(output_file, results)
    pause()


def menu_certificate_transparency_search() -> None:
    clear_screen()
    print_header()
    print("[*] Certificate Transparency Discovery / Subdomain Enumeration\n{}".format("-" * 68))
    print(
        "This is the passive subdomain-enumeration workflow. It combines names "
        "observed by crt.sh and Cert Spotter.\n"
    )
    targets = get_targets()
    if not targets:
        pause()
        return
    output_file = get_input(
        "Output JSON path", default_result_path("certificate_transparency.json")
    )
    rate = get_float("Delay between targets (seconds)", RATE_LIMIT)
    max_results = get_int("Maximum names per target", 5000, 1, 100000)
    results = run_queries(
        [f"site:{target}" for target in targets],
        "crtsh",
        rate_limit=rate,
        max_results=max_results,
    )
    _write_search_outputs(output_file, results)
    observed = sum(row.get("result_type") == "observed" for row in results)
    if observed:
        _success(f"{observed} observed subdomain(s) collected")
    else:
        _warning("No CT-observed subdomains were returned; review any error row in the JSON.")
    pause()


def _hosts_from_discovery(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        raise ValueError("Discovery JSON must contain a list")
    hosts: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("result_type") in ("candidate", "error"):
            continue
        value = row.get("title") or row.get("url")
        if not value:
            continue
        try:
            if str(value).startswith(("http://", "https://")):
                _, host = parse_http_url(str(value))
            else:
                host = normalize_hostname(str(value))
            hosts.append(host)
        except ScopeError:
            continue
    return list(dict.fromkeys(hosts))


def menu_cross_reference() -> None:
    clear_screen()
    print_header()
    print("[*] Structural Hostname Cross-Reference\n{}".format("-" * 68))
    results_file = get_input("Search/Wayback results JSON path")
    discovery_file = get_input("Observed-host discovery JSON path")
    try:
        with open(results_file, encoding="utf-8") as source:
            result_rows = json.load(source)
        with open(discovery_file, encoding="utf-8") as source:
            discovery_rows = json.load(source)
        if not isinstance(result_rows, list):
            raise ValueError("Results JSON must contain a list")
        hosts = _hosts_from_discovery(discovery_rows)
        urls = [
            str(row.get("url")) for row in result_rows if isinstance(row, dict) and row.get("url")
        ]
        matches = cross_reference_with_subdomains(urls, hosts)
        output_rows = [
            {
                "query": "cross_reference",
                "title": match["subdomain"],
                "url": match["url"],
                "snippet": match["match_type"],
                "source": "cross_reference",
                "result_type": "observed",
                "verified": False,
                "error": "",
            }
            for match in matches
        ]
        output_file = get_input("Output JSON path", default_result_path("cross_reference.json"))
        _write_search_outputs(output_file, output_rows)
        _success(f"{len(output_rows)} structural hostname match(es)")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _error(f"Error: {exc}")
    pause()


def menu_view_templates() -> None:
    while True:
        clear_screen()
        print_header()
        print("[*] Dork Templates\n{}".format("-" * 68))
        print("Built-in templates:")
        for index, template in enumerate(DORK_TEMPLATES, 1):
            print(f"{index:2d}. {template}")

        custom_templates = load_custom_dork_templates()
        print("\nCustom templates:")
        if custom_templates:
            for index, template in enumerate(custom_templates, 1):
                print(f"C{index:02d}. {template}")
        else:
            print("  (none)")
        print(f"\nCustom dork file: {custom_dork_path()}")
        _menu_item("A", "Add custom dorks")
        _menu_item("R", "Remove a custom dork")
        _menu_item("0", "Return to main menu")
        action = input(_paint("\nSelect an option: ", _Ansi.CYAN)).strip().lower()

        if action == "0" or not action:
            return
        if action == "a":
            print(
                "Enter one dork per line. Use {t} for the target; a missing site "
                "restriction is added automatically. Submit a blank line to finish."
            )
            added = 0
            while True:
                raw = input("Dork: ").strip()
                if not raw:
                    break
                try:
                    template = normalize_custom_dork_template(raw)
                except ValueError as exc:
                    _error(f"Invalid dork: {exc}")
                    continue
                if template in DORK_TEMPLATES or template in custom_templates:
                    _warning("That dork already exists.")
                    continue
                custom_templates.append(template)
                added += 1
            if added:
                save_custom_dork_templates(custom_templates)
                _success(f"Saved {added} custom dork(s)")
            pause()
            continue
        if action == "r":
            if not custom_templates:
                _warning("There are no custom dorks to remove.")
                pause()
                continue
            raw_index = get_input("Custom dork number to remove (for example, 1)")
            try:
                index = int(raw_index)
                if index < 1 or index > len(custom_templates):
                    raise ValueError
            except ValueError:
                _error("Invalid custom dork number.")
                pause()
                continue
            removed = custom_templates.pop(index - 1)
            save_custom_dork_templates(custom_templates)
            _success(f"Removed: {removed}")
            pause()
            continue
        _error("Invalid option.")
        pause()


def menu_passive_probe() -> None:
    clear_screen()
    print_header()
    print("[*] Active HTTP Metadata / Header / CORS Probe\n{}".format("-" * 68))
    print("This sends GET requests but does not download response bodies.")
    if not confirm("I confirm every target is explicitly authorized"):
        print("Probe cancelled.")
        pause()
        return

    mode = get_input("Input mode: [1] targets  [2] URL file", "1")
    allowed_targets: list[str] | None = None
    if mode == "1":
        targets = get_targets()
        if not targets:
            pause()
            return
        urls = build_target_urls_from_domains(targets)
        allowed_targets = targets
    elif mode == "2":
        urls_file = get_input("Authorized URL file path")
        with open(urls_file, encoding="utf-8") as source:
            urls = [
                line.strip()
                for line in source
                if line.strip() and not line.lstrip().startswith("#")
            ]
    else:
        print("Invalid mode.")
        pause()
        return

    output_file = get_input("Output JSON path", default_result_path("http_probe_results.json"))
    csv_file = get_input("CSV output path", derived_csv_path(output_file))
    ensure_distinct_paths(output_file, csv_file)
    concurrency = get_int("Concurrency", DEFAULT_CONCURRENCY, 1, MAX_CONCURRENCY)
    timeout = get_float("Timeout (seconds)", DEFAULT_TIMEOUT, 0.1, 120.0)
    max_redirects = get_int("Maximum in-scope redirects", DEFAULT_MAX_REDIRECTS, 0, 10)
    allow_subdomains = confirm("Allow redirects to child subdomains?")
    allow_private = confirm("Allow private/local IP destinations? (owned labs only)")
    test_cors = confirm("Send an Origin header for CORS analysis?")
    origin = (
        get_input("CORS test Origin", "https://example.com") if test_cors else "https://example.com"
    )

    results = asyncio.run(
        run_probes(
            urls,
            concurrency=concurrency,
            timeout=timeout,
            test_cors=test_cors,
            origin=origin,
            allowed_targets=allowed_targets,
            allow_subdomains=allow_subdomains,
            allow_private=allow_private,
            max_redirects=max_redirects,
        )
    )
    save_probe_json(output_file, results)
    _success(f"JSON saved to: {output_file}")
    if csv_file:
        save_probe_csv(csv_file, results)
        _success(f"CSV saved to: {csv_file}")
    pause()


def menu_recon_pipeline() -> None:
    clear_screen()
    print_header()
    print("[*] Wayback Recon + Parameter Inventory\n{}".format("-" * 68))
    targets = get_targets()
    if not targets:
        pause()
        return
    output_file = get_input("Output JSON path", default_result_path("recon_pipeline_report.json"))
    csv_file = get_input("CSV output path", derived_csv_path(output_file))
    ensure_distinct_paths(output_file, csv_file)
    rate = get_float("Delay between CDX requests (seconds)", RECON_RATE)
    max_urls = get_int("Maximum archived URLs per target", DEFAULT_MAX_URLS, 1, 1000000)
    include_subdomains = confirm("Include subdomains?")
    include_sensitive = confirm("Include token-like archived parameter values? (unsafe)")
    report = summarize_targets(
        targets,
        rate=rate,
        max_urls=max_urls,
        include_subdomains=include_subdomains,
        include_sensitive_values=include_sensitive,
    )
    save_recon_json(output_file, report)
    _success(f"JSON saved to: {output_file}")
    if csv_file:
        save_recon_csv(csv_file, report)
        _success(f"CSV saved to: {csv_file}")
    pause()


def main_menu() -> None:
    actions: dict[str, Callable[[], None]] = {
        "1": menu_google_search,
        "2": menu_duckduckgo_search,
        "3": menu_dogpile_search,
        "4": menu_wayback_search,
        "5": menu_recon_pipeline,
        "6": menu_certificate_transparency_search,
        "7": menu_dnsdumpster_search,
        "8": menu_passive_probe,
        "9": menu_cross_reference,
        "10": menu_view_templates,
    }
    show_authorization_notice = True
    while True:
        clear_screen()
        print_header()
        if show_authorization_notice:
            print_authorization_notice()
            show_authorization_notice = False
        _menu_section("Dork_Search")
        _menu_item("1", "Google (API Req)")
        _menu_item("2", "DuckDuckGo Search")
        _menu_item("3", "Dogpile Direct Search")
        _menu_section("Wayback / Parser")
        _menu_item("4", "Wayback CDX URL Collection")
        _menu_item("5", "Wayback Recon + Parameter Inventory")
        _menu_section("Sub-Domain Search")
        _menu_item("6", "Certificate Transparency Discovery")
        _menu_item("7", "DNSDumpster Discovery (API Req)")
        _menu_section("CORS Check")
        _menu_item("8", "Active HTTP Header/CORS Probe")
        _menu_section("Other")
        _menu_item("9", "Cross-Reference Existing Results")
        _menu_item("10", "View Dork Templates")
        _menu_item("0", "Exit")
        choice = input(_paint("\nSelect an option: ", _Ansi.CYAN)).strip()
        if choice == "0":
            return
        action = actions.get(choice)
        if not action:
            _error("Invalid option.")
            pause()
            continue
        try:
            action()
        except KeyboardInterrupt:
            _warning("\nOperation cancelled.")
            pause()
        except Exception as exc:
            _error(f"\n[!] Operation failed: {exc}")
            pause()


def main() -> int:
    try:
        main_menu()
        return 0
    except KeyboardInterrupt:
        _warning("\nExiting.")
        return 130


if __name__ == "__main__":
    sys.exit(main())

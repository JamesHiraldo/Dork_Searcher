#!/usr/bin/env python3
"""Interactive CLI menu for Dork Searcher"""
import os
import sys
import json
import getpass
import asyncio
from pathlib import Path
from searcher import (
    run_queries, 
    build_queries,
    save_json, 
    save_csv,
    DORK_TEMPLATES,
    RATE_LIMIT
)
from passive_probe import (
    run_probes,
    build_target_urls_from_domains,
    save_json as save_probe_json,
    save_csv as save_probe_csv,
    DEFAULT_CONCURRENCY,
    DEFAULT_TIMEOUT,
)
from recon_pipeline import (
    summarize_targets,
    save_json as save_recon_json,
    save_csv as save_recon_csv,
    RATE as RECON_RATE,
)


def clear_screen():
    """Clear terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header():
    """Print application header"""
    print("=" * 60)
    print("         DORK SEARCHER - Reconnaissance Tool By Maydayx2")
    print("=" * 60)
    print()


def ensure_result_folder():
    """Ensure Result folder exists"""
    result_dir = Path("Result")
    result_dir.mkdir(exist_ok=True)
    return result_dir


def get_input(prompt: str, default: str = None) -> str:
    """Get user input with optional default"""
    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "
    value = input(prompt).strip()
    return value if value else default


def get_multiple_inputs(prompt: str) -> list:
    """Get multiple comma/space-separated inputs"""
    value = input(f"{prompt} (comma or space separated): ").strip()
    # Split by comma or space
    items = [item.strip() for item in value.replace(',', ' ').split()]
    return [item for item in items if item]


def menu_google_search():
    """Menu for Google CSE search"""
    clear_screen()
    print_header()
    print("[*] Google CSE Search")
    print("-" * 60)
    
    api_key = getpass.getpass("Enter Google API Key (input hidden): ").strip()
    if not api_key:
        print("Error: API Key required")
        return
    
    cse_id = get_input("Enter Google CSE ID")
    if not cse_id:
        print("Error: CSE ID required")
        return
    
    targets = get_multiple_inputs("Enter target domain(s)")
    if not targets:
        print("Error: At least one target required")
        return
    
    ensure_result_folder()
    output_file = get_input("Output file path", "Result/google_results.json")
    rate_limit = float(get_input("Rate limit (seconds)", str(RATE_LIMIT)))
    
    print(f"\n[*] Building {len(targets)} target(s) with {len(DORK_TEMPLATES)} templates...")
    queries = build_queries(targets)
    
    print(f"[*] Running {len(queries)} queries...")
    results = run_queries(queries, 'google', api_key=api_key, cse_id=cse_id, rate_limit=rate_limit)
    
    save_json(output_file, results)
    print(f"[+] Results saved to: {output_file}")
    
    if input("\nAlso save as CSV? (y/n): ").lower() == 'y':
        csv_file = output_file.replace('.json', '.csv')
        save_csv(csv_file, results)
        print(f"[+] CSV saved to: {csv_file}")

    # Clear sensitive references before returning to menu.
    api_key = None
    
    input("\nPress Enter to continue...")


def menu_wayback_search():
    """Menu for Wayback Machine search"""
    clear_screen()
    print_header()
    print("[*] Wayback Machine (CDX) Search")
    print("-" * 60)
    
    targets = get_multiple_inputs("Enter target domain(s)")
    if not targets:
        print("Error: At least one target required")
        return
    
    ensure_result_folder()
    output_file = get_input("Output file path", "Result/wayback_results.json")
    rate_limit = float(get_input("Rate limit (seconds)", str(RATE_LIMIT)))
    
    queries = [f'site:{t}' for t in targets]
    
    print(f"[*] Running {len(queries)} queries...")
    results = run_queries(queries, 'wayback', rate_limit=rate_limit)
    
    save_json(output_file, results)
    print(f"[+] Results saved to: {output_file}")
    
    if input("\nAlso save as CSV? (y/n): ").lower() == 'y':
        csv_file = output_file.replace('.json', '.csv')
        save_csv(csv_file, results)
        print(f"[+] CSV saved to: {csv_file}")
    
    input("\nPress Enter to continue...")


def menu_duckduckgo_search():
    """Menu for DuckDuckGo search"""
    clear_screen()
    print_header()
    print("[*] DuckDuckGo Search")
    print("-" * 60)
    
    targets = get_multiple_inputs("Enter target domain(s)")
    if not targets:
        print("Error: At least one target required")
        return
    
    ensure_result_folder()
    output_file = get_input("Output file path", "Result/duckduckgo_results.json")
    rate_limit = float(get_input("Rate limit (seconds)", str(RATE_LIMIT)))
    
    queries = build_queries(targets)
    
    print(f"[*] Running {len(queries)} queries...")
    results = run_queries(queries, 'duckduckgo', rate_limit=rate_limit)
    
    save_json(output_file, results)
    print(f"[+] Results saved to: {output_file}")
    
    if input("\nAlso save as CSV? (y/n): ").lower() == 'y':
        csv_file = output_file.replace('.json', '.csv')
        save_csv(csv_file, results)
        print(f"[+] CSV saved to: {csv_file}")
    
    input("\nPress Enter to continue...")


def menu_c99_subdomain_search():
    """Menu for C99.nl Subdomain search"""
    clear_screen()
    print_header()
    print("[*] C99.nl Subdomain Finder")
    print("-" * 60)
    
    targets = get_multiple_inputs("Enter target domain(s)")
    if not targets:
        print("Error: At least one target required")
        return
    
    ensure_result_folder()
    output_file = get_input("Output file path", "Result/c99_subdomains.json")
    rate_limit = float(get_input("Rate limit (seconds)", str(RATE_LIMIT)))
    
    queries = [f'site:{t}' for t in targets]
    
    print(f"[*] Running {len(queries)} subdomain searches...")
    results = run_queries(queries, 'c99subdomain', rate_limit=rate_limit)
    
    save_json(output_file, results)
    print(f"[+] Results saved to: {output_file}")
    
    if input("\nAlso save as CSV? (y/n): ").lower() == 'y':
        csv_file = output_file.replace('.json', '.csv')
        save_csv(csv_file, results)
        print(f"[+] CSV saved to: {csv_file}")
    
    input("\nPress Enter to continue...")


def menu_cross_reference():
    """Menu for cross-referencing results"""
    clear_screen()
    print_header()
    print("[*] Cross-Reference Subdomains with Search Results")
    print("-" * 60)
    
    backend = input("\nSearch backend to cross-reference (wayback/duckduckgo/google): ").strip().lower()
    if backend not in ['wayback', 'duckduckgo', 'google']:
        print("Invalid backend")
        return
    
    if backend == 'google':
        api_key = getpass.getpass("Enter Google API Key (input hidden): ").strip()
        cse_id = get_input("Enter Google CSE ID")
        if not api_key or not cse_id:
            print("Error: API Key and CSE ID required for Google")
            return
    
    targets = get_multiple_inputs("Enter target domain(s)")
    if not targets:
        print("Error: At least one target required")
        return
    
    subdomain_file = get_input("Path to subdomain results JSON (from C99 search)")
    if not os.path.exists(subdomain_file):
        print(f"Error: File not found: {subdomain_file}")
        return
    
    ensure_result_folder()
    output_file = get_input("Output file path", "Result/crossref_results.json")
    rate_limit = float(get_input("Rate limit (seconds)", str(RATE_LIMIT)))
    
    # Load subdomain data
    with open(subdomain_file, 'r', encoding='utf-8') as f:
        subdomain_results = json.load(f)
    
    queries = build_queries(targets)
    if backend == 'wayback':
        queries = [f'site:{t}' for t in targets]
    
    api_key_val = None
    cse_id_val = None
    if backend == 'google':
        api_key_val = api_key
        cse_id_val = cse_id
    
    print(f"[*] Running {len(queries)} queries with cross-reference...")
    results = run_queries(queries, backend, api_key=api_key_val, cse_id=cse_id_val, rate_limit=rate_limit)
    
    # Add cross-reference data
    subdomains = [item.get('url', '').replace('https://', '').replace('http://', '') 
                 for item in subdomain_results if item.get('url')]
    urls_to_check = [item.get('url', '') for item in results if item.get('url')]
    
    matches = 0
    for url in urls_to_check:
        for subdomain in subdomains:
            if subdomain.lower() in url.lower():
                results.append({
                    'query': 'cross_reference',
                    'title': subdomain,
                    'url': url,
                    'snippet': 'CROSS_REF_MATCH'
                })
                matches += 1
    
    save_json(output_file, results)
    print(f"[+] Results saved to: {output_file}")
    print(f"[+] Found {matches} cross-reference matches")
    
    if input("\nAlso save as CSV? (y/n): ").lower() == 'y':
        csv_file = output_file.replace('.json', '.csv')
        save_csv(csv_file, results)
        print(f"[+] CSV saved to: {csv_file}")

    # Clear sensitive references before returning to menu.
    api_key_val = None
    if backend == 'google':
        api_key = None
    
    input("\nPress Enter to continue...")


def menu_view_templates():
    """View available dork templates"""
    clear_screen()
    print_header()
    print("[*] Available Dork Templates")
    print("-" * 60)
    for i, template in enumerate(DORK_TEMPLATES, 1):
        print(f"{i:2d}. {template}")
    print()
    input("Press Enter to continue...")


def menu_passive_probe():
    """Menu for passive header/CSP/CORS probing"""
    clear_screen()
    print_header()
    print("[*] Passive Probe (Headers/CSP/CORS)")
    print("-" * 60)

    mode = input("Input mode: [1] Targets  [2] URLs file: ").strip()
    urls = []

    if mode == '1':
        targets = get_multiple_inputs("Enter target domain(s)")
        if not targets:
            print("Error: At least one target required")
            input("\nPress Enter to continue...")
            return
        urls = build_target_urls_from_domains(targets)
    elif mode == '2':
        urls_file = get_input("Path to URLs file")
        if not urls_file or not os.path.exists(urls_file):
            print("Error: URLs file not found")
            input("\nPress Enter to continue...")
            return
        with open(urls_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
    else:
        print("Invalid mode")
        input("\nPress Enter to continue...")
        return

    if not urls:
        print("Error: No URLs to probe")
        input("\nPress Enter to continue...")
        return

    ensure_result_folder()
    output_file = get_input("Output file path", "Result/passive_probe_results.json")
    csv_file = get_input("CSV output path (optional)", "Result/passive_probe_results.csv")
    concurrency = int(get_input("Concurrency", str(DEFAULT_CONCURRENCY)))
    timeout = float(get_input("Timeout (seconds)", str(DEFAULT_TIMEOUT)))
    test_cors = input("Enable CORS reflection test? (y/n): ").strip().lower() == 'y'

    print(f"\n[*] Probing {len(urls)} URL(s) (concurrency={concurrency})...")
    results = asyncio.run(
        run_probes(urls, concurrency=concurrency, timeout=timeout, test_cors=test_cors)
    )

    save_probe_json(output_file, results)
    print(f"[+] JSON saved to: {output_file}")

    if csv_file:
        save_probe_csv(csv_file, results)
        print(f"[+] CSV saved to: {csv_file}")

    input("\nPress Enter to continue...")


def menu_recon_pipeline():
    """Menu for Wayback recon pipeline"""
    clear_screen()
    print_header()
    print("[*] Recon Pipeline (Wayback + Parameter Extraction)")
    print("-" * 60)

    targets = get_multiple_inputs("Enter target domain(s)")
    if not targets:
        print("Error: At least one target required")
        input("\nPress Enter to continue...")
        return

    ensure_result_folder()
    output_file = get_input("Output file path", "Result/recon_pipeline_report.json")
    csv_file = get_input("CSV output path (optional)", "Result/recon_pipeline_report.csv")
    rate = float(get_input("Rate limit (seconds)", str(RECON_RATE)))

    print(f"\n[*] Running Wayback recon for {len(targets)} target(s)...")
    report = summarize_targets(targets, rate=rate)

    save_recon_json(output_file, report)
    print(f"[+] JSON saved to: {output_file}")

    if csv_file:
        save_recon_csv(csv_file, report)
        print(f"[+] CSV saved to: {csv_file}")

    input("\nPress Enter to continue...")


def main_menu():
    """Main menu loop"""
    while True:
        clear_screen()
        print_header()
        print("[1] Google CSE Search")
        print("[2] Wayback Machine (CDX) Search")
        print("[3] DuckDuckGo Search")
        print("[4] C99.nl Subdomain Finder")
        print("[5] Cross-Reference Results")
        print("[6] Recon Pipeline (Wayback + Params)")
        print("[7] Passive Probe (Headers/CSP/CORS)")
        print("[8] View Dork Templates")
        print("[0] Exit")
        print()
        
        choice = input("Select an option (0-8): ").strip()
        
        if choice == '1':
            menu_google_search()
        elif choice == '2':
            menu_wayback_search()
        elif choice == '3':
            menu_duckduckgo_search()
        elif choice == '4':
            menu_c99_subdomain_search()
        elif choice == '5':
            menu_cross_reference()
        elif choice == '6':
            menu_recon_pipeline()
        elif choice == '7':
            menu_passive_probe()
        elif choice == '8':
            menu_view_templates()
        elif choice == '0':
            print("\n[*] Exiting Dork Searcher. Goodbye!")
            sys.exit(0)
        else:
            print("Invalid option. Please try again.")
            input("Press Enter to continue...")


def main():
    """Entry point"""
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n[*] Interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n[!] Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Recon pipeline — Wayback + parameter extraction (gau-like)

Usage:
python recon_pipeline.py --targets t-mobile.com account.t-mobile.com --output out.json --csv out.csv

This script is passive: it only queries public archives (Internet Archive CDX).
"""
from __future__ import annotations
import argparse
import json
import time
import sys
from typing import List, Dict, Set, Tuple
from urllib.parse import urlparse, parse_qsl, unquote

import requests

RATE = 1.0  # seconds between archive requests


def fetch_wayback_urls(target: str, limit: int = 5000) -> List[str]:
    """Fetch unique historical URLs for a given target from the Wayback CDX API."""
    endpoint = 'http://web.archive.org/cdx/search/cdx'
    params = {
        'url': f'{target}/*',
        'output': 'json',
        'fl': 'original',
        'collapse': 'urlkey',
        'limit': limit,
    }
    r = requests.get(endpoint, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    urls = []
    # first row may be header
    for row in data[1:]:
        urls.append(row[0])
    return urls


def extract_params_from_url(url: str) -> Dict[str, List[str]]:
    parsed = urlparse(url)
    query = parsed.query
    params = {}
    if query:
        for k, v in parse_qsl(query, keep_blank_values=True):
            k = unquote(k)
            v = unquote(v)
            params.setdefault(k, []).append(v)
    return params


def summarize_targets(targets: List[str], rate: float = RATE) -> Dict[str, Dict]:
    report = {}
    for t in targets:
        print(f"[+] Fetching Wayback URLs for: {t}")
        try:
            urls = fetch_wayback_urls(t)
        except Exception as e:
            print(f"  ! Error fetching for {t}: {e}", file=sys.stderr)
            urls = []
        print(f"  -> Retrieved {len(urls)} historical URLs")

        unique_urls = list(dict.fromkeys(urls))
        params_map: Dict[str, Set[str]] = {}
        endpoints: Set[str] = set()

        for u in unique_urls:
            parsed = urlparse(u)
            path = parsed.path or '/'
            endpoints.add(path)
            p = extract_params_from_url(u)
            for k, vals in p.items():
                if k not in params_map:
                    params_map[k] = set()
                for v in vals:
                    params_map[k].add(v)

        # convert sets to lists for JSON
        params_summary = {k: {'count': len(vs), 'examples': list(list(vs)[:10])} for k, vs in params_map.items()}

        report[t] = {
            'target': t,
            'total_historical_urls': len(unique_urls),
            'unique_endpoints': len(endpoints),
            'endpoints_sample': list(list(endpoints)[:50]),
            'parameters': params_summary,
            'urls': unique_urls,
        }

        time.sleep(rate)

    return report


def save_json(path: str, data: Dict):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_csv(path: str, report: Dict[str, Dict]):
    import csv

    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['target', 'url', 'path', 'params'])
        for t, data in report.items():
            for u in data.get('urls', []):
                parsed = urlparse(u)
                path = parsed.path or '/'
                params = parsed.query
                w.writerow([t, u, path, params])


def parse_args():
    p = argparse.ArgumentParser(description='Wayback recon pipeline')
    p.add_argument('--targets', nargs='+', required=True)
    p.add_argument('--output', required=True, help='JSON output path')
    p.add_argument('--csv', help='Optional CSV path')
    p.add_argument('--rate', type=float, default=RATE, help='Seconds between archive requests')
    return p.parse_args()


def main():
    args = parse_args()
    report = summarize_targets(args.targets, rate=args.rate)
    save_json(args.output, report)
    print(f"Saved JSON report to: {args.output}")
    if args.csv:
        save_csv(args.csv, report)
        print(f"Saved CSV to: {args.csv}")


if __name__ == '__main__':
    main()

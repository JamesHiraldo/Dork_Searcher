#!/usr/bin/env python3
"""Passive probe — parameter extraction + header/CSP/CORS checker using httpx

Usage examples:
python passive_probe.py --urls-file urls.txt --output out.json --csv out.csv
python passive_probe.py --targets t-mobile.com account.t-mobile.com --output out.json --csv out.csv --test-cors

Important: This script makes safe, read-only GET requests. Use only against in-scope targets.
"""
from __future__ import annotations
import argparse
import json
import csv
import asyncio
import sys
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qsl, unquote, urljoin

import httpx

DEFAULT_CONCURRENCY = 8
DEFAULT_TIMEOUT = 15.0

SEC_HEADERS = [
    'content-security-policy',
    'access-control-allow-origin',
    'x-frame-options',
    'x-content-type-options',
    'strict-transport-security',
    'referrer-policy',
    'permissions-policy',
    'x-xss-protection',
]

COMMON_PATHS = ['/', '/robots.txt', '/.well-known/security.txt', '/favicon.ico']


def extract_params(url: str) -> Dict[str, List[str]]:
    parsed = urlparse(url)
    params: Dict[str, List[str]] = {}
    if parsed.query:
        for k, v in parse_qsl(parsed.query, keep_blank_values=True):
            k = unquote(k)
            v = unquote(v)
            params.setdefault(k, []).append(v)
    return params


async def probe_url(client: httpx.AsyncClient, url: str, test_cors: bool = False, origin: str = 'https://example.com') -> Dict[str, Any]:
    result: Dict[str, Any] = {'url': url, 'status': None, 'headers': {}, 'params': {}, 'cors_test': None}
    try:
        headers = {}
        if test_cors:
            headers['Origin'] = origin
        r = await client.get(url, headers=headers)
        result['status'] = r.status_code
        # normalize headers to lowercase keys
        headers_map = {k.lower(): v for k, v in r.headers.items()}
        result['headers'] = {k: headers_map.get(k) for k in SEC_HEADERS if k in headers_map}
        result['params'] = extract_params(str(r.url))

        # CORS analysis (if ACAO present)
        acao = headers_map.get('access-control-allow-origin')
        if acao is not None:
            result['cors_test'] = {'access_control_allow_origin': acao, 'vulnerable_reflection': False}
            if test_cors:
                # if ACAO equals the Origin we sent or '*', flag potential issue
                if acao == '*' or acao == origin:
                    result['cors_test']['vulnerable_reflection'] = True
    except httpx.RequestError as e:
        result['error'] = str(e)
    except Exception as e:
        result['error'] = str(e)
    return result


async def worker(urls_queue: asyncio.Queue, client: httpx.AsyncClient, results: List[Dict[str, Any]], test_cors: bool):
    while not urls_queue.empty():
        url = await urls_queue.get()
        try:
            res = await probe_url(client, url, test_cors=test_cors)
            results.append(res)
        except Exception as e:
            results.append({'url': url, 'error': str(e)})
        urls_queue.task_done()


async def run_probes(urls: List[str], concurrency: int = DEFAULT_CONCURRENCY, timeout: float = DEFAULT_TIMEOUT, test_cors: bool = False) -> List[Dict[str, Any]]:
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True, verify=True) as client:
        q: asyncio.Queue = asyncio.Queue()
        for u in urls:
            await q.put(u)
        results: List[Dict[str, Any]] = []
        tasks = [asyncio.create_task(worker(q, client, results, test_cors)) for _ in range(min(concurrency, len(urls)))]
        await q.join()
        for t in tasks:
            t.cancel()
        return results


def build_target_urls_from_domains(domains: List[str]) -> List[str]:
    urls: List[str] = []
    for d in domains:
        if not d.startswith('http'):
            base = 'https://' + d
        else:
            base = d
        for p in COMMON_PATHS:
            urls.append(urljoin(base, p))
    return urls


def save_json(path: str, data: List[Dict[str, Any]]):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_csv(path: str, data: List[Dict[str, Any]]):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['url', 'status', 'headers', 'params', 'cors_vulnerable', 'error'])
        for r in data:
            cors_vuln = ''
            if r.get('cors_test'):
                cors_vuln = str(r['cors_test'].get('vulnerable_reflection', False))
            w.writerow([r.get('url'), r.get('status'), json.dumps(r.get('headers', {})), json.dumps(r.get('params', {})), cors_vuln, r.get('error', '')])


def parse_args():
    p = argparse.ArgumentParser(description='Passive header/CSP/CORS checker')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--urls-file', help='File with one URL per line')
    g.add_argument('--targets', nargs='+', help='One or more domain targets (will probe common paths)')
    p.add_argument('--output', required=True, help='JSON output path')
    p.add_argument('--csv', help='Optional CSV path')
    p.add_argument('--concurrency', type=int, default=DEFAULT_CONCURRENCY)
    p.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
    p.add_argument('--test-cors', action='store_true', help='Send an Origin header to test CORS reflections (non-destructive)')
    return p.parse_args()


def main():
    args = parse_args()
    urls: List[str] = []
    if args.urls_file:
        with open(args.urls_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    urls.append(line)
    else:
        urls = build_target_urls_from_domains(args.targets)

    if not urls:
        print('No URLs to probe', file=sys.stderr)
        sys.exit(1)

    print(f'Probing {len(urls)} URLs (concurrency={args.concurrency})')
    results = asyncio.run(run_probes(urls, concurrency=args.concurrency, timeout=args.timeout, test_cors=args.test_cors))

    save_json(args.output, results)
    print(f'JSON saved to: {args.output}')
    if args.csv:
        save_csv(args.csv, results)
        print(f'CSV saved to: {args.csv}')


if __name__ == '__main__':
    main()

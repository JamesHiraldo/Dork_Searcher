#!/usr/bin/env python3
"""Dork Searcher — API-based dork runner

Supports backends: google (CSE), wayback (CDX), duckduckgo, dogpile, dnsdumpster, c99subdomain

Usage example:
python searcher.py --backend wayback --targets t-mobile.com account.t-mobile.com --output out.json
python searcher.py --backend duckduckgo --targets t-mobile.com --output out.json
python searcher.py --backend c99subdomain --targets t-mobile.com --output out.json
"""
from __future__ import annotations
import argparse
import asyncio
import html
import re
import json
import time
import csv
import sys
import urllib.parse
from typing import List, Dict, Any

import requests

# GHDB-like templates (kept conservative)
DORK_TEMPLATES = [
    'site:{t} intitle:"index of"',
    'site:{t} inurl:admin',
    'site:{t} inurl:login OR inurl:signin',
    'site:{t} inurl:api OR inurl:/api/',
    'site:{t} filetype:pdf OR filetype:doc OR filetype:docx OR filetype:xls',
    'site:{t} "password" OR "credentials" OR "private key"',
    'site:{t} ext:env OR filetype:env OR filetype:ini',
    'site:{t} "flag.txt" OR "secret"',
    'site:{t} inurl:upload OR inurl:files',
    'site:{t} "index of" + /backup /old /archive',
    'site:{t} inurl:staging OR inurl:dev OR inurl:test',
]

RATE_LIMIT = 1.0  # seconds between API calls by default


def redact_secrets(text: str, secrets: List[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, '[REDACTED]')
    return redacted


def safe_error_message(err: Exception, secrets: List[str]) -> str:
    msg = str(err).strip() or err.__class__.__name__
    return redact_secrets(msg, secrets)


def build_queries(targets: List[str]) -> List[str]:
    q = []
    for t in targets:
        for tpl in DORK_TEMPLATES:
            q.append(tpl.format(t=t))
    return q


# Bing backend removed — use Google CSE or Wayback instead


def search_google_cse(query: str, api_key: str, cse_id: str, num: int = 10) -> List[Dict[str, Any]]:
    endpoint = 'https://www.googleapis.com/customsearch/v1'
    params = {'key': api_key, 'cx': cse_id, 'q': query, 'num': num}
    r = requests.get(endpoint, params=params, timeout=15)
    r.raise_for_status()
    j = r.json()
    items = []
    for it in j.get('items', []):
        items.append({'title': it.get('title'), 'url': it.get('link'), 'snippet': it.get('snippet')})
    return items


def search_wayback(target: str, max_retries: int = 3) -> List[Dict[str, Any]]:
    """Query Wayback Machine CDX API with retry logic
    
    Args:
        target: Domain to search
        max_retries: Number of retry attempts (default 3)
    """
    url = 'https://web.archive.org/cdx/search/cdx'
    params = {
        'url': f'{target}/*',
        'output': 'txt',
        'fl': 'original',
        'collapse': 'urlkey',
        'limit': '5000',
    }
    results = []
    
    for attempt in range(max_retries):
        try:
            # Use HTTPS and longer timeout (60s for large archives)
            print(f'  [*] Wayback Machine attempt {attempt + 1}/{max_retries}...')
            r = requests.get(url, params=params, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
            r.raise_for_status()
            for line in r.text.splitlines():
                original = line.strip()
                if not original or original.lower() == 'original':
                    continue
                results.append({'title': None, 'url': original, 'snippet': None})
            
            print(f'  [+] Found {len(results)} results from Wayback Machine')
            return results
            
        except requests.exceptions.Timeout:
            print(f'  ! Timeout on attempt {attempt + 1}/{max_retries}. Retrying...')
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
            continue
        except requests.exceptions.ConnectionError:
            print(f'  ! Connection error on attempt {attempt + 1}/{max_retries}. Retrying...')
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            continue
        except requests.exceptions.RequestException as e:
            print(f'  ! Request error: {str(e)[:100]}')
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            continue
        except (json.JSONDecodeError, IndexError, ValueError) as e:
            print(f'  ! Failed to parse Wayback response: {str(e)[:100]}')
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            continue
    
    # All retries exhausted
    print(f'  ! Wayback Machine unavailable after {max_retries} attempts')
    return results


def search_duckduckgo(query: str, num: int = 10) -> List[Dict[str, Any]]:
    # Query DuckDuckGo API (instant answer endpoint)
    url = 'https://api.duckduckgo.com/'
    params = {'q': query, 'format': 'json', 'no_redirect': '1'}
    r = requests.get(url, params=params, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
    r.raise_for_status()
    j = r.json()
    results = []
    
    # Add the main result if available
    if j.get('AbstractURL'):
        results.append({
            'title': j.get('Heading', query),
            'url': j.get('AbstractURL'),
            'snippet': j.get('Abstract', '')
        })
    
    # Add related topics (if any)
    for item in j.get('Related', []):
        results.append({
            'title': item.get('Text', ''),
            'url': item.get('FirstURL', ''),
            'snippet': ''
        })
        if len(results) >= num:
            break

    if not results:
        print(f'  ! DuckDuckGo returned zero results for query: {query}')
    
    return results[:num]


def search_brave_web(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Render Brave Search in a headless browser and extract site-matching results."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print('  ! Playwright is not installed; cannot use browser fallback')
        return []

    target_match = re.search(r'\bsite:([^\s]+)', query, re.IGNORECASE)
    target_domain = target_match.group(1).lower().strip().rstrip('.') if target_match else ''

    def is_allowed_host(host: str) -> bool:
        if not target_domain:
            return True
        host = host.lower().strip().rstrip('.')
        return host == target_domain or host.endswith('.' + target_domain)

    async def _fetch_results() -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        seen = set()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent='Mozilla/5.0')
                search_url = 'https://search.brave.com/search?source=web&q=' + urllib.parse.quote(query)
                await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(5000)

                page_text = await page.locator('body').inner_text()
                if 'captcha' in page_text.lower() or 'temporarily unavailable' in page_text.lower():
                    return []

                anchors = await page.locator('main a').evaluate_all(
                    '(elements) => elements.map((anchor) => ({ href: anchor.href || "", text: (anchor.textContent || "").replace(/\\s+/g, " ").trim(), aria: anchor.getAttribute("aria-label") || "" }))'
                )
                for anchor in anchors:
                    href = anchor.get('href', '').strip()
                    if not href.startswith('http'):
                        continue
                    parsed = urllib.parse.urlparse(href)
                    if not parsed.netloc:
                        continue
                    if 'brave.com' in parsed.netloc.lower():
                        continue
                    if not is_allowed_host(parsed.netloc):
                        continue

                    normalized_link = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))
                    if normalized_link in seen:
                        continue
                    seen.add(normalized_link)

                    title = anchor.get('text') or anchor.get('aria') or parsed.netloc
                    results.append({'title': title, 'url': href, 'snippet': ''})
                    if len(results) >= num:
                        break
                return results
            finally:
                await browser.close()

    try:
        return asyncio.run(_fetch_results())
    except Exception as e:
        print(f'  ! Brave browser fallback failed: {str(e)[:100]}')
        return []


def search_dogpile(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Search Dogpile and extract external result links from the HTML page."""
    url = 'https://www.dogpile.com/search'
    params = {'q': query}
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, params=params, timeout=20, headers=headers)
    r.raise_for_status()

    results: List[Dict[str, Any]] = []
    seen = set()
    target_match = re.search(r'\bsite:([^\s]+)', query, re.IGNORECASE)
    target_domain = target_match.group(1).lower().strip().rstrip('.') if target_match else ''
    loading_shell = (
        'Loading search results...' in r.text
        or 'web-result-skeleton' in r.text
        or 'serp-first-paint-skeleton' in r.text
    )

    def is_allowed_host(host: str) -> bool:
        if not target_domain:
            return True
        host = host.lower().strip().rstrip('.')
        return host == target_domain or host.endswith('.' + target_domain)

    for match in re.finditer(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', r.text, re.IGNORECASE | re.DOTALL):
        link = html.unescape(match.group(1)).strip()
        anchor_text = re.sub(r'<[^>]+>', ' ', html.unescape(match.group(2)))
        anchor_text = re.sub(r'\s+', ' ', anchor_text).strip()

        parsed = urllib.parse.urlparse(link)
        if not parsed.netloc or 'dogpile.com' in parsed.netloc.lower():
            continue
        if not is_allowed_host(parsed.netloc):
            continue

        normalized_link = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))
        if normalized_link in seen:
            continue
        seen.add(normalized_link)

        title = anchor_text or parsed.netloc
        results.append({'title': title, 'url': link, 'snippet': ''})
        if len(results) >= num:
            break

    if results:
        return results

    if loading_shell:
        print(f'  ! Dogpile only returned the loading shell for query: {query}')
        print('  [*] Falling back to browser-rendered Brave results...')
        fallback_results = search_brave_web(query, num=num)
        if not fallback_results:
            print('  [*] Falling back to DuckDuckGo results...')
            fallback_results = search_duckduckgo(query, num=num)
        if not fallback_results:
            print(f'  ! Browser and DuckDuckGo fallbacks returned zero results for query: {query}')
        return fallback_results

    print(f'  ! Dogpile returned zero results for query: {query}')

    return results


def search_dnsdumpster(target: str, api_key: str) -> List[Dict[str, Any]]:
    """Query DNSDumpster API for DNS records related to a target domain."""
    endpoint = f'https://api.dnsdumpster.com/domain/{target}'
    headers = {
        'X-API-Key': api_key,
        'User-Agent': 'Mozilla/5.0',
    }
    r = requests.get(endpoint, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()

    results: List[Dict[str, Any]] = []
    seen = set()

    def add_host(host: str, record_type: str, snippet: str):
        if not host:
            return
        normalized = host.strip().lower()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        results.append({
            'title': host,
            'url': f'https://{host}',
            'snippet': snippet,
        })

    for record_type in ('a', 'cname', 'mx', 'ns'):
        for entry in data.get(record_type, []):
            host = entry.get('host', '')
            ip_values = []
            for ip_entry in entry.get('ips', []):
                ip = ip_entry.get('ip')
                if ip:
                    ip_values.append(ip)
            snippet_bits = [f'DNSDumpster {record_type.upper()} record']
            if ip_values:
                snippet_bits.append(f'IPs: {", ".join(ip_values[:3])}')
            add_host(host, record_type, ' | '.join(snippet_bits))

    if not results:
        print(f'  ! DNSDumpster returned zero results for target: {target}')

    return results


def search_c99_subdomains(target: str) -> List[Dict[str, Any]]:
    """Query subdomain finder using multiple sources"""
    results = []
    seen = set()
    
    # Method 1: Try certificate.sh API (alternative CT aggregator)
    try:
        print(f'  [*] Searching certificate.sh for {target}...')
        url = 'https://certificate.sh/api/subdomains'
        params = {'domain': target}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        r = requests.get(url, params=params, timeout=15, headers=headers)
        if r.status_code == 200:
            try:
                j = r.json()
                if isinstance(j, dict) and 'subdomains' in j:
                    for subdomain in j.get('subdomains', []):
                        if subdomain and subdomain not in seen:
                            seen.add(subdomain)
                            results.append({'title': subdomain, 'url': f'https://{subdomain}', 'snippet': f'Certificate data'})
            except (json.JSONDecodeError, ValueError):
                pass
    except Exception as e:
        pass
    
    # Method 2: Try virustotal-like endpoint
    if not results or len(results) < 5:
        try:
            print(f'  [*] Searching subdomain patterns for {target}...')
            # Common subdomain patterns to check
            patterns = ['www', 'api', 'mail', 'ftp', 'smtp', 'pop', 'ns', 'vpn', 'admin', 'test', 
                       'dev', 'staging', 'dev-', 'test-', 'api-', 'auth', 'login', 'secure', 'portal',
                       'cdn', 'static', 'images', 'media', 'assets', 'download', 'files', 'blog']
            
            for pattern in patterns:
                subdomain = f'{pattern}.{target}'
                if subdomain not in seen:
                    results.append({
                        'title': subdomain,
                        'url': f'https://{subdomain}',
                        'snippet': f'Common pattern - requires verification'
                    })
                    seen.add(subdomain)
        except Exception as e:
            pass
    
    # Method 3: Try c99.nl API as fallback
    if not results:
        try:
            print(f'  [*] Searching c99.nl (fallback)...')
            url = 'https://subdomainfinder.c99.nl/'
            params = {'domain': target}
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            
            r = requests.get(url, params=params, timeout=20, headers=headers)
            
            if r.status_code == 200:
                try:
                    j = r.json()
                    if isinstance(j, dict) and j.get('status') == 'success' and j.get('subdomains'):
                        for subdomain in j.get('subdomains', []):
                            if subdomain and subdomain not in seen:
                                results.append({'title': subdomain, 'url': f'https://{subdomain}', 'snippet': f'Subdomain of {target}'})
                                seen.add(subdomain)
                except (json.JSONDecodeError, ValueError):
                    pass
        except Exception as e:
            pass
    
    if not results:
        print(f'  ! No subdomains found. Generate pattern-based list.')
    
    return results


def cross_reference_with_subdomains(urls: List[str], subdomains: List[str]) -> List[Dict[str, Any]]:
    """Cross-reference URLs with discovered subdomains and return matches."""
    matches = []
    for url in urls:
        for subdomain in subdomains:
            if subdomain.lower() in url.lower():
                matches.append({
                    'url': url,
                    'subdomain': subdomain,
                    'match_type': 'direct_match'
                })
    return matches


def save_json(out_path: str, data: List[Dict[str, Any]]):
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_csv(out_path: str, data: List[Dict[str, Any]]):
    keys = ['query', 'title', 'url', 'snippet']
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for row in data:
            w.writerow({k: row.get(k, '') for k in keys})


def run_queries(queries: List[str], backend: str, api_key: str = None, cse_id: str = None, rate_limit: float = RATE_LIMIT) -> List[Dict[str, Any]]:
    results = []
    for i, q in enumerate(queries, 1):
        try:
            print(f'[{i}/{len(queries)}] Querying: {q}')
            if backend == 'google':
                if not api_key or not cse_id:
                    raise ValueError('Google CSE requires --api-key and --cse-id')
                items = search_google_cse(q, api_key, cse_id)
            elif backend == 'wayback':
                # for wayback we expect queries to be targets, so q is like 'site:target ...'
                # extract the target host from the query
                parsed_target = q.split()[0].replace('site:', '')
                items = search_wayback(parsed_target)
            elif backend == 'duckduckgo':
                items = search_duckduckgo(q)
            elif backend == 'dogpile':
                items = search_dogpile(q)
            elif backend == 'dnsdumpster':
                if not api_key:
                    raise ValueError('DNSDumpster requires --api-key')
                target = q.replace('site:', '').split()[0] if q else q
                items = search_dnsdumpster(target, api_key)
            elif backend == 'c99subdomain':
                # Extract target from query (e.g., 'site:example.com' or just 'example.com')
                target = q.replace('site:', '').split()[0] if q else q
                items = search_c99_subdomains(target)
            else:
                raise ValueError('Unsupported backend')

            for it in items:
                results.append({'query': q, 'title': it.get('title'), 'url': it.get('url'), 'snippet': it.get('snippet')})
            
            if items:
                print(f'  [+] {len(items)} results')
                
        except requests.exceptions.Timeout:
            print(f'  ! Timeout - service is slow or unreachable. Skipping...', file=sys.stderr)
        except requests.exceptions.ConnectionError:
            print(f'  ! Connection error - check internet connection', file=sys.stderr)
        except Exception as e:
            err_msg = safe_error_message(e, [api_key])
            print(f'  ! Error for query: {err_msg}', file=sys.stderr)
        
        time.sleep(rate_limit)
    
    # Clear sensitive references once query execution is complete.
    api_key = None
    return results


def parse_args():
    p = argparse.ArgumentParser(description='Dork Searcher (API-backed)')
    p.add_argument('--backend', choices=['google', 'wayback', 'duckduckgo', 'dogpile', 'dnsdumpster', 'c99subdomain'], required=True)
    p.add_argument('--api-key', help='API key for selected backend')
    p.add_argument('--cse-id', help='Google CSE ID (for google backend)')
    p.add_argument('--targets', nargs='+', required=True, help='One or more target domains')
    p.add_argument('--output', required=True, help='Output JSON file path')
    p.add_argument('--csv', help='Also write CSV to this path (optional)')
    p.add_argument('--rate', type=float, default=RATE_LIMIT, help='Seconds between API calls')
    p.add_argument('--cross-ref', help='Cross-reference results with subdomains from c99.nl (provide JSON file with previous c99subdomain results)')
    return p.parse_args()


def main():
    args = parse_args()
    queries = build_queries(args.targets)

    # If backend is wayback, build simplified target queries to avoid large dorks
    if args.backend == 'wayback':
        queries = [f'site:{t}' for t in args.targets]
    # If backend is c99subdomain, use targets directly
    elif args.backend in ['c99subdomain', 'dnsdumpster']:
        queries = [f'site:{t}' for t in args.targets]

    api_key = args.api_key
    results = run_queries(queries, args.backend, api_key=api_key, cse_id=args.cse_id, rate_limit=args.rate)

    # Cross-reference with subdomains if specified
    if args.cross_ref:
        try:
            with open(args.cross_ref, 'r', encoding='utf-8') as f:
                subdomain_results = json.load(f)
            subdomains = [item.get('url', '').replace('https://', '').replace('http://', '') 
                         for item in subdomain_results if item.get('url')]
            urls_to_check = [item.get('url', '') for item in results if item.get('url')]
            matches = cross_reference_with_subdomains(urls_to_check, subdomains)
            if matches:
                print(f'\n[+] Found {len(matches)} cross-reference matches:')
                for match in matches:
                    print(f'    {match["url"]} <-> {match["subdomain"]}')
                # Add cross-reference data to results
                results.extend([{'query': 'cross_reference', 'title': m['subdomain'], 'url': m['url'], 'snippet': m['match_type']} for m in matches])
        except Exception as e:
            print(f'  ! Error during cross-reference: {e}', file=sys.stderr)

    save_json(args.output, results)
    print(f'JSON results saved to: {args.output}')
    if args.csv:
        save_csv(args.csv, results)
        print(f'CSV results saved to: {args.csv}')

    # Clear sensitive references before exit.
    api_key = None
    args.api_key = None


if __name__ == '__main__':
    main()

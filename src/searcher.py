"""Legacy command alias. Web scraping backends were retired in Wayback-Recon 3.0."""

from __future__ import annotations

from .scope import match_url_to_scoped_hosts


def cross_reference_with_subdomains(urls: list[str], subdomains: list[str]) -> list[dict[str, str]]:
    matches = {}
    for url in urls:
        for host in match_url_to_scoped_hosts(url, subdomains):
            matches[url, host] = {"url": url, "subdomain": host, "match_type": "hostname_match"}
    return list(matches.values())


def main() -> int:
    from .cli import main as atlas_main

    return atlas_main()


if __name__ == "__main__":
    raise SystemExit(main())

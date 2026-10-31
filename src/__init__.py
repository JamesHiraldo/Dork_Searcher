"""Authorized search, archive, discovery, and HTTP reconnaissance tooling."""

__version__ = "4.0.1"
__author__ = "Maydayx2"
__description__ = "Wayback-Recon: subdomain discovery and availability history"


def main() -> int:
    """Load the interactive application lazily to keep library imports lightweight."""
    from .cli import main as cli_main

    return cli_main()


__all__ = ["main"]

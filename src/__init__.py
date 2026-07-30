"""Authorized search, archive, discovery, and HTTP reconnaissance tooling."""

__version__ = "2.0.0"
__author__ = "Maydayx2"
__description__ = "Authorized reconnaissance and endpoint research toolkit"


def main() -> int:
    """Load the interactive application lazily to keep library imports lightweight."""
    from .cli import main as cli_main

    return cli_main()


__all__ = ["main"]

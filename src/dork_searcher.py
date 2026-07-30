#!/usr/bin/env python3
"""Compatibility entry point for source checkouts."""

import sys

if __package__:
    from .cli import main
else:  # pragma: no cover
    from cli import main  # type: ignore

if __name__ == "__main__":
    sys.exit(main())

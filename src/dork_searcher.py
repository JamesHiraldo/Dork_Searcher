#!/usr/bin/env python3
"""Compatibility entry point for source checkouts."""

import sys

if __package__:
    from .cli import main
else:  # pragma: no cover
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.cli import main

if __name__ == "__main__":
    sys.exit(main())

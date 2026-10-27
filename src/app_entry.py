"""Executable bootstrap; keep imports identical to python -m src.cli."""

from src.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

"""Explicit release check: small passive provider queries and HTTP/DNS for example.com only."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.availability import check_host  # noqa: E402
from src.discovery import collect  # noqa: E402

for source in ("crtsh", "certspotter", "wayback"):
    result = collect("example.com", source, limit=5, max_pages=1)
    print(
        json.dumps(
            {
                "source": source,
                "status": result.status,
                "count": len(result.records),
                "truncated": result.truncated,
                "error": result.error,
            }
        ),
        flush=True,
    )
print(json.dumps(asyncio.run(check_host("example.com", timeout=5))), flush=True)

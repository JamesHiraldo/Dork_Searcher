"""Check publish-candidate files, not ignored private data or Git history. No network."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = {"dist", "build", "Wayback_Atlas_App", "__pycache__", "reports", "Result"}
SENSITIVE_SUFFIXES = {".exe", ".whl", ".sqlite3", ".db", ".pem", ".key", ".pyc"}
SIGNATURES = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b"),
}


def main() -> int:
    listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    issues = []
    files = [ROOT / name for name in set(listing.split("\0")) if name and (ROOT / name).is_file()]
    for path in files:
        relative = path.relative_to(ROOT)
        if (
            set(relative.parts) & GENERATED
            or path.suffix.lower() in SENSITIVE_SUFFIXES
            or path.name.startswith(".env")
            and path.name != ".env.example"
        ):
            issues.append(f"Generated/private artifact: {relative.as_posix()}")
            continue
        if path.stat().st_size > 1024 * 1024:
            issues.append(f"Unexpected file over 1 MiB: {relative.as_posix()}")
            continue
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            issues.append(f"Unexpected binary file: {relative.as_posix()}")
            continue
        for label, pattern in SIGNATURES.items():
            if pattern.search(content):
                issues.append(f"Possible {label}: {relative.as_posix()} (value withheld)")
        if path.suffix == ".md":
            for match in re.finditer(r"\]\(([^)]+)\)", content):
                link = match[1].split("#", 1)[0]
                if link and not re.match(r"[a-z]+:", link) and not (path.parent / link).exists():
                    issues.append(f"Broken local link in {relative.as_posix()}: {link}")
    for issue in sorted(issues):
        print(issue)
    if issues:
        return 1
    print(f"Repository hygiene passed for {len(files)} publish-candidate files.")
    print("This is a lightweight check, not a secrets audit of Git history or ignored data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

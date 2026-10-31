"""Transactional discovery inventory and append-only availability samples."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from .artifacts import atomic_write_text, save_csv, save_json
from .classification import EXPORT_STATES, classify_sample
from .discovery import DiscoveryResult
from .html_report import render_html
from .scope import normalize_hostname


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def availability_trend(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Distinguish observed changes from DNS/transport uncertainty and unchecked hosts."""
    transitions = 0
    previous = None
    known = 0
    positive = 0
    trailing_down = 0
    dns_transitions = 0
    prior_dns = None
    address_changes = 0
    prior_addresses = None
    for sample in samples:
        dns_state = sample.get("dns_state")
        dns_up = (
            True
            if dns_state == "resolved"
            else (False if dns_state in ("nxdomain", "no_address") else None)
        )
        if dns_up is not None and prior_dns is not None and dns_up != prior_dns:
            dns_transitions += 1
        prior_dns = dns_up
        addresses = tuple(sample.get("addresses", [])) if dns_up else None
        if addresses and prior_addresses and addresses != prior_addresses:
            address_changes += 1
        prior_addresses = addresses
        state = sample.get("state")
        value = (
            True
            if state in ("online", "tls_error")
            else (False if state in ("nxdomain", "no_address", "unreachable") else None)
        )
        if sample.get("http_requested") is False:
            value = None
        if value is None:
            previous = None
            trailing_down = 0
            continue
        known += 1
        positive += int(value)
        trailing_down = 0 if value else trailing_down + 1
        if previous is not None and previous != value:
            transitions += 1
        previous = value
    return {
        "sample_count": len(samples),
        "conclusive_samples": known,
        "observed_availability_percent": round(100 * positive / known, 1) if known else None,
        "transitions": transitions,
        "intermittent_candidate": transitions >= 2 or dns_transitions >= 2,
        "dns_transitions": dns_transitions,
        "address_changes": address_changes,
        "consecutive_down_observations": trailing_down,
    }


class Inventory:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS assets (
                target TEXT NOT NULL, hostname TEXT NOT NULL,
                first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
                PRIMARY KEY (target, hostname)
            );
            CREATE TABLE IF NOT EXISTS evidence (
                target TEXT NOT NULL, hostname TEXT NOT NULL, source TEXT NOT NULL,
                fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (target, hostname, source, fingerprint),
                FOREIGN KEY (target, hostname) REFERENCES assets(target, hostname)
            );
            CREATE TABLE IF NOT EXISTS provider_runs (
                id INTEGER PRIMARY KEY, target TEXT NOT NULL, source TEXT NOT NULL,
                observed_at TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY, target TEXT NOT NULL, hostname TEXT NOT NULL,
                checked_at TEXT NOT NULL, payload TEXT NOT NULL,
                FOREIGN KEY (target, hostname) REFERENCES assets(target, hostname)
            );
            CREATE INDEX IF NOT EXISTS checks_host ON checks(target, hostname, id);
        """)

    def __enter__(self) -> Inventory:
        return self

    def __exit__(self, *args: Any) -> None:
        self.db.close()

    def merge(self, target: str, result: DiscoveryResult) -> list[str]:
        with self.db:
            return self.merge_in_transaction(target, result)

    def merge_in_transaction(self, target: str, result: DiscoveryResult) -> list[str]:
        """Caller owns the transaction (also used by atomic discovery checkpoints)."""
        now = utc_now()
        new = []
        for item in result.records:
            host = item["hostname"]
            inserted = self.db.execute(
                "INSERT OR IGNORE INTO assets VALUES (?,?,?,?)", (target, host, now, now)
            ).rowcount
            if inserted:
                new.append(host)
            else:
                self.db.execute(
                    "UPDATE assets SET last_seen=? WHERE target=? AND hostname=?",
                    (now, target, host),
                )
            payload = json.dumps(item, sort_keys=True)
            digest = hashlib.sha256(payload.encode()).hexdigest()
            self.db.execute(
                "INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?)",
                (target, host, result.source, digest, payload),
            )
        summary = {
            "count": len(result.records),
            "new_hosts": new,
            "error": result.error,
            "truncated": result.truncated,
            "metadata": result.metadata,
        }
        self.db.execute(
            "INSERT INTO provider_runs(target,source,observed_at,status,payload) "
            "VALUES (?,?,?,?,?)",
            (target, result.source, now, result.status, json.dumps(summary)),
        )
        return new

    def targets(self) -> list[str]:
        return [
            row[0]
            for row in self.db.execute(
                "SELECT target FROM assets UNION SELECT target FROM provider_runs ORDER BY target"
            )
        ]

    def hosts(self, target: str, *, only_unchecked: bool = False) -> list[str]:
        condition = (
            " AND NOT EXISTS (SELECT 1 FROM checks c "
            "WHERE c.target=assets.target AND c.hostname=assets.hostname)"
            if only_unchecked
            else ""
        )
        return [
            row[0]
            for row in self.db.execute(
                "SELECT hostname FROM assets WHERE target=?" + condition + " ORDER BY hostname",
                (target,),
            )
        ]

    def save_check(self, target: str, sample: dict[str, Any]) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO checks(target,hostname,checked_at,payload) VALUES (?,?,?,?)",
                (target, sample["hostname"], sample["checked_at"], json.dumps(sample)),
            )

    def backup(self, destination: str | Path) -> Path:
        """Create a consistent full-database copy without overwriting any existing file."""
        path = Path(destination).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        deadline = time.monotonic() + 30

        def progress(status: int, remaining: int, total: int) -> None:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    "Database backup exceeded 30 seconds; retry during a quiet period"
                )

        try:
            connection = sqlite3.connect(path)
            try:
                self.db.backup(connection, pages=256, progress=progress, sleep=0.1)
                connection.execute("PRAGMA journal_mode=DELETE")
                if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed")
            finally:
                connection.close()
        except BaseException:
            # This path was created exclusively above, never an existing user file.
            path.unlink(missing_ok=True)
            raise
        return path

    def report(self, target: str) -> dict[str, Any]:
        assets = []
        for row in self.db.execute(
            "SELECT * FROM assets WHERE target=? ORDER BY hostname", (target,)
        ):
            asset = dict(row)
            evidence = [
                dict(e)
                for e in self.db.execute(
                    "SELECT source,payload FROM evidence WHERE target=? AND hostname=?",
                    (target, row["hostname"]),
                )
            ]
            asset["sources"] = sorted({e["source"] for e in evidence})
            asset["evidence"] = [
                {"source": e["source"], **json.loads(e["payload"])} for e in evidence
            ]
            archive_dates = sorted(
                {
                    str(e.get("observed_at"))
                    for e in asset["evidence"]
                    if e["source"] in ("wayback", "commoncrawl") and e.get("observed_at")
                }
            )
            asset["first_archived_sample"] = archive_dates[0] if archive_dates else None
            asset["last_archived_sample"] = archive_dates[-1] if archive_dates else None
            asset["archived_url_count"] = len({e["url"] for e in asset["evidence"] if e.get("url")})
            samples = [
                classify_sample(json.loads(s[0]))
                for s in reversed(
                    list(
                        self.db.execute(
                            "SELECT payload FROM checks WHERE target=? AND hostname=? "
                            "ORDER BY id DESC LIMIT 100",
                            (target, row["hostname"]),
                        )
                    )
                )
            ]
            asset["samples"] = samples
            asset["latest"] = samples[-1] if samples else classify_sample({"state": "unchecked"})
            asset.update(availability_trend(samples))
            assets.append(asset)
        runs = [
            {**dict(row), "payload": json.loads(row["payload"])}
            for row in self.db.execute(
                "SELECT * FROM provider_runs WHERE target=? ORDER BY id DESC LIMIT 100", (target,)
            )
        ]
        archived_urls = {e["url"] for a in assets for e in a["evidence"] if e.get("url")}
        parameters = sorted(
            {
                key
                for url in archived_urls
                for key, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)
            }
        )
        response_groups: dict[tuple[Any, ...], list[str]] = {}
        for asset in assets:
            for attempt in asset["latest"].get("http", []):
                fingerprint = attempt.get("body_fingerprint")
                if fingerprint:
                    key = (attempt.get("final_status", attempt.get("status")), fingerprint)
                    response_groups.setdefault(key, []).append(asset["hostname"])
        return {
            "schema_version": 2,
            "response_groups": [
                {
                    "status": key[0],
                    "fingerprint": key[1],
                    "hosts": sorted(set(hosts)),
                    "host_count": len(set(hosts)),
                }
                for key, hosts in response_groups.items()
                if len(set(hosts)) > 1
            ],
            "target": target,
            "generated_at": utc_now(),
            "history_window": "last 100 checks per host; complete history remains in SQLite",
            "notes": [
                "First/last seen are local discovery times, not creation/deletion dates.",
                "Archive dates are sampled captures, not exhaustive lifetime bounds.",
                "Intermittent is a candidate based on observed transitions, not proven randomness.",
                "No response is not proof a host is permanently dead.",
                "Alive means heuristically validated HTML, not guaranteed browser usability.",
                "Legacy online state describes transport only; "
                "use classification and webpage_accessible.",
            ],
            "assets": assets,
            "archive_summary": {
                "unique_urls": len(archived_urls),
                "parameter_names": parameters,
                "unique_endpoints": len(
                    {(urlsplit(u).netloc, urlsplit(u).path) for u in archived_urls}
                ),
            },
            "provider_runs": runs,
        }

    def export(
        self, target: str, directory: Path, *, filters: dict[str, Any] | None = None
    ) -> Path:
        target = normalize_hostname(target)
        report = self.report(target)
        if filters:
            report["assets"] = filter_assets(report["assets"], filters)
            selected_hosts = {a["hostname"] for a in report["assets"]}
            report["response_groups"] = [
                {
                    **group,
                    "hosts": [h for h in group["hosts"] if h in selected_hosts],
                    "host_count": sum(h in selected_hosts for h in group["hosts"]),
                }
                for group in report["response_groups"]
                if sum(h in selected_hosts for h in group["hosts"]) > 1
            ]
            report["filters"] = filters
            report["notes"].append(
                "Host inventory is filtered; archive/provider summaries retain target-wide context."
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        root = directory.expanduser().resolve()
        # Leave room for snapshot names and atomic-write temporary filenames on Windows.
        folder_limit = min(80, 170 - len(str(root))) if os.name == "nt" else 80
        if folder_limit < 16:
            raise ValueError(
                "Output path is too long for report folders; choose a shorter --output-dir"
            )
        folder = re.sub(r"[^a-z0-9.-]", "_", target)
        if folder != target or len(folder) > folder_limit:
            folder = (
                folder[: folder_limit - 11] + "-" + hashlib.sha256(target.encode()).hexdigest()[:10]
            )
        reserved = {
            "con",
            "prn",
            "aux",
            "nul",
            *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10)),
        }
        if folder.split(".")[0] in reserved:
            folder = "_" + folder
        destination = root / "reports" / folder / f"{stamp}_{uuid.uuid4().hex[:8]}"
        if not destination.resolve().is_relative_to(root):
            raise ValueError("Report folder resolves outside the output directory")
        destination.mkdir(parents=True, exist_ok=False)
        fields = [
            "hostname",
            "sources",
            "first_seen",
            "last_seen",
            "first_archived_sample",
            "last_archived_sample",
            "archived_url_count",
            "state",
            "classification",
            "network_reachable",
            "webpage_accessible",
            "confidence",
            "title",
            "final_url",
            "final_status",
            "cnames",
            "http_wildcard_possible",
            "dns_state",
            "addresses",
            "transitions",
            "dns_transitions",
            "address_changes",
            "intermittent_candidate",
            "sample_count",
            "observed_availability_percent",
        ]
        rows = []
        for asset in report["assets"]:
            rows.append(
                {
                    **asset,
                    "sources": ";".join(asset["sources"]),
                    "state": asset["latest"]["state"],
                    **{
                        key: asset["latest"].get(key)
                        for key in (
                            "classification",
                            "network_reachable",
                            "webpage_accessible",
                            "confidence",
                            "title",
                            "final_url",
                            "final_status",
                            "http_wildcard_possible",
                        )
                    },
                    "cnames": ";".join(asset["latest"].get("cnames", [])),
                    "dns_state": asset["latest"].get("dns_state", "unchecked"),
                    "addresses": ";".join(asset["latest"].get("addresses", [])),
                }
            )
        save_csv(str(destination / "inventory.csv"), fields, rows)
        for label, hosts in {
            "hosts": [a["hostname"] for a in report["assets"]],
            "alive": [a["hostname"] for a in report["assets"] if a["latest"]["webpage_accessible"]],
            "intermittent": [
                a["hostname"] for a in report["assets"] if a["intermittent_candidate"]
            ],
            "down_observed": [
                a["hostname"]
                for a in report["assets"]
                if a["latest"]["state"] in ("nxdomain", "no_address", "unreachable")
            ],
        }.items():
            atomic_write_text(
                str(destination / f"{label}.txt"), "\n".join(hosts) + ("\n" if hosts else "")
            )
        for label, states in EXPORT_STATES.items():
            hosts = [
                a["hostname"] for a in report["assets"] if a["latest"]["classification"] in states
            ]
            atomic_write_text(
                str(destination / f"{label}.txt"), "\n".join(hosts) + ("\n" if hosts else "")
            )
        atomic_write_text(str(destination / "report.html"), render_html(report))
        # Write the main report last: its presence marks a completed snapshot bundle.
        path = destination / "report.json"
        save_json(str(path), report)
        return path


def filter_assets(assets: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    selected = []
    for asset in assets:
        latest = asset["latest"]
        if filters.get("only_webpages"):
            allowed = {"confirmed_webpage"}
            if filters.get("include_protected"):
                allowed |= EXPORT_STATES["protected"]
            if filters.get("include_redirects"):
                allowed |= EXPORT_STATES["redirects"]
            if latest["classification"] not in allowed:
                continue
        if filters.get("classification") and latest["classification"] != filters["classification"]:
            continue
        if filters.get("status") and not any(
            a.get("final_status", a.get("status")) == filters["status"]
            for a in latest.get("http", [])
        ):
            continue
        selected.append(asset)
    return selected

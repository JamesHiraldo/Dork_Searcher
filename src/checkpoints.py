"""Versioned discovery runs with atomic evidence/cursor commits and optimistic concurrency."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections.abc import Callable
from typing import Any

import requests

from .discovery import DiscoveryResult
from .discovery_pages import CC_INDEX, SOURCES, Page, fetch_page, validate_dates
from .inventory import Inventory, utc_now
from .scope import normalize_hostname

FORMAT_VERSION = 1
KEY_NAMES = {
    "rapiddns": "RAPIDDNS_API_KEY",
    "completedns": "COMPLETEDNS_API_KEY",
    "certspotter": "CERTSPOTTER_API_KEY",
}


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Checkpoints:
    def __init__(self, inventory: Inventory) -> None:
        self.store = inventory
        self.db = inventory.db
        # Additive migration: old inventory/evidence/check tables are untouched.
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS discovery_jobs (
                id TEXT PRIMARY KEY, version INTEGER NOT NULL, target TEXT NOT NULL,
                created_at TEXT NOT NULL, config TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS discovery_checkpoints (
                job_id TEXT NOT NULL REFERENCES discovery_jobs(id), source TEXT NOT NULL,
                revision INTEGER NOT NULL, updated_at TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(job_id, source)
            );
            CREATE TABLE IF NOT EXISTS discovery_cursors (
                job_id TEXT NOT NULL, source TEXT NOT NULL, digest TEXT NOT NULL,
                PRIMARY KEY(job_id, source, digest),
                FOREIGN KEY(job_id, source) REFERENCES discovery_checkpoints(job_id, source)
            );
        """)

    def create(
        self,
        target: str,
        sources: list[str],
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        cc_indexes: list[str] | None = None,
        cc_latest: int = 1,
        page_size: int = 1000,
    ) -> str:
        target = normalize_hostname(target)
        validate_dates(from_date, to_date)
        sources = list(dict.fromkeys(sources))
        if not sources or any(source not in SOURCES for source in sources):
            raise ValueError("Select at least one supported discovery source")
        indexes = list(dict.fromkeys(cc_indexes or []))
        if len(indexes) > 100 or any(not CC_INDEX.fullmatch(index) for index in indexes):
            raise ValueError("Use at most 100 crawl IDs in CC-MAIN-YYYY-NN format")
        if not 1 <= cc_latest <= 100 or not 1 <= page_size <= 10000:
            raise ValueError("Use 1-100 latest crawl indexes and a page size of 1-10000")
        config = {
            "sources": sources,
            "from_date": from_date,
            "to_date": to_date,
            "cc_indexes": indexes,
            "cc_latest": cc_latest,
            "page_size": page_size,
        }
        job = uuid.uuid4().hex
        now = utc_now()
        with self.db:
            self.db.execute(
                "INSERT INTO discovery_jobs VALUES (?,?,?,?,?)",
                (job, FORMAT_VERSION, target, now, json.dumps(config)),
            )
            for source in sources:
                state: dict[str, Any] = {
                    "status": "pending",
                    "cursor": {},
                    "pending": None,
                    "error": None,
                    "pages": 0,
                    "records": 0,
                }
                self.db.execute(
                    "INSERT INTO discovery_checkpoints VALUES (?,?,?,?,?)",
                    (job, source, 0, now, json.dumps(state)),
                )
        return job

    def job(self, job_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM discovery_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Discovery run not found in this output folder; use 'runs'")
        if row["version"] != FORMAT_VERSION:
            raise ValueError(
                "Unsupported checkpoint version; use the matching Wayback-Recon version"
            )
        return {**dict(row), "config": json.loads(row["config"])}

    def state(self, job_id: str, source: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT revision,payload FROM discovery_checkpoints WHERE job_id=? AND source=?",
            (job_id, source),
        ).fetchone()
        if row is None:
            raise ValueError("Missing source checkpoint")
        return {**json.loads(row["payload"]), "revision": row["revision"]}

    def save(
        self,
        job: dict[str, Any],
        source: str,
        state: dict[str, Any],
        result: DiscoveryResult | None = None,
        *,
        cursor_digest: str | None = None,
    ) -> list[str]:
        revision = state["revision"]
        payload = {key: value for key, value in state.items() if key != "revision"}
        with self.db:
            updated = self.db.execute(
                "UPDATE discovery_checkpoints SET revision=revision+1, updated_at=?, payload=? "
                "WHERE job_id=? AND source=? AND revision=?",
                (utc_now(), json.dumps(payload), job["id"], source, revision),
            ).rowcount
            if updated != 1:
                raise ValueError(
                    "Run changed in another process; stop duplicate workers and resume"
                )
            if cursor_digest:
                self.db.execute(
                    "INSERT INTO discovery_cursors VALUES (?,?,?)",
                    (job["id"], source, cursor_digest),
                )
            new = self.store.merge_in_transaction(job["target"], result) if result else []
        state["revision"] = revision + 1
        return new

    def stage(self, job: dict[str, Any], source: str, state: dict[str, Any], page: Page) -> None:
        digest = fingerprint(page.cursor)
        if not page.done and (
            page.cursor == state["cursor"]
            or self.db.execute(
                "SELECT 1 FROM discovery_cursors WHERE job_id=? AND source=? AND digest=?",
                (job["id"], source, digest),
            ).fetchone()
        ):
            raise ValueError(
                "Provider repeated a cursor; checkpoint retained. Start a new run if it persists"
            )
        state["pending"] = {
            "records": page.result.records,
            "offset": 0,
            "metadata": page.result.metadata,
            "cursor": page.cursor,
            "done": page.done,
        }
        state["pages"] += 1
        state["status"], state["error"] = "paused", None
        self.save(job, source, state, cursor_digest=digest if not page.done else None)

    def runs(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = []
        for row in self.db.execute(
            "SELECT id FROM discovery_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall():
            job = self.job(row["id"])
            states = {s: self.state(job["id"], s) for s in job["config"]["sources"]}
            rows.append(
                {
                    "id": job["id"],
                    "target": job["target"],
                    "created_at": job["created_at"],
                    "query": job["config"],
                    "crawl_indexes": (
                        states.get("commoncrawl", {}).get("cursor", {}).get("indexes")
                        or (states.get("commoncrawl", {}).get("pending") or {})
                        .get("cursor", {})
                        .get("indexes")
                        or job["config"].get("cc_indexes", [])
                    ),
                    "sources": {
                        s: {k: v[k] for k in ("status", "pages", "records", "error")}
                        for s, v in states.items()
                    },
                }
            )
        return rows


def run_discovery(
    checkpoints: Checkpoints,
    job_id: str,
    *,
    limit: int = 5000,
    max_pages: int = 20,
    on_progress: Callable[[str], None] | None = None,
) -> list[DiscoveryResult]:
    """Budgets are per source/per invocation. Completed sources are never re-fetched."""
    if not 1 <= limit <= 1000000 or not 1 <= max_pages <= 10000:
        raise ValueError("Use a record budget of 1-1000000 and a page budget of 1-10000")
    job = checkpoints.job(job_id)
    summaries = []
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Wayback-Recon/4.0"})
        for source in job["config"]["sources"]:
            state = checkpoints.state(job_id, source)
            processed = fetched = new_hosts = 0
            key = os.getenv(KEY_NAMES.get(source, ""), "")
            while state["status"] != "complete" and processed < limit:
                if state["pending"] is None:
                    if fetched >= max_pages:
                        break
                    if on_progress:
                        on_progress(f"{source}: fetching page; {state['records']} records saved")
                    try:
                        if fetched:
                            # Sequential provider queries, in addition to retry backoff.
                            time.sleep(1)
                        page = fetch_page(
                            job["target"], source, job["config"], state["cursor"], session, key
                        )
                        checkpoints.stage(job, source, state, page)
                    except (ValueError, requests.RequestException) as exc:
                        # A concurrent writer must not be overwritten by this error update: CAS.
                        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                        state["error"] = message.replace(key, "[REDACTED]") if key else message
                        state["status"] = "error"
                        checkpoints.save(
                            job,
                            source,
                            state,
                            DiscoveryResult(
                                source,
                                error=state["error"],
                                truncated=True,
                                metadata={"job_id": job_id},
                            ),
                        )
                        break
                    fetched += 1
                pending = state["pending"]
                offset = pending["offset"]
                batch = pending["records"][offset : offset + limit - processed]
                pending["offset"] += len(batch)
                if pending["offset"] == len(pending["records"]):
                    state["cursor"] = pending["cursor"]
                    state["status"] = "complete" if pending["done"] else "paused"
                    state["pending"] = None
                else:
                    state["status"] = "paused"
                state["error"] = None
                state["records"] += len(batch)
                result = DiscoveryResult(
                    source,
                    batch,
                    truncated=state["status"] != "complete",
                    metadata={
                        **pending["metadata"],
                        "job_id": job_id,
                        "page": state["pages"],
                        "page_offset": offset,
                        "checkpoint_status": state["status"],
                    },
                )
                new_hosts += len(checkpoints.save(job, source, state, result))
                processed += len(batch)
                if on_progress:
                    on_progress(f"{source}: {state['records']} records saved / {state['status']}")
            summaries.append(
                DiscoveryResult(
                    source,
                    error=state["error"],
                    truncated=state["status"] != "complete",
                    metadata={
                        "processed": processed,
                        "new_hosts": new_hosts,
                        "status": state["status"],
                        "total_records": state["records"],
                        "pages": state["pages"],
                        "job_id": job_id,
                    },
                )
            )
    return summaries

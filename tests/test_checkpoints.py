import io
import json
import sqlite3

import pytest
from rich.console import Console

import src.checkpoints as engine
import src.cli as cli
import src.discovery_pages as providers
from src.checkpoints import Checkpoints, run_discovery
from src.discovery import DiscoveryResult
from src.discovery_pages import Page, fetch_page
from src.inventory import Inventory


@pytest.fixture(autouse=True)
def no_delays(monkeypatch):
    monkeypatch.setattr(engine.time, "sleep", lambda _: None)


def page(source="wayback", names=("a", "b", "c"), cursor=None, done=False):
    return Page(
        DiscoveryResult(source, [{"hostname": f"{name}.example.com"} for name in names]),
        cursor or {"resume_key": "next"},
        done,
    )


def test_midpage_resume_survives_reopen_without_refetch(monkeypatch, tmp_path):
    calls = []

    def fetch(target, source, config, cursor, *args):
        calls.append(cursor)
        return page() if not cursor else page(names=("d",), done=True)

    monkeypatch.setattr(engine, "fetch_page", fetch)
    path = tmp_path / "inventory.sqlite3"
    with Inventory(path) as store:
        checkpoints = Checkpoints(store)
        job = checkpoints.create("example.com", ["wayback"])
        run_discovery(checkpoints, job, limit=1)
        assert store.hosts("example.com") == ["a.example.com"]
        assert checkpoints.state(job, "wayback")["pending"]["offset"] == 1
        assert store.report("example.com")["provider_runs"][0]["payload"]["truncated"] is True
    with Inventory(path) as store:
        checkpoints = Checkpoints(store)
        run_discovery(checkpoints, job, limit=2)
        assert len(calls) == 1  # Consumed the durable buffer, no request repeated.
        run_discovery(checkpoints, job)
        assert calls == [{}, {"resume_key": "next"}]
        assert len(store.hosts("example.com")) == 4
        assert checkpoints.state(job, "wayback")["status"] == "complete"
        assert store.report("example.com")["provider_runs"][0]["payload"]["truncated"] is False
        run_discovery(checkpoints, job)
        assert len(calls) == 2


def test_failed_page_resumes_same_cursor_and_skips_completed_source(monkeypatch, tmp_path):
    calls = []
    fail = True

    def fetch(target, source, config, cursor, *args):
        nonlocal fail
        calls.append((source, cursor))
        if source == "crtsh":
            return page(source, names=("ct",), done=True)
        if cursor and fail:
            fail = False
            raise ValueError("temporary provider error")
        return page() if not cursor else page(names=("d",), done=True)

    monkeypatch.setattr(engine, "fetch_page", fetch)
    with Inventory(tmp_path / "i.db") as store:
        cp = Checkpoints(store)
        job = cp.create("example.com", ["crtsh", "wayback"])
        results = run_discovery(cp, job)
        assert results[1].error
        assert len(store.hosts("example.com")) == 4
        run_discovery(cp, job)
        assert [source for source, _ in calls].count("crtsh") == 1
        assert calls[-1][1] == {"resume_key": "next"}
        assert len(store.hosts("example.com")) == 5


def test_failure_between_staging_and_merge_preserves_buffer(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "fetch_page", lambda *a: page(done=True))
    path = tmp_path / "i.db"
    with Inventory(path) as store:
        cp = Checkpoints(store)
        job = cp.create("example.com", ["wayback"])

        def crash(*args):
            raise KeyboardInterrupt

        monkeypatch.setattr(store, "merge_in_transaction", crash)
        with pytest.raises(KeyboardInterrupt):
            run_discovery(cp, job)
        assert cp.state(job, "wayback")["pending"]["offset"] == 0
        assert cp.state(job, "wayback")["records"] == 0
        assert store.hosts("example.com") == []
    monkeypatch.setattr(engine, "fetch_page", lambda *a: pytest.fail("Must use staged page"))
    with Inventory(path) as store:
        run_discovery(Checkpoints(store), job)
        assert len(store.hosts("example.com")) == 3


def test_evidence_and_cursor_rollback_together(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "fetch_page", lambda *a: page(done=True))
    with Inventory(tmp_path / "i.db") as store:
        cp = Checkpoints(store)
        job = cp.create("example.com", ["wayback"])
        original = store.merge_in_transaction

        def fail_after_insert(*args):
            original(*args)
            raise sqlite3.OperationalError("synthetic disk failure")

        monkeypatch.setattr(store, "merge_in_transaction", fail_after_insert)
        with pytest.raises(sqlite3.OperationalError):
            run_discovery(cp, job)
        assert store.db.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0
        assert cp.state(job, "wayback")["pending"]["offset"] == 0
        monkeypatch.setattr(store, "merge_in_transaction", original)
        run_discovery(cp, job)
        assert len(store.hosts("example.com")) == 3


def test_two_connections_cannot_commit_stale_progress(tmp_path):
    path = tmp_path / "i.db"
    with Inventory(path) as first, Inventory(path) as second:
        a, b = Checkpoints(first), Checkpoints(second)
        job = a.create("example.com", ["wayback"])
        stale = b.state(job, "wayback")
        a.stage(a.job(job), "wayback", a.state(job, "wayback"), page())
        with pytest.raises(ValueError, match="another process"):
            b.stage(b.job(job), "wayback", stale, page(names=("lost",), done=True))
        assert b.state(job, "wayback")["pending"]["records"][0]["hostname"] == "a.example.com"


def test_cycle_across_restarts_is_detected(monkeypatch, tmp_path):
    next_keys = iter(["A", "B", "A"])
    monkeypatch.setattr(engine, "fetch_page", lambda *a: page(cursor={"key": next(next_keys)}))
    with Inventory(tmp_path / "i.db") as store:
        cp = Checkpoints(store)
        job = cp.create("example.com", ["wayback"])
        for _ in range(3):
            run_discovery(cp, job, max_pages=1)
        state = cp.state(job, "wayback")
        assert state["status"] == "error"
        assert "repeated" in state["error"]
        assert state["cursor"] == {"key": "B"}
        assert store.db.execute("SELECT count(*) FROM evidence").fetchone()[0] == 3


def test_backup_contains_resumable_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "fetch_page", lambda *a: page(done=True))
    backup = tmp_path / "copy.db"
    with Inventory(tmp_path / "i.db") as store:
        cp = Checkpoints(store)
        job = cp.create("example.com", ["wayback"])
        run_discovery(cp, job, limit=1)
        store.backup(backup)
    monkeypatch.setattr(engine, "fetch_page", lambda *a: pytest.fail("No network"))
    with Inventory(backup) as store:
        run_discovery(Checkpoints(store), job)
        assert len(store.hosts("example.com")) == 3


@pytest.mark.parametrize(
    "options",
    [
        {"from_date": "20260230"},
        {"from_date": "2026", "to_date": "2025"},
        {"page_size": 0},
        {"cc_latest": 101},
        {"cc_indexes": ["https://attacker.invalid/"]},
    ],
)
def test_invalid_query_options_create_no_run(tmp_path, options):
    with Inventory(tmp_path / "i.db") as store:
        cp = Checkpoints(store)
        with pytest.raises(ValueError):
            cp.create("example.com", ["wayback"], **options)
        assert cp.runs() == []


def test_unknown_checkpoint_version_refused(tmp_path):
    with Inventory(tmp_path / "i.db") as store:
        cp = Checkpoints(store)
        job = cp.create("example.com", ["crtsh"])
        with store.db:
            store.db.execute("UPDATE discovery_jobs SET version=999")
        with pytest.raises(ValueError, match="version"):
            run_discovery(cp, job)


def test_cli_resume_and_json_runs(monkeypatch, tmp_path):
    stream = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=stream, width=40, color_system=None))
    monkeypatch.setattr(engine, "fetch_page", lambda *a: page(done=True))
    base = ["--output-dir", str(tmp_path)]
    assert (
        cli.main(
            [*base, "discover", "example.com", "--sources", "wayback", "--limit", "1", "--strict"]
        )
        == 1
    )
    stream.seek(0)
    stream.truncate()
    assert cli.main([*base, "runs", "--json"]) == 0
    runs = json.loads(stream.getvalue())
    assert runs[0]["sources"]["wayback"]["status"] == "paused"
    assert cli.main([*base, "resume", runs[0]["id"], "--strict"]) == 0
    assert cli.main([*base, "resume", "missing"]) == 2


class Response:
    def __init__(self, data, *, lines=False, status=200):
        self.body = ("\n".join(json.dumps(r) for r in data) if lines else json.dumps(data)).encode()
        self.status_code, self.headers, self.closed = status, {}, False

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        self.closed = True


class Session:
    def __init__(self, *responses):
        self.responses, self.calls = iter(responses), []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


CONFIG = {
    "page_size": 1000,
    "cc_latest": 2,
    "cc_indexes": [],
    "from_date": "2024",
    "to_date": "2026",
}


def test_commoncrawl_pins_catalog_and_paginates_indexes():
    session = Session(
        Response(
            [
                {"id": "CC-MAIN-2026-10", "cdx-api": "http://attacker.invalid"},
                {"id": "CC-MAIN-2025-50"},
                {"id": "../invalid"},
            ]
        ),
        Response({"pages": 2, "pageSize": 1}),
        Response(
            [
                {"url": "https://old.example.com/a?token=private", "timestamp": "20250101"},
                {"url": "https://notexample.com/"},
            ],
            lines=True,
        ),
        Response([], lines=True),
        Response([], status=404),
    )
    cursor = {}
    collected = []
    for _ in range(5):
        result = fetch_page("example.com", "commoncrawl", CONFIG, cursor, session)
        cursor = result.cursor
        collected.extend(result.result.records)
    assert result.done
    assert len(collected) == 1
    assert collected[0]["crawl_index"] == "CC-MAIN-2026-10"
    assert "private" not in collected[0]["url"]
    assert all(url.startswith(providers.CC_ROOT) for url, _ in session.calls)
    assert session.calls[2][1]["params"]["page"] == 0
    assert session.calls[3][1]["params"]["page"] == 1
    assert session.calls[2][1]["params"]["from"] == "2024"
    assert "limit" not in session.calls[2][1]["params"]
    assert session.calls[-1][0].endswith("CC-MAIN-2025-50-index")


def test_commoncrawl_jsonl_failure_does_not_advance():
    reply = Response([])
    reply.body = b'{"url":"https://example.com/"}\nprivate-invalid-json'
    cursor = {"indexes": ["CC-MAIN-2026-10"], "index": 0, "page": 0, "pages": 1}
    with pytest.raises(ValueError, match="invalid JSONL") as exc:
        fetch_page("example.com", "commoncrawl", CONFIG, cursor, Session(reply))
    assert "private" not in str(exc.value)
    assert cursor["page"] == 0 and reply.closed


def test_commoncrawl_unknown_explicit_index_is_not_empty_success():
    with pytest.raises(ValueError, match="published catalog"):
        fetch_page(
            "example.com",
            "commoncrawl",
            {**CONFIG, "cc_indexes": ["CC-MAIN-2000-01"]},
            {},
            Session(Response([])),
        )


def test_certspotter_saved_cursor_and_credentials_only_in_headers():
    session = Session(Response([{"id": "123", "dns_names": ["*.dev.example.com"]}]))
    result = fetch_page(
        "example.com", "certspotter", CONFIG, {"after": "122"}, session, "secret-key"
    )
    assert result.cursor == {"after": "123"}
    assert session.calls[0][1]["params"]["after"] == "122"
    assert session.calls[0][1]["headers"]["Authorization"] == "Bearer secret-key"
    assert "secret-key" not in json.dumps(result.result.__dict__)


def test_rapiddns_starts_from_saved_page():
    session = Session(
        Response(
            {
                "data": {
                    "total": 101,
                    "data": [{"subdomain": "old.example.com", "type": "A", "value": "1.1.1.1"}],
                }
            }
        )
    )
    result = fetch_page("example.com", "rapiddns", CONFIG, {"page": 2}, session, "secret")
    assert result.done and result.cursor == {"page": 3}
    assert session.calls[0][1]["params"]["page"] == 2
    assert result.result.records[0]["value"] == "1.1.1.1"


def test_wayback_sends_saved_key_and_stable_query(monkeypatch):
    calls = []

    def get(self, params):
        calls.append(params)
        return [
            ["original", "timestamp"],
            ["https://old.example.com/", "20240101000000"],
            [],
            ["next-key"],
        ]

    monkeypatch.setattr(providers.WaybackClient, "_get_page", get)
    result = fetch_page("example.com", "wayback", CONFIG, {"resume_key": "old-key"}, Session())
    assert result.cursor == {"resume_key": "next-key"} and not result.done
    assert calls[0]["resumeKey"] == "old-key"
    assert calls[0]["limit"] == 1000 and calls[0]["from"] == "2024"


@pytest.mark.parametrize(
    "payload",
    [
        [["original"], ["https://example.com/"], [], [None]],
        [["original"], ["https://example.com/"], []],
        [["original"], ["https://example.com/", "extra"]],
        [["original", "original"]],
    ],
)
def test_malformed_wayback_page_never_claims_completion(monkeypatch, payload):
    monkeypatch.setattr(providers.WaybackClient, "_get_page", lambda *a: payload)
    with pytest.raises(ValueError, match="Malformed"):
        fetch_page("example.com", "wayback", CONFIG, {}, Session())


def test_commoncrawl_resume_keeps_index_list_and_pending_rows(monkeypatch, tmp_path):
    calls = []
    replies = iter(
        [
            [{"id": "CC-MAIN-2026-20"}, {"id": "CC-MAIN-2026-10"}],
            {"pages": 1, "pageSize": 1},
            [{"url": "https://a.example.com/"}, {"url": "https://b.example.com/"}],
            {"pages": 1, "pageSize": 1},
            [{"url": "https://c.example.com/"}],
        ]
    )

    def request(session, url, **kwargs):
        calls.append(url)
        return next(replies)

    monkeypatch.setattr(providers, "request_json", request)
    path = tmp_path / "i.db"
    with Inventory(path) as store:
        cp = Checkpoints(store)
        job = cp.create("example.com", ["commoncrawl"], cc_latest=2)
        run_discovery(cp, job, limit=1, max_pages=3)
        assert cp.runs()[0]["crawl_indexes"] == ["CC-MAIN-2026-20", "CC-MAIN-2026-10"]
    with Inventory(path) as store:
        cp = Checkpoints(store)
        run_discovery(cp, job)
        assert cp.state(job, "commoncrawl")["status"] == "complete"
        assert len(store.hosts("example.com")) == 3
        assert sum(url.endswith("collinfo.json") for url in calls) == 1
        assert calls[-1].endswith("CC-MAIN-2026-10-index")


def test_network_interruption_before_staging_repeats_only_uncommitted_page(monkeypatch, tmp_path):
    attempts = []
    interrupt = True

    def fetch(target, source, config, cursor, *args):
        nonlocal interrupt
        attempts.append(cursor)
        if cursor and interrupt:
            interrupt = False
            raise KeyboardInterrupt
        return page(names=("b",), done=True) if cursor else page(names=("a",))

    monkeypatch.setattr(engine, "fetch_page", fetch)
    with Inventory(tmp_path / "i.db") as store:
        cp = Checkpoints(store)
        job = cp.create("example.com", ["wayback"])
        with pytest.raises(KeyboardInterrupt):
            run_discovery(cp, job)
        assert store.hosts("example.com") == ["a.example.com"]
        run_discovery(cp, job)
        assert attempts == [{}, {"resume_key": "next"}, {"resume_key": "next"}]
        assert len(store.hosts("example.com")) == 2


def test_single_response_source_buffers_after_close(monkeypatch, tmp_path):
    calls = []

    def request(*args, **kwargs):
        calls.append(1)
        return [{"name_value": "a.example.com\nb.example.com", "entry_timestamp": "2025-01-01"}]

    monkeypatch.setattr("src.discovery.request_json", request)
    with Inventory(tmp_path / "i.db") as store:
        cp = Checkpoints(store)
        job = cp.create("example.com", ["crtsh"])
        run_discovery(cp, job, limit=1)
        run_discovery(cp, job, limit=1)
        assert len(calls) == 1
        assert cp.state(job, "crtsh")["status"] == "complete"


def test_credentials_never_enter_checkpoint_or_error(monkeypatch, tmp_path):
    monkeypatch.setenv("RAPIDDNS_API_KEY", "private-secret")

    def fail(*args):
        raise ValueError("Bad key private-secret")

    monkeypatch.setattr(engine, "fetch_page", fail)
    with Inventory(tmp_path / "i.db") as store:
        cp = Checkpoints(store)
        job = cp.create("example.com", ["rapiddns"])
        run_discovery(cp, job)
        assert "private-secret" not in "\n".join(store.db.iterdump())
        assert "[REDACTED]" in cp.state(job, "rapiddns")["error"]


@pytest.mark.parametrize(
    "data",
    [{"pages": True, "pageSize": 1}, {"pages": -1, "pageSize": 1}, {"pages": 3, "pageSize": 5}, []],
)
def test_invalid_cc_page_counts_are_errors(data):
    # An HTTP-200 JSON [] is not the documented pagination response.
    session = Session(Response(data))
    with pytest.raises(ValueError, match="pagination schema"):
        fetch_page(
            "example.com",
            "commoncrawl",
            CONFIG,
            {"indexes": ["CC-MAIN-2026-10"], "index": 0, "page": 0},
            session,
        )

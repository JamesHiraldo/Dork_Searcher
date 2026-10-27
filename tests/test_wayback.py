import json

import requests

from src.wayback import WaybackClient, _parse_cdx_payload


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload

    def iter_content(self, chunk_size):
        yield json.dumps(self._payload).encode()

    def close(self):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_parse_cdx_resumption_trailer():
    urls, key = _parse_cdx_payload([["original"], ["https://example.com/a"], [], ["resume-key"]])
    assert urls == ["https://example.com/a"]
    assert key == "resume-key"


def test_wayback_paginates_and_filters_out_of_scope_urls():
    session = FakeSession(
        [
            FakeResponse(
                [
                    ["original"],
                    ["https://example.com/a"],
                    ["https://notexample.com/false-positive"],
                    [],
                    ["resume-key"],
                ]
            ),
            FakeResponse([["original"], ["https://example.com/b"]]),
        ]
    )
    client = WaybackClient(session=session, page_size=2, retries=1, backoff=0)
    result = client.fetch("example.com", max_urls=10, rate=0)

    assert result.ok
    assert result.urls == ["https://example.com/a", "https://example.com/b"]
    assert result.pages == 2
    assert session.calls[1][1]["params"]["resumeKey"] == "resume-key"


def test_wayback_transport_failure_is_explicit():
    session = FakeSession([requests.ConnectionError("offline")])
    client = WaybackClient(session=session, retries=1, backoff=0)
    result = client.fetch("example.com", rate=0)
    assert not result.ok
    assert "failed after 1 attempts" in result.error


def test_empty_cdx_is_valid_no_results():
    assert _parse_cdx_payload([]) == ([], None)


def test_capture_dates_and_page_budget_are_retained():
    session = FakeSession(
        [
            FakeResponse(
                [
                    ["original", "timestamp", "statuscode", "mimetype"],
                    ["https://old.example.com/", "20100102030405", "200", "text/html"],
                    [],
                    ["next-page"],
                ]
            )
        ]
    )
    result = WaybackClient(session=session).fetch(
        "example.com", include_subdomains=True, from_date="2000", max_pages=1, rate=0
    )
    assert result.truncated
    assert result.captures[0]["timestamp"] == "20100102030405"
    assert session.calls[0][1]["params"]["from"] == "2000"

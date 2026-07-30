import requests

from src.searcher import (
    build_queries,
    cross_reference_with_subdomains,
    search_certificate_transparency,
    search_dogpile,
    search_duckduckgo,
    search_google_cse,
)


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text
        self.status_code = 200
        self.headers = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_cross_reference_does_not_match_parent_string():
    assert cross_reference_with_subdomains(["https://notexample.com/path"], ["example.com"]) == []


def test_queries_scope_or_groups():
    queries = build_queries(["example.com"])
    assert len(queries) == 11
    assert "site:example.com (inurl:login OR inurl:signin)" in queries


def test_certificate_transparency_returns_only_observed_valid_scoped_names():
    session = FakeSession(
        [
            FakeResponse(
                [
                    {"name_value": "api.example.com\n*.dev.example.com"},
                    {"name_value": "notexample.com\ndev-.example.com"},
                ]
            )
        ]
    )
    results = search_certificate_transparency("example.com", session=session)
    assert [row["title"] for row in results] == ["api.example.com", "dev.example.com"]
    assert all(row["result_type"] == "observed" for row in results)


def test_certificate_transparency_falls_back_to_certspotter(monkeypatch):
    monkeypatch.setattr("src.searcher.time.sleep", lambda _delay: None)
    unavailable = FakeResponse([])
    unavailable.status_code = 502
    session = FakeSession(
        [
            unavailable,
            FakeResponse([{"id": "42", "dns_names": ["api.example.com"]}]),
            FakeResponse([]),
        ]
    )
    results = search_certificate_transparency("example.com", session=session)
    assert [row["title"] for row in results] == ["api.example.com"]
    assert results[0]["source"] == "certspotter"


def test_duckduckgo_html_parser_unwraps_and_enforces_scope():
    html = """
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">A</a>
    <a class="result__a" href="https://notexample.com/">Wrong scope</a>
    """
    session = FakeSession([FakeResponse(text=html)])
    results = search_duckduckgo("site:example.com test", session=session)
    assert [row["url"] for row in results] == ["https://example.com/a"]


def test_duckduckgo_falls_back_to_dogpile(monkeypatch):
    session = FakeSession([FakeResponse(text="<html>No results</html>")])
    dogpile_result = {
        "title": "Fallback",
        "url": "https://example.com/fallback",
        "snippet": "",
        "source": "dogpile_html",
        "result_type": "observed",
        "verified": False,
    }
    monkeypatch.setattr(
        "src.searcher.search_dogpile",
        lambda query, num, session: [dogpile_result],
    )
    monkeypatch.setattr(
        "src.searcher.search_brave_web",
        lambda query, num: (_ for _ in ()).throw(AssertionError("Brave should not run")),
    )

    assert search_duckduckgo("site:example.com test", session=session) == [dogpile_result]


def test_direct_dogpile_does_not_recurse_to_duckduckgo(monkeypatch):
    session = FakeSession([FakeResponse(text="<html>No results</html>")])
    monkeypatch.setattr(
        "src.searcher.search_duckduckgo",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected recursion")),
    )

    assert search_dogpile("site:example.com test", session=session) == []


def test_google_uses_pagination_and_api_site_restriction():
    first = [{"link": f"https://example.com/{index}"} for index in range(10)]
    second = [{"link": "https://example.com/10"}]
    session = FakeSession([FakeResponse({"items": first}), FakeResponse({"items": second})])
    results = search_google_cse(
        "site:example.com inurl:api", "secret", "engine", num=11, session=session
    )
    assert len(results) == 11
    assert len(session.calls) == 2
    assert session.calls[0][1]["params"]["siteSearch"] == "example.com"
    assert session.calls[1][1]["params"]["start"] == 11

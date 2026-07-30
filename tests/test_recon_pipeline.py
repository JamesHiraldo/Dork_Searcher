from src.recon_pipeline import (
    extract_params_from_url,
    redact_sensitive_url,
    summarize_targets,
)
from src.wayback import WaybackResult


class FakeWaybackClient:
    def fetch(self, target, **kwargs):
        return WaybackResult(
            target=target,
            urls=[
                "https://example.com/api?access_token=topsecret&id=2",
                "https://example.com/api?id=1&id=2",
            ],
            pages=2,
        )


def test_query_values_are_decoded_exactly_once():
    assert extract_params_from_url("https://example.com/?a=hello%2520world") == {
        "a": ["hello%20world"]
    }


def test_sensitive_values_are_redacted_in_urls():
    redacted = redact_sensitive_url(
        "https://example.com/callback?code=secret&id=4", include_sensitive_values=False
    )
    assert "secret" not in redacted
    assert "%5BREDACTED%5D" in redacted
    assert "id=4" in redacted


def test_report_counts_are_deterministic_and_errors_are_explicit():
    report = summarize_targets(
        ["example.com"], rate=0, client=FakeWaybackClient(), include_sensitive_values=False
    )["example.com"]
    assert report["status"] == "ok"
    assert report["pages_fetched"] == 2
    assert report["endpoints_sample"] == ["/api"]
    assert report["parameters"]["id"]["occurrences"] == 3
    assert report["parameters"]["id"]["unique_value_count"] == 2
    assert report["parameters"]["access_token"]["examples"] == ["[REDACTED]"]
    assert "topsecret" not in "".join(report["urls"])

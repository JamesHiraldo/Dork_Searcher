import pytest

from src.scope import (
    ScopeError,
    ensure_public_url,
    host_in_scope,
    match_url_to_scoped_hosts,
    normalize_hostname,
    normalize_targets,
    url_in_scope,
)


def test_normalize_and_dedupe_targets():
    assert normalize_targets(["Example.COM", "https://example.com/", "example.com."]) == [
        "example.com"
    ]


@pytest.mark.parametrize("target", ["dev-.example.com", "-api.example.com", "bad_name.example.com"])
def test_invalid_dns_labels_are_rejected(target):
    with pytest.raises(ScopeError):
        normalize_hostname(target)


def test_scope_uses_dns_boundaries_not_substrings():
    assert host_in_scope("api.example.com", "example.com")
    assert not host_in_scope("notexample.com", "example.com")
    assert not url_in_scope("https://notexample.com/x", ["example.com"])
    assert match_url_to_scoped_hosts("https://notexample.com/x", ["example.com"]) == []


def test_private_literal_is_blocked_without_dns_lookup():
    with pytest.raises(ScopeError):
        ensure_public_url("http://127.0.0.1/", resolve=False)

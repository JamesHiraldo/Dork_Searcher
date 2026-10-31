import pytest

import src.availability as availability


@pytest.mark.asyncio
async def test_private_dns_addresses_are_not_probed(monkeypatch):
    async def resolve(*args):
        return {"dns_state": "resolved", "addresses": ["127.0.0.1"], "cnames": [], "dns_errors": []}

    async def fail(*args):
        raise AssertionError("Private address should not be contacted")

    monkeypatch.setattr(availability, "resolve_host", resolve)
    monkeypatch.setattr(availability, "probe_address", fail)
    row = await availability.check_host("api.example.com")
    assert row["state"] == "private_address"


@pytest.mark.asyncio
async def test_dns_timeout_is_unknown_not_dead(monkeypatch):
    async def resolve(*args):
        return {
            "dns_state": "unknown",
            "addresses": [],
            "cnames": [],
            "dns_errors": ["LifetimeTimeout"],
        }

    monkeypatch.setattr(availability, "resolve_host", resolve)
    assert (await availability.check_host("api.example.com"))["state"] == "unknown"


@pytest.mark.asyncio
async def test_dns_only_missing_host_does_not_count_as_http_check(monkeypatch):
    async def resolve(*args):
        return {"dns_state": "nxdomain", "addresses": [], "cnames": [], "dns_errors": []}

    monkeypatch.setattr(availability, "resolve_host", resolve)
    row = await availability.check_host("api.example.com", http=False)
    assert row["state"] == "nxdomain"
    assert row["http_requested"] is False


@pytest.mark.asyncio
async def test_http_403_is_reachable_not_webpage_and_uses_pinned_ip(monkeypatch):
    class Response:
        status_code = 403
        headers = {"location": "https://unrelated.example/"}

        async def aiter_raw(self, **kwargs):
            yield b"Forbidden"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def stream(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return Response()

    monkeypatch.setattr(availability.httpx, "AsyncClient", Client)
    row = await availability.probe_address("api.example.com", "93.184.216.34", 2)
    assert row["state"] == "online"
    assert row["classification"] == "forbidden"
    assert row["network_reachable"] and not row["webpage_accessible"]
    assert calls[0][1] == "https://93.184.216.34/"
    assert calls[0][2]["headers"]["Host"] == "api.example.com"
    assert calls[0][2]["extensions"]["sni_hostname"] == "api.example.com"
    assert calls[0][2]["follow_redirects"] is False
    assert len(calls) == 1

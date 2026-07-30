import asyncio

import httpx
import pytest

from src.passive_probe import analyze_cors, probe_url, run_probes


def test_cors_wildcard_is_not_called_reflection():
    finding = analyze_cors({"access-control-allow-origin": "*"}, "https://example.com")
    assert finding["risk"] == "informational"
    assert not finding["origin_reflected"]
    assert not finding["vulnerable_reflection"]


def test_cors_reflection_with_credentials_is_high_risk():
    finding = analyze_cors(
        {
            "access-control-allow-origin": "https://example.com",
            "access-control-allow-credentials": "true",
            "vary": "Origin",
        },
        "https://example.com",
    )
    assert finding["risk"] == "high"
    assert finding["varies_on_origin"]


def test_zero_concurrency_is_rejected_instead_of_hanging():
    with pytest.raises(ValueError):
        asyncio.run(run_probes(["https://example.com"], concurrency=0))


def test_redirect_outside_scope_is_blocked():
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://outside.test/"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await probe_url(
                client,
                "https://example.test/",
                allowed_targets=["example.test"],
                allow_private=True,
            )

    result = asyncio.run(run())
    assert result["redirect_blocked"]
    assert "outside the authorized scope" in result["redirect_blocked"]["reason"]

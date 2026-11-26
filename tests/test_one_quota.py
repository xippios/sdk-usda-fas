"""One process that builds two clients on the gateway holds one quota policy for the key.

api.data.gov counts one hourly quota per key over every API behind it, so the sources that read
``DATA_GOV_API_KEY`` must spend it through one ``QuotaPolicy`` per process. Three copies of the
gateway, one in each source, could not give that; the one module here can (sdk-core ADR-0065,
decision 1). The tests build each client as a source's ``_client.py`` does and hold the policy
behind both by its identity and by what it does: what one client observes, the other's next
request sees, and a quota spent through one is refused through the other without sending.
"""

from collections.abc import Callable

import httpx
import pytest
from xippios.core import AsyncClient, ClientConfig, RateLimitError, XippiosError
from xippios.core.testing import CLOCK_SLACK

from xippios.usda.fas import Gateway, data_gov

BASE = "https://api.fas.usda.gov"
OVER_RATE_LIMIT = {"error": {"code": "OVER_RATE_LIMIT", "message": "You have exceeded your rate"}}


class Upstream:
    """NOT RECORDED: a ``MockTransport`` handler that serves composed answers in turn, in the
    shape sdk-usda-psd recorded behind the gateway on 2026-10-23, its quota headers and its
    429, and keeps what was sent (conventions §10, kind 2)."""

    def __init__(self, *answers: tuple[int, object, dict[str, str]]) -> None:
        self.answers = list(answers)
        self.sent: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(f"{request.method} {request.url.path}")
        status, body, headers = self.answers.pop(0)
        return httpx.Response(status, json=body, headers=headers)


def source_client(
    source: str,
    gateway: data_gov.Gateway,
    upstream: Callable[[httpx.Request], httpx.Response],
) -> AsyncClient:
    """The client a source's ``_client.py`` builds: its classify asks the gateway's first."""

    def classify(response: httpx.Response) -> XippiosError | None:
        return gateway.classify(response)

    config = gateway.install(
        ClientConfig(source=source, version="1", base_url=BASE, classify=classify)
    )
    return AsyncClient(config, auth=gateway.auth, transport=httpx.MockTransport(upstream))


@pytest.mark.anyio
@pytest.mark.rate_limited
async def test_two_clients_on_the_gateway_in_one_process_hold_one_quota_policy() -> None:
    first_upstream = Upstream(
        (200, [], {"x-ratelimit-limit": "1000", "x-ratelimit-remaining": "998"}),
        (429, OVER_RATE_LIMIT, {"retry-after": "3151", "x-ratelimit-remaining": "0"}),
    )
    second_upstream = Upstream(
        (200, [], {"x-ratelimit-limit": "1000", "x-ratelimit-remaining": "999"}),
    )
    first_gateway, second_gateway = Gateway("usda-esr"), Gateway("usda-gats")
    first = source_client("usda-esr", first_gateway, first_upstream)
    second = source_client("usda-gats", second_gateway, second_upstream)

    policy = data_gov.Gateway.policy
    assert first_gateway.policy is second_gateway.policy is policy
    for client in (first, second):
        assert client.config.observe == policy.observe
        assert client.config.before_request == policy.before_request

    await second.get_answer("/api/gats/regions")
    await first.get_answer("/api/esr/regions")
    snapshot = second_gateway.policy.snapshot()
    assert snapshot is not None
    assert (snapshot.limit, snapshot.remaining) == (1000, 998), "the first client's answer"

    with pytest.raises(RateLimitError):
        await first.get_answer("/api/esr/countries")
    with pytest.raises(
        RateLimitError, match="nothing was sent for GET /api/gats/countries"
    ) as info:
        await second.get_answer("/api/gats/countries")
    assert second_upstream.sent == ["GET /api/gats/regions"], "refused before sending"
    assert info.value.source == "api.data.gov"
    slack = CLOCK_SLACK.total_seconds()
    assert info.value.retry_after is not None
    assert 3151 - slack <= info.value.retry_after <= 3151 + slack

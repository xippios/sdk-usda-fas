"""xippios.usda.fas.data_gov: the api.data.gov gateway's key, answers and one shared quota.

The tests of sdk-core's ``tests/test_data_gov.py`` as it stood at
https://github.com/xippios/sdk-core/commit/76f69b5f12b2dcf02e093d0ba5e60176c59ad148, before the
module left core (sdk-core ADR-0065), run here against xippios-core 0.5.0, and the gateway's
tests that sdk-usda-psd, sdk-usda-esr and sdk-usda-gats held alike. Four things changed with the
module: the names ``KEY_HEADER``, ``LIMIT_HEADER`` and ``WINDOW`` are private, so the tests read
the policy's own values; core's refusal before sending says "quota spent" and no longer names
the key's variable (sdk-core ADR-0065, decision 2); each message names the request that was sent
(conventions §5); and FAS's empty 404 on a data path is FAS's own answer, outside this module,
which tests the gateway alone and the hook ``answers`` that a publisher's own answers take.
``Gateway.policy`` runs on the real clock, so a wait read through it is bracketed with
``CLOCK_SLACK``.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from xippios.core import (
    AsyncClient,
    AuthError,
    ClientConfig,
    KeyAuth,
    NotFoundError,
    RateLimitError,
    RetryPolicy,
    XippiosError,
)
from xippios.core.testing import CLOCK_SLACK

from xippios.usda.fas.data_gov import API_KEY_ENV, REMAINING_HEADER, Gateway

BASE = "https://api.fas.usda.gov"
HOST = "api.fas.usda.gov"
INVALID_KEY = {
    "error": {
        "code": "API_KEY_INVALID",
        "message": f"An invalid api_key was supplied. Get one at {BASE}:443",
    }
}
"""NOT RECORDED here: api.data.gov's 403 body, composed in the shape sdk-usda-psd recorded
behind the gateway on 2026-10-23, its ``tests/fixtures/get_commodities/invalid_key.json``
(conventions §10, kind 2)."""
OVER_RATE_LIMIT = {
    "error": {
        "code": "OVER_RATE_LIMIT",
        "message": "You have exceeded your rate limit. Try again later or contact us for "
        f"assistance: {BASE}:443",
    }
}
"""NOT RECORDED here: api.data.gov's 429 body, composed in the shape sdk-usda-psd recorded on
2026-10-23, its ``over_rate_limit.json`` (conventions §10, kind 2)."""
RECORDED_429 = {"retry-after": "3151", "x-ratelimit-limit": "1000", "x-ratelimit-remaining": "0"}
"""The headers of sdk-usda-psd's ``over_rate_limit.json``: ``Retry-After`` and the quota at zero,
no reset header."""
QUOTA = {"x-ratelimit-limit": "1000", "x-ratelimit-remaining": "999"}
GATEWAY_NOT_FOUND = {"error": {"code": "NOT_FOUND", "message": "The requested URL was not found."}}
"""NOT RECORDED: api.data.gov's documented ``NOT_FOUND`` body (conventions §10, kind 2)."""


def answer(
    status: int, body: object, headers: dict[str, str] | None = None, path: str = "/api/psd/x"
) -> httpx.Response:
    """NOT RECORDED: an answer to ``GET <path>`` with the body given; ``body=None`` is an empty
    body. The bodies above are composed in the shapes api.data.gov sends (conventions §10,
    kind 2), and a test that passes another marks it where it builds it."""
    content = b"" if body is None else json.dumps(body).encode()
    return httpx.Response(
        status, content=content, headers=headers or {}, request=httpx.Request("GET", BASE + path)
    )


class Upstream:
    """NOT RECORDED: a ``MockTransport`` handler that serves one composed answer for every
    request and keeps what was sent (conventions §10, kind 2)."""

    def __init__(self, status: int, body: object, headers: dict[str, str] | None = None) -> None:
        self.status, self.body, self.headers = status, body, headers or {}
        self.sent: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(f"{request.method} {request.url.path}")
        return httpx.Response(self.status, json=self.body, headers=self.headers)


def client_for(
    gateway: Gateway, upstream: Callable[[httpx.Request], httpx.Response]
) -> AsyncClient:
    config = ClientConfig(
        source=gateway.source, version="1", base_url=BASE, classify=gateway.classify
    )
    return AsyncClient(
        gateway.install(config), auth=gateway.auth, transport=httpx.MockTransport(upstream)
    )


def test_the_gateway_wires_its_key_and_the_one_policy(placeholder_api_key: str) -> None:
    gateway = Gateway("usda-psd")
    config = gateway.install(ClientConfig(source="usda-psd", version="1", base_url=BASE))
    assert config.observe == Gateway.policy.observe
    assert config.before_request == Gateway.policy.before_request
    assert isinstance(gateway.auth, KeyAuth), "core's one key class"
    assert (gateway.auth.location, gateway.auth.name) == ("header", "X-Api-Key")
    assert gateway.auth.env_var == API_KEY_ENV == "DATA_GOV_API_KEY"  # pragma: allowlist secret
    assert gateway.auth.source == "usda-psd", "the source's slug (sdk-core#526)"
    assert gateway.auth.key() == placeholder_api_key
    assert gateway.answers is None
    policy = Gateway.policy
    assert (policy.limit_header, policy.remaining_header) == (
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
    )
    assert policy.remaining_header == REMAINING_HEADER
    assert (policy.window, policy.source) == (3600.0, "api.data.gov")
    assert Gateway("usda-esr").policy is policy, "one policy per process for the key"


def test_a_refused_key_is_an_auth_error_naming_the_variable_and_the_code() -> None:
    error = Gateway("usda-psd").classify(answer(403, INVALID_KEY))
    assert isinstance(error, AuthError)
    assert error.status == 403
    assert error.message.startswith(
        f"api.data.gov refused the key in {API_KEY_ENV} for GET /api/psd/x (HTTP 403 "
        "API_KEY_INVALID: An invalid api_key was supplied. Get one at <host>). Check that"
    ), "what was sent, by core's request_description (conventions §5)"
    assert API_KEY_ENV in error.message
    assert HOST not in error.message, "host-free (sdk-core ADR-0030)"
    assert error.source == "usda-psd"


@pytest.mark.anyio
async def test_a_429_waits_until_the_snapshot_says_the_quota_is_back() -> None:
    upstream = Upstream(429, OVER_RATE_LIMIT, RECORDED_429)
    client = client_for(Gateway("usda-psd"), upstream)
    with pytest.raises(RateLimitError) as info:
        await client.get_answer("/api/psd/commodities")
    assert upstream.sent == ["GET /api/psd/commodities"], "3151 s is beyond backoff_max"
    snapshot = Gateway.policy.snapshot()
    assert snapshot is not None
    assert snapshot.resumes_at is not None
    assert (snapshot.resumes_at - snapshot.observed_at).total_seconds() == 3151
    slack = CLOCK_SLACK.total_seconds()
    assert info.value.retry_after is not None
    assert 3151 - slack <= info.value.retry_after <= 3151 + slack
    message = info.value.message
    assert message.startswith(
        f"api.data.gov rate limit reached for the key in {API_KEY_ENV} on GET "
        "/api/psd/commodities (HTTP 429 OVER_RATE_LIMIT: You have exceeded your rate limit."
    ), "what was sent, by core's request_description (conventions §5)"
    assert "1000 requests per rolling hour per key" in message
    assert f"Quota: {snapshot.describe()}." in message
    assert "expected back in" not in message, "the snapshot's time, not the seconds again"
    assert API_KEY_ENV in message
    assert HOST not in message
    assert info.value.source == "usda-psd"


@pytest.mark.anyio
async def test_a_429_without_retry_after_waits_the_window() -> None:
    client = client_for(Gateway("usda-gats"), Upstream(429, OVER_RATE_LIMIT))
    with pytest.raises(RateLimitError) as info:
        await client.get_answer("/api/gats/x")
    assert info.value.retry_after is not None
    slack = CLOCK_SLACK.total_seconds()
    window = Gateway.policy.window
    assert window - slack <= info.value.retry_after <= window + slack
    assert "an hourly quota per key" in info.value.message, "no limit known, none invented"


def test_a_429_classified_on_its_own_waits_what_the_policy_would_set() -> None:
    # No client observed the answer, so no snapshot holds it.
    error = Gateway("usda-psd").classify(answer(429, OVER_RATE_LIMIT, RECORDED_429))
    assert isinstance(error, RateLimitError)
    assert error.retry_after == 3151.0
    assert "Quota:" not in error.message
    assert "The quota is expected back in 3151 s." in error.message
    assert Gateway.policy.snapshot() is None, "classify reads the policy, never writes it"


def test_a_429_after_the_quota_is_back_waits_what_its_own_answer_says() -> None:
    # The snapshot holds a spent quota that is back already, a Retry-After of 0 observed: the
    # gateway reads the new answer, not a wait that has run out.
    Gateway.policy.observe(answer(429, OVER_RATE_LIMIT, {**RECORDED_429, "retry-after": "0"}))
    spent = Gateway.policy.snapshot()
    assert spent is not None
    assert spent.resumes_at == spent.observed_at
    error = Gateway("usda-psd").classify(answer(429, OVER_RATE_LIMIT, RECORDED_429))
    assert isinstance(error, RateLimitError)
    assert error.retry_after == 3151.0
    assert "The quota is expected back in 3151 s." in error.message
    assert "Quota:" not in error.message


def test_a_429_after_another_answer_replaced_the_snapshot_waits_what_its_own_answer_says() -> None:
    # The last answer observed left requests: the snapshot names no wait, so the gateway reads
    # the new answer, and names no allowance that the snapshot alone would give. The policy's
    # observe alone reads it, so the empty list at HTTP 200 with the quota headers is an input
    # of the test, not an answer from api.data.gov.
    Gateway.policy.observe(answer(200, [], QUOTA))
    snapshot = Gateway.policy.snapshot()
    assert snapshot is not None
    assert (snapshot.remaining, snapshot.resumes_at) == (999, None)
    error = Gateway("usda-psd").classify(answer(429, OVER_RATE_LIMIT, RECORDED_429))
    assert isinstance(error, RateLimitError)
    assert error.retry_after == 3151.0
    assert "The quota is expected back in 3151 s." in error.message
    assert "Quota:" not in error.message
    assert "an hourly quota per key" in error.message


@pytest.mark.parametrize(
    "retry_after",
    [
        "3151",
        None,  # no Retry-After: one window
        "999999",  # beyond the window: cut to it
        "soon",  # no number and no date: one window
        format_datetime(datetime.now(UTC) + timedelta(seconds=120), usegmt=True),
    ],
)
def test_a_429_classified_on_its_own_waits_as_long_as_the_policy_would_keep_it_spent(
    retry_after: str | None,
) -> None:
    # The gateway words its refusal from the policy's public names alone (sdk-core ADR-0065,
    # decision 2), so its wait for an answer no client observed is held to the one that the
    # policy sets once it observes the same answer.
    headers = {"x-ratelimit-limit": "1000", "x-ratelimit-remaining": "0"}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    response = answer(429, OVER_RATE_LIMIT, headers)
    error = Gateway("usda-psd").classify(response)
    assert isinstance(error, RateLimitError)
    assert error.retry_after is not None
    Gateway.policy.observe(response)
    snapshot = Gateway.policy.snapshot()
    assert snapshot is not None
    assert snapshot.resumes_at is not None
    kept = (snapshot.resumes_at - snapshot.observed_at).total_seconds()
    slack = CLOCK_SLACK.total_seconds()
    assert kept - slack <= error.retry_after <= kept + slack
    assert error.retry_after <= Gateway.policy.window


def test_the_gateway_s_not_found_is_a_not_found_error_naming_the_path() -> None:
    error = Gateway("usda-esr").classify(answer(404, GATEWAY_NOT_FOUND, path="/api/esr/nowhere"))
    assert isinstance(error, NotFoundError)
    assert "api.data.gov has no route for GET /api/esr/nowhere (HTTP 404 NOT_FOUND" in error.message
    assert error.source == "usda-esr"


def test_the_gateway_s_not_found_built_without_a_request_names_no_path() -> None:
    """NOT RECORDED: api.data.gov's documented ``NOT_FOUND`` body, built without its request
    (conventions §10, kind 2)."""
    response = httpx.Response(404, json=GATEWAY_NOT_FOUND)
    error = Gateway("usda-esr").classify(response)
    assert isinstance(error, NotFoundError)
    assert error.message == (
        "api.data.gov has no route for the request (HTTP 404 NOT_FOUND: The requested URL was "
        "not found.)"
    )


def test_each_message_names_what_was_sent_never_its_host_or_query() -> None:
    """NOT RECORDED: the gateway's three documented answers to a request with a query, composed
    in the shapes above (conventions §10, kind 2)."""
    sent = httpx.Request("POST", BASE + "/api/esr/exports?commodityCode=104&key=not-a-key")
    gateway = Gateway("usda-esr")
    for status, body, headers, words in (
        (401, INVALID_KEY, {}, "refused the key in DATA_GOV_API_KEY for POST /api/esr/exports"),
        (
            429,
            OVER_RATE_LIMIT,
            RECORDED_429,
            "rate limit reached for the key in DATA_GOV_API_KEY on POST /api/esr/exports",
        ),
        (404, GATEWAY_NOT_FOUND, {}, "has no route for POST /api/esr/exports"),
    ):
        error = gateway.classify(httpx.Response(status, json=body, headers=headers, request=sent))
        assert error is not None
        assert f"api.data.gov {words} (HTTP {status} " in error.message
        assert "commodityCode" not in error.message
        assert "not-a-key" not in error.message
        assert HOST not in error.message


def test_each_message_of_a_response_built_without_a_request_names_the_request() -> None:
    """NOT RECORDED: the gateway's three documented answers, built without their request
    (conventions §10, kind 2)."""
    gateway = Gateway("usda-esr")
    refused = gateway.classify(httpx.Response(403, json=INVALID_KEY))
    spent = gateway.classify(httpx.Response(429, json=OVER_RATE_LIMIT, headers=RECORDED_429))
    missing = gateway.classify(httpx.Response(404, json=GATEWAY_NOT_FOUND))
    assert refused is not None
    assert spent is not None
    assert missing is not None
    assert f"refused the key in {API_KEY_ENV} for the request (HTTP 403 " in refused.message
    assert f"for the key in {API_KEY_ENV} on the request (HTTP 429 " in spent.message
    assert "has no route for the request (HTTP 404 " in missing.message


@pytest.mark.parametrize(
    ("status", "code"), [(401, "API_KEY_MISSING"), (403, "API_KEY_DISABLED"), (404, "NOT_FOUND")]
)
def test_a_code_with_an_empty_message_is_quoted_alone(status: int, code: str) -> None:
    """NOT RECORDED: the gateway's documented body with its code and an empty message
    (conventions §10, kind 2), https://github.com/xippios/sdk-usda-fas/issues/7."""
    error = Gateway("usda-esr").classify(answer(status, {"error": {"code": code, "message": ""}}))
    assert error is not None
    assert f"(HTTP {status} {code})" in error.message
    assert f"{code}:" not in error.message, "no colon before an empty message"


@pytest.mark.parametrize(
    ("status", "code"), [(401, "API_KEY_MISSING"), (403, "API_KEY_DISABLED"), (404, "NOT_FOUND")]
)
def test_a_code_with_its_message_is_quoted_with_it_after_the_colon(status: int, code: str) -> None:
    """NOT RECORDED: the gateway's documented body with its code and its message (conventions
    §10, kind 2), https://github.com/xippios/sdk-usda-fas/issues/7."""
    body = {"error": {"code": code, "message": "as documented"}}
    error = Gateway("usda-esr").classify(answer(status, body))
    assert error is not None
    assert f"(HTTP {status} {code}: as documented)" in error.message


def test_a_code_without_a_message_is_worded_without_an_empty_one() -> None:
    """NOT RECORDED: the gateway's documented bodies with no ``message`` (conventions §10,
    kind 2)."""
    gateway = Gateway("usda-esr")
    refused = gateway.classify(answer(403, {"error": {"code": "API_KEY_DISABLED"}}))
    assert isinstance(refused, AuthError)
    assert refused.message == (
        f"api.data.gov refused the key in {API_KEY_ENV} for GET /api/psd/x (HTTP 403 "
        "API_KEY_DISABLED). Check that "
        "the variable holds a valid, active api.data.gov key."
    )
    missing = gateway.classify(answer(404, {"error": {"code": "NOT_FOUND"}}, path="/api/esr/x"))
    assert isinstance(missing, NotFoundError)
    assert missing.message == "api.data.gov has no route for GET /api/esr/x (HTTP 404 NOT_FOUND)"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (403, {"Message": "Access denied"}),
        (404, None),  # an empty 404 is no answer of the gateway's
        (500, {"Message": "An error has occurred."}),
        (200, []),
    ],
)
def test_every_other_answer_is_left_to_the_source(status: int, body: object) -> None:
    """NOT RECORDED: a ``{"Message": ...}`` 403 and 500, in no shape that the gateway sends, to
    show that it leaves them to the source (conventions §10, kind 5), and an empty 404 and an
    empty list, in the shapes that FAS's services were recorded answering (kind 2)."""
    assert Gateway("usda-psd").classify(answer(status, body)) is None


@pytest.mark.anyio
@pytest.mark.rate_limited
async def test_two_sources_draw_on_one_quota() -> None:
    psd = client_for(Gateway("usda-psd"), Upstream(429, OVER_RATE_LIMIT, RECORDED_429))
    # NOT RECORDED: an empty list at 200 with the quota headers, in the shapes that FAS's
    # services were recorded answering behind the gateway (conventions §10, kind 2).
    esr_upstream = Upstream(200, [], QUOTA)
    esr = client_for(Gateway("usda-esr"), esr_upstream)
    with pytest.raises(RateLimitError):
        await psd.get_answer("/api/psd/commodities")
    with pytest.raises(RateLimitError, match="nothing was sent for GET /api/esr/regions") as info:
        await esr.get_answer("/api/esr/regions", params={"key": "not-sent"})
    assert esr_upstream.sent == []
    assert info.value.source == "api.data.gov", "the refusal speaks for the gateway"
    assert info.value.message.startswith("quota spent ("), "core's words (sdk-core ADR-0065)"
    assert info.value.retry_after is not None
    slack = CLOCK_SLACK.total_seconds()
    assert 3151 - slack <= info.value.retry_after <= 3151 + slack
    assert HOST not in info.value.message
    assert "not-sent" not in info.value.message


# -- the gateway's own answers alone (https://github.com/xippios/sdk-core/issues/163) -----


@pytest.mark.parametrize(
    ("status", "body"), [(429, OVER_RATE_LIMIT), (403, INVALID_KEY), (404, None)]
)
def test_an_answer_from_another_origin_is_not_the_gateway_s(status: int, body: object) -> None:
    """NOT RECORDED: a composed answer on another host, marked as the client marks a request
    to another origin (conventions §10, kind 2)."""
    request = httpx.Request(
        "GET", "https://files.example.test/psd_alldata.zip", extensions={"xippios_origin": "other"}
    )
    content = b"" if body is None else json.dumps(body).encode()
    response = httpx.Response(status, content=content, request=request)
    asked: list[httpx.Response] = []

    def everything(response: httpx.Response) -> XippiosError | None:
        asked.append(response)
        return NotFoundError("a publisher's answer", source="usda-psd")

    assert Gateway("usda-psd").classify(response) is None
    assert Gateway("usda-psd", answers=everything).classify(response) is None
    assert asked == [], "a publisher's answers are the gateway's origin's alone"


@pytest.mark.anyio
@pytest.mark.rate_limited
async def test_a_429_from_another_host_spends_no_gateway_quota() -> None:
    # A keyless bulk download through the source's one client (sdk-usda-psd's plan).
    upstream = Upstream(429, OVER_RATE_LIMIT, RECORDED_429)
    client = client_for(Gateway("usda-psd"), upstream)
    with pytest.raises(RateLimitError) as info:
        await client.get_answer("https://files.example.test/psd_alldata.zip")
    assert not info.value.message.startswith("api.data.gov"), "core's mapping, not the gateway's"
    assert Gateway.policy.snapshot() is None
    sent = len(upstream.sent)
    with pytest.raises(RateLimitError):
        await client.get_answer("https://files.example.test/psd_alldata.zip")
    assert len(upstream.sent) > sent, "sent again: no gateway quota holds it back"


# -- a publisher's own answers behind the gateway: the hook ``answers`` ----------------------


def test_a_publisher_s_answers_come_after_the_gateway_s_own() -> None:
    asked: list[int] = []

    def publisher(response: httpx.Response) -> XippiosError | None:
        asked.append(response.status_code)
        if response.status_code == 404 and not response.content:
            return NotFoundError("the publisher's empty 404", source="usda-psd")
        return None

    gateway = Gateway("usda-psd", answers=publisher)
    assert gateway.answers is publisher
    assert isinstance(gateway.classify(answer(403, INVALID_KEY)), AuthError)
    assert isinstance(gateway.classify(answer(429, OVER_RATE_LIMIT, RECORDED_429)), RateLimitError)
    not_found = gateway.classify(answer(404, GATEWAY_NOT_FOUND))
    assert isinstance(not_found, NotFoundError)
    assert not_found.message.startswith("api.data.gov has no route")
    assert asked == [], "the gateway's own answers are never the publisher's"
    # NOT RECORDED: an empty 404, in the shape that FAS's services were recorded answering
    # (conventions §10, kind 2).
    error = gateway.classify(answer(404, None))
    assert isinstance(error, NotFoundError)
    assert error.message == "the publisher's empty 404"
    # NOT RECORDED: a 403 in no shape that the gateway sends, which it leaves to the publisher
    # (conventions §10, kind 5).
    assert gateway.classify(answer(403, {"Message": "Access denied"})) is None
    # NOT RECORDED: an empty list at 200, in the shape that FAS's services were recorded
    # answering (conventions §10, kind 2).
    assert gateway.classify(answer(200, [])) is None
    assert asked == [404, 403, 200], "every answer the gateway leaves, once"


def test_a_response_built_without_a_request_goes_to_the_publisher_s_answers() -> None:
    # As the gateway reads it: an answer without a request counts as the base URL's.
    asked: list[int] = []

    def publisher(response: httpx.Response) -> XippiosError | None:
        asked.append(response.status_code)
        return None

    # NOT RECORDED: a 404 in a shape that no recording of the three sources holds, built without
    # its request, to show where the gateway sends an answer it leaves (conventions §10, kind 5).
    response = httpx.Response(404, content=b'{"Message": "No HTTP resource was found"}')
    assert Gateway("usda-psd", answers=publisher).classify(response) is None
    assert asked == [404]


# -- the gateway tests the three sources held alike (sdk-core ADR-0065, consequences) ---------
#
# sdk-usda-psd, sdk-usda-esr and sdk-usda-gats each tested the gateway's answers through their
# own classify; their tests of the gateway leave at their adoption, so the package holds what
# those tests held beyond core's: every documented key code, a gateway code that names no
# key, and the retries a 429 gets from core's client once the gateway shapes them.


@pytest.mark.parametrize(
    "code",
    [
        "API_KEY_MISSING",
        "API_KEY_INVALID",
        "API_KEY_DISABLED",
        "API_KEY_UNAUTHORIZED",
        "API_KEY_UNVERIFIED",
    ],
)
@pytest.mark.parametrize("status", [401, 403])
def test_every_documented_key_code_is_an_auth_error(code: str, status: int) -> None:
    """NOT RECORDED: the codes the developer manual documents, in the shape of the recorded
    ``API_KEY_INVALID`` (conventions §10, kind 2)."""
    body = {"error": {"code": code, "message": f"documented, see {BASE}:443"}}
    error = Gateway("usda-esr").classify(answer(status, body))
    assert isinstance(error, AuthError)
    assert error.status == status
    assert f"(HTTP {status} {code}: documented, see <host>)" in error.message
    assert API_KEY_ENV in error.message
    assert error.source == "usda-esr"


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("code", ["OVER_RATE_LIMIT", "NOT_FOUND"])
def test_a_gateway_code_that_names_no_key_is_left_to_the_source(status: int, code: str) -> None:
    """NOT RECORDED: the gateway's error body with a code that names no key at 401 or 403,
    where api.data.gov documents its key codes alone, a form that it is not documented to
    send, to show that the gateway leaves it to the source (conventions §10, kind 5)."""
    body = {"error": {"code": code, "message": "not a key's"}}
    assert Gateway("usda-gats").classify(answer(status, body)) is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("retry_after", "shaped", "attempts"),
    [("3151", True, 1), (None, True, 1), (None, False, 4)],
    ids=["with_retry_after", "without_retry_after", "control_without_classify"],
)
async def test_core_retries_a_429_only_within_its_backoff(
    retry_after: str | None, shaped: bool, attempts: int
) -> None:
    # The gateway's RateLimitError carries the wait, Retry-After or else the window, beyond
    # backoff_max, so core's client sends a 429 once, with or without the header. Without
    # the gateway's classify, core retries a 429 without Retry-After on its status alone, at
    # its short backoff, so this test fails if the gateway stops shaping the retries.
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    headers = {"x-ratelimit-limit": "1000", "x-ratelimit-remaining": "0"}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    upstream = Upstream(429, OVER_RATE_LIMIT, headers)
    gateway = Gateway("usda-esr")
    config = ClientConfig(
        source="usda-esr",
        version="1",
        base_url=BASE,
        classify=gateway.classify if shaped else None,
    )
    client = AsyncClient(
        gateway.install(config),
        auth=gateway.auth,
        transport=httpx.MockTransport(upstream),
        sleep=sleep,
    )
    with pytest.raises(RateLimitError) as info:
        await client.get_answer("/api/esr/commodities")
    assert len(upstream.sent) == attempts
    assert len(sleeps) == attempts - 1
    assert all(seconds <= RetryPolicy().backoff_max for seconds in sleeps)
    if shaped:
        slack = CLOCK_SLACK.total_seconds()
        expected = float(retry_after or Gateway.policy.window)
        assert info.value.retry_after is not None
        assert expected - slack <= info.value.retry_after <= expected + slack
    else:
        assert info.value.retry_after is None, "core's own mapping: no Retry-After, no wait"

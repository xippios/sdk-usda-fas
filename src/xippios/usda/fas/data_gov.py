"""The api.data.gov gateway: its key, its documented answers and one quota per key.

api.data.gov (API Umbrella) fronts the APIs of every agency that takes part in it. One key
serves them all, and one hourly quota counts every request made with it (sdk-core ADR-0032).
``Gateway`` holds what every source behind it shares, once, and nothing of the agency behind
it: a publisher's own answers come in through the hook ``answers``::

    from xippios.usda.fas.data_gov import Gateway

    gateway = Gateway("usda-psd")


    def classify(response: httpx.Response) -> XippiosError | None:
        error = gateway.classify(response)
        if error is not None:
            return error
        ...  # the source's own documented answers, then None


    config = gateway.install(ClientConfig(..., classify=classify))
    client = AsyncClient(config, auth=gateway.auth)

The FAS sources build the package's exported ``Gateway`` in its place, this gateway with FAS's
answer for a year without data as its ``answers`` (``no_data``).

What the gateway sends, as a source behind it recorded it on 2026-10-23 (sdk-usda-psd's
``tests/fixtures/PSDData_GetCommodities/``):

- Every answer to a valid key carries ``x-ratelimit-limit: 1000`` and
  ``x-ratelimit-remaining``, the requests left in the key's rolling hour; no reset
  header.
- A spent quota answers 429 ``{"error": {"code": "OVER_RATE_LIMIT", "message": ...}}``
  with ``x-ratelimit-remaining: 0`` and ``Retry-After: 3151`` (``over_rate_limit.json``).
  The developer manual (https://api.data.gov/docs/developer-manual/, read 2026-10-23)
  documents no ``Retry-After``, only that "the block will automatically be lifted by
  waiting an hour", which sdk-core ADR-0033's context records; so the wait is
  ``Retry-After`` when the gateway sends one and the policy's window, the hour, when it
  does not.
- A key the gateway refuses answers 401 or 403 with an ``API_KEY_*`` code in the same
  body and no quota headers (``invalid_key.json``: 403 ``API_KEY_INVALID``); a path it
  does not route answers 404 ``NOT_FOUND`` (documented, not recorded).

The gateway ends its messages with the URL of the API it fronts
(``"... https://<host>:443"``); every error here writes it ``<host>`` (sdk-core ADR-0030).
``classify`` reads the answers of the client's base URL alone: the answer to a request the
client marks as sent to another origin, a file link on another host, is none of the
gateway's.

The refusal of a spent quota reads the policy's public names alone, ``snapshot()``,
``window`` and the clock that the module hands the policy, and ``parse_retry_after``: core's
policy keeps its subject and its wait private, and its own refusal before sending says
"quota spent" with the policy's ``source`` (sdk-core ADR-0065, decision 2).
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import ClassVar

import httpx
from xippios.core import (
    AuthError,
    ClientConfig,
    KeyAuth,
    NotFoundError,
    QuotaPolicy,
    RateLimitError,
    XippiosError,
    parse_retry_after,
    request_description,
)

__all__ = [
    "API_KEY_ENV",
    "REMAINING_HEADER",
    "Gateway",
]

API_KEY_ENV = "DATA_GOV_API_KEY"  # pragma: allowlist secret (a variable name, not a key)
"""The variable every source behind api.data.gov reads its key from (sdk-core ADR-0032)."""
REMAINING_HEADER = "x-ratelimit-remaining"
"""The header with the requests left in the key's rolling hour, on every keyed answer."""

_KEY_HEADER = "X-Api-Key"
"""The header the key is sent in."""
_LIMIT_HEADER = "x-ratelimit-limit"
"""The header with the quota's size, 1,000 requests by default."""
_WINDOW = 3600.0
"""The quota's window in seconds: a rolling hour per key, and the wait without ``Retry-After``."""
_GATEWAY = "api.data.gov"
_URL = re.compile(r"https?://[^/\s]+")


def _clock() -> datetime:
    """The current time, UTC: the clock the module hands ``Gateway.policy`` and reads itself."""
    return datetime.now(UTC)


def _from_elsewhere(response: httpx.Response) -> bool:
    """True for the answer to a request the client sent to another origin than its base URL's.

    A response built without a request, or whose request carries no mark, counts as the
    base URL's.
    """
    try:
        request = response.request
    except RuntimeError:  # httpx raises it for a response built without a request
        return False
    return request.extensions.get("xippios_origin") == "other"


def _asked(response: httpx.Response) -> str:
    """The request ``response`` answers as a message names it, by core's ``request_description``.

    Its method and path, ``GET /api/psd/commodities``, never its host or its query
    (conventions §5; sdk-core ADR-0030, decision 4); ``the request`` for a response built
    without one.
    """
    try:
        return request_description(response)
    except RuntimeError:  # httpx raises it for a response built without a request
        return "the request"


def _said(code: str, message: str) -> str:
    """The gateway's code and its message as a message quotes them, ``CODE: message``.

    A code without a message stands alone, so no empty message follows a colon.
    """
    return f"{code}: {message}" if message else code


def _gateway_error(response: httpx.Response) -> tuple[str | None, str]:
    """The gateway's ``{"error": {"code": ..., "message": ...}}``, or ``(None, "")``.

    The message comes back host-free: the gateway's URL is written ``<host>``.
    """
    try:
        payload = response.json()
    except ValueError:
        return None, ""
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict) or not isinstance(error.get("code"), str):
        return None, ""
    message = error.get("message")
    return error["code"], _URL.sub("<host>", message) if isinstance(message, str) else ""


class Gateway:
    """api.data.gov for one source behind it: the key, the gateway's answers, the quota.

    Every instance shares ``Gateway.policy``, one ``QuotaPolicy`` per process for the key
    in ``DATA_GOV_API_KEY``: what one source spends, another source's next request sees,
    and it waits that out within the policy's cap or is refused without being sent
    (sdk-core ADR-0032; sdk-core ADR-0033, decision 4). ``classify``'s errors carry the
    source's slug; the policy's refusal before sending speaks for the gateway,
    ``source="api.data.gov"``, and names the method and the path.

    Args:
        source: The calling source's slug, e.g. ``"usda-psd"``, for its errors and for the
            ``ConfigError`` when ``DATA_GOV_API_KEY`` is unset.
        answers: The documented answers of the publisher behind the gateway that its
            sources share, as a function of an answer like a ``classify``: asked for each
            answer from the client's base URL that the gateway's own answers leave, and
            its error, or ``None``, is ``classify``'s. ``None``, the default, asks none.

    Attributes:
        source: As given.
        answers: As given.
        auth: The key from ``DATA_GOV_API_KEY`` in the ``X-Api-Key`` header, read on the
            first request (conventions §7): core's one key class with the source's slug,
            the client's ``auth``.
        policy: The process's one policy for the key: ``x-ratelimit-limit`` and
            ``x-ratelimit-remaining`` read from every answer from the wire, a window of
            one hour, created when this module is imported.
    """

    policy: ClassVar[QuotaPolicy] = QuotaPolicy(
        limit_header=_LIMIT_HEADER,
        remaining_header=REMAINING_HEADER,
        window=_WINDOW,
        source=_GATEWAY,
        clock=_clock,
    )

    def __init__(
        self,
        source: str,
        *,
        answers: Callable[[httpx.Response], XippiosError | None] | None = None,
    ) -> None:
        self.source = source
        self.answers = answers
        self.auth = KeyAuth(API_KEY_ENV, location="header", name=_KEY_HEADER, source=source)

    def install(self, config: ClientConfig) -> ClientConfig:
        """``config`` with the shared policy's ``before_request`` and ``observe`` hooks.

        ``Gateway.policy.install(config)``: ``config`` itself is unchanged, hooks it had
        are replaced, and installing again changes nothing.

        Args:
            config: The source's client configuration, whose ``classify`` asks this
                gateway's ``classify`` first.
        """
        return self.policy.install(config)

    def classify(self, response: httpx.Response) -> XippiosError | None:
        """The gateway's documented answers as taxonomy errors in the source's name.

        - 401 or 403 with an ``error.code`` starting ``API_KEY_`` (the developer manual
          names ``API_KEY_MISSING``, ``API_KEY_INVALID``, ``API_KEY_DISABLED``,
          ``API_KEY_UNAUTHORIZED`` and ``API_KEY_UNVERIFIED``) is an ``AuthError`` naming
          the code and the variable, never the key.
        - 429 (``OVER_RATE_LIMIT``) is a ``RateLimitError`` whose ``retry_after`` is the
          wait ``Gateway.policy`` keeps the quota spent for: ``observe`` has read this
          answer before ``classify`` runs (sdk-core ADR-0037, decision 1), so the wait
          counts to the snapshot's ``resumes_at``, from ``Retry-After`` or one window.
          The message names the gateway's allowance, that every package using the key
          shares it, and the quota as the snapshot reports it. Whether the client
          retries is the retry loop's: a wait beyond its ``backoff_max`` ends the
          retries after one request. When the shared snapshot shows no spent quota
          still ahead, because no client observed this answer, another answer has
          replaced the snapshot since, or the quota is back already, the wait is the
          one the policy sets for this answer, ``Retry-After`` cut to the window or one
          window, and the message says it in seconds. Called on its own while the
          shared quota is spent, it reads the snapshot like any other call.
        - 404 with ``error.code`` ``NOT_FOUND`` is a ``NotFoundError``.

        Every other answer goes to ``answers``, the publisher's, and without it is
        ``None``: the source's own ``classify`` goes on with its documented answers, and
        core's status mapping follows. So is every answer to a request the client marked
        as sent to another origin than its base URL's (``xippios_origin: "other"``), a
        download from a file host say: none of those is the gateway's or its publisher's,
        and ``answers`` is not asked. Each message names the request that was sent by core's
        ``request_description``, ``GET /api/psd/commodities``, never its host or its query
        (conventions §5), and "the request" for a response built without one.

        Args:
            response: A response from the wire, any status.
        """
        if _from_elsewhere(response):
            return None
        status = response.status_code
        if status in (401, 403):
            code, message = _gateway_error(response)
            if code is not None and code.startswith("API_KEY_"):
                return AuthError(
                    f"api.data.gov refused the key in {API_KEY_ENV} for {_asked(response)} "
                    f"(HTTP {status} {_said(code, message)}). Check that the variable holds a "
                    "valid, active api.data.gov key.",
                    status=status,
                    source=self.source,
                )
        elif status == 429:
            return self._over_rate_limit(response)
        elif status == 404:
            code, message = _gateway_error(response)
            if code == "NOT_FOUND":
                return NotFoundError(
                    f"api.data.gov has no route for {_asked(response)} "
                    f"(HTTP 404 {_said(code, message)})",
                    source=self.source,
                )
        return None if self.answers is None else self.answers(response)

    def _over_rate_limit(self, response: httpx.Response) -> RateLimitError:
        """The gateway's 429, ``retry_after`` as long as the shared policy keeps it spent."""
        code, message = _gateway_error(response)
        upstream = ": ".join(part for part in (code, message) if part)
        now = _clock()
        snapshot = self.policy.snapshot()
        wait = None
        if snapshot is not None and snapshot.resumes_at is not None:
            left = (snapshot.resumes_at - now).total_seconds()
            wait = left if left > 0 else None
        if wait is None:  # the snapshot shows no spent quota still ahead: read this answer
            snapshot, wait = None, self._spent_for(response, now)
        allowance = (
            f"{snapshot.limit} requests per rolling hour per key"
            if snapshot is not None and snapshot.limit is not None
            else "an hourly quota per key"
        )
        state = (
            f"Quota: {snapshot.describe()}."
            if snapshot is not None
            else f"The quota is expected back in {wait:.0f} s."
        )
        return RateLimitError(
            f"api.data.gov rate limit reached for the key in {API_KEY_ENV} on "
            f"{_asked(response)} (HTTP 429{' ' + upstream if upstream else ''}). The gateway "
            f"allows {allowance}, "
            f"shared by every package using that key. {state}",
            retry_after=wait,
            source=self.source,
        )

    def _spent_for(self, response: httpx.Response, now: datetime) -> float:
        """Seconds the policy keeps the quota spent after the 429 ``response``.

        Its ``Retry-After`` cut to the policy's window, or one window without one, as the
        policy's ``observe`` sets ``resumes_at`` for a 429.
        """
        window = self.policy.window
        retry_after = parse_retry_after(response.headers.get("Retry-After"), now=now)
        return window if retry_after is None else min(retry_after, window)

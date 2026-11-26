"""xippios.usda.fas.no_data: FAS's answer for a year without data, and the gateway that gives it.

The tests of FAS's empty 404 in sdk-core's ``tests/test_data_gov.py`` as it stood at
https://github.com/xippios/sdk-core/commit/76f69b5f12b2dcf02e093d0ba5e60176c59ad148
(https://github.com/xippios/sdk-core/issues/106, https://github.com/xippios/sdk-core/issues/163,
the findings of https://github.com/xippios/sdk-core/pull/275), run here on the ``Gateway`` that
the package exports, as the three sources build it: ``Gateway(SOURCE, data_path=DATA_PATH)``.
"""

import json
import re

import httpx
import pytest
from xippios.core import NotFoundError

from xippios.usda.fas import Gateway, NoDataForYear, data_gov

BASE = "https://api.fas.usda.gov"
HOST = "api.fas.usda.gov"
INVALID_KEY = {"error": {"code": "API_KEY_INVALID", "message": "An invalid api_key was supplied."}}
"""NOT RECORDED here: api.data.gov's 403 body, composed in the shape sdk-usda-psd recorded behind
the gateway on 2026-10-23 (conventions §10, kind 2)."""
OVER_RATE_LIMIT = {"error": {"code": "OVER_RATE_LIMIT", "message": "You have exceeded your rate"}}
"""NOT RECORDED here: api.data.gov's 429 body, in the same shape (conventions §10, kind 2)."""
GATEWAY_NOT_FOUND = {"error": {"code": "NOT_FOUND", "message": "The requested URL was not found."}}
"""NOT RECORDED: api.data.gov's documented ``NOT_FOUND`` body (conventions §10, kind 2)."""

# sdk-usda-psd's and sdk-usda-esr's data paths, as their _client.py write them.
PSD_DATA = re.compile(r"/api/psd/commodity/[^/]+/(?:country/[^/]+|world)/year/[^/]+")
ESR_DATA = re.compile(
    r"/api/esr/exports/commodityCode/[^/]+/(?:allCountries|countryCode/[^/]+)/marketYear/[^/]+"
)
YEAR_1900 = "/api/psd/commodity/0410000/country/US/year/1900"
TEXT = {"content-type": "text/plain; charset=utf-8"}


def answer(
    status: int, body: object, headers: dict[str, str] | None = None, path: str = "/api/psd/x"
) -> httpx.Response:
    """NOT RECORDED: an answer to ``GET <path>``, composed in the shape that sdk-usda-psd and
    sdk-usda-esr recorded for market year 1900, their ``year_1900.json`` and
    ``unknown_year.json``, at the path given; ``body=None`` is an empty body (conventions §10,
    kind 2)."""
    content = b"" if body is None else json.dumps(body).encode()
    return httpx.Response(
        status, content=content, headers=headers or {}, request=httpx.Request("GET", BASE + path)
    )


def test_the_gateway_the_package_exports_is_api_data_gov_s_with_fas_s_answer() -> None:
    gateway = Gateway("usda-esr", data_path=ESR_DATA)
    assert isinstance(gateway, data_gov.Gateway)
    assert (gateway.source, gateway.data_path) == ("usda-esr", ESR_DATA)
    assert gateway.policy is data_gov.Gateway.policy, "one policy per process for the key"
    assert gateway.auth.source == "usda-esr"
    assert Gateway("usda-gats").data_path is None


def test_an_empty_text_404_on_a_data_path_says_the_year_holds_no_data() -> None:
    # Both sources recorded it for market year 1900 on every data form.
    error = Gateway("usda-psd", data_path=PSD_DATA).classify(
        answer(404, None, TEXT, path=YEAR_1900)
    )
    assert isinstance(error, NoDataForYear)
    assert isinstance(error, NotFoundError), "in the taxonomy, conventions §5"
    assert error.path == YEAR_1900
    assert error.source == "usda-psd"
    assert error.message == (
        f"no data for GET {YEAR_1900} (HTTP 404 with an empty body): the year it names holds "
        "no data upstream"
    ), "the request by core's request_description, as the gateway's other messages name it"
    assert HOST not in error.message
    path = "/api/esr/exports/commodityCode/104/allCountries/marketYear/1900"
    esr = Gateway("usda-esr", data_path=ESR_DATA)
    upper = {"Content-Type": "TEXT/PLAIN; charset=utf-8"}  # media types ignore case (RFC 9110)
    assert isinstance(esr.classify(answer(404, None, upper, path=path)), NoDataForYear)


def test_the_gateway_s_four_messages_name_one_request_alike() -> None:
    """NOT RECORDED: the gateway's three documented answers and FAS's empty 404, each to the
    same request on a data path (conventions §10, kind 2)."""
    gateway = Gateway("usda-psd", data_path=PSD_DATA)
    answers = (
        answer(403, INVALID_KEY, path=YEAR_1900),
        answer(429, OVER_RATE_LIMIT, {"retry-after": "60"}, path=YEAR_1900),
        answer(404, GATEWAY_NOT_FOUND, path=YEAR_1900),
        answer(404, None, TEXT, path=YEAR_1900),
    )
    for response in answers:
        error = gateway.classify(response)
        assert error is not None
        assert f" GET {YEAR_1900} " in error.message, error.message


@pytest.mark.parametrize(
    ("headers", "path", "body"),
    [
        (TEXT, "/api/psd/commodity/0410000/dataReleaseDates", None),  # off a data path
        ({"content-type": "application/json"}, YEAR_1900, None),  # not text
        ({}, YEAR_1900, None),  # no content type
        (TEXT, YEAR_1900, "no such year"),  # a body
        (TEXT, YEAR_1900 + "/extra", None),  # a path that only begins with a data path
        (TEXT, "/v2" + YEAR_1900, None),  # a path that only ends with one
    ],
)
def test_any_other_404_is_left_to_the_source(
    headers: dict[str, str], path: str, body: object
) -> None:
    gateway = Gateway("usda-psd", data_path=PSD_DATA)
    assert gateway.classify(answer(404, body, headers, path=path)) is None


def test_the_gateway_s_own_answers_come_before_fas_s() -> None:
    # api.data.gov's NOT_FOUND on a data path is the gateway's: no route, not an empty year.
    gateway = Gateway("usda-psd", data_path=PSD_DATA)
    error = gateway.classify(answer(404, GATEWAY_NOT_FOUND, path=YEAR_1900))
    assert isinstance(error, NotFoundError)
    assert not isinstance(error, NoDataForYear)
    assert error.message.startswith("api.data.gov has no route")


def test_a_gateway_without_data_paths_maps_no_empty_404() -> None:
    # sdk-usda-gats: its data paths answer [], never the empty 404.
    assert Gateway("usda-gats").classify(answer(404, None, TEXT, path=YEAR_1900)) is None


def test_no_data_for_year_takes_a_message_of_the_source_s_own() -> None:
    # A task raises it again naming commodity, country and market year.
    error = NoDataForYear(YEAR_1900, "PSD has no data for wheat, US, 1900", source="usda-psd")
    assert (error.path, error.message, error.source) == (
        YEAR_1900,
        "PSD has no data for wheat, US, 1900",
        "usda-psd",
    )


# -- the gateway's own answers alone (https://github.com/xippios/sdk-core/issues/163) -----


@pytest.mark.parametrize(
    ("status", "body"), [(429, OVER_RATE_LIMIT), (403, INVALID_KEY), (404, None)]
)
def test_an_answer_from_another_origin_is_not_the_gateway_s(status: int, body: object) -> None:
    """NOT RECORDED: a composed answer at a data path on another host, marked as the client
    marks a request to another origin (conventions §10, kind 2)."""
    request = httpx.Request(
        "GET", "https://files.example.test" + YEAR_1900, extensions={"xippios_origin": "other"}
    )
    content = b"" if body is None else json.dumps(body).encode()
    response = httpx.Response(status, content=content, headers=TEXT, request=request)
    assert Gateway("usda-psd", data_path=PSD_DATA).classify(response) is None


# -- a response built without a request (findings of https://github.com/xippios/sdk-core/pull/275)


@pytest.mark.parametrize(
    ("body", "headers"),
    [
        (b'{"Message": "No HTTP resource was found"}', {"content-type": "application/json"}),
        (b"", TEXT),  # an empty text 404 whose path cannot be read
    ],
)
@pytest.mark.parametrize("data_path", [None, PSD_DATA])
def test_a_404_built_without_a_request_is_left_to_the_source(
    body: bytes, headers: dict[str, str], data_path: re.Pattern[str] | None
) -> None:
    """NOT RECORDED: a 404 without its request, FAS's empty text answer in the shape recorded
    for 1900 (conventions §10, kind 2), or a JSON body that no recording holds (kind 5)."""
    # As on core's main: only the gateway's own NOT_FOUND names the path it reads.
    response = httpx.Response(404, content=body, headers=headers)
    assert Gateway("usda-psd", data_path=data_path).classify(response) is None

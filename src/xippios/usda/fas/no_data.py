"""FAS's answer for a year without data, and the gateway that gives it to a FAS source.

Behind api.data.gov's gateway, FAS's PSD and ESR answer a market year they hold no data for
with HTTP 404, an empty body and ``content-type: text/plain; charset=utf-8``, on every data
path (sdk-usda-psd and sdk-usda-esr recorded it for 1900, their ``year_1900.json`` and
``unknown_year.json``). ``Gateway`` is ``data_gov.Gateway`` with that rule as its publisher's
answers: a gateway given the source's data paths maps the answer there to ``NoDataForYear``
(https://github.com/xippios/sdk-core/issues/106), and every FAS source builds its gateway so::

    from xippios.usda.fas import API_KEY_ENV, Gateway

    gateway = Gateway(SOURCE, data_path=DATA_PATH)

The pattern of the data paths is the source's own; GATS's data paths answer ``[]`` and never
the empty 404, so sdk-usda-gats gives none.
"""

import re

import httpx
from xippios.core import NotFoundError, XippiosError, request_description

from xippios.usda.fas import data_gov

__all__ = ["Gateway", "NoDataForYear"]


class NoDataForYear(NotFoundError):
    """FAS's answer for a year a data path holds no data for: HTTP 404, an empty text body.

    ``Gateway.classify`` returns it for that answer on a path that the gateway's
    ``data_path`` matches, and nowhere else: the gateway's ``NOT_FOUND`` (no such route)
    and an empty 404 on any other path say the request is wrong, not that the year is
    empty, and stay the source's or core's plain ``NotFoundError``. A task that reads a
    range of years skips a year that raises it; a task that asked for one year raises it
    again with a message naming what it asked for, ``NoDataForYear(error.path, message,
    source=error.source)``.

    Args:
        path: The request path, e.g. ``"/api/psd/commodity/0410000/country/US/year/1900"``.
        message: The text; by default it names the path and says that the year it names
            holds no data. The gateway gives it the request in place of the path, its method
            and path by core's ``request_description``, as its other messages name it.
        source: The source slug, e.g. ``"usda-psd"``.

    Attributes:
        path: As given.
    """

    def __init__(self, path: str, message: str | None = None, *, source: str | None = None) -> None:
        super().__init__(message or _no_data(path), source=source)
        self.path = path


def _no_data(asked: str) -> str:
    """The text of ``NoDataForYear`` for what was asked, a request or a path."""
    return (
        f"no data for {asked} (HTTP 404 with an empty body): the year it names holds no data "
        "upstream"
    )


def _path(response: httpx.Response) -> str | None:
    """The path of ``response``'s request; ``None`` for a response built without one."""
    try:
        return response.request.url.path
    except RuntimeError:  # httpx raises it for a response built without a request
        return None


def _empty_text(response: httpx.Response) -> bool:
    """True for an empty body (blanks aside) sent as ``text/plain``, in any letter case."""
    content_type = response.headers.get("content-type", "").lower()
    return not response.content.strip() and content_type.startswith("text/plain")


class Gateway(data_gov.Gateway):
    """api.data.gov for one FAS source: the gateway and FAS's answer for a year without data.

    ``data_gov.Gateway``, its key, its answers and its one ``policy`` per process, with
    FAS's rule as the publisher's answers that ``classify`` asks after the gateway's own:
    an empty ``text/plain`` 404 on a path that ``data_path`` matches is ``NoDataForYear``.
    Any other answer that the gateway leaves stays ``None``, for the source's own
    ``classify``.

    Args:
        source: The calling source's slug, e.g. ``"usda-psd"``, for its errors and for the
            ``ConfigError`` when ``DATA_GOV_API_KEY`` is unset.
        data_path: The source's data paths, a pattern the whole request path matches,
            e.g. ``re.compile(r"/api/psd/commodity/[^/]+/(?:country/[^/]+|world)/year/[^/]+")``.
            ``None``, the default, maps the empty 404 nowhere, for a source whose data
            paths never answer it (sdk-usda-gats's answer ``[]``).

    Attributes:
        data_path: As given.
    """

    def __init__(self, source: str, *, data_path: re.Pattern[str] | None = None) -> None:
        super().__init__(source, answers=self._no_data_for_year)
        self.data_path = data_path

    def _no_data_for_year(self, response: httpx.Response) -> XippiosError | None:
        """``NoDataForYear`` for FAS's empty ``text/plain`` 404 on a data path, else ``None``."""
        if response.status_code != 404 or self.data_path is None or not _empty_text(response):
            return None
        path = _path(response)
        if path is None or not self.data_path.fullmatch(path):
            return None
        return NoDataForYear(path, _no_data(request_description(response)), source=self.source)

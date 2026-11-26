r"""The kit of the FAS Open Data Services portal: what the FAS snapshot scripts share.

USDA's Foreign Agricultural Service documents three APIs behind api.data.gov, ESR, GATS and
PSD, on one portal, https://apps.fas.usda.gov/opendatawebV2/: an Angular app whose page is a
shell without documentation text, whose Swagger window loads a Swagger 2.0 document, and beside
which the API serves its own Swashbuckle document, which the classic Swagger UI names. Each FAS
source snapshots both documents cut to its own service. The pages' URLs and the files' names
are the kit's own: a source reaches them through ``Portal.pages``.

A source's ``scripts/refresh_upstream.py`` declares its snapshot on core's frame
(``xippios.core.refresh``, sdk-core ADR-0062) and takes from here the portal's pages, the hooks
that read them, and the paragraphs of ``FETCHED.md``'s "How this is captured" that say how::

    from xippios.core.refresh import Page, Row, Snapshot, run
    from xippios.usda.fas.portal import Portal

    PORTAL = Portal("/api/esr/")


    def note(row: Row) -> str:
        ...  # the notes of the source's own pages, then PORTAL.note(row)


    SNAPSHOT = Snapshot(
        name="USDA FAS Export Sales Reporting",
        slug="usda-esr",
        pages=(*PORTAL.pages, ...),  # then the source's own pages
        capture=f"{PORTAL.capture}\n\n...",  # then the source's own paragraphs
        reduce=PORTAL.reduce,
        linked=PORTAL.linked,
        note=note,
        sections=PORTAL.sections,
    )

The source keeps its own pages, their notes and the paragraph on them, and every check of its
own, such as one on the paths that its documents' cut leaves out. Every hook stops the run with
the frame's ``changed`` on a page it does not recognise, before anything is written.
"""

import json
import re
import textwrap
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit

from xippios.core.refresh import (
    Page,
    Response,
    Row,
    Section,
    changed,
    decode,
    dump_json,
    parse_json,
    read_json,
)

__all__ = [
    "Portal",
    "shell_text",
]

_PORTAL_URL = "https://apps.fas.usda.gov/opendatawebV2/"
"""The portal's page, a client-rendered shell."""
_PORTAL_SWAGGER_URL = "https://apps.fas.usda.gov/opendatawebV2/assets/swagger/swagger.json"
"""Named by the Swagger UI configuration in the portal's ``main.<hash>.js`` bundle."""
_CLASSIC_UI_URL = "https://apps.fas.usda.gov/opendata/swagger/ui/index"
"""The classic Swagger UI page, a shell that names the backend document's URL."""
_PORTAL_FILE = "openapi/portal-document.json"
"""The file of the service's part of the portal's document."""
_BACKEND_FILE = "openapi/backend-docs-v1.json"
"""The file of the service's part of the backend document. No ``swagger`` in either name:
detect-secrets' ``is_swagger_file`` would skip such a file."""
_SHELL_NOTE = "client-rendered shell, no documentation text"
"""The note of a page recorded as a shell, the start of its row's note."""
_MAX_SHELL_BYTES = 16_384
"""A page recorded as a shell must stay this small; a larger one needs a look by hand."""

_PORTAL_SWAGGER_FOUND_ON = "2026-10-23"
"""The day ``_PORTAL_SWAGGER_URL`` was found in a temporary copy of the bundle, since deleted."""
_API_HOST = "apps.fas.usda.gov"
"""The host the backend document URL read from the classic UI page must have."""
_SERVICES = {"/api/esr/": "ESR", "/api/gats/": "GATS", "/api/psd/": "PSD"}
"""The services both documents describe, by the prefix of their paths, in the portal's order."""

_BUNDLE = re.compile(r"""<script\s+src=["'](main\.[0-9a-f]+\.js)["']""")
_ROOT_URL = re.compile(r"rootUrl:\s*'([^']+)'")
_DISCOVERY = re.compile(r"discoveryPaths:\s*arrayFrom\('([^']*)'\)")
_PREFIX = re.compile(r"/api/[^/]+/")


def shell_text(response: Response, marker: str) -> str:
    """The text of a page that must still be a small client-rendered shell carrying ``marker``.

    Args:
        response: The page's answer, as the frame hands a hook it.
        marker: The shell's mount point, e.g. ``"<app-root>"``, which the page must hold.

    Returns:
        The page's text.
    """
    text = decode(response)
    if marker not in text:
        raise changed(response.url, f"the client-rendering mount point {marker!r} is gone")
    if len(response.body) > _MAX_SHELL_BYTES:
        raise changed(response.url, f"{len(response.body)} bytes, more than a shell's")
    return text


def _bundle(response: Response) -> str:
    """The name of the bundle the portal page loads."""
    bundles: list[str] = sorted(set(_BUNDLE.findall(shell_text(response, "<app-root>"))))
    if len(bundles) != 1:
        raise changed(response.url, f"expected one main.<hash>.js, found {bundles}")
    return bundles[0]


def _backend_url(response: Response) -> str:
    """The backend document's URL, read from the classic Swagger UI page."""
    text = shell_text(response, 'id="swagger-ui-container"')
    roots, discovery = _ROOT_URL.findall(text), _DISCOVERY.findall(text)
    if len(roots) != 1 or len(discovery) != 1:
        raise changed(response.url, f"rootUrl {roots}, discoveryPaths {discovery}")
    paths = [path for path in discovery[0].split("|") if path]
    if len(paths) != 1:
        raise changed(response.url, f"expected one discovery path, found {paths}")
    url = f"{roots[0].rstrip('/')}/{paths[0].lstrip('/')}"
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != _API_HOST:
        raise changed(response.url, f"the document URL {url!r} left https://{_API_HOST}")
    return url


def _swagger(document: Any, url: str) -> dict[str, Any]:
    """``document``, once it is a Swagger 2.0 document with paths, definitions and info."""
    if not isinstance(document, dict) or document.get("swagger") != "2.0":
        raise changed(url, "it is no Swagger 2.0 document")
    if not isinstance(document.get("paths"), dict):
        raise changed(url, "it has no paths object")
    if not isinstance(document.get("definitions", {}), dict):
        raise changed(url, "its definitions are not an object")
    if not isinstance(document.get("info"), dict):
        raise changed(url, "it has no info object")
    return document


def _refs(value: Any) -> set[str]:
    """Every definition name a ``#/definitions/...`` reference in ``value`` points at."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str) and item.startswith("#/definitions/"):
                name = unquote(item.removeprefix("#/definitions/"))
                found.add(name.replace("~1", "/").replace("~0", "~"))
            else:
                found |= _refs(item)
    elif isinstance(value, list):
        for item in value:
            found |= _refs(item)
    return found


def _fields(names: list[str], conjunction: str = "and") -> str:
    """The names in code spans, joined as a sentence lists them; ``nothing`` for none."""
    quoted = [f"`{name}`" for name in names]
    if len(quoted) < 2:
        return "".join(quoted) or "nothing"
    return f"{', '.join(quoted[:-1])} {conjunction} {quoted[-1]}"


def _comparison(portal: dict[str, Any], backend: dict[str, Any]) -> str:
    """How the two parts compare, top-level field by top-level field."""
    keys = list(dict.fromkeys([*portal, *backend]))
    both = [key for key in keys if key in portal and key in backend]
    differ = [key for key in both if portal[key] != backend[key]]
    agree = [key for key in both if key not in differ]
    clauses = [f"differ in {_fields(differ)}"] if differ else []
    for name, mine, other in (("portal", portal, backend), ("backend", backend, portal)):
        only = [key for key in keys if key in mine and key not in other]
        if only:
            clauses.append(f"only the {name} document has {_fields(only)}")
    clauses.append(f"they agree in {_fields(agree)}")
    return "; ".join(clauses)


def _info_fields(portal: dict[str, Any], backend: dict[str, Any]) -> str:
    """Which fields the two documents' ``info`` objects carry."""
    mine, other = list(portal.get("info", {})), list(backend.get("info", {}))
    if mine == other:
        return f"the `info` object of each carries only {_fields(mine)}"
    return (
        f"the portal document's `info` object carries only {_fields(mine)}, the backend "
        f"document's only {_fields(other)}"
    )


@dataclass(frozen=True)
class _Part:
    """One service's part of a Swagger document of the portal, and what was left out of it.

    Attributes:
        part: The document's top-level fields verbatim and in upstream order, ``paths`` cut
            to the keys that start with the service's prefix and ``definitions`` to those the
            kept paths reference, directly or through other definitions.
        kept: The number of paths kept.
        dropped: The paths left out, counted by their ``/api/<service>/`` prefix in upstream
            order; a path under no such prefix counts under itself.
        definitions_kept: The number of definitions kept.
        definitions_total: The number of definitions in the whole document.
    """

    part: dict[str, Any]
    kept: int
    dropped: dict[str, int]
    definitions_kept: int
    definitions_total: int


@dataclass(frozen=True)
class Portal:
    """The portal as the snapshot of one of its services reads it: its pages and its hooks.

    Bound to the service's prefix, each method is a hook of core's ``Snapshot`` as the frame
    calls it.

    Attributes:
        prefix: The prefix of the service's paths: ``"/api/esr/"``, ``"/api/gats/"`` or
            ``"/api/psd/"``.

    Raises:
        ValueError: ``prefix`` is the prefix of none of the portal's three services.
    """

    prefix: str

    def __post_init__(self) -> None:
        if self.prefix not in _SERVICES:
            raise ValueError(
                f"the portal documents the services under {', '.join(list(_SERVICES)[:-1])} "
                f"or {list(_SERVICES)[-1]}, not {self.prefix!r}"
            )

    @property
    def service(self) -> str:
        """The service's name as the portal gives it, e.g. ``"ESR"``."""
        return _SERVICES[self.prefix]

    @property
    def pages(self) -> tuple[Page, ...]:
        """The portal's three pages, first among the snapshot's, in this order.

        The portal page, a shell; its Swagger document, kept cut to the service's part as
        ``openapi/portal-document.json``, an excerpt; and the classic Swagger UI page, a
        shell, after which ``linked`` captures the backend document it names.
        """
        return (
            Page(_PORTAL_URL),
            Page(_PORTAL_SWAGGER_URL, _PORTAL_FILE, excerpt=True),
            Page(_CLASSIC_UI_URL),
        )

    @property
    def capture(self) -> str:
        """The paragraphs of "How this is captured": the portal, its documents, cut and shells.

        Four paragraphs parted by a blank line, before the source's own; each is one line,
        which the frame wraps. A source's own shell page, checked with ``shell_text``, is held
        to the same bound, which its own paragraph need not repeat.
        """
        others = " and ".join(name for name in _SERVICES.values() if name != self.service)
        return "\n\n".join(
            (
                f"The FAS Open Data Services portal, {_PORTAL_URL}, documents three APIs of "
                "USDA's Foreign Agricultural Service: ESR, GATS and PSD. It is an Angular app "
                "whose page is a shell without documentation text. Its Swagger window loads the "
                f"Swagger 2.0 document {_PORTAL_SWAGGER_URL}. On {_PORTAL_SWAGGER_FOUND_ON}, when "
                "sdk-usda-psd's snapshot was set up, the portal page and its JavaScript bundle "
                "were fetched into a temporary directory and that URL was found in the bundle's "
                "Swagger UI configuration; those copies have since been deleted, and this "
                "script reuses the URL. The script never downloads the bundle, since it embeds "
                "the portal's own api.data.gov signup-widget key, and this file records only "
                "its file name, in the portal page's row.",
                "The API also serves its own Swashbuckle document, which the classic Swagger UI "
                f"at {_CLASSIC_UI_URL} loads; the script reads its URL from the UI page's "
                "`rootUrl` and `discoveryPaths`, and the UI page's row names it.",
                f"Both documents cover ESR, GATS and PSD, and {others} get their own packages "
                f"in this family, so each file here holds the {self.service} part only: every "
                "top-level field verbatim and in upstream order, `paths` reduced to the keys "
                f"starting with `{self.prefix}` and `definitions` reduced to those the kept "
                "paths reference, directly or through other definitions; each document's row "
                "counts the paths kept and dropped, per prefix. The script writes the part with "
                "`json.dumps(indent=2, ensure_ascii=False)` in upstream key order, with LF line "
                "endings and a final newline, and stops unless the full document re-serialised "
                "the same way reproduces the fetched text up to line endings, so each file is "
                "the upstream text with the other APIs cut out.",
                "The portal page and the classic Swagger UI page are client-rendered shells "
                "without documentation text: each gets no file, only a row with its HTTP status "
                f"and the size and sha256 of its body, and a shell larger than {_MAX_SHELL_BYTES} "
                "bytes, or without its mount point, stops the run.",
            )
        )

    def _part(self, response: Response) -> _Part:
        """The service's part of a Swagger document: its paths and the definitions they reach.

        The document is read with the frame's ``read_json``, which holds it to upstream's text,
        since ``reduce`` writes the part.

        Args:
            response: The answer that holds the whole document.
        """
        return self._cut(_swagger(read_json(response), response.url), response.url)

    def _cut(self, document: dict[str, Any], url: str) -> _Part:
        """The service's part of a Swagger document read from ``url``."""
        paths: dict[str, Any] = document["paths"]
        definitions: dict[str, Any] = document.get("definitions", {})
        kept = {key: value for key, value in paths.items() if key.startswith(self.prefix)}
        if not kept:
            raise changed(url, f"no path starts with {self.prefix}")
        dropped: Counter[str] = Counter()
        for key in paths:
            if not key.startswith(self.prefix):
                match = _PREFIX.match(key)
                dropped[match.group(0) if match else key] += 1

        wanted: set[str] = set()
        pending = _refs(kept)
        while pending:
            name = min(pending)  # in name order, so a run names the same absent one each time
            pending.remove(name)
            if name in wanted:
                continue
            if name not in definitions:
                raise changed(url, f"#/definitions/{name} is referenced, absent")
            wanted.add(name)
            pending |= _refs(definitions[name])

        part: dict[str, Any] = {}
        for key, value in document.items():
            if key == "paths":
                part[key] = kept
            elif key == "definitions":
                part[key] = {name: item for name, item in value.items() if name in wanted}
            else:
                part[key] = value
        return _Part(
            part=part,
            kept=len(kept),
            dropped=dict(dropped),
            definitions_kept=len(wanted),
            definitions_total=len(definitions),
        )

    def reduce(self, page: Page, response: Response) -> bytes:
        """A document's file: the service's part, as ``json.dumps(indent=2, ensure_ascii=False)``.

        The ``Snapshot.reduce`` hook, for the two documents, the pages with a file.
        """
        return dump_json(self._part(response).part)

    def linked(self, row: Row) -> Sequence[Page]:
        """The backend document, whose URL the classic Swagger UI page names, after that page.

        The ``Snapshot.linked`` hook: no page for any other row.
        """
        if row.page.url != _CLASSIC_UI_URL:
            return ()
        return (Page(_backend_url(row.response), _BACKEND_FILE, excerpt=True),)

    def note(self, row: Row) -> str:
        """The note of a row of the portal's, made from its answer; any other row's own note.

        The portal page's names the bundle it loads, the classic UI page's the document it
        loads, and a document's counts what the cut kept and dropped, reading the document as
        served with the frame's ``parse_json``, since the note writes nothing of it. A
        ``Snapshot.note`` hook as it stands, or the last step of the source's own, after its
        own pages' notes.
        """
        page, response = row.page, row.response
        if page.url == _PORTAL_URL:
            return f"{_SHELL_NOTE}; loads the bundle `{_bundle(response)}`"
        if page.url == _CLASSIC_UI_URL:
            return f"{_SHELL_NOTE}; Swagger UI that loads `{_backend_url(response)}`"
        if page.file in (_PORTAL_FILE, _BACKEND_FILE):
            cut = self._cut(_swagger(parse_json(response), response.url), response.url)
            dropped = ", ".join(f"{count} `{prefix}`" for prefix, count in cut.dropped.items())
            return (
                f"{self.service} part: kept {cut.kept} `{self.prefix}` paths; dropped "
                f"{dropped or 'none'} (out of scope here, own packages); kept "
                f"{cut.definitions_kept} of {cut.definitions_total} definitions"
            )
        return row.note

    def sections(self, rows: Sequence[Row]) -> Sequence[Section]:
        """How the service's parts of the two documents compare, as fetched, after the capture.

        The ``Snapshot.sections`` hook: the section "The two documents", or none where the
        rows hold not both files.
        """
        parts = {row.page.file: row.content for row in rows if row.page.file and row.content}
        if _PORTAL_FILE not in parts or _BACKEND_FILE not in parts:
            return ()
        portal, backend = (
            json.loads(parts[name] or b"{}") for name in (_PORTAL_FILE, _BACKEND_FILE)
        )
        text = (
            "Both documents are kept because they are two upstream statements of the same API "
            f"that need not agree on how it is reached. As fetched, their {self.service} parts "
            f"{_comparison(portal, backend)}; {_info_fields(portal, backend)}."
        )
        wrapped = textwrap.fill(text, width=88, break_long_words=False, break_on_hyphens=False)
        return (Section("The two documents", wrapped),)
